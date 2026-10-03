"""Calendar sync, both directions.

**Out — bookings into the business's calendar**

- *Calendar feed* (no setup): ``/api/public/calendar/{token}.ics`` (whole account)
  or ``…?item={catalog_item_id}`` (one doctor) — subscribe from Google Calendar,
  Outlook or Apple Calendar ("add calendar from URL").
- *Google Calendar* (optional, OAuth): every booking / move / cancellation is
  written to the chosen calendar (a doctor's own calendar if mapped) within
  seconds, tagged with the record id so we never mistake it for a busy time.

**In — busy times that block booking slots**

- iCal links: the account's (``calendar_settings.busy_ics_urls``) and each
  doctor's (``catalog item data.calendar_ics``).
- Google: the connected calendar(s), via ``events.list`` (our own events skipped).

Busy times are cached per account (``CALENDAR_BUSY_CACHE_SECONDS``) and served
stale-while-revalidate, so a call never waits on a slow calendar server.
"""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from app.core import memo
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.regions import region_of
from app.core.security import sign_token, verify_token
from app.db.session import AsyncSessionLocal
from app.flows.context import CatalogEntry
from app.flows.timefmt import business_tz, parse_time
from app.models import CatalogItem, Merchant, Order, OrderStatus
from app.services.ics import FeedEvent, build_calendar, busy_intervals, merge
from app.voice.llm import shared_client

logger = structlog.get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_API = "https://www.googleapis.com/calendar/v3"
GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/calendar"
#: Private extended property our events carry (so busy-time reads skip them).
EVENT_TAG = "agent_record"
LIVE = (OrderStatus.pending, OrderStatus.calling, OrderStatus.confirmed)
FETCH_TIMEOUT = 6.0
#: How long a call's context build waits for busy times it has never fetched.
FIRST_FETCH_WAIT = 2.5
MAX_ICS_BYTES = 3_000_000


def http() -> httpx.AsyncClient:
    """The HTTP client (module-level so tests can swap in a mock transport)."""
    return shared_client()


def settings_of(merchant: Any) -> dict[str, Any]:
    stored = getattr(merchant, "calendar_settings", None)
    return dict(stored) if isinstance(stored, dict) else {}


def _tz(merchant: Any):
    return business_tz(getattr(merchant, "timezone", "") or region_of(merchant).timezone)


# ============================================================================ feed (out)
def new_token() -> str:
    return secrets.token_urlsafe(24)


def _duration_minutes(record: Order, merchant: Merchant, item: CatalogItem | None) -> int:
    vertical = getattr(merchant, "vertical", "")
    config = getattr(merchant, "vertical_config", None) or {}
    if vertical == "clinic" and item is not None:
        return int((item.data or {}).get("slot_minutes") or 20)
    if vertical == "real_estate":
        return int(config.get("visit_slot_minutes") or 60)
    if vertical == "home_service":
        key = (record.details or {}).get("time_window")
        for window in config.get("time_windows") or []:
            if isinstance(window, dict) and window.get("key") == key:
                start, end = parse_time(window.get("start")), parse_time(window.get("end"))
                if start and end:
                    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        return 180
    return 60


def event_for(record: Order, merchant: Merchant, item: CatalogItem | None) -> FeedEvent:
    start = record.scheduled_at
    assert start is not None
    end = start + timedelta(minutes=max(15, _duration_minutes(record, merchant, item)))
    details = dict(record.details or {})
    item_name = item.name if item is not None else ""
    if record.kind == "appointment":
        summary = f"{record.customer_name} · {item_name}" if item_name else record.customer_name
    elif record.kind == "booking":
        summary = f"{item_name or record.items_summary} · {record.customer_name}"
    elif record.kind == "lead":
        summary = f"Viewing · {record.customer_name}" + (f" · {item_name}" if item_name else "")
    else:
        summary = record.customer_name
    lines = [f"Phone: {record.customer_phone}"]
    for key, label in (("serial", "Queue no."), ("reason", "Reason"), ("problem", "Problem"), ("budget", "Budget"), ("lead_score", "Lead")):
        if details.get(key):
            lines.append(f"{label}: {details[key]}")
    if record.notes:
        lines.append(record.notes)
    lines.append(f"Status: {record.status.value if hasattr(record.status, 'value') else record.status}")
    return FeedEvent(
        uid=f"{record.id}@voice-agent",
        start=start,
        end=end,
        summary=summary,
        description="\n".join(lines),
        location=record.address or "",
        status="CONFIRMED" if record.status == OrderStatus.confirmed else "TENTATIVE",
        updated=record.updated_at,
    )


