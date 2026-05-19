"""CIK resolution from the SEC's ticker→CIK map.

The SEC publishes a complete JSON file mapping ticker symbols to CIK numbers.
We cache it for the lifetime of the process (typically one CLI run) to avoid
hammering the endpoint.  The cache is a plain module-level dict so it survives
across multiple calls but resets on process restart.

Source: https://www.sec.gov/files/company_tickers.json
"""

from __future__ import annotations

import logging

from gct.ingestion.edgar_client import EdgarClient
from gct.ingestion.exceptions import TickerNotFoundError

logger = logging.getLogger(__name__)

# Process-lifetime cache: UPPERCASE_TICKER → 10-digit zero-padded CIK
_ticker_cik_cache: dict[str, str] | None = None


def _clear_ticker_cache() -> None:
    """Reset the in-process cache.  Called by tests and on fresh CLI runs."""
    global _ticker_cik_cache
    _ticker_cik_cache = None


async def resolve_ticker_to_cik(ticker: str, client: EdgarClient) -> str | None:
    """Return the 10-digit zero-padded CIK for ``ticker``, or ``None`` if not found.

    Behaviour:
    - If the cache is already populated, a lookup miss returns ``None`` immediately
      (no network call is made).
    - If the cache is empty, one fetch is performed.  A miss after that fresh
      fetch raises :exc:`TickerNotFoundError` because the ticker genuinely
      doesn't exist in the SEC database.

    Args:
        ticker: Stock ticker symbol (case-insensitive).
        client: An open :class:`EdgarClient` instance.

    Returns:
        10-digit zero-padded CIK string, e.g. ``"0000320193"`` for AAPL.
        Returns ``None`` when the ticker is absent from the *cached* map.

    Raises:
        TickerNotFoundError: When the ticker is absent even after a fresh fetch.
    """
    global _ticker_cik_cache

    ticker = ticker.upper().strip()

    if _ticker_cik_cache is not None:
        # Use cached data — return None on miss (no network call)
        cik = _ticker_cik_cache.get(ticker)
        if cik is None:
            logger.warning("Ticker %s not found in cached CIK map", ticker)
        return cik

    # Cache is empty — fetch fresh data
    logger.info("Fetching SEC ticker→CIK map (cache empty)")
    _ticker_cik_cache = await client.get_ticker_cik_map()

    if ticker not in _ticker_cik_cache:
        raise TickerNotFoundError(ticker)

    return _ticker_cik_cache[ticker]
