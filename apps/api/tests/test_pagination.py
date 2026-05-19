"""Tests for pagination cursor encode/decode."""

from __future__ import annotations

from datetime import datetime

import pytest

from gct.pagination import decode_cursor, encode_cursor


def test_roundtrip_datetime_cursor() -> None:
    """Encoding then decoding a datetime cursor returns the original values."""
    dt = datetime(2026, 5, 17, 19, 42, 0)
    item_id = "550e8400-e29b-41d4-a716-446655440000"
    cursor = encode_cursor(dt, item_id)
    key, decoded_id = decode_cursor(cursor)
    assert datetime.fromisoformat(key) == dt
    assert decoded_id == item_id


def test_roundtrip_string_cursor() -> None:
    """Encoding then decoding a string sort key roundtrips correctly."""
    cursor = encode_cursor("Tupperware Brands Corp", "abc-123")
    key, item_id = decode_cursor(cursor)
    assert key == "Tupperware Brands Corp"
    assert item_id == "abc-123"


def test_cursor_is_url_safe() -> None:
    """Encoded cursor must be URL-safe (no +, /, or = that break query strings)."""
    cursor = encode_cursor(datetime(2026, 1, 1), "some-uuid-here")
    assert "+" not in cursor
    assert "/" not in cursor
    # Padding = is ok in base64url but let's verify it's actually base64 decodable
    key, _ = decode_cursor(cursor)
    assert key  # non-empty


def test_decode_invalid_cursor_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Invalid pagination cursor"):
        decode_cursor("not-valid-base64!!!")


def test_different_datetimes_produce_different_cursors() -> None:
    dt1 = datetime(2026, 5, 17)
    dt2 = datetime(2025, 5, 17)
    c1 = encode_cursor(dt1, "id-1")
    c2 = encode_cursor(dt2, "id-1")
    assert c1 != c2
