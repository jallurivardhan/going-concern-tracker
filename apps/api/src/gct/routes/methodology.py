"""GET /api/methodology — evaluation methodology and current metrics."""

from __future__ import annotations

from fastapi import APIRouter

from gct.schemas.api import MethodologyResponse
from gct.services.stats_service import get_methodology

router = APIRouter(prefix="/methodology", tags=["methodology"])


@router.get(
    "",
    response_model=MethodologyResponse,
    summary="Evaluation methodology and current benchmark metrics",
)
def get_methodology_endpoint() -> MethodologyResponse:
    """Returns the classification methodology, scope, and latest benchmark results.

    ``current_metrics`` is null when no benchmark report has been run yet.
    """
    return get_methodology()