async def feed(token: str, item_id: str | None = None) -> tuple[str, str] | None:
    """(file name, iCalendar text) for a feed token, or None if unknown."""
    if not token or len(token) > 64:
        return None
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        merchant = await session.scalar(select(Merchant).where(Merchant.calendar_token == token))
        if merchant is None or not merchant.active:
            return None
        now = datetime.now(timezone.utc)
        stmt = select(Order).where(
            Order.merchant_id == merchant.id,
            Order.scheduled_at.is_not(None),
            Order.scheduled_at >= now - timedelta(days=30),
            Order.scheduled_at <= now + timedelta(days=180),
            Order.status.in_(LIVE),
        )
        if item_id:
            stmt = stmt.where(Order.catalog_item_id == item_id)
        records = list(await session.scalars(stmt.order_by(Order.scheduled_at)))
        item_ids = {r.catalog_item_id for r in records if r.catalog_item_id} | ({item_id} if item_id else set())
        items = {i.id: i for i in await session.scalars(select(CatalogItem).where(CatalogItem.id.in_(item_ids)))} if item_ids else {}
    name = merchant.business_name
    if item_id and item_id in items:
        name = f"{merchant.business_name} — {items[item_id].name}"
    events = [event_for(r, merchant, items.get(r.catalog_item_id or "")) for r in records]
    return f"{merchant.username}.ics", build_calendar(name, events, timezone_name=str(_tz(merchant)))


# ============================================================================ busy (in)
def _normalize_url(url: str) -> str:
    url = url.strip()
    return "https://" + url[len("webcal://"):] if url.lower().startswith("webcal://") else url


async def fetch_ics_busy(url: str, *, window_start: datetime, window_end: datetime, timezone_name: str) -> list[tuple[datetime, datetime]]:
    response = await http().get(_normalize_url(url), timeout=FETCH_TIMEOUT, follow_redirects=True)
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


# ============================================================================ Google
def google_available() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    settings = get_settings()
    if settings.google_redirect_uri:
        return settings.google_redirect_uri
    base = str(settings.public_base_url or "http://localhost:8000").rstrip("/")
    return f"{base}/api/integrations/google/callback"


def auth_url(merchant_id: str) -> str:
    settings = get_settings()
    state = sign_token({"typ": "google_oauth", "mid": merchant_id, "n": secrets.token_hex(6)}, ttl_seconds=900)
    query = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(query)}"


def merchant_from_state(state: str) -> str:
    payload = verify_token(state)
    if payload.get("typ") != "google_oauth" or not payload.get("mid"):
        raise ValueError("bad state")
    return str(payload["mid"])


def _email_from_id_token(id_token: str) -> str:
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("email") or "")
    except (IndexError, ValueError):
        return ""


async def exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    response = await http().post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=FETCH_TIMEOUT,
    )
    if response.status_code != 200:
        raise ValueError(f"google_token_exchange_{response.status_code}: {response.text[:200]}")
    data = response.json()
    if not data.get("refresh_token"):
        raise ValueError("Google did not return a refresh token — remove the app's access in your Google account and connect again.")
    return {
        "refresh_token_enc": encrypt(str(data["refresh_token"])),
        "email": _email_from_id_token(str(data.get("id_token") or "")),
        "calendar_id": "primary",
        "check_busy": True,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "_access_token": str(data.get("access_token") or ""),
        "_expires_in": int(data.get("expires_in") or 3600),
    }


