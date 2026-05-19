"""Company search query logic.

Searches by ticker (exact and prefix) and name (substring).
Results are sorted by match quality: exact ticker first, then prefix, then substring.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from gct.models import Company, GoingConcernFlag
from gct.schemas.api import SearchResponse, SearchResult

_POSITIVE_SEVERITIES = ("critical", "elevated", "watch")


def search_companies(db: Session, q: str, limit: int = 10) -> SearchResponse:
    """Search companies by ticker or name.

    Returns up to ``limit`` results ranked by match quality.
    """
    q_clean = q.strip()
    q_upper = q_clean.upper()
    q_lower = q_clean.lower()

    # Fetch candidates: ticker exact/prefix OR name substring
    candidates = db.execute(
        select(Company).where(
            or_(
                Company.ticker == q_upper,
                func.lower(Company.ticker).like(f"{q_lower}%"),
                func.lower(Company.name).like(f"%{q_lower}%"),
            )
        ).order_by(Company.name).limit(50)
    ).scalars().all()

    # Determine which companies have a critical flag
    company_ids = [c.id for c in candidates]
    critical_ids: set = set()
    if company_ids:
        rows = db.execute(
            select(GoingConcernFlag.company_id)
            .where(
                GoingConcernFlag.company_id.in_(company_ids),
                GoingConcernFlag.severity.in_(_POSITIVE_SEVERITIES),
            )
            .distinct()
        ).scalars().all()
        critical_ids = set(rows)

    results: list[SearchResult] = []
    seen: set = set()
    for company in candidates:
        if company.id in seen:
            continue
        seen.add(company.id)

        ticker = (company.ticker or "").upper()
        name_lower = company.name.lower()

        if ticker == q_upper:
            match_type = "ticker_exact"
        elif ticker.startswith(q_upper):
            match_type = "ticker_prefix"
        else:
            match_type = "name_substring"

        results.append(
            SearchResult(
                cik=company.cik,
                ticker=company.ticker,
                name=company.name,
                display_name=getattr(company, "display_name", None),
                match_type=match_type,
                has_critical_flag=company.id in critical_ids,
            )
        )

    # Sort: ticker_exact first, then ticker_prefix, then name_substring
    _rank = {"ticker_exact": 0, "ticker_prefix": 1, "name_substring": 2}
    results.sort(key=lambda r: (_rank[r.match_type], r.name))
    results = results[:limit]

    return SearchResponse(results=results, query=q_clean, total_returned=len(results))
