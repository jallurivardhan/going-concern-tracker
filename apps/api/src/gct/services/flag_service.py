"""Query logic for GoingConcernFlag data.

Keeps route handlers thin — all SQL lives here.
Pagination uses keyset (cursor) strategy; see gct.pagination for details.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from gct.models import AuditorReport, Company, Filing, GoingConcernFlag
from gct.pagination import decode_cursor, encode_cursor
from gct.schemas.api import (
    CompanyBrief,
    FilingBrief,
    FilingResponse,
    FlagDetailResponse,
    FlagListResponse,
    FlagResponse,
)

_POSITIVE = {"critical", "elevated", "watch"}


def _build_filing_url(company: Company, filing: Filing) -> str:
    """Prefer the stored filing_url; fall back to EDGAR browse URL."""
    if filing.filing_url:
        return filing.filing_url
    cik_int = int(filing.company.cik)
    return (
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&CIK={cik_int}&type=10-K"
    )


def _to_flag_response(
    flag: GoingConcernFlag,
    filing: Filing,
    company: Company,
    audit_firm: str | None,
) -> FlagResponse:
    return FlagResponse(
        id=flag.id,
        company=CompanyBrief(
            cik=company.cik,
            ticker=company.ticker,
            name=company.name,
            display_name=getattr(company, "display_name", None),
        ),
        filing=FilingBrief(
            id=filing.id,
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            period_of_report=getattr(filing, "period_of_report", None),
            filing_url=_build_filing_url(company, filing),
        ),
        severity=flag.severity,
        flag_type=flag.flag_type,
        quoted_language=flag.quoted_language,
        char_offset_start=flag.char_offset_start,
        char_offset_end=flag.char_offset_end,
        classification_confidence=flag.classification_confidence,
        classifier_version=flag.classifier_version,
        detected_at=flag.detected_at,
        audit_firm=audit_firm,
    )


def list_flags(
    db: Session,
    severity: list[str] | None = None,
    flag_type: list[str] | None = None,
    cik: str | None = None,
    since: date | None = None,
    limit: int = 20,
    cursor: str | None = None,
    sort: str = "filing_date_desc",
) -> FlagListResponse:
    """Paginated list of going-concern flags.

    Returns ``limit + 1`` rows internally to determine ``has_more``.

    Sort options:
      filing_date_desc  — newest filing first (default)
      detected_at_desc  — newest detection first
      detected_at_asc   — oldest detection first
    """
    # Default severity filter: exclude "none"
    if severity is None:
        severity = list(_POSITIVE)

    stmt = (
        select(GoingConcernFlag, Filing, Company, AuditorReport)
        .join(Filing, GoingConcernFlag.filing_id == Filing.id)
        .join(Company, GoingConcernFlag.company_id == Company.id)
        .outerjoin(AuditorReport, AuditorReport.filing_id == Filing.id)
    )

    # Filters
    if severity:
        stmt = stmt.where(GoingConcernFlag.severity.in_(severity))
    if flag_type:
        stmt = stmt.where(GoingConcernFlag.flag_type.in_(flag_type))
    if cik:
        stmt = stmt.where(Company.cik == cik)
    if since:
        stmt = stmt.where(GoingConcernFlag.detected_at >= since)

    # Cursor (keyset) — each branch decodes its own key type
    if cursor:
        after_key, after_id = decode_cursor(cursor)
        if sort == "filing_date_desc":
            after_date = date.fromisoformat(after_key)
            stmt = stmt.where(
                or_(
                    Filing.filing_date < after_date,
                    and_(
                        Filing.filing_date == after_date,
                        GoingConcernFlag.id < uuid.UUID(after_id),
                    ),
                )
            )
        elif sort == "detected_at_asc":
            after_dt = datetime.fromisoformat(after_key)
            stmt = stmt.where(
                or_(
                    GoingConcernFlag.detected_at > after_dt,
                    and_(
                        GoingConcernFlag.detected_at == after_dt,
                        GoingConcernFlag.id > uuid.UUID(after_id),
                    ),
                )
            )
        else:  # detected_at_desc
            after_dt = datetime.fromisoformat(after_key)
            stmt = stmt.where(
                or_(
                    GoingConcernFlag.detected_at < after_dt,
                    and_(
                        GoingConcernFlag.detected_at == after_dt,
                        GoingConcernFlag.id < uuid.UUID(after_id),
                    ),
                )
            )

    # Sort
    if sort == "filing_date_desc":
        stmt = stmt.order_by(Filing.filing_date.desc(), GoingConcernFlag.id.desc())
    elif sort == "detected_at_asc":
        stmt = stmt.order_by(GoingConcernFlag.detected_at.asc(), GoingConcernFlag.id.asc())
    else:  # detected_at_desc
        stmt = stmt.order_by(GoingConcernFlag.detected_at.desc(), GoingConcernFlag.id.desc())

    stmt = stmt.limit(limit + 1)
    rows = db.execute(stmt).all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    items: list[FlagResponse] = []
    for flag, filing, company, ar in rows:
        items.append(_to_flag_response(flag, filing, company, ar.audit_firm if ar else None))

    next_cursor = None
    if has_more and rows:
        last_flag, last_filing = rows[-1][0], rows[-1][1]
        if sort == "filing_date_desc":
            next_cursor = encode_cursor(last_filing.filing_date.isoformat(), str(last_flag.id))
        else:
            next_cursor = encode_cursor(last_flag.detected_at, str(last_flag.id))

    return FlagListResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_returned=len(items),
    )


def get_flag(db: Session, flag_id: uuid.UUID) -> FlagDetailResponse | None:
    """Single flag with an auditor report excerpt centered on the cited span."""
    row = db.execute(
        select(GoingConcernFlag, Filing, Company, AuditorReport)
        .join(Filing, GoingConcernFlag.filing_id == Filing.id)
        .join(Company, GoingConcernFlag.company_id == Company.id)
        .outerjoin(AuditorReport, AuditorReport.filing_id == Filing.id)
        .where(GoingConcernFlag.id == flag_id)
    ).first()

    if row is None:
        return None

    flag, filing, company, ar = row
    base = _to_flag_response(flag, filing, company, ar.audit_firm if ar else None)

    report_excerpt = None
    report_total_length = None
    if ar and ar.report_text:
        report_text = ar.report_text
        report_total_length = len(report_text)
        # Build a 1000-char window centred on the cited span
        start = max(0, flag.char_offset_start - 200)
        end = min(len(report_text), flag.char_offset_end + 600)
        if start == 0 and end < 1000:
            end = min(len(report_text), 1000)
        report_excerpt = report_text[start:end]

    return FlagDetailResponse(
        **base.model_dump(),
        report_excerpt=report_excerpt,
        report_total_length=report_total_length,
    )