async def access_token(merchant: Merchant) -> str:
    google = settings_of(merchant).get("google") or {}
    refresh = decrypt(str(google.get("refresh_token_enc") or ""))
    if not refresh:
        raise PermissionError("Google Calendar is not connected")
    key = f"gtoken:{merchant.id}"
    cached = memo.get(key)
    if cached:
        return str(cached)
    settings = get_settings()
    response = await http().post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
        timeout=FETCH_TIMEOUT,
    )
    if response.status_code != 200:
        raise PermissionError(f"google_token_refresh_{response.status_code}: {response.text[:160]}")
    data = response.json()
    token = str(data["access_token"])
    memo.put(key, token, ttl=max(60, int(data.get("expires_in") or 3600) - 120))
    return token


async def _google(merchant: Merchant, method: str, path: str, **kwargs: Any) -> httpx.Response:
    token = await access_token(merchant)
    response = await http().request(
        method, f"{GOOGLE_API}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=FETCH_TIMEOUT, **kwargs
    )
    if response.status_code == 401:
        memo.drop(f"gtoken:{merchant.id}")
    return response


async def list_calendars(merchant: Merchant) -> list[dict[str, Any]]:
    response = await _google(merchant, "GET", "/users/me/calendarList", params={"minAccessRole": "writer", "maxResults": 100})
    response.raise_for_status()
    return [
        {"id": item.get("id"), "name": item.get("summaryOverride") or item.get("summary") or item.get("id"), "primary": bool(item.get("primary"))}
        for item in response.json().get("items", [])
    ]


def _google_time(value: dict[str, Any], tz: Any) -> datetime | None:
    if value.get("dateTime"):
        return datetime.fromisoformat(str(value["dateTime"]).replace("Z", "+00:00"))
    if value.get("date"):
        return datetime.fromisoformat(str(value["date"])).replace(tzinfo=tz)
    return None


async def google_busy(merchant: Merchant, calendar_id: str, *, window_start: datetime, window_end: datetime) -> list[tuple[datetime, datetime]]:
    """Busy times in a Google calendar — events we created ourselves are not busy times."""
    tz = _tz(merchant)
    intervals: list[tuple[datetime, datetime]] = []
    page_token = ""
    for _ in range(10):
        params: dict[str, Any] = {
            "timeMin": window_start.astimezone(timezone.utc).isoformat(),
            "timeMax": window_end.astimezone(timezone.utc).isoformat(),
            "singleEvents": "true",
            "maxResults": 250,
            "fields": "items(status,transparency,start,end,extendedProperties),nextPageToken",
        }
        if page_token:
            params["pageToken"] = page_token
        response = await _google(merchant, "GET", f"/calendars/{_quote(calendar_id)}/events", params=params)
        response.raise_for_status()
        data = response.json()
        for event in data.get("items", []):
            if event.get("status") == "cancelled" or event.get("transparency") == "transparent":
                continue
            if ((event.get("extendedProperties") or {}).get("private") or {}).get(EVENT_TAG):
                continue
            start, end = _google_time(event.get("start") or {}, tz), _google_time(event.get("end") or {}, tz)
            if start and end and end > start:
                intervals.append((start, end))
        page_token = str(data.get("nextPageToken") or "")
        if not page_token:
            break
    return merge(intervals)


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def google_event_body(record: Order, merchant: Merchant, item: CatalogItem | None) -> dict[str, Any]:
    event = event_for(record, merchant, item)
    tz = str(_tz(merchant))
    return {
        "summary": event.summary,
        "description": event.description,
        "location": event.location or None,
        "start": {"dateTime": event.start.isoformat(), "timeZone": tz},
        "end": {"dateTime": event.end.isoformat(), "timeZone": tz},
        "status": "confirmed" if record.status == OrderStatus.confirmed else "tentative",
        "extendedProperties": {"private": {EVENT_TAG: record.id}},
        "reminders": {"useDefault": True},
    }


