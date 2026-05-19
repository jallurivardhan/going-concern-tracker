from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from gct.database import get_db
from gct.main import app

client = TestClient(app)


def _make_db_session(connected: bool) -> MagicMock:
    """Return a mock Session that either passes or raises on execute()."""
    mock_session = MagicMock()
    if not connected:
        mock_session.execute.side_effect = Exception("DB connection refused")
    return mock_session


def _make_db_override(mock_session: MagicMock):  # type: ignore[return]
    """Return a generator-function override for the get_db dependency."""

    def override() -> Generator[MagicMock, None, None]:
        yield mock_session

    return override


def test_health_returns_200_when_db_connected() -> None:
    """Health endpoint reports ok and 200 when the DB query succeeds."""
    mock_session = _make_db_session(connected=True)
    app.dependency_overrides[get_db] = _make_db_override(mock_session)

    try:
        response = client.get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert "version" in body


def test_health_returns_503_when_db_fails() -> None:
    """Health endpoint reports degraded and 503 when the DB query raises."""
    mock_session = _make_db_session(connected=False)
    app.dependency_overrides[get_db] = _make_db_override(mock_session)

    try:
        response = client.get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "disconnected"
