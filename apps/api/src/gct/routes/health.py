from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from gct.database import check_db_connection, get_db

router = APIRouter(tags=["health"])

_VERSION = "0.1.0"


@router.get("/health", response_model=None)
def health_check(
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Returns service health. Checks database connectivity via SELECT 1."""
    db_ok = check_db_connection(db)

    if db_ok:
        return {"status": "ok", "version": _VERSION, "database": "connected"}

    response.status_code = 503
    return {"status": "degraded", "database": "disconnected"}