async def sync_record(record_id: str) -> None:
    """Mirror one record into the connected Google calendar (create / update / delete)."""
    if not google_available():
        return
    try:
        async with AsyncSessionLocal() as session:
            record = await session.get(Order, record_id)
            if record is None:
                return
            merchant = await session.get(Merchant, record.merchant_id)
            if merchant is None:
                return
            google = settings_of(merchant).get("google") or {}
            if not google.get("refresh_token_enc"):
                return
            item = await session.get(CatalogItem, record.catalog_item_id) if record.catalog_item_id else None
            details = dict(record.details or {})
            event_id = str(details.get("google_event_id") or "")
            # A doctor's own calendar if mapped, else the account's; an existing
            # event stays in the calendar it was created in.
            item_calendar = str((item.data or {}).get("google_calendar_id") or "") if item is not None else ""
            calendar_id = item_calendar or str(google.get("calendar_id") or "primary")
            if event_id and details.get("google_calendar_id"):
                calendar_id = str(details["google_calendar_id"])
            live = record.scheduled_at is not None and record.status in LIVE
            if live:
                body = google_event_body(record, merchant, item)
                if event_id:
                    response = await _google(merchant, "PATCH", f"/calendars/{_quote(calendar_id)}/events/{_quote(event_id)}", json=body)
                    if response.status_code == 404:
                        event_id = ""
                if not event_id:
                    response = await _google(merchant, "POST", f"/calendars/{_quote(calendar_id)}/events", json=body)
                response.raise_for_status()
                details["google_event_id"] = str(response.json().get("id") or event_id)
                details["google_calendar_id"] = calendar_id
            elif event_id:
                response = await _google(merchant, "DELETE", f"/calendars/{_quote(calendar_id)}/events/{_quote(event_id)}")
                if response.status_code not in (200, 204, 404, 410):
                    response.raise_for_status()
                details.pop("google_event_id", None)
                details.pop("google_calendar_id", None)
            else:
                return
            record.details = details
            await session.commit()
        await logger.ainfo("google_calendar_synced", record_id=record_id, live=live)
    except Exception as exc:  # noqa: BLE001 — calendar trouble never breaks bookings
        await logger.awarning("google_calendar_sync_failed", record_id=record_id, error=str(exc)[:200])


async def delete_event(merchant: Merchant, details: dict[str, Any]) -> None:
    """Remove a deleted record's event (the record row itself is gone)."""
    event_id = str(details.get("google_event_id") or "")
    if not event_id or not google_available():
        return
    calendar_id = str(details.get("google_calendar_id") or "primary")
    try:
        await _google(merchant, "DELETE", f"/calendars/{_quote(calendar_id)}/events/{_quote(event_id)}")
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("google_calendar_delete_failed", error=str(exc)[:200])


async def revoke(merchant: Merchant) -> None:
    google = settings_of(merchant).get("google") or {}
    refresh = decrypt(str(google.get("refresh_token_enc") or ""))
    memo.drop(f"gtoken:{merchant.id}")
    if refresh:
        try:
            await http().post(GOOGLE_REVOKE_URL, data={"token": refresh}, timeout=FETCH_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 — disconnect locally regardless
            await logger.ainfo("google_revoke_failed", error=str(exc)[:160])


__all__ = [
    "EVENT_TAG",
    "auth_url",
    "busy_for",
    "event_for",
    "exchange_code",
    "feed",
    "google_available",
    "google_busy",
    "google_event_body",
    "invalidate_busy",
    "list_calendars",
    "merchant_from_state",
    "new_token",
    "redirect_uri",
    "revoke",
    "settings_of",
    "sources",
    "sync_record",
]
