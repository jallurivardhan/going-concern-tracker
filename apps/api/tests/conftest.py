"""Shared pytest configuration for the gct test suite."""

from __future__ import annotations

import pytest

import gct.ingestion.ticker_lookup as tlu


@pytest.fixture(autouse=True)
def isolate_ticker_cache() -> None:
    """Clear the in-process ticker→CIK cache before and after every test.

    Without this, a test that populates the cache would silently affect
    subsequent tests that expect a fresh fetch.
    """
    tlu._clear_ticker_cache()
    yield
    tlu._clear_ticker_cache()
