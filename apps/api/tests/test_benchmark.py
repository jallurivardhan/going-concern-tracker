"""Unit tests for gct.eval.benchmark.

All tests use synthetic data — no live database required.
"""

from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from gct.eval.benchmark import (
    ALL_SEVERITIES,
    CaseResult,
    BenchmarkReport,
    _compute_report,
)


# ── Synthetic eval set helpers ────────────────────────────────────────────────


def _eval_set(cases: list[dict]) -> dict:
    return {
        "version": "v1.0-test",
        "created_at": "2026-05-17",
        "labeler": "test_labeler",
        "methodology_version": "v1.0",
        "cases": cases,
    }


def _case(
    *,
    case_id: str = "test_case",
    accession: str = "0000000001-24-000001",
    expected_severity: str = "none",
    expected_phrase: str | None = None,
    expected_flag_type: str = "none",
) -> dict:
    return {
        "case_id": case_id,
        "company_ticker_or_name": "Test Co.",
        "company_cik": "0000000001",
        "filing_accession": accession,
        "filing_date": "2024-03-01",
        "filing_form_type": "10-K",
        "expected_severity": expected_severity,
        "expected_flag_type": expected_flag_type,
        "expected_has_going_concern": expected_severity != "none",
        "expected_quoted_phrase_contains": expected_phrase,
        "labeler_justification": "Synthetic test case.",
        "source_evidence_url": "https://example.com",
    }


def _row(
    severity: str,
    quoted_language: str = "",
    confidence: str = "0.95",
) -> dict:
    return {
        "severity": severity,
        "quoted_language": quoted_language,
        "confidence": confidence,
    }


# ── Test 1: loads eval set from JSON ─────────────────────────────────────────


def test_loads_eval_set_from_json() -> None:
    """_compute_report parses eval set JSON correctly."""
    synthetic = _eval_set([
        _case(case_id="aapl_none", accession="A001", expected_severity="none"),
        _case(case_id="bbby_critical", accession="A002", expected_severity="critical",
              expected_phrase="substantial doubt"),
    ])
    row_lookup = {
        "A001": _row("none"),
        "A002": _row("critical", "There is substantial doubt about going concern"),
    }
    report = _compute_report(synthetic, row_lookup)
    assert report.total_cases == 2
    assert report.eval_set_version == "v1.0-test"
    assert all(cr.matches_expected for cr in report.case_results)


# ── Test 2: confusion matrix computation ─────────────────────────────────────


def test_computes_confusion_matrix_correctly() -> None:
    """Confusion matrix correctly counts TP, TN, FP, FN off-diagonals."""
    synthetic = _eval_set([
        _case(case_id="c1", accession="A001", expected_severity="critical"),
        _case(case_id="c2", accession="A002", expected_severity="critical"),
        _case(case_id="c3", accession="A003", expected_severity="none"),
        _case(case_id="c4", accession="A004", expected_severity="none"),
        _case(case_id="c5", accession="A005", expected_severity="none"),
    ])
    row_lookup = {
        "A001": _row("critical"),    # TP
        "A002": _row("none"),        # FN
        "A003": _row("none"),        # TN
        "A004": _row("none"),        # TN
        "A005": _row("critical"),    # FP
    }
    report = _compute_report(synthetic, row_lookup)

    cm = report.confusion_matrix
    # TP: expected=critical, predicted=critical
    assert cm["critical"]["critical"] == 1
    # FN: expected=critical, predicted=none
    assert cm["critical"]["none"] == 1
    # FP: expected=none, predicted=critical
    assert cm["none"]["critical"] == 1
    # TN: expected=none, predicted=none
    assert cm["none"]["none"] == 2

    assert report.true_positives == 1
    assert report.true_negatives == 2
    assert report.false_positives == 1
    assert report.false_negatives == 1

    # Precision = TP / (TP+FP) = 1/2 = 0.5
    assert report.precision == Decimal("0.5000")
    # Recall = TP / (TP+FN) = 1/2 = 0.5
    assert report.recall == Decimal("0.5000")


