"""Tests for GET /api/stats and GET /api/methodology."""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gct.main import app
from gct.schemas.api import (
    EvalMetrics,
    FlagSummary,
    MethodologyResponse,
    RecentFlagBrief,
    StatsResponse,
)

client = TestClient(app)


def _make_stats(**kwargs) -> StatsResponse:
    defaults = dict(
        total_companies_tracked=8,
        total_filings_analyzed=38,
        total_auditor_reports_extracted=38,
        total_flags_active=2,
        flag_breakdown=FlagSummary(critical=2, none=36),
        most_recent_critical_flag=None,
        last_pipeline_run=None,
    )
    defaults.update(kwargs)
    return StatsResponse(**defaults)


# ── GET /api/stats ─────────────────────────────────────────────────────────────


def test_stats_returns_200() -> None:
    with patch("gct.routes.stats.get_stats", return_value=_make_stats()):
        response = client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_companies_tracked"] == 8
    assert body["total_flags_active"] == 2


def test_stats_includes_flag_breakdown() -> None:
    with patch("gct.routes.stats.get_stats", return_value=_make_stats()):
        response = client.get("/api/stats")
    body = response.json()
    assert body["flag_breakdown"]["critical"] == 2
    assert body["flag_breakdown"]["none"] == 36


def test_stats_most_recent_flag_is_null_when_none() -> None:
    with patch("gct.routes.stats.get_stats", return_value=_make_stats(most_recent_critical_flag=None)):
        response = client.get("/api/stats")
    assert response.json()["most_recent_critical_flag"] is None


def test_stats_most_recent_flag_contains_minutes_to_detect() -> None:
    import uuid
    flag_brief = RecentFlagBrief(
        id=uuid.uuid4(),
        company_name="TUPPERWARE BRANDS CORPORATION",
        company_display_name="Tupperware Brands Corporation",
        company_ticker="TUP",
        severity="critical",
        filing_date=date(2023, 10, 13),
        detected_at=datetime(2026, 5, 17),
        minutes_to_detect=None,  # backfilled, so null
    )
    with patch("gct.routes.stats.get_stats",
               return_value=_make_stats(most_recent_critical_flag=flag_brief)):
        response = client.get("/api/stats")
    body = response.json()
    assert body["most_recent_critical_flag"]["minutes_to_detect"] is None
    assert body["most_recent_critical_flag"]["company_display_name"] == "Tupperware Brands Corporation"
    assert body["most_recent_critical_flag"]["company_name"] == "TUPPERWARE BRANDS CORPORATION"


# ── GET /api/methodology ───────────────────────────────────────────────────────


def test_methodology_returns_200() -> None:
    with patch("gct.routes.methodology.get_methodology") as mock_svc:
        mock_svc.return_value = MethodologyResponse(
            methodology_version="v1.0",
            classifier_version="v1.0-claude",
            eval_set_version="v1.0",
            current_metrics=None,
            in_scope=["10-K annual filings"],
            out_of_scope=["10-Q quarterly filings"],
        )
        response = client.get("/api/methodology")
    assert response.status_code == 200
    body = response.json()
    assert body["methodology_version"] == "v1.0"


def test_methodology_returns_null_metrics_when_no_report(tmp_path: Path) -> None:
    """current_metrics is null when no eval report file exists."""
    with patch("gct.services.stats_service._REPORTS_DIR", tmp_path):
        from gct.services.stats_service import get_methodology
        result = get_methodology()
    assert result.current_metrics is None


def test_methodology_loads_metrics_from_report_file(tmp_path: Path) -> None:
    """current_metrics is populated from the most recent report JSON."""
    report_data = {
        "total_cases": 38,
        "precision": "1.0000",
        "recall": "1.0000",
        "f1": "1.0000",
        "accuracy": "1.0000",
        "timestamp": "2026-05-17T04:00:42.586723",
    }
    report_file = tmp_path / "20260517T040042.json"
    report_file.write_text(json.dumps(report_data))

    with patch("gct.services.stats_service._REPORTS_DIR", tmp_path):
        from gct.services.stats_service import get_methodology
        result = get_methodology()

    assert result.current_metrics is not None
    assert result.current_metrics.total_cases == 38
    assert isinstance(result.current_metrics.precision, Decimal)
    assert result.current_metrics.precision == Decimal("1.0000")


def test_decimal_serialization_preserves_precision() -> None:
    """Decimal values in responses serialize as strings with original precision."""
    metrics = EvalMetrics(
        total_cases=38,
        precision=Decimal("1.0000"),
        recall=Decimal("0.9999"),
        f1=Decimal("0.9999"),
        accuracy=Decimal("1.0000"),
        last_run=datetime(2026, 5, 17),
    )
    with patch("gct.routes.methodology.get_methodology") as mock_svc:
        mock_svc.return_value = MethodologyResponse(
            methodology_version="v1.0",
            classifier_version="v1.0-claude",
            eval_set_version="v1.0",
            current_metrics=metrics,
            in_scope=[],
            out_of_scope=[],
        )
        response = client.get("/api/methodology")
    body = response.json()
    # Must be a string "1.0000" not a float 1.0
    assert body["current_metrics"]["precision"] == "1.0000"
    assert body["current_metrics"]["recall"] == "0.9999"
    assert isinstance(body["current_metrics"]["precision"], str)
