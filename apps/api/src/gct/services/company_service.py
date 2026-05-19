"""Query logic for Company data with aggregated flag summaries.

Uses a single aggregation query to avoid N+1 problems.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from gct.models import AuditorReport, Company, Filing, GoingConcernFlag
from gct.pagination import decode_cursor, encode_cursor
from gct.schemas.api import (
    CompanyBrief,
    CompanyDetailResponse,
    CompanyListResponse,
    CompanyResponse,
    FilingBrief,
    FilingListResponse,
    FilingResponse,
    FlagBrief,
    FlagResponse,
    FlagSummary,
)
from gct.services.flag_service import _to_flag_response

_POSITIVE_SEVERITIES = ("critical", "elevated", "watch")


def _aggregate_flags(db: Session, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Single query: per-company flag counts and most-recent flag.

    Returns a dict keyed by company_id.
    """
    if not company_ids:
        return {}

    # Count flags per severity per company
    count_stmt = (
        select(
            GoingConcernFlag.company_id,
            GoingConcernFlag.severity,
            func.count().label("cnt"),
        )
        .where(GoingConcernFlag.company_id.in_(company_ids))
        .group_by(GoingConcernFlag.company_id, GoingConcernFlag.severity)
    )
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for company_id, severity, cnt in db.execute(count_stmt).all():
        counts.setdefault(company_id, {})[severity] = cnt

    # Most recent positive flag per company
    latest_stmt = (
        select(
            GoingConcernFlag.company_id,
            GoingConcernFlag.id,
            GoingConcernFlag.severity,
            Filing.filing_date,
            GoingConcernFlag.detected_at,
        )
        .join(Filing, GoingConcernFlag.filing_id == Filing.id)
        .where(
            GoingConcernFlag.company_id.in_(company_ids),
            GoingConcernFlag.severity.in_(_POSITIVE_SEVERITIES),
        )
        .order_by(
            GoingConcernFlag.company_id,
            GoingConcernFlag.detected_at.desc(),
        )
        .distinct(GoingConcernFlag.company_id)
    )
    latest_flags: dict[uuid.UUID, dict] = {}
    for company_id, flag_id, severity, filing_date, detected_at in db.execute(latest_stmt).all():
        latest_flags[company_id] = {
            "id": flag_id,
            "severity": severity,
            "filing_date": filing_date,
            "detected_at": detected_at,
        }

    result: dict[uuid.UUID, dict] = {}
    for cid in company_ids:
        sev_counts = counts.get(cid, {})
        result[cid] = {
            "flag_summary": FlagSummary(
                critical=sev_counts.get("critical", 0),
                elevated=sev_counts.get("elevated", 0),
                watch=sev_counts.get("watch", 0),
                none=sev_counts.get("none", 0),
            ),
            "most_recent_flag": (
                FlagBrief(**latest_flags[cid]) if cid in latest_flags else None
            ),
            "total_10ks": sev_counts.get("critical", 0)
                + sev_counts.get("elevated", 0)
                + sev_counts.get("watch", 0)
                + sev_counts.get("none", 0),
        }
    return result


