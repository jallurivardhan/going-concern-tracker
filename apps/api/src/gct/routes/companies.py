"""GET /api/companies, GET /api/companies/{cik}, GET /api/companies/{cik}/filings."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from gct.database import get_db
from gct.ingestion import normalize_cik
from gct.schemas.api import (
    CompanyDetailResponse,
    CompanyListResponse,
    FilingListResponse,
)
from gct.services.company_service import (
    get_company,
    list_companies,
    list_company_filings,
)

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get(
    "",
    response_model=CompanyListResponse,
    summary="Company list with flag statistics",
)
def get_companies(
    q: Annotated[
        str | None,
        Query(description="Case-insensitive substring match on name or ticker"),
    ] = None,
    has_flags: Annotated[
        bool | None,
        Query(description="Filter to companies with at least one active flag"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Page size (max 200)")] = 50,
    cursor: Annotated[str | None, Query(description="Pagination cursor")] = None,
    sort: Annotated[
        str,
        Query(description="name_asc (default), name_desc, or recent_flag_first"),
    ] = "name_asc",
    db: Session = Depends(get_db),
) -> CompanyListResponse:
    return list_companies(db, q=q, has_flags=has_flags, limit=limit, cursor=cursor, sort=sort)


@router.get(
    "/{cik}",
    response_model=CompanyDetailResponse,
    summary="Company detail with flag history",
)
def get_company_detail(
    cik: str,
    db: Session = Depends(get_db),
) -> CompanyDetailResponse:
    try:
        normalized = normalize_cik(cik)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid CIK format: {cik!r}")
    company = get_company(db, normalized)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company with CIK {cik!r} not found")
    return company


@router.get(
    "/{cik}/filings",
    response_model=FilingListResponse,
    summary="All filings for a company",
)
def get_company_filings(
    cik: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> FilingListResponse:
    try:
        normalized = normalize_cik(cik)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid CIK format: {cik!r}")
    return list_company_filings(db, normalized, limit=limit, cursor=cursor)
