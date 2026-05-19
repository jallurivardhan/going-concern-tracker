"""Tests for GET /api/search."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from gct.main import app
from gct.schemas.api import SearchResponse, SearchResult

client = TestClient(app)


def _result(ticker: str, name: str, match_type: str = "ticker_exact") -> SearchResult:
    return SearchResult(
        cik="0001008654",
        ticker=ticker,
        name=name,
        match_type=match_type,
        has_critical_flag=False,
    )


def test_search_returns_400_for_short_query() -> None:
    """q shorter than 2 characters returns 422 (FastAPI query validation)."""
    response = client.get("/api/search?q=a")
    assert response.status_code == 422


def test_search_returns_400_when_q_missing() -> None:
    """Missing q parameter returns 422."""
    response = client.get("/api/search")
    assert response.status_code == 422


def test_search_returns_200_with_results() -> None:
    with patch("gct.routes.search.search_companies") as mock_svc:
        mock_svc.return_value = SearchResponse(
            results=[_result("TUP", "Tupperware Brands Corp", "name_substring")],
            query="tupp",
            total_returned=1,
        )
        response = client.get("/api/search?q=tupp")
    assert response.status_code == 200
    body = response.json()
    assert body["total_returned"] == 1
    assert body["results"][0]["name"] == "Tupperware Brands Corp"
    assert body["results"][0]["match_type"] == "name_substring"


def test_search_returns_200_empty_results_not_404() -> None:
    """No matches returns 200 with empty results, not 404."""
    with patch("gct.routes.search.search_companies") as mock_svc:
        mock_svc.return_value = SearchResponse(
            results=[], query="zzzzzzzzzz", total_returned=0
        )
        response = client.get("/api/search?q=zzzzzzzzzz")
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_search_result_includes_has_critical_flag() -> None:
    with patch("gct.routes.search.search_companies") as mock_svc:
        mock_svc.return_value = SearchResponse(
            results=[
                SearchResult(
                    cik="0001008654",
                    ticker="TUP",
                    name="Tupperware",
                    match_type="ticker_exact",
                    has_critical_flag=True,
                )
            ],
            query="TUP",
            total_returned=1,
        )
        response = client.get("/api/search?q=TUP")
    assert response.status_code == 200
    assert response.json()["results"][0]["has_critical_flag"] is True
