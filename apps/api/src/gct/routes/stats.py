"""GET /api/stats — landing page aggregate statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from gct.database import get_db
from gct.schemas.api import StatsResponse
from gct.services.stats_service import get_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get(
    "",
    response_model=StatsResponse,
    summary="System-wide aggregate statistics for the landing page",
)
def get_stats_endpoint(db: Session = Depends(get_db)) -> StatsResponse:
    """Returns aggregate counts and the most recent critical flag.

    ``minutes_to_detect`` is null for backfilled historical filings (where the
    gap between filing_date and detected_at exceeds 7 days).
    """
    return get_stats(db)
