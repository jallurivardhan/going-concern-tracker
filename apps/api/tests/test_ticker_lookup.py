"""Tests for ticker_lookup.py — CIK resolution with cached and fresh maps."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import gct.ingestion.ticker_lookup as tlu
from gct.ingestion.exceptions import TickerNotFoundError
from gct.ingestion.ticker_lookup import _clear_ticker_cache, resolve_ticker_to_cik


# Reset the cache before and after every test to prevent cross-test pollution
@pytest.fixture(autouse=True)
def reset_cache() -> None:
    _clear_ticker_cache()
    yield
    _clear_ticker_cache()


def _mock_client(cik_map: dict[str, str]) -> MagicMock:
    """Return a mock EdgarClient whose get_ticker_cik_map() returns ``cik_map``."""
    client = MagicMock()
    client.get_ticker_cik_map = AsyncMock(return_value=cik_map)
    return client


# ── basic resolution ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolves_uppercase_ticker_to_cik() -> None:
    """AAPL resolves to the expected 10-digit zero-padded CIK."""
    client = _mock_client({"AAPL": "0000320193", "MSFT": "0000789019"})

    cik = await resolve_ticker_to_cik("aapl", client)  # lowercase input

    assert cik == "0000320193"
    client.get_ticker_cik_map.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolves_ticker_already_uppercase() -> None:
    client = _mock_client({"TSLA": "0001318605"})
    cik = await resolve_ticker_to_cik("TSLA", client)
    assert cik == "0001318605"


# ── cache behaviour ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_second_call_uses_cache_no_network() -> None:
    """A second lookup must not make another network call."""
    client = _mock_client({"AAPL": "0000320193"})

    await resolve_ticker_to_cik("AAPL", client)  # populates cache
    await resolve_ticker_to_cik("AAPL", client)  # should use cache

    client.get_ticker_cik_map.assert_awaited_once()


@pytest.mark.asyncio
async def test_returns_none_for_unknown_ticker_with_cached_map() -> None:
    """When the cache is already populated, an unknown ticker returns None (no re-fetch)."""
    client = _mock_client({"AAPL": "0000320193"})

    # Populate cache
    await resolve_ticker_to_cik("AAPL", client)
    assert tlu._ticker_cik_cache is not None

    # Unknown ticker with warm cache → None, no extra network call
    result = await resolve_ticker_to_cik("UNKNOWN_TICKER_XYZ", client)

    assert result is None
    client.get_ticker_cik_map.assert_awaited_once()  # still only one call


# ── fresh-fetch miss raises ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_raises_after_fresh_fetch_miss() -> None:
    """Unknown ticker causes TickerNotFoundError when fetched fresh (empty cache)."""
    client = _mock_client({})  # fresh fetch returns empty map

    with pytest.raises(TickerNotFoundError) as exc_info:
        await resolve_ticker_to_cik("GHOST", client)

    assert "GHOST" in str(exc_info.value)
    client.get_ticker_cik_map.assert_awaited_once()


@pytest.mark.asyncio
async def test_raises_includes_ticker_in_error() -> None:
    """TickerNotFoundError must include the offending ticker in its message."""
    client = _mock_client({"REAL": "0001234567"})

    with pytest.raises(TickerNotFoundError) as exc_info:
        await resolve_ticker_to_cik("FAKE_123", client)

    assert "FAKE_123" in str(exc_info.value)


# ── cache clear ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_cache_forces_fresh_fetch() -> None:
    """After clearing the cache, the next lookup must hit the network again."""
    client = _mock_client({"AAPL": "0000320193"})

    await resolve_ticker_to_cik("AAPL", client)   # 1st fetch
    _clear_ticker_cache()
    await resolve_ticker_to_cik("AAPL", client)   # 2nd fetch after clear

    assert client.get_ticker_cik_map.await_count == 2
