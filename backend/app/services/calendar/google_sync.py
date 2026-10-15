"""Google Calendar API: list calendars, read busy times (skipping our own events), and
mirror each booking / move / cancellation into the chosen calendar."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.core import memo
from app.db.session import AsyncSessionLocal
from app.models import CatalogItem, Merchant, Order, OrderStatus
from app.services.calendar import common
from app.services.calendar.common import EVENT_TAG, FETCH_TIMEOUT, LIVE, _tz, settings_of
from app.services.calendar.ics_feed import event_for
from app.services.calendar.google_oauth import access_token, google_available
from app.services.ics import merge

logger = structlog.get_logger(__name__)

GOOGLE_API = "https://www.googleapis.com/calendar/v3"


async def _google(merchant: Merchant, method: str, path: str, **kwargs: Any) -> httpx.Response:
    token = await access_token(merchant)
    response = await common.http().request(
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