def _count_filings(db: Session, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    stmt = (
        select(Filing.company_id, func.count().label("cnt"))
        .where(Filing.company_id.in_(company_ids))
        .group_by(Filing.company_id)
    )
    return {company_id: cnt for company_id, cnt in db.execute(stmt).all()}


def list_companies(
    db: Session,
    q: str | None = None,
    has_flags: bool | None = None,
    limit: int = 50,
    cursor: str | None = None,
    sort: str = "name_asc",
) -> CompanyListResponse:
    """Paginated company list with aggregated flag stats."""
    stmt = select(Company)

    # Text search
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Company.name).like(like),
                func.lower(Company.ticker).like(like),
            )
        )

    # has_flags filter
    if has_flags is True:
        stmt = stmt.where(
            Company.id.in_(
                select(GoingConcernFlag.company_id)
                .where(GoingConcernFlag.severity.in_(_POSITIVE_SEVERITIES))
                .distinct()
            )
        )
    elif has_flags is False:
        stmt = stmt.where(
            Company.id.not_in(
                select(GoingConcernFlag.company_id)
                .where(GoingConcernFlag.severity.in_(_POSITIVE_SEVERITIES))
                .distinct()
            )
        )

    # Cursor
    if cursor:
        after_key, after_id = decode_cursor(cursor)
        if sort == "name_desc":
            stmt = stmt.where(
                or_(
                    func.lower(Company.name) < after_key.lower(),
                    and_(
                        func.lower(Company.name) == after_key.lower(),
                        Company.id < uuid.UUID(after_id),
                    ),
                )
            )
        else:
            stmt = stmt.where(
                or_(
                    func.lower(Company.name) > after_key.lower(),
                    and_(
                        func.lower(Company.name) == after_key.lower(),
                        Company.id > uuid.UUID(after_id),
                    ),
                )
            )

    # Sort
    if sort == "name_desc":
        stmt = stmt.order_by(func.lower(Company.name).desc(), Company.id.desc())
    elif sort == "recent_flag_first":
        # Sub-select to get most recent detected_at per company
        recent_sub = (
            select(
                GoingConcernFlag.company_id,
                func.max(GoingConcernFlag.detected_at).label("recent_at"),
            )
            .where(GoingConcernFlag.severity.in_(_POSITIVE_SEVERITIES))
            .group_by(GoingConcernFlag.company_id)
            .subquery()
        )
        stmt = stmt.outerjoin(recent_sub, recent_sub.c.company_id == Company.id)
        stmt = stmt.order_by(recent_sub.c.recent_at.desc().nullslast(), Company.id)
    else:
        stmt = stmt.order_by(func.lower(Company.name).asc(), Company.id.asc())

    stmt = stmt.limit(limit + 1)
    companies = db.execute(stmt).scalars().all()

    has_more = len(companies) > limit
    companies = list(companies[:limit])

    # Aggregate stats in two bulk queries
    company_ids = [c.id for c in companies]
    agg = _aggregate_flags(db, company_ids)
    filing_counts = _count_filings(db, company_ids)

    items: list[CompanyResponse] = []
    for company in companies:
        stats = agg.get(company.id, {
            "flag_summary": FlagSummary(),
            "most_recent_flag": None,
            "total_10ks": 0,
        })
        total_filings = filing_counts.get(company.id, 0)
        items.append(
            CompanyResponse(
                cik=company.cik,
                ticker=company.ticker,
                name=company.name,
                display_name=getattr(company, "display_name", None),
                sector=company.sector,
                industry=company.industry,
                total_filings=total_filings,
                total_10ks=stats["total_10ks"],
                flag_summary=stats["flag_summary"],
                most_recent_flag=stats["most_recent_flag"],
            )
        )

    next_cursor = None
    if has_more and companies:
        last = companies[-1]
        next_cursor = encode_cursor(last.name, str(last.id))

    return CompanyListResponse(items=items, next_cursor=next_cursor, has_more=has_more)


def get_company(db: Session, cik: str) -> CompanyDetailResponse | None:
    """Full company detail with flag history and recent filings."""
    company = db.execute(
        select(Company).where(Company.cik == cik)
    ).scalar_one_or_none()

    if company is None:
        return None

    # Flag history (all severities, newest first)
    flag_rows = db.execute(
        select(GoingConcernFlag, Filing, Company, AuditorReport)
        .join(Filing, GoingConcernFlag.filing_id == Filing.id)
        .join(Company, GoingConcernFlag.company_id == Company.id)
        .outerjoin(AuditorReport, AuditorReport.filing_id == Filing.id)
        .where(GoingConcernFlag.company_id == company.id)
        .order_by(Filing.filing_date.desc())
    ).all()

    flag_history = [
        _to_flag_response(flag, filing, co, ar.audit_firm if ar else None)
        for flag, filing, co, ar in flag_rows
    ]

    # Recent filings (latest 20)
    filings = db.execute(
        select(Filing)
        .where(Filing.company_id == company.id)
        .order_by(Filing.filing_date.desc())
        .limit(20)
    ).scalars().all()

    filing_list = []
    for f in filings:
        # Fetch auditor report and flag for this filing
        ar = db.execute(
            select(AuditorReport).where(AuditorReport.filing_id == f.id)
        ).scalar_one_or_none()
        gcf_row = db.execute(
            select(GoingConcernFlag, Filing, Company, AuditorReport)
            .join(Filing, GoingConcernFlag.filing_id == Filing.id)
            .join(Company, GoingConcernFlag.company_id == Company.id)
            .outerjoin(AuditorReport, AuditorReport.filing_id == Filing.id)
            .where(GoingConcernFlag.filing_id == f.id)
        ).first()
        flag_resp = None
        if gcf_row:
            flag_resp = _to_flag_response(gcf_row[0], gcf_row[1], gcf_row[2],
                                           gcf_row[3].audit_firm if gcf_row[3] else None)
        filing_list.append(
            FilingResponse(
                id=f.id,
                accession_number=f.accession_number,
                form_type=f.form_type,
                filing_date=f.filing_date,
                period_of_report=f.period_of_report,
                filing_url=f.filing_url,
                company=CompanyBrief(
                    cik=company.cik,
                    ticker=company.ticker,
                    name=company.name,
                    display_name=getattr(company, "display_name", None),
                ),
                auditor_report_excerpt=(ar.report_text[:2000] if ar else None),
                audit_firm=(ar.audit_firm if ar else None),
                going_concern_flag=flag_resp,
            )
        )

    most_recent_filing_date = filings[0].filing_date if filings else None

    # Aggregate stats
    agg = _aggregate_flags(db, [company.id])
    stats = agg.get(company.id, {
        "flag_summary": FlagSummary(),
        "most_recent_flag": None,
        "total_10ks": 0,
    })
    total_filings = db.execute(
        select(func.count()).where(Filing.company_id == company.id)
    ).scalar() or 0

    return CompanyDetailResponse(
        cik=company.cik,
        ticker=company.ticker,
        name=company.name,
        display_name=getattr(company, "display_name", None),
        sector=company.sector,
        industry=company.industry,
        total_filings=total_filings,
        total_10ks=stats["total_10ks"],
        flag_summary=stats["flag_summary"],
        most_recent_flag=stats["most_recent_flag"],
        most_recent_filing_date=most_recent_filing_date,
        flag_history=flag_history,
        filings=filing_list,
    )


