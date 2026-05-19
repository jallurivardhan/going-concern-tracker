"""Main classify_auditor_report function — orchestrates the full pipeline.

Pipeline steps
--------------
1. Load AuditorReport + joined Filing + Company from DB.
2. Check idempotency: if GoingConcernFlag already exists and not force, return early.
3. Build ClassifierInput; call ClaudeClassifier.classify().
4. Validate response (quote present, offsets correct).
5. Determine flag_type by comparing to prior filing's flag status.
6. Upsert GoingConcernFlag row.
7. Return ClassificationResult.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from gct.classifier.claude_client import ClaudeClassifier
from gct.classifier.exceptions import ClassificationError
from gct.classifier.prompts import CLASSIFIER_VERSION
from gct.classifier.schemas import ClassificationResult, ClassifierInput
from gct.classifier.validator import validate_classification
from gct.models import AuditorReport, Company, Filing, GoingConcernFlag

logger = logging.getLogger(__name__)


async def classify_auditor_report(
    session: Session,
    auditor_report_id: uuid.UUID,
    client: ClaudeClassifier,
    force: bool = False,
) -> ClassificationResult:
    """Classify one AuditorReport and upsert the GoingConcernFlag row.

    Parameters
    ----------
    session:            SQLAlchemy Session (caller manages commit/rollback).
    auditor_report_id:  PK of the AuditorReport to classify.
    client:             Configured ClaudeClassifier instance.
    force:              Re-classify even if a GoingConcernFlag already exists.

    Returns
    -------
    ClassificationResult — includes validation errors and trace URL.
    """
    # ── 1. Load report + filing + company ────────────────────────────────────
    report = session.execute(
        select(AuditorReport).where(AuditorReport.id == auditor_report_id)
    ).scalar_one_or_none()

    if report is None:
        raise ClassificationError(f"AuditorReport {auditor_report_id} not found")

    filing: Filing = report.filing  # type: ignore[assignment]
    company: Company = filing.company  # type: ignore[assignment]

    # ── 2. Idempotency check ─────────────────────────────────────────────────
    existing_flag = session.execute(
        select(GoingConcernFlag).where(GoingConcernFlag.filing_id == filing.id)
    ).scalar_one_or_none()

    if existing_flag is not None and not force:
        logger.debug(
            "Skipping %s (%s) — flag already exists (severity=%s); pass --force to re-classify",
            company.ticker,
            filing.accession_number,
            existing_flag.severity,
        )
        return _result_from_existing(report, filing, company, existing_flag, client)

    # ── 3. Validate input and call Claude ────────────────────────────────────
    ClassifierInput(
        report_text=report.report_text,
        company_name=company.name,
        filing_form_type=filing.form_type,
        filing_date=filing.filing_date,
    )

    llm_response, trace_url = await client.classify(
        report_text=report.report_text,
        company_name=company.name,
        filing_form_type=filing.form_type,
        filing_date=filing.filing_date,
    )

    model_used = client.get_model_used()

    # ── 4. Post-LLM validation ───────────────────────────────────────────────
    is_valid, validation_errors, offset_start, offset_end = validate_classification(
        llm_response, report.report_text
    )

    has_going_concern = llm_response.severity != "none"

    # Hard validation failure (e.g. quoted language not found after whitespace
    # normalisation) → do NOT persist a GoingConcernFlag row so we never
    # store corrupt offset data.  The ClassificationResult is returned so the
    # CLI can surface the error and the caller can decide to --force re-classify
    # or investigate the raw report text manually.
    if not is_valid:
        logger.warning(
            "Validation HARD FAIL for %s (%s): %s — GoingConcernFlag NOT written",
            company.ticker or company.name,
            filing.accession_number,
            "; ".join(validation_errors),
        )
        return ClassificationResult(
            auditor_report_id=auditor_report_id,
            has_going_concern=has_going_concern,
            severity=llm_response.severity,
            flag_type="none",
            quoted_language=llm_response.quoted_language,
            char_offset_start=None,
            char_offset_end=None,
            classification_confidence=Decimal(str(llm_response.classification_confidence)),
            classifier_version=CLASSIFIER_VERSION,
            model_used=model_used,
            reasoning=llm_response.reasoning,
            validation_passed=False,
            validation_errors=validation_errors,
            trace_url=trace_url,
        )

    # ── 5. Determine flag_type ───────────────────────────────────────────────
    flag_type = _determine_flag_type(session, company.id, filing, has_going_concern)

    # ── 6. Upsert GoingConcernFlag ───────────────────────────────────────────
    _upsert_flag(
        session=session,
        filing=filing,
        company=company,
        llm_response=llm_response,
        flag_type=flag_type,
        offset_start=offset_start,
        offset_end=offset_end,
        model_used=model_used,
    )

    # ── 7. Return result ─────────────────────────────────────────────────────
    return ClassificationResult(
        auditor_report_id=auditor_report_id,
        has_going_concern=has_going_concern,
        severity=llm_response.severity,
        flag_type=flag_type,
        quoted_language=llm_response.quoted_language,
        char_offset_start=offset_start,
        char_offset_end=offset_end,
        classification_confidence=Decimal(str(llm_response.classification_confidence)),
        classifier_version=CLASSIFIER_VERSION,
        model_used=model_used,
        reasoning=llm_response.reasoning,
        validation_passed=is_valid,
        validation_errors=validation_errors,
        trace_url=trace_url,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _determine_flag_type(
    session: Session,
    company_id: uuid.UUID,
    current_filing: Filing,
    current_has_concern: bool,
) -> str:
    """Return "new" | "continuing" | "resolved" | "none" by comparing to prior filing."""
    prior_filing = session.execute(
        select(Filing)
        .where(
            Filing.company_id == company_id,
            Filing.form_type == "10-K",
            Filing.filing_date < current_filing.filing_date,
        )
        .order_by(Filing.filing_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    prior_has_concern = False
    if prior_filing is not None:
        prior_flag = session.execute(
            select(GoingConcernFlag).where(GoingConcernFlag.filing_id == prior_filing.id)
        ).scalar_one_or_none()
        prior_has_concern = prior_flag is not None and prior_flag.severity != "none"

    if prior_has_concern and current_has_concern:
        return "continuing"
    if not prior_has_concern and current_has_concern:
        return "new"
    if prior_has_concern and not current_has_concern:
        return "resolved"
    return "none"


def _upsert_flag(
    session: Session,
    filing: Filing,
    company: Company,
    llm_response: "ClassifierResponse",  # type: ignore[name-defined]
    flag_type: str,
    offset_start: int | None,
    offset_end: int | None,
    model_used: str,
) -> None:
    """Insert a new GoingConcernFlag row, or update the existing one (force mode)."""
    from gct.classifier.schemas import ClassifierResponse  # local import to avoid cycle

    now = datetime.utcnow()
    quoted = llm_response.quoted_language or ""
    start = offset_start if offset_start is not None else 0
    end = offset_end if offset_end is not None else 0
    confidence = Decimal(str(llm_response.classification_confidence))
    classifier_ver = f"{CLASSIFIER_VERSION}-{model_used}"

    existing = session.execute(
        select(GoingConcernFlag).where(GoingConcernFlag.filing_id == filing.id)
    ).scalar_one_or_none()

    if existing is not None:
        session.execute(
            update(GoingConcernFlag)
            .where(GoingConcernFlag.id == existing.id)
            .values(
                severity=llm_response.severity,
                flag_type=flag_type,
                quoted_language=quoted,
                char_offset_start=start,
                char_offset_end=end,
                classification_confidence=confidence,
                classifier_version=classifier_ver,
                detected_at=now,
            )
        )
    else:
        flag = GoingConcernFlag(
            id=uuid.uuid4(),
            filing_id=filing.id,
            company_id=company.id,
            severity=llm_response.severity,
            flag_type=flag_type,
            quoted_language=quoted,
            char_offset_start=start,
            char_offset_end=end,
            classification_confidence=confidence,
            classifier_version=classifier_ver,
            detected_at=now,
            created_at=now,
        )
        session.add(flag)


def _result_from_existing(
    report: AuditorReport,
    filing: Filing,
    company: Company,
    flag: GoingConcernFlag,
    client: ClaudeClassifier,
) -> ClassificationResult:
    """Build a ClassificationResult from an already-stored GoingConcernFlag."""
    return ClassificationResult(
        auditor_report_id=report.id,
        has_going_concern=flag.severity != "none",
        severity=flag.severity,  # type: ignore[arg-type]
        flag_type=flag.flag_type,  # type: ignore[arg-type]
        quoted_language=flag.quoted_language or None,
        char_offset_start=flag.char_offset_start,
        char_offset_end=flag.char_offset_end,
        classification_confidence=flag.classification_confidence,
        classifier_version=flag.classifier_version,
        model_used="(cached)",
        reasoning="(loaded from existing GoingConcernFlag — not re-classified)",
        validation_passed=True,
        validation_errors=[],
        trace_url=None,
    )
