"""Shared calendar plumbing: the HTTP client seam, the account's calendar settings,
its time zone, and the constants every direction uses."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.regions import region_of
from app.flows.timefmt import business_tz
from app.models import OrderStatus
from app.voice.llm import shared_client

#: Private extended property our events carry (so busy-time reads skip them).
EVENT_TAG = "agent_record"
LIVE = (OrderStatus.pending, OrderStatus.calling, OrderStatus.confirmed)
FETCH_TIMEOUT = 6.0


def http() -> httpx.AsyncClient:
    """The HTTP client. Callers look it up as ``common.http()`` at call time, so tests
    can swap in a mock transport here once."""
    return shared_client()


def settings_of(merchant: Any) -> dict[str, Any]:
    stored = getattr(merchant, "calendar_settings", None)
    return dict(stored) if isinstance(stored, dict) else {}


def _tz(merchant: Any):
    return business_tz(getattr(merchant, "timezone", "") or region_of(merchant).timezone)
