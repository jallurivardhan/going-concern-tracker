"""Deterministic accuracy benchmark for the Going Concern Tracker classifier.

Design principles
-----------------
* NO live LLM calls.  The benchmark reads GoingConcernFlag rows that are already
  in the database and compares them to the hand-labeled golden eval set.
* Deterministic.  Given the same eval set and same database state the report
  is identical on every run.
* Testable.  The core computation (_compute_report) is separate from the DB
  query so unit tests can pass synthetic data without a real database.

Positive definition: any severity in {"critical", "elevated", "watch"}.
Negative definition: severity == "none".
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from gct.classifier.prompts import CLASSIFIER_VERSION
from gct.models import Filing, GoingConcernFlag

# Severeties that count as "positive" in binary precision/recall/F1 calculations.
POSITIVE_SEVERITIES: frozenset[str] = frozenset({"critical", "elevated", "watch"})

# All recognised severity levels (for confusion matrix rows/columns).
ALL_SEVERITIES: list[str] = ["critical", "elevated", "watch", "none"]

_FOUR = Decimal("0.0001")


def _d4(value: Decimal) -> Decimal:
    """Round a Decimal to 4 decimal places."""
    return value.quantize(_FOUR, rounding=ROUND_HALF_UP)


# ── Pydantic result models ────────────────────────────────────────────────────


class CaseResult(BaseModel):
    """Result for one eval-set case."""

    case_id: str
    expected_severity: str
    actual_severity: str | None  # None when no GoingConcernFlag row in DB
    matches_expected: bool
    expected_quoted_phrase: str | None
    actual_quoted_phrase: str | None  # first 300 chars of stored quoted_language
    quote_contains_expected: bool
    notes: str


class BenchmarkReport(BaseModel):
    """Complete benchmark report for one run."""

    version: str = "v1.0"
    eval_set_version: str
    classifier_version: str
    timestamp: datetime

    total_cases: int
    cases_with_db_match: int
    cases_without_db_match: int

    # Confusion matrix: actual_severity → {predicted_severity: count}
    confusion_matrix: dict[str, dict[str, int]]

    # Binary classification metrics
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    precision: Decimal
    recall: Decimal
    f1: Decimal
    accuracy: Decimal

    # Confidence calibration
    avg_confidence_when_correct: Decimal
    avg_confidence_when_wrong: Decimal

    case_results: list[CaseResult]


# ── Core computation (DB-free; accepts pre-fetched row data) ──────────────────


def _compute_report(
    eval_set: dict[str, Any],
    row_lookup: dict[str, dict[str, Any] | None],
) -> BenchmarkReport:
    """Build a BenchmarkReport from an eval set and pre-fetched DB data.

    Parameters
    ----------
    eval_set:    Parsed golden_set.json dict.
    row_lookup:  ``{accession_number: {"severity": ..., "quoted_language": ...,
                 "confidence": ...} | None}``.  None means no DB row found.
    """
    cases: list[dict] = eval_set.get("cases", [])

    # ── Per-case results ──────────────────────────────────────────────────────
    case_results: list[CaseResult] = []
    correct_confidences: list[Decimal] = []
    wrong_confidences: list[Decimal] = []

    for case in cases:
        accession = case["filing_accession"]
        expected_severity = case["expected_severity"]
        expected_phrase: str | None = case.get("expected_quoted_phrase_contains")
        db_row = row_lookup.get(accession)

        if db_row is None:
            case_results.append(
                CaseResult(
                    case_id=case["case_id"],
                    expected_severity=expected_severity,
                    actual_severity=None,
                    matches_expected=False,
                    expected_quoted_phrase=expected_phrase,
                    actual_quoted_phrase=None,
                    quote_contains_expected=False,
                    notes="No GoingConcernFlag row found in database",
                )
            )
            continue

        actual_severity = db_row["severity"]
        matches = actual_severity == expected_severity
        confidence = db_row.get("confidence")
        if confidence is not None:
            conf_dec = Decimal(str(confidence))
            if matches:
                correct_confidences.append(conf_dec)
            else:
                wrong_confidences.append(conf_dec)

        # Quote verification: only required when expected severity is positive
        actual_quote = db_row.get("quoted_language") or ""
        quote_ok = True
        if expected_phrase and expected_severity in POSITIVE_SEVERITIES:
            quote_ok = expected_phrase.lower() in actual_quote.lower()
        
        notes = "" if matches else (
            f"Expected severity='{expected_severity}', got '{actual_severity}'"
        )
        if matches and expected_phrase and expected_severity in POSITIVE_SEVERITIES and not quote_ok:
            notes = f"Severity matches but expected phrase not in quote: {expected_phrase!r}"

        case_results.append(
            CaseResult(
                case_id=case["case_id"],
                expected_severity=expected_severity,
                actual_severity=actual_severity,
                matches_expected=matches,
                expected_quoted_phrase=expected_phrase,
                actual_quoted_phrase=actual_quote[:300] if actual_quote else None,
                quote_contains_expected=quote_ok,
                notes=notes,
            )
        )

    # ── Confusion matrix ──────────────────────────────────────────────────────
    confusion: dict[str, dict[str, int]] = {
        s: {s2: 0 for s2 in ALL_SEVERITIES} for s in ALL_SEVERITIES
    }
    for cr in case_results:
        if cr.actual_severity is not None:
            exp = cr.expected_severity
            act = cr.actual_severity
            if exp in confusion and act in confusion[exp]:
                confusion[exp][act] += 1

    # ── Binary metrics ────────────────────────────────────────────────────────
    tp = tn = fp = fn = 0
    for cr in case_results:
        exp_pos = cr.expected_severity in POSITIVE_SEVERITIES
        if cr.actual_severity is None:
            # No DB row — treat as false negative if positive expected
            if exp_pos:
                fn += 1
            # We don't count missing "none" cases as TN (data gap)
            continue
        act_pos = cr.actual_severity in POSITIVE_SEVERITIES
        if exp_pos and act_pos:
            tp += 1
        elif not exp_pos and not act_pos:
            tn += 1
        elif not exp_pos and act_pos:
            fp += 1
        else:
            fn += 1

    total = tp + tn + fp + fn
    prec = _d4(Decimal(tp) / Decimal(tp + fp)) if (tp + fp) else Decimal("0")
    rec = _d4(Decimal(tp) / Decimal(tp + fn)) if (tp + fn) else Decimal("0")
    f1 = _d4(2 * prec * rec / (prec + rec)) if (prec + rec) else Decimal("0")
    acc = _d4(Decimal(tp + tn) / Decimal(total)) if total else Decimal("0")

    def _avg(vals: list[Decimal]) -> Decimal:
        if not vals:
            return Decimal("0")
        return _d4(sum(vals) / Decimal(len(vals)))

    # ── Assemble report ───────────────────────────────────────────────────────
    with_match = sum(1 for cr in case_results if cr.actual_severity is not None)
    without_match = len(case_results) - with_match

    return BenchmarkReport(
        eval_set_version=eval_set.get("version", "unknown"),
        classifier_version=CLASSIFIER_VERSION,
        timestamp=datetime.utcnow(),
        total_cases=len(cases),
        cases_with_db_match=with_match,
        cases_without_db_match=without_match,
        confusion_matrix=confusion,
        true_positives=tp,
        true_negatives=tn,
        false_positives=fp,
        false_negatives=fn,
        precision=prec,
        recall=rec,
        f1=f1,
        accuracy=acc,
        avg_confidence_when_correct=_avg(correct_confidences),
        avg_confidence_when_wrong=_avg(wrong_confidences),
        case_results=case_results,
    )


# ── Public entry point ────────────────────────────────────────────────────────


def run_benchmark(
    eval_set_path: str | Path | None = None,
    session: Session | None = None,
) -> BenchmarkReport:
    """Load the eval set, query the database, and return a BenchmarkReport.

    Parameters
    ----------
    eval_set_path:
        Path to ``golden_set.json``.  Defaults to the canonical location
        ``apps/api/eval/golden_set.json`` relative to the current working dir.
    session:
        Optional SQLAlchemy Session.  If omitted the function creates (and
        closes) its own session.  Pass a session in tests to avoid DB
        connections.

    The benchmark NEVER makes LLM calls — it reads GoingConcernFlag rows that
    are already in the database.
    """
    from gct.database import SessionLocal  # local import to keep module importable without DB

    if eval_set_path is None:
        # Resolve relative to this file's project root
        eval_set_path = Path(__file__).parents[3] / "eval" / "golden_set.json"
    eval_set_path = Path(eval_set_path)

    with eval_set_path.open(encoding="utf-8") as fh:
        eval_set = json.load(fh)

    own_session = session is None
    if own_session:
        session = SessionLocal()

    try:
        row_lookup: dict[str, dict[str, Any] | None] = {}
        for case in eval_set.get("cases", []):
            accession = case["filing_accession"]
            # Join GoingConcernFlag → Filing to look up by accession number.
            row = session.execute(
                select(GoingConcernFlag, Filing)
                .join(Filing, GoingConcernFlag.filing_id == Filing.id)
                .where(Filing.accession_number == accession)
            ).first()
            if row is None:
                row_lookup[accession] = None
            else:
                flag, _filing = row
                row_lookup[accession] = {
                    "severity": flag.severity,
                    "quoted_language": flag.quoted_language,
                    "confidence": flag.classification_confidence,
                }

        return _compute_report(eval_set, row_lookup)
    finally:
        if own_session:
            session.close()