# ── Test 3: missing DB rows ───────────────────────────────────────────────────


def test_handles_missing_db_rows() -> None:
    """Cases without a DB row count as unmatched; no KeyError or crash."""
    synthetic = _eval_set([
        _case(case_id="present", accession="A001", expected_severity="none"),
        _case(case_id="missing", accession="A999", expected_severity="critical"),
    ])
    row_lookup = {
        "A001": _row("none"),
        # A999 deliberately absent
    }
    report = _compute_report(synthetic, row_lookup)

    assert report.cases_with_db_match == 1
    assert report.cases_without_db_match == 1

    missing_result = next(cr for cr in report.case_results if cr.case_id == "missing")
    assert missing_result.actual_severity is None
    assert not missing_result.matches_expected
    assert "No GoingConcernFlag row" in missing_result.notes

    # Missing critical case counted as FN
    assert report.false_negatives >= 1


# ── Test 4: quote substring check is case-insensitive ─────────────────────────


def test_quote_substring_check_case_insensitive() -> None:
    """expected_quoted_phrase_contains match ignores case in actual quote."""
    synthetic = _eval_set([
        _case(
            case_id="case1",
            accession="A001",
            expected_severity="critical",
            expected_phrase="SUBSTANTIAL DOUBT",
        ),
        _case(
            case_id="case2",
            accession="A002",
            expected_severity="critical",
            expected_phrase="substantial doubt",
        ),
    ])
    quote_text = "There is Substantial Doubt about the company's ability to continue."
    row_lookup = {
        "A001": _row("critical", quote_text),
        "A002": _row("critical", quote_text),
    }
    report = _compute_report(synthetic, row_lookup)

    for cr in report.case_results:
        assert cr.quote_contains_expected, (
            f"Expected quote found to match for {cr.case_id}"
        )


# ── Test 5: metrics are Decimal, not float ────────────────────────────────────


def test_metrics_are_decimal_not_float() -> None:
    """precision, recall, f1, accuracy, and confidence fields are Decimal."""
    synthetic = _eval_set([
        _case(case_id="c1", accession="A001", expected_severity="critical"),
        _case(case_id="c2", accession="A002", expected_severity="none"),
    ])
    row_lookup = {
        "A001": _row("critical", "substantial doubt going concern"),
        "A002": _row("none"),
    }
    report = _compute_report(synthetic, row_lookup)

    for field_name in ("precision", "recall", "f1", "accuracy",
                       "avg_confidence_when_correct", "avg_confidence_when_wrong"):
        value = getattr(report, field_name)
        assert isinstance(value, Decimal), (
            f"{field_name} must be Decimal, got {type(value).__name__}"
        )


# ── Test 6: strict mode exits non-zero below threshold ────────────────────────


def test_strict_mode_exits_nonzero_below_threshold(tmp_path: Path) -> None:
    """CLI --strict exits with code 1 when precision is below 0.90."""
    from typer.testing import CliRunner
    from unittest.mock import patch
    from gct.cli.eval import app

    # Build a minimal golden_set.json with one FP (precision=0.0)
    bad_set = _eval_set([
        _case(case_id="fp_case", accession="A001", expected_severity="none"),
    ])
    eval_path = tmp_path / "golden_set.json"
    eval_path.write_text(json.dumps(bad_set))

    # Mock run_benchmark to return a report with low precision
    low_prec_report = _compute_report(
        bad_set,
        {"A001": _row("critical")},  # FP: expected=none, got=critical
    )

    runner = CliRunner()
    with patch("gct.cli.eval.run_benchmark", return_value=low_prec_report):
        result = runner.invoke(
            app,
            ["--eval-set", str(eval_path), "--strict", "--json"],
        )

    # precision = 0 (no TPs, 1 FP) → should trigger exit 1
    assert result.exit_code == 1, (
        f"Expected exit code 1 for low precision, got {result.exit_code}"
    )
