"""Tests for GET /api/pipeline/status."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gct.database import get_db
from gct.main import app
from gct.models import PipelineRun


def _make_run(
    status: str = "success",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    trigger: str = "scheduled",
) -> MagicMock:
    run = MagicMock(spec=PipelineRun)
    run.id = uuid.uuid4()
    run.started_at = started_at or datetime(2026, 5, 17, 6, 0, 0, tzinfo=timezone.utc)
    run.completed_at = completed_at or datetime(2026, 5, 17, 6, 4, 0, tzinfo=timezone.utc)
    run.status = status
    run.filings_checked = 12
    run.filings_new = 0
    run.filings_classified = 0
    run.flags_created = 0
    run.total_cost_estimate = Decimal("0.000000")
    run.trigger = trigger
    return run


def _make_db_override(mock_session: MagicMock):
    """Return a FastAPI dependency-override generator for get_db."""
    def override() -> Generator[MagicMock, None, None]:
        yield mock_session
    return override


@pytest.fixture()
def client():
    return TestClient(app)


def _db_no_runs() -> MagicMock:
    """Session that returns no rows."""
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    return db


def _db_with_run(run: MagicMock) -> MagicMock:
    """Session that always returns the given run."""
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = run
    return db


class TestPipelineStatusNoRuns:
    def test_returns_200(self, client):
        app.dependency_overrides[get_db] = _make_db_override(_db_no_runs())
        try:
            with patch("gct.routes.pipeline._get_watchlist_size", return_value=12):
                resp = client.get("/api/pipeline/status")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200

    def test_null_when_no_runs(self, client):
        app.dependency_overrides[get_db] = _make_db_override(_db_no_runs())
        try:
            with patch("gct.routes.pipeline._get_watchlist_size", return_value=12):
                data = client.get("/api/pipeline/status").json()
        finally:
            app.dependency_overrides.clear()
        assert data["last_successful_run"] is None
        assert data["last_run"] is None

    def test_schedule_field_present(self, client):
        app.dependency_overrides[get_db] = _make_db_override(_db_no_runs())
        try:
            with patch("gct.routes.pipeline._get_watchlist_size", return_value=12):
                data = client.get("/api/pipeline/status").json()
        finally:
            app.dependency_overrides.clear()
        assert data["schedule"] == "daily 6am UTC"


class TestPipelineStatusWithRuns:
    def test_last_successful_run_returned(self, client):
        run = _make_run(status="success")
        app.dependency_overrides[get_db] = _make_db_override(_db_with_run(run))
        try:
            with patch("gct.routes.pipeline._get_watchlist_size", return_value=12):
                data = client.get("/api/pipeline/status").json()
        finally:
            app.dependency_overrides.clear()
        assert data["last_run"] is not None or data["last_successful_run"] is not None

    def test_run_fields_present(self, client):
        run = _make_run(status="success")
        app.dependency_overrides[get_db] = _make_db_override(_db_with_run(run))
        try:
            with patch("gct.routes.pipeline._get_watchlist_size", return_value=12):
                data = client.get("/api/pipeline/status").json()
        finally:
            app.dependency_overrides.clear()

        run_data = data["last_run"] or data["last_successful_run"]
        assert run_data is not None
        for field in (
            "id",
            "started_at",
            "status",
            "filings_checked",
            "filings_new",
            "filings_classified",
            "flags_created",
            "total_cost_estimate",
            "trigger",
        ):
            assert field in run_data, f"Missing field: {field}"


class TestPipelineStatusWatchlistSize:
    def test_watchlist_size_included(self, client):
        app.dependency_overrides[get_db] = _make_db_override(_db_no_runs())
        try:
            with patch("gct.routes.pipeline._get_watchlist_size", return_value=12):
                data = client.get("/api/pipeline/status").json()
        finally:
            app.dependency_overrides.clear()
        assert data["watchlist_size"] == 12

    def test_watchlist_size_fallback_on_error(self, client):
        """_get_watchlist_size returning 0 should not crash the endpoint."""
        app.dependency_overrides[get_db] = _make_db_override(_db_no_runs())
        try:
            with patch("gct.routes.pipeline._get_watchlist_size", return_value=0):
                resp = client.get("/api/pipeline/status")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["watchlist_size"] == 0
