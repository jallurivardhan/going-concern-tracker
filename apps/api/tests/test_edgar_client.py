"""Tests for edgar_client.py — rate limiting, User-Agent header, retry logic.

All HTTP is mocked via respx so no real network calls are made.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from gct.ingestion.edgar_client import (
    EdgarClient,
    _MAX_RETRIES,
    _SlidingWindowRateLimiter,
    _accession_no_dashes,
    _cik_as_int_str,
)
from gct.ingestion.exceptions import EdgarError, FilingFetchError


# ── helper fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def ticker_json() -> dict:
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corporation"},
    }


# ── URL / format helpers ────────────────────────────────────────────────────


def test_accession_no_dashes() -> None:
    assert _accession_no_dashes("0000320193-24-000123") == "000032019324000123"


def test_cik_as_int_str() -> None:
    assert _cik_as_int_str("0000320193") == "320193"
    assert _cik_as_int_str("0000012345") == "12345"


# ── User-Agent header ───────────────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_user_agent_header_is_set(ticker_json: dict) -> None:
    """Every outgoing request must carry the SEC-mandated User-Agent header."""
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=ticker_json)
    )

    async with EdgarClient() as client:
        await client.get_ticker_cik_map()

    assert route.called
    sent_headers = route.calls[0].request.headers
    assert "user-agent" in sent_headers
    ua = sent_headers["user-agent"]
    assert "Going Concern Tracker" in ua
    # Must contain the configured email so SEC can contact us
    assert "@" in ua


# ── Rate limiting ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limiter_allows_calls_within_window() -> None:
    """``max_calls`` requests within the window must not trigger a sleep."""
    limiter = _SlidingWindowRateLimiter(max_calls=3, period=1.0)
    sleep_calls: list[float] = []

    async def fake_sleep(t: float) -> None:
        sleep_calls.append(t)

    with patch("gct.ingestion.edgar_client.asyncio.sleep", side_effect=fake_sleep):
        # monotonic always returns 0.0 → all calls appear simultaneous in window
        with patch("gct.ingestion.edgar_client.time.monotonic", return_value=0.0):
            await limiter.acquire()
            await limiter.acquire()
            await limiter.acquire()

    # No sleep needed for the first 3 calls at timestamp 0.0
    # (The implementation may or may not sleep 0s; we just check no positive wait)
    assert all(t <= 0 for t in sleep_calls), f"Unexpected sleep: {sleep_calls}"


@pytest.mark.asyncio
async def test_rate_limit_enforces_max_rps() -> None:
    """The (max_calls + 1)th call in the same window must trigger a sleep."""
    limiter = _SlidingWindowRateLimiter(max_calls=2, period=1.0)
    sleep_calls: list[float] = []

    async def fake_sleep(t: float) -> None:
        sleep_calls.append(t)

    with patch("gct.ingestion.edgar_client.asyncio.sleep", side_effect=fake_sleep):
        with patch("gct.ingestion.edgar_client.time.monotonic", return_value=0.0):
            await limiter.acquire()  # call 1 — ok
            await limiter.acquire()  # call 2 — ok (window full)
            await limiter.acquire()  # call 3 — must sleep

    # At least one positive sleep should have been issued
    positive_sleeps = [t for t in sleep_calls if t > 0]
    assert len(positive_sleeps) >= 1, "Expected at least one positive sleep for rate limiting"
    assert positive_sleeps[0] == pytest.approx(1.0, abs=0.01)


# ── Retry logic ─────────────────────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_retry_on_429_with_exponential_backoff(ticker_json: dict) -> None:
    """A 429 response should be retried; the second attempt should succeed."""
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        side_effect=[
            httpx.Response(429),          # first attempt → rate limited
            httpx.Response(200, json=ticker_json),  # retry → success
        ]
    )

    sleep_calls: list[float] = []

    async def fake_sleep(t: float) -> None:
        sleep_calls.append(t)

    with patch("gct.ingestion.edgar_client.asyncio.sleep", side_effect=fake_sleep):
        async with EdgarClient() as client:
            result = await client.get_ticker_cik_map()

    assert route.call_count == 2, "Expected exactly 2 HTTP calls (1 fail + 1 retry)"
    assert "AAPL" in result
    # At least one sleep was for the retry backoff
    assert len(sleep_calls) >= 1


@respx.mock
@pytest.mark.asyncio
async def test_retry_gives_up_after_max_attempts() -> None:
    """After _MAX_RETRIES exhausted, EdgarError must be raised."""
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(429)
    )

    with patch("gct.ingestion.edgar_client.asyncio.sleep"):
        with pytest.raises(EdgarError):
            async with EdgarClient() as client:
                await client.get_ticker_cik_map()


@respx.mock
@pytest.mark.asyncio
async def test_retry_on_503() -> None:
    """503 responses are also retried."""
    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"0": {"cik_str": 1, "ticker": "X", "title": "X Co"}}),
        ]
    )

    with patch("gct.ingestion.edgar_client.asyncio.sleep"):
        async with EdgarClient() as client:
            result = await client.get_ticker_cik_map()

    assert route.call_count == 2
    assert "X" in result


# ── get_ticker_cik_map ──────────────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_get_ticker_cik_map_normalises_cik(ticker_json: dict) -> None:
    """CIKs must be returned as 10-digit zero-padded strings."""
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=ticker_json)
    )

    async with EdgarClient() as client:
        result = await client.get_ticker_cik_map()

    assert result["AAPL"] == "0000320193"
    assert result["MSFT"] == "0000789019"


@respx.mock
@pytest.mark.asyncio
async def test_get_ticker_cik_map_uppercases_tickers() -> None:
    """Tickers in the result dict must be UPPERCASE regardless of source data."""
    raw = {"0": {"cik_str": 999, "ticker": "lower", "title": "Lower Co"}}
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=raw)
    )

    async with EdgarClient() as client:
        result = await client.get_ticker_cik_map()

    assert "LOWER" in result
    assert "lower" not in result


# ── get_filing_document error wrapping ─────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_get_company_submissions_returns_json() -> None:
    """get_company_submissions fetches and returns parsed JSON."""
    submissions = {"cik": "0000320193", "name": "Apple Inc.", "filings": {"recent": {}}}
    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=submissions)
    )

    async with EdgarClient() as client:
        result = await client.get_company_submissions("0000320193")

    assert result["name"] == "Apple Inc."
    assert result["cik"] == "0000320193"


@respx.mock
@pytest.mark.asyncio
async def test_get_filing_index_returns_json() -> None:
    """get_filing_index fetches the -index.json for an accession number."""
    index = {"directory": {"name": "0000320193-24-000123"}, "items": []}
    respx.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/000032019324000123-index.json"
    ).mock(return_value=httpx.Response(200, json=index))

    async with EdgarClient() as client:
        result = await client.get_filing_index("0000320193", "0000320193-24-000123")

    assert "directory" in result


@respx.mock
@pytest.mark.asyncio
async def test_get_filing_document_returns_html() -> None:
    """get_filing_document fetches and returns the document text."""
    html_content = "<html><body><p>Test filing content</p></body></html>"
    respx.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"
    ).mock(return_value=httpx.Response(200, text=html_content))

    async with EdgarClient() as client:
        result = await client.get_filing_document(
            "0000320193", "0000320193-24-000123", "aapl-20240928.htm"
        )

    assert "Test filing content" in result


@respx.mock
@pytest.mark.asyncio
async def test_get_filing_document_wraps_error_as_filing_fetch_error() -> None:
    """A persistent error fetching a document is wrapped as FilingFetchError."""
    # Construct the exact URL that get_filing_document will request
    # cik "0000320193" → int str "320193"
    # accession "0000320193-24-000123" → no dashes "000032019324000123"
    doc_url = (
        "https://www.sec.gov/Archives/edgar/data"
        "/320193/000032019324000123/aapl-20240928.htm"
    )
    respx.get(doc_url).mock(return_value=httpx.Response(429))

    with patch("gct.ingestion.edgar_client.asyncio.sleep"):
        with pytest.raises(FilingFetchError) as exc_info:
            async with EdgarClient() as client:
                await client.get_filing_document(
                    "0000320193", "0000320193-24-000123", "aapl-20240928.htm"
                )

    assert "0000320193-24-000123" in str(exc_info.value)
