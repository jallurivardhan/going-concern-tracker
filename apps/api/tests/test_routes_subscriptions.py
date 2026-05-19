"""Tests for POST /api/subscriptions and DELETE /api/subscriptions/{token}."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from gct.database import get_db
from gct.main import app
from gct.routes.subscriptions import _ip_timestamps
from tests.conftest_api import clear_db, patch_db

client = TestClient(app)


def _make_db_override(mock_session: MagicMock) -> callable:
    def override() -> Generator[MagicMock, None, None]:
        yield mock_session
    return override


def _mock_db_no_existing() -> MagicMock:
    """DB session mock where the subscription email doesn't exist yet."""
    db = MagicMock()
    # first execute (select existing) returns None
    db.execute.return_value.scalar_one_or_none.return_value = None
    return db


def _mock_db_with_existing(sub_id: uuid.UUID) -> MagicMock:
    """DB session mock where the subscription already exists."""
    from gct.models import Subscription
    existing = MagicMock(spec=Subscription)
    existing.id = sub_id
    existing.email = "user@example.com"
    existing.confirmed = False
    existing.confirmation_token = str(uuid.uuid4())

    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = existing
    return db


# ── POST /api/subscriptions ───────────────────────────────────────────────────


def test_subscription_creates_new_row() -> None:
    _ip_timestamps.clear()
    mock_db = _mock_db_no_existing()
    app.dependency_overrides[get_db] = _make_db_override(mock_db)
    try:
        response = client.post(
            "/api/subscriptions", json={"email": "newuser@example.com"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["already_subscribed"] is False
    assert body["subscription_id"] is not None


def test_subscription_already_subscribed_returns_200() -> None:
    _ip_timestamps.clear()
    sub_id = uuid.uuid4()
    mock_db = _mock_db_with_existing(sub_id)
    app.dependency_overrides[get_db] = _make_db_override(mock_db)
    try:
        response = client.post(
            "/api/subscriptions", json={"email": "user@example.com"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["already_subscribed"] is True
    assert body["subscription_id"] == str(sub_id)


def test_subscription_rejects_invalid_email() -> None:
    _ip_timestamps.clear()
    mock_db = _mock_db_no_existing()
    app.dependency_overrides[get_db] = _make_db_override(mock_db)
    try:
        response = client.post(
            "/api/subscriptions", json={"email": "not-an-email"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_subscription_rate_limit_triggers_after_5_requests() -> None:
    """6th request from the same IP within the window returns 429."""
    _ip_timestamps.clear()
    mock_db = _mock_db_no_existing()
    app.dependency_overrides[get_db] = _make_db_override(mock_db)
    try:
        # Make 5 successful requests
        for i in range(5):
            r = client.post(
                "/api/subscriptions",
                json={"email": f"user{i}@example.com"},
            )
            # May get 200 or already_subscribed but not 429 yet
            assert r.status_code in (200, 422)

        # 6th request should be rate-limited
        r = client.post(
            "/api/subscriptions",
            json={"email": "newone@example.com"},
        )
        assert r.status_code == 429
    finally:
        app.dependency_overrides.clear()
        _ip_timestamps.clear()


# ── DELETE /api/subscriptions/{token} ────────────────────────────────────────


def test_unsubscribe_returns_404_for_unknown_token() -> None:
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    app.dependency_overrides[get_db] = _make_db_override(mock_db)
    try:
        response = client.delete(f"/api/subscriptions/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_unsubscribe_returns_200_for_valid_token() -> None:
    from gct.models import Subscription
    token = str(uuid.uuid4())
    sub = MagicMock(spec=Subscription)
    sub.id = uuid.uuid4()
    sub.email = "user@example.com"
    sub.confirmation_token = token
    sub.unsubscribed_at = None

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = sub

    app.dependency_overrides[get_db] = _make_db_override(mock_db)
    try:
        response = client.delete(f"/api/subscriptions/{token}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
