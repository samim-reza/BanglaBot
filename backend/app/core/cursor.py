"""Opaque keyset-pagination cursors: ``(timestamp, id)`` of the last row on a page."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

MAX_PAGE_SIZE = 100


def encode_cursor(at: datetime, row_id: str) -> str:
    stamp = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    raw = json.dumps([stamp.isoformat(), str(row_id)], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Raises ``ValueError`` for anything that isn't a cursor we made."""
    text = str(cursor or "")
    if not text or len(text) > 200:
        raise ValueError("bad cursor")
    try:
        stamp, row_id = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)).decode("utf-8"))
        at = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("bad cursor") from exc
    if not isinstance(row_id, str) or not row_id:
        raise ValueError("bad cursor")
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)), row_id


def page_size(value: int | None, default: int = 50) -> int:
    try:
        size = int(value or default)
    except (TypeError, ValueError):
        size = default
    return max(1, min(MAX_PAGE_SIZE, size))


__all__ = ["MAX_PAGE_SIZE", "decode_cursor", "encode_cursor", "page_size"]
