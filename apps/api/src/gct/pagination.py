"""Cursor-based pagination utilities.

Design choice: keyset (cursor) pagination instead of OFFSET/LIMIT.

Rationale:
- OFFSET/LIMIT drifts under concurrent writes: inserting a row on page 1 shifts
  every subsequent page, causing items to be skipped or duplicated during traversal.
- Keyset pagination is O(1) for both the query and the cursor decode — the WHERE
  clause uses indexed columns (detected_at, id) so the query plan is the same
  regardless of which page you are on.
- Cursors are opaque to callers (base64-encoded JSON), so the encoding can change
  without breaking the API contract.

Usage:
    # Encoding (after fetching a page):
    next_cursor = encode_cursor(last_item.detected_at, str(last_item.id))

    # Decoding (before executing the next query):
    after_dt, after_id = decode_cursor(cursor_string)
"""

from __future__ import annotations

import base64
import json
from datetime import datetime


def encode_cursor(sort_key: datetime | str, item_id: str) -> str:
    """Encode a pagination cursor from the sort key and item id of the last result.

    Parameters
    ----------
    sort_key:
        The value of the sort column for the last item on the page.
        Pass a ``datetime`` for time-sorted feeds, or a ``str`` for name-sorted lists.
    item_id:
        UUID (as string) of the last item — used as a tiebreaker when sort_key
        values are equal.
    """
    if isinstance(sort_key, datetime):
        key_str = sort_key.isoformat()
    else:
        key_str = sort_key
    payload = json.dumps({"k": key_str, "id": item_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, str]:
    """Decode a cursor back to ``(sort_key_str, item_id)``.

    Both values are returned as strings.  The caller must cast ``sort_key_str``
    to the appropriate type (e.g. ``datetime.fromisoformat(sort_key_str)``).

    Raises ``ValueError`` if the cursor is malformed or base64-invalid.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return payload["k"], payload["id"]
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid pagination cursor: {cursor!r}") from exc
