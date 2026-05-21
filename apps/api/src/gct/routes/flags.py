"""GET /api/flags and GET /api/flags/{flag_id}."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from gct.database import get_db
from gct.schemas.api import FlagDetailResponse, FlagListResponse
from gct.services.flag_service import get_flag, list_flags

router = APIRouter(prefix="/flags", tags=["flags"])


@router.get(
    "",
    response_model=FlagListResponse,
    summary="Paginated feed of going-concern flags",
    response_description="List of flags, newest first. Default excludes severity=none.",
)
def get_flags(
    severity: Annotated[
        str | None,
        Query(description="Comma-separated severities: critical,elevated,watch,none"),
    ] = None,
    flag_type: Annotated[
        str | None,
        Query(description="Comma-separated flag types: new,continuation,none"),
    ] = None,
    cik: Annotated[str | None, Query(description="Filter to a single company CIK")] = None,
    since: Annotated[date | None, Query(description="Only flags detected on or after this ISO date")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size (max 100)")] = 20,
    cursor: Annotated[str | None, Query(description="Opaque pagination cursor from previous response")] = None,
    sort: Annotated[str, Query(description="filing_date_desc (default), detected_at_desc, or detected_at_asc")] = "filing_date_desc",
    db: Session = Depends(get_db),
) -> FlagListResponse:
    severity_list = [s.strip() for s in severity.split(",")] if severity else None
    flag_type_list = [f.strip() for f in flag_type.split(",")] if flag_type else None
    return list_flags(
        db,
        severity=severity_list,
        flag_type=flag_type_list,
        cik=cik,
        since=since,
        limit=limit,
        cursor=cursor,
        sort=sort,
    )


@router.get(
    "/{flag_id}",
    response_model=FlagDetailResponse,
    summary="Single flag with auditor report excerpt",
)
def get_flag_detail(
    flag_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FlagDetailResponse:
    flag = get_flag(db, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail=f"Flag {flag_id} not found")
    return flag
