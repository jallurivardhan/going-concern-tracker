"""Tests for GET /api/flags and GET /api/flags/{flag_id}."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gct.main import app
from gct.schemas.api import FlagDetailResponse, FlagListResponse
from gct.database import get_db
from tests.conftest_api import (
    clear_db,
    make_auditor_report,
    make_company,
    make_filing,
    make_flag,
    patch_db,
)

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_flag_list_response(severity: str = "critical"):
    company = make_company()
    filing = make_filing(company)
    flag = make_flag(filing, company, severity=severity)
    ar = make_auditor_report(filing)
    return FlagListResponse(
        items=[],
        next_cursor=None,
        has_more=False,
        total_returned=0,
    )


# ── GET /api/flags ────────────────────────────────────────────────────────────


def test_flags_returns_200_empty_list() -> None:
    """GET /api/flags returns 200 with empty items when service returns nothing."""
    with patch("gct.routes.flags.list_flags") as mock_svc:
        mock_svc.return_value = FlagListResponse(
            items=[], next_cursor=None, has_more=False, total_returned=0
        )
        response = client.get("/api/flags")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["has_more"] is False
    assert body["total_returned"] == 0


def test_flags_passes_severity_filter() -> None:
    """Severity query param is forwarded to the service as a list."""
    with patch("gct.routes.flags.list_flags") as mock_svc:
        mock_svc.return_value = FlagListResponse(
            items=[], next_cursor=None, has_more=False, total_returned=0
        )
        response = client.get("/api/flags?severity=critical,elevated")

    assert response.status_code == 200
    call_kwargs = mock_svc.call_args[1] if mock_svc.call_args[1] else {}
    call_args = mock_svc.call_args
    # severity should be parsed from comma-separated string
    passed_severity = call_args[0][1] if len(call_args[0]) > 1 else call_kwargs.get("severity")
    assert passed_severity == ["critical", "elevated"]


def test_flags_limit_bounds() -> None:
    """Limit must be between 1 and 100."""
    with patch("gct.routes.flags.list_flags") as mock_svc:
        mock_svc.return_value = FlagListResponse(
            items=[], next_cursor=None, has_more=False, total_returned=0
        )
        r_low = client.get("/api/flags?limit=0")
        r_high = client.get("/api/flags?limit=101")

    assert r_low.status_code == 422
    assert r_high.status_code == 422


def test_flags_default_excludes_none_severity() -> None:
    """Default /api/flags call passes None severity (service applies default filter)."""
    with patch("gct.routes.flags.list_flags") as mock_svc:
        mock_svc.return_value = FlagListResponse(
            items=[], next_cursor=None, has_more=False, total_returned=0
        )
        client.get("/api/flags")

    call_args = mock_svc.call_args
    # When no severity param, the route passes None; the service uses its own default
    passed_severity = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("severity")
    assert passed_severity is None


# ── GET /api/flags/{flag_id} ──────────────────────────────────────────────────


def test_flag_detail_returns_404_for_unknown_id() -> None:
    """GET /api/flags/{unknown_id} returns 404."""
    with patch("gct.routes.flags.get_flag", return_value=None):
        response = client.get(f"/api/flags/{uuid.uuid4()}")
    assert response.status_code == 404


def test_flag_detail_returns_200_with_excerpt() -> None:
    """GET /api/flags/{id} returns 200 with report_excerpt field."""
    company = make_company()
    filing = make_filing(company)
    flag = make_flag(filing, company)
    ar = make_auditor_report(filing)

    detail = FlagDetailResponse(
        id=flag.id,
        company=dict(cik=company.cik, ticker=company.ticker, name=company.name),
        filing=dict(
            id=filing.id,
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            filing_url=filing.filing_url,
        ),
        severity="critical",
        flag_type="new",
        quoted_language="substantial doubt",
        char_offset_start=10,
        char_offset_end=50,
        classification_confidence="0.990",
        classifier_version="v1.0-claude",
        detected_at=flag.detected_at,
        audit_firm="PwC LLP",
        report_excerpt="...text excerpt...",
        report_total_length=3000,
    )

    with patch("gct.routes.flags.get_flag", return_value=detail):
        response = client.get(f"/api/flags/{flag.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["report_excerpt"] == "...text excerpt..."
    assert body["report_total_length"] == 3000
    assert body["severity"] == "critical"
