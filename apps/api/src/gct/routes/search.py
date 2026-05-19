"""GET /api/search — company ticker and name search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from gct.database import get_db
from gct.schemas.api import SearchResponse
from gct.services.search_service import search_companies

router = APIRouter(prefix="/search", tags=["search"])


@router.get(
    "",
    response_model=SearchResponse,
    summary="Search companies by ticker or name",
)
def search(
    q: Annotated[
        str,
        Query(min_length=2, description="Search query (min 2 characters)"),
    ],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Search companies by ticker (exact and prefix) or name (substring).

    Returns 400 when ``q`` is shorter than 2 characters (enforced by FastAPI
    query parameter validation).
    """
    return search_companies(db, q=q, limit=limit)
