"""Tests for GET /api/companies, GET /api/companies/{cik}, /filings."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from gct.main import app
from gct.schemas.api import (
    CompanyDetailResponse,
    CompanyListResponse,
    CompanyResponse,
    FilingListResponse,
    FlagSummary,
)
from tests.conftest_api import make_company, make_filing

client = TestClient(app)


def _make_company_response(**kwargs) -> CompanyResponse:
    defaults = dict(
        cik="0001008654",
        ticker="TUP",
        name="Tupperware Brands Corp",
        sector=None,
        industry=None,
        total_filings=5,
        total_10ks=5,
        flag_summary=FlagSummary(critical=1, none=4),
        most_recent_flag=None,
    )
    defaults.update(kwargs)
    return CompanyResponse(**defaults)


# ── GET /api/companies ────────────────────────────────────────────────────────


def test_companies_returns_200_empty() -> None:
    with patch("gct.routes.companies.list_companies") as mock_svc:
        mock_svc.return_value = CompanyListResponse(
            items=[], next_cursor=None, has_more=False
        )
        response = client.get("/api/companies")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["has_more"] is False


def test_companies_with_q_filter() -> None:
    """q parameter is forwarded to the service."""
    with patch("gct.routes.companies.list_companies") as mock_svc:
        mock_svc.return_value = CompanyListResponse(
            items=[_make_company_response()], next_cursor=None, has_more=False
        )
        response = client.get("/api/companies?q=tupperware")
    assert response.status_code == 200
    call_kwargs = mock_svc.call_args[1]
    assert call_kwargs.get("q") == "tupperware"


def test_companies_limit_max_200() -> None:
    with patch("gct.routes.companies.list_companies") as mock_svc:
        mock_svc.return_value = CompanyListResponse(
            items=[], next_cursor=None, has_more=False
        )
        r = client.get("/api/companies?limit=201")
    assert r.status_code == 422


# ── GET /api/companies/{cik} ──────────────────────────────────────────────────


def test_company_detail_404_for_unknown_cik() -> None:
    with patch("gct.routes.companies.get_company", return_value=None):
        response = client.get("/api/companies/0000000000")
    assert response.status_code == 404


def test_company_detail_accepts_short_cik() -> None:
    """Short CIK (no leading zeros) is normalized and accepted."""
    detail = CompanyDetailResponse(
        cik="0001008654",
        ticker="TUP",
        name="Tupperware",
        sector=None,
        industry=None,
        total_filings=5,
        total_10ks=5,
        flag_summary=FlagSummary(critical=1),
        most_recent_flag=None,
        most_recent_filing_date=None,
        flag_history=[],
        filings=[],
    )
    with patch("gct.routes.companies.get_company", return_value=detail) as mock_svc:
        # Pass short CIK; normalize_cik should zero-pad it
        response = client.get("/api/companies/1008654")
    assert response.status_code == 200
    # The service was called with the normalized CIK
    mock_svc.assert_called_once()
    called_cik = mock_svc.call_args[0][1]
    assert called_cik == "0001008654"


def test_company_detail_returns_flag_history() -> None:
    detail = CompanyDetailResponse(
        cik="0001008654",
        ticker="TUP",
        name="Tupperware",
        sector=None,
        industry=None,
        total_filings=5,
        total_10ks=5,
        flag_summary=FlagSummary(critical=1),
        most_recent_flag=None,
        most_recent_filing_date=None,
        flag_history=[],
        filings=[],
    )
    with patch("gct.routes.companies.get_company", return_value=detail):
        response = client.get("/api/companies/0001008654")
    assert response.status_code == 200
    body = response.json()
    assert "flag_history" in body
    assert "filings" in body


# ── GET /api/companies/{cik}/filings ─────────────────────────────────────────


def test_company_filings_returns_empty_list_not_404() -> None:
    """Empty filing list returns 200, not 404."""
    with patch("gct.routes.companies.list_company_filings") as mock_svc:
        mock_svc.return_value = FilingListResponse(
            items=[], next_cursor=None, has_more=False
        )
        response = client.get("/api/companies/0001008654/filings")
    assert response.status_code == 200
    assert response.json()["items"] == []


# ── display_name tests ────────────────────────────────────────────────────────


def test_company_response_uses_display_name_when_set() -> None:
    """When display_name is set, the API response uses it directly."""
    resp = _make_company_response(
        name="TUPPERWARE BRANDS CORP",
        display_name="Tupperware Brands Corporation",
    )
    with patch("gct.routes.companies.list_companies") as mock_svc:
        mock_svc.return_value = CompanyListResponse(
            items=[resp], next_cursor=None, has_more=False
        )
        response = client.get("/api/companies")
    body = response.json()
    assert body["items"][0]["display_name"] == "Tupperware Brands Corporation"
    assert body["items"][0]["name"] == "TUPPERWARE BRANDS CORP"


def test_company_response_falls_back_to_humanized_name_when_display_name_null() -> None:
    """When display_name is None, the validator applies title-casing to all-caps names."""
    from gct.schemas.api import _humanize_name

    # All-caps names get title-cased
    assert _humanize_name("TUPPERWARE BRANDS CORP") == "Tupperware Brands Corp"
    assert _humanize_name("MICROSOFT CORP") == "Microsoft Corp"

    # Mixed-case names are returned unchanged
    assert _humanize_name("Apple Inc.") == "Apple Inc."
    assert _humanize_name("WeWork Inc.") == "WeWork Inc."
    assert _humanize_name("Beyond Meat, Inc.") == "Beyond Meat, Inc."

    # The model validator fills display_name on construction
    resp = _make_company_response(name="MICROSOFT CORP", display_name=None)
    # display_name should be auto-filled to the title-cased version
    assert resp.display_name == "Microsoft Corp"
