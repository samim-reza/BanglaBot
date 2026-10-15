"""Busy times (in) that block booking slots: iCal links and connected Google calendars,
cached per account and served stale-while-revalidate so a call never waits on a slow
calendar server."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

import structlog

from app.core import memo
from app.core.config import get_settings
from app.flows.context import CatalogEntry
from app.models import Merchant
from app.services.calendar import common
from app.services.calendar.common import FETCH_TIMEOUT, _tz, settings_of
from app.services.calendar.google_oauth import google_available
from app.services.calendar.google_sync import google_busy
from app.services.ics import busy_intervals, merge

logger = structlog.get_logger(__name__)

#: How long a call's context build waits for busy times it has never fetched.
FIRST_FETCH_WAIT = 2.5
MAX_ICS_BYTES = 3_000_000


def _normalize_url(url: str) -> str:
    url = url.strip()
    return "https://" + url[len("webcal://"):] if url.lower().startswith("webcal://") else url


async def fetch_ics_busy(url: str, *, window_start: datetime, window_end: datetime, timezone_name: str) -> list[tuple[datetime, datetime]]:
    response = await common.http().get(_normalize_url(url), timeout=FETCH_TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    if len(response.content) > MAX_ICS_BYTES:
        raise ValueError("calendar feed too large")
    return busy_intervals(response.text, window_start=window_start, window_end=window_end, timezone_name=timezone_name)


def sources(merchant: Any, catalog: list[CatalogEntry]) -> list[tuple[str, str, str]]:
    """(key, kind, address): key "" = whole business, else a catalog item id."""
    config = settings_of(merchant)
    out: list[tuple[str, str, str]] = []
    for url in config.get("busy_ics_urls") or []:
        if str(url).strip():
            out.append(("", "ics", str(url).strip()))
    for item in catalog:
        if item.get("calendar_ics"):
            out.append((item.id, "ics", str(item.get("calendar_ics"))))
    google = config.get("google") or {}
    if google.get("refresh_token_enc") and google_available():
        if google.get("check_busy", True):
            out.append(("", "google", str(google.get("calendar_id") or "primary")))
        for item in catalog:
            if item.get("google_calendar_id"):
                out.append((item.id, "google", str(item.get("google_calendar_id"))))
    return out


async def _load_busy(merchant: Merchant, catalog: list[CatalogEntry], days: int) -> dict[str, list[tuple[datetime, datetime]]]:
    tz = _tz(merchant)
    now = datetime.now(tz)
    window_start, window_end = now - timedelta(days=1), now + timedelta(days=days + 1)
    busy: dict[str, list[tuple[datetime, datetime]]] = {}

    async def one(key: str, kind: str, address: str) -> None:
        try:
            if kind == "ics":
                found = await fetch_ics_busy(address, window_start=window_start, window_end=window_end, timezone_name=str(tz))
            else:
                found = await google_busy(merchant, address, window_start=window_start, window_end=window_end)
        except Exception as exc:  # noqa: BLE001 — one broken calendar must not block booking
            await logger.awarning("calendar_busy_fetch_failed", merchant_id=merchant.id, kind=kind, error=str(exc)[:200])
            return
        busy.setdefault(key, []).extend(found)

    await asyncio.gather(*(one(*source) for source in sources(merchant, catalog)))
    return {key: merge(value) for key, value in busy.items()}


async def busy_for(merchant: Merchant, catalog: list[CatalogEntry], *, days: int) -> dict[str, list[tuple[datetime, datetime]]]:
    """Busy times for a call's context — cached, stale-while-revalidate."""
    if not sources(merchant, catalog):
        return {}
    ttl = max(30, int(get_settings().calendar_busy_cache_seconds))
    key = f"busy:{merchant.id}"
    cached = memo.get(key)
    if cached is not None:
        fetched_at, value = cached
        if time.monotonic() - fetched_at > ttl and not memo.get(f"{key}:refreshing"):
            memo.put(f"{key}:refreshing", True, ttl=30)
            asyncio.create_task(_refresh(merchant, catalog, days, key))
        return value
    task = asyncio.create_task(_refresh(merchant, catalog, days, key))
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=FIRST_FETCH_WAIT)
    except asyncio.TimeoutError:
        # Too slow for a live call: book without it this time; the cache fills in the background.
        return {}


async def _refresh(merchant: Merchant, catalog: list[CatalogEntry], days: int, key: str) -> dict[str, list[tuple[datetime, datetime]]]:
    value = await _load_busy(merchant, catalog, days)
    memo.put(key, (time.monotonic(), value), ttl=24 * 3600)
    memo.drop(f"{key}:refreshing")
    return value


def invalidate_busy(merchant_id: str) -> None:
    memo.drop(f"busy:{merchant_id}")
