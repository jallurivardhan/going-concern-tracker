"""Tests for filing_fetcher.py — orchestration of per-company filing retrieval.

All external calls (EdgarClient, ticker lookup) are mocked so no real network
calls are made.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gct.ingestion.filing_fetcher import FetchedFiling, FilingFetcher, _parse_date
from gct.ingestion.exceptions import FilingFetchError


def _make_submissions_with_ticker(
    cik: str = "0000886158",
    name: str = "Bed Bath & Beyond Inc.",
    tickers: list[str] | None = None,
    **kwargs,
) -> dict:
    """Submissions response that includes the tickers list field."""
    base = _make_submissions(**kwargs)
    base["cik"] = cik
    base["name"] = name
    base["tickers"] = tickers if tickers is not None else []
    return base


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_submissions(
    accessions: list[str],
    dates: list[str],
    forms: list[str],
    primary_docs: list[str],
    report_dates: list[str] | None = None,
) -> dict:
    """Build a minimal submissions JSON response."""
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": accessions,
                "filingDate": dates,
                "reportDate": report_dates or [""] * len(accessions),
                "form": forms,
                "primaryDocument": primary_docs,
            }
        },
    }


def _make_client(submissions: dict, html: str = "<html><body>Filing</body></html>") -> MagicMock:
    client = MagicMock()
    client.get_company_submissions = AsyncMock(return_value=submissions)
    client.get_filing_document = AsyncMock(return_value=html)
    return client


# ── _parse_date ───────────────────────────────────────────────────────────────


def test_parse_date_parses_iso_format() -> None:
    assert _parse_date("2024-01-15") == date(2024, 1, 15)
    assert _parse_date("2023-12-31") == date(2023, 12, 31)


# ── FetchedFiling model ──────────────────────────────────────────────────────


def test_fetched_filing_is_pydantic_model() -> None:
    f = FetchedFiling(
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        form_type="10-K",
        accession_number="0000320193-24-000123",
        filing_date=date(2024, 11, 1),
        period_of_report=date(2024, 9, 28),
        filing_url="https://www.sec.gov/Archives/...",
        raw_html="<html/>",
    )
    assert f.ticker == "AAPL"
    assert f.cik == "0000320193"


# ── FilingFetcher ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_filings_returns_correct_count() -> None:
    """FilingFetcher returns at most max_per_type filings for each form type."""
    subs = _make_submissions(
        accessions=[
            "0000320193-24-000001",
            "0000320193-24-000002",
            "0000320193-24-000003",
            "0000320193-23-000001",
        ],
        dates=["2024-11-01", "2024-02-01", "2023-11-01", "2024-08-01"],
        forms=["10-K", "10-K", "10-K", "10-Q"],
        primary_docs=["aapl1.htm", "aapl2.htm", "aapl3.htm", "aapl4.htm"],
    )
    client = _make_client(subs)

    with patch(
        "gct.ingestion.filing_fetcher.resolve_ticker_to_cik",
        new=AsyncMock(return_value="0000320193"),
    ):
        fetcher = FilingFetcher(client)
        results = await fetcher.fetch_filings_for_company(
            "AAPL",
            form_types=["10-K", "10-Q"],
            max_per_type={"10-K": 2, "10-Q": 5},
        )

    ten_ks = [r for r in results if r.form_type == "10-K"]
    ten_qs = [r for r in results if r.form_type == "10-Q"]
    assert len(ten_ks) == 2  # capped at max_per_type
    assert len(ten_qs) == 1


@pytest.mark.asyncio
async def test_fetch_filings_skips_failed_filing() -> None:
    """A FilingFetchError on one filing does not abort the whole batch."""
    subs = _make_submissions(
        accessions=["0000320193-24-000001", "0000320193-24-000002"],
        dates=["2024-11-01", "2023-11-01"],
        forms=["10-K", "10-K"],
        primary_docs=["good.htm", "bad.htm"],
    )

    client = MagicMock()
    client.get_company_submissions = AsyncMock(return_value=subs)
    # First call succeeds; second raises FilingFetchError
    client.get_filing_document = AsyncMock(
        side_effect=[
            "<html>good</html>",
            FilingFetchError("0000320193-24-000002", "connection error"),
        ]
    )

    with patch(
        "gct.ingestion.filing_fetcher.resolve_ticker_to_cik",
        new=AsyncMock(return_value="0000320193"),
    ):
        fetcher = FilingFetcher(client)
        results = await fetcher.fetch_filings_for_company(
            "AAPL", form_types=["10-K"], max_per_type={"10-K": 5}
        )

    assert len(results) == 1
    assert results[0].accession_number == "0000320193-24-000001"


@pytest.mark.asyncio
async def test_fetch_filings_returns_empty_for_unknown_ticker() -> None:
    """When ticker lookup returns None, an empty list is returned."""
    client = MagicMock()

    with patch(
        "gct.ingestion.filing_fetcher.resolve_ticker_to_cik",
        new=AsyncMock(return_value=None),
    ):
        fetcher = FilingFetcher(client)
        results = await fetcher.fetch_filings_for_company("GHOST")

    assert results == []


# ── fetch_filings_by_cik ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_filings_by_cik_returns_correct_count() -> None:
    """fetch_filings_by_cik respects max_per_type caps (same as ticker path)."""
    subs = _make_submissions_with_ticker(
        cik="0000886158",
        name="Bed Bath & Beyond Inc.",
        tickers=["BBBY"],
        accessions=["0000886158-23-000001", "0000886158-22-000001"],
        dates=["2023-04-01", "2022-04-01"],
        forms=["10-K", "10-K"],
        primary_docs=["bbby23.htm", "bbby22.htm"],
    )
    client = _make_client(subs, html="<html><body>BBBY filing</body></html>")

    fetcher = FilingFetcher(client)
    results = await fetcher.fetch_filings_by_cik(
        cik="0000886158",
        form_types=["10-K"],
        max_per_type={"10-K": 1},
    )

    assert len(results) == 1
    assert results[0].cik == "0000886158"
    assert results[0].form_type == "10-K"
    # Ticker populated from submissions tickers list
    assert results[0].ticker == "BBBY"


@pytest.mark.asyncio
async def test_fetch_filings_by_cik_no_ticker_returns_none_ticker() -> None:
    """When submissions has no tickers (bankrupt/delisted), FetchedFiling.ticker is None."""
    subs = _make_submissions_with_ticker(
        cik="0000886158",
        name="Bed Bath & Beyond Inc.",
        tickers=[],  # no active tickers
        accessions=["0000886158-23-000001"],
        dates=["2023-04-01"],
        forms=["10-K"],
        primary_docs=["bbby23.htm"],
    )
    client = _make_client(subs)

    fetcher = FilingFetcher(client)
    results = await fetcher.fetch_filings_by_cik("0000886158", form_types=["10-K"], max_per_type={"10-K": 5})

    assert len(results) == 1
    assert results[0].ticker is None
    assert results[0].company_name == "Bed Bath & Beyond Inc."


@pytest.mark.asyncio
async def test_fetch_filings_by_cik_skips_failed_download() -> None:
    """A FilingFetchError on one filing does not abort the CIK batch."""
    subs = _make_submissions_with_ticker(
        cik="0000886158",
        name="Bed Bath & Beyond Inc.",
        tickers=["BBBY"],
        accessions=["0000886158-23-000001", "0000886158-22-000001"],
        dates=["2023-04-01", "2022-04-01"],
        forms=["10-K", "10-K"],
        primary_docs=["bbby23.htm", "bbby22.htm"],
    )
    client = MagicMock()
    client.get_company_submissions = AsyncMock(return_value=subs)
    client.get_filing_document = AsyncMock(
        side_effect=[
            "<html>good</html>",
            FilingFetchError("0000886158-22-000001", "timeout"),
        ]
    )

    fetcher = FilingFetcher(client)
    results = await fetcher.fetch_filings_by_cik("0000886158", form_types=["10-K"], max_per_type={"10-K": 5})

    assert len(results) == 1
    assert results[0].accession_number == "0000886158-23-000001"


@pytest.mark.asyncio
async def test_fetch_filings_populates_filing_url() -> None:
    """FetchedFiling.filing_url should be a valid EDGAR archive URL."""
    subs = _make_submissions(
        accessions=["0000320193-24-000001"],
        dates=["2024-11-01"],
        forms=["10-K"],
        primary_docs=["aapl-20240928.htm"],
        report_dates=["2024-09-28"],
    )
    client = _make_client(subs)

    with patch(
        "gct.ingestion.filing_fetcher.resolve_ticker_to_cik",
        new=AsyncMock(return_value="0000320193"),
    ):
        fetcher = FilingFetcher(client)
        results = await fetcher.fetch_filings_for_company(
            "AAPL", form_types=["10-K"], max_per_type={"10-K": 1}
        )

    assert len(results) == 1
    url = results[0].filing_url
    assert "sec.gov" in url
    assert "aapl-20240928.htm" in url
    assert results[0].period_of_report is not None