def list_company_filings(
    db: Session,
    cik: str,
    limit: int = 20,
    cursor: str | None = None,
) -> FilingListResponse:
    """All filings for a company with their linked going-concern flag."""
    company = db.execute(
        select(Company).where(Company.cik == cik)
    ).scalar_one_or_none()
    if company is None:
        return FilingListResponse(items=[], next_cursor=None, has_more=False)

    stmt = (
        select(Filing)
        .where(Filing.company_id == company.id)
        .order_by(Filing.filing_date.desc(), Filing.id.desc())
    )

    if cursor:
        after_key, after_id = decode_cursor(cursor)
        after_date = date.fromisoformat(after_key)
        stmt = stmt.where(
            or_(
                Filing.filing_date < after_date,
                and_(
                    Filing.filing_date == after_date,
                    Filing.id < uuid.UUID(after_id),
                ),
            )
        )

    stmt = stmt.limit(limit + 1)
    filings = db.execute(stmt).scalars().all()
    has_more = len(filings) > limit
    filings = list(filings[:limit])

    items: list[FilingResponse] = []
    for f in filings:
        ar = db.execute(
            select(AuditorReport).where(AuditorReport.filing_id == f.id)
        ).scalar_one_or_none()
        gcf_row = db.execute(
            select(GoingConcernFlag, Filing, Company, AuditorReport)
            .join(Filing, GoingConcernFlag.filing_id == Filing.id)
            .join(Company, GoingConcernFlag.company_id == Company.id)
            .outerjoin(AuditorReport, AuditorReport.filing_id == Filing.id)
            .where(GoingConcernFlag.filing_id == f.id)
        ).first()
        flag_resp = None
        if gcf_row:
            flag_resp = _to_flag_response(gcf_row[0], gcf_row[1], gcf_row[2],
                                           gcf_row[3].audit_firm if gcf_row[3] else None)
        items.append(
            FilingResponse(
                id=f.id,
                accession_number=f.accession_number,
                form_type=f.form_type,
                filing_date=f.filing_date,
                period_of_report=f.period_of_report,
                filing_url=f.filing_url,
                company=CompanyBrief(
                    cik=company.cik,
                    ticker=company.ticker,
                    name=company.name,
                    display_name=getattr(company, "display_name", None),
                ),
                auditor_report_excerpt=(ar.report_text[:2000] if ar else None),
                audit_firm=(ar.audit_firm if ar else None),
                going_concern_flag=flag_resp,
            )
        )

    next_cursor = None
    if has_more and filings:
        last = filings[-1]
        next_cursor = encode_cursor(last.filing_date.isoformat(), str(last.id))

    return FilingListResponse(items=items, next_cursor=next_cursor, has_more=has_more)
