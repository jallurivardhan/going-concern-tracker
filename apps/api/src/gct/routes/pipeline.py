"""GET /api/pipeline/status — pipeline run history and watchlist info."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from gct.database import get_db
from gct.models import PipelineRun
from gct.schemas.api import PipelineRunBrief, PipelineStatusResponse

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_WATCHLIST_PATH = Path(__file__).parents[3] / "data" / "watchlist.yaml"


def _get_watchlist_size() -> int:
    try:
        with open(_WATCHLIST_PATH) as f:
            data = yaml.safe_load(f)
        return len(data.get("companies", []))
    except Exception:
        return 0


@router.get(
    "/status",
    response_model=PipelineStatusResponse,
    summary="Pipeline run status and watchlist metadata",
)
def get_pipeline_status(db: Session = Depends(get_db)) -> PipelineStatusResponse:
    last_run_row = db.execute(
        select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()

    last_successful_row = db.execute(
        select(PipelineRun)
        .where(PipelineRun.status == "success")
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    def _brief(row: PipelineRun | None) -> PipelineRunBrief | None:
        if row is None:
            return None
        return PipelineRunBrief.model_validate(row)

    return PipelineStatusResponse(
        last_successful_run=_brief(last_successful_row),
        last_run=_brief(last_run_row),
        watchlist_size=_get_watchlist_size(),
        schedule="daily 6am UTC",
    )
