"""HTTP client for SEC EDGAR with rate limiting and exponential-backoff retries.

SEC EDGAR fair-access policy:
  - User-Agent must identify the accessing application and a contact email.
  - Maximum 10 requests per second per https://www.sec.gov/os/accessing-edgar-data
  - Respect Retry-After headers on 429 responses.

All public methods are async. Instantiate as an async context manager:

    async with EdgarClient() as client:
        data = await client.get_ticker_cik_map()
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from gct.config import settings
from gct.ingestion.exceptions import EdgarError, FilingFetchError

logger = logging.getLogger(__name__)

# Base URLs — defined once so tests and production code reference the same constants.
_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# Retry configuration
_MAX_RETRIES = 3
_RETRY_STATUS_CODES = {429, 503}
_INITIAL_BACKOFF = 1.0  # seconds; doubles on each retry


class _SlidingWindowRateLimiter:
    """Enforces a maximum number of requests per one-second sliding window.

    Callers await ``acquire()`` before each HTTP request.  If the window is
    saturated, ``acquire()`` sleeps until the oldest request in the window
    expires.  The internal lock serialises concurrent callers so no two
    coroutines mutate ``_call_times`` simultaneously.
    """

    def __init__(self, max_calls: int, period: float = 1.0) -> None:
        self._max_calls = max_calls
        self._period = period
        self._call_times: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._period
            self._call_times = [t for t in self._call_times if t > cutoff]

            if len(self._call_times) >= self._max_calls:
                # Sleep until the oldest call exits the window
                wait = (self._call_times[0] + self._period) - now
                if wait > 0:
                    await asyncio.sleep(wait)
                # Re-trim after waking
                now = time.monotonic()
                self._call_times = [t for t in self._call_times if t > now - self._period]

            self._call_times.append(time.monotonic())


def _accession_no_dashes(accession_number: str) -> str:
    """Convert '0000320193-24-000123' → '000032019324000123' for URL construction."""
    return accession_number.replace("-", "")


def _cik_as_int_str(cik: str) -> str:
    """Convert zero-padded '0000320193' → '320193' for EDGAR archive URLs."""
    return str(int(cik))


class EdgarClient:
    """Async HTTP client for SEC EDGAR APIs.

    All outgoing requests carry the required User-Agent header and are subject
    to the sliding-window rate limiter.  Transient 429/503 responses are
    retried with exponential backoff up to ``_MAX_RETRIES`` times.
    """

    def __init__(self) -> None:
        self._user_agent = f"Going Concern Tracker {settings.sec_user_agent_email}"
        self._rate_limiter = _SlidingWindowRateLimiter(settings.sec_rate_limit_rps)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self._user_agent},
            timeout=30.0,
            follow_redirects=True,
        )

    # ── async context manager support ──────────────────────────────────────

    async def __aenter__(self) -> "EdgarClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── internal HTTP primitive ─────────────────────────────────────────────

    async def _get(self, url: str) -> httpx.Response:
        """GET ``url`` with rate limiting and exponential-backoff retries."""
        backoff = _INITIAL_BACKOFF
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            await self._rate_limiter.acquire()
            try:
                response = await self._client.get(url)
                logger.info("GET %s → %d", url, response.status_code)

                if response.status_code in _RETRY_STATUS_CODES:
                    if attempt < _MAX_RETRIES:
                        wait = backoff * (2**attempt)
                        logger.warning(
                            "HTTP %d from %s; retrying in %.1fs (attempt %d/%d)",
                            response.status_code,
                            url,
                            wait,
                            attempt + 1,
                            _MAX_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise EdgarError(
                        f"HTTP {response.status_code} from {url} after {_MAX_RETRIES} retries"
                    )

                response.raise_for_status()
                return response

            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = backoff * (2**attempt)
                    logger.warning(
                        "Request error fetching %s: %s; retrying in %.1fs",
                        url,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise EdgarError(
                        f"Request failed for {url} after {_MAX_RETRIES} retries: {exc}"
                    ) from exc

        raise EdgarError(
            f"Exhausted {_MAX_RETRIES} retries for {url}"
        ) from last_exc

    # ── public API methods ──────────────────────────────────────────────────

    async def get_ticker_cik_map(self) -> dict[str, str]:
        """Fetch the SEC's complete ticker→CIK mapping.

        Source: https://www.sec.gov/files/company_tickers.json
        Returns a dict mapping UPPERCASE ticker → 10-digit zero-padded CIK string.
        """
        response = await self._get(_TICKER_CIK_URL)
        raw: dict[str, dict[str, Any]] = response.json()
        # The JSON keys are ordinal strings ("0", "1", …); values have cik_str + ticker.
        return {
            entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
            for entry in raw.values()
        }

    async def get_company_submissions(self, cik: str) -> dict[str, Any]:
        """Fetch submission history for a company from the EDGAR submissions API.

        Source: https://data.sec.gov/submissions/CIK{cik}.json
        ``cik`` must be the 10-digit zero-padded form.
        """
        url = _SUBMISSIONS_URL.format(cik=cik)
        response = await self._get(url)
        return response.json()  # type: ignore[return-value]

    async def get_filing_index(self, cik: str, accession_number: str) -> dict[str, Any]:
        """Fetch the filing index JSON for a specific accession number.

        Source: EDGAR archives /{cik}/{accession_no_dashes}/{accession_no_dashes}-index.json
        Returns a dict with 'directory' and 'items' keys listing all documents.
        """
        cik_int = _cik_as_int_str(cik)
        acc = _accession_no_dashes(accession_number)
        url = f"{_ARCHIVES_BASE}/{cik_int}/{acc}/{acc}-index.json"
        response = await self._get(url)
        return response.json()  # type: ignore[return-value]

    async def get_filing_document(
        self, cik: str, accession_number: str, primary_doc: str
    ) -> str:
        """Fetch the raw HTML of the primary filing document.

        Constructs the canonical EDGAR archive URL:
          https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_dashes}/{primary_doc}
        """
        cik_int = _cik_as_int_str(cik)
        acc = _accession_no_dashes(accession_number)
        url = f"{_ARCHIVES_BASE}/{cik_int}/{acc}/{primary_doc}"
        try:
            response = await self._get(url)
            return response.text
        except EdgarError as exc:
            raise FilingFetchError(accession_number, str(exc)) from exc
