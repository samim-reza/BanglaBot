"""Calendar feed (out): bookings as an iCalendar feed the business subscribes to from
Google Calendar, Outlook or Apple Calendar — the whole account or one catalog item."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.db.session import AsyncSessionLocal
from app.flows.timefmt import parse_time
from app.models import CatalogItem, Merchant, Order, OrderStatus
from app.services.calendar.common import LIVE, _tz
from app.services.ics import FeedEvent, build_calendar

logger = structlog.get_logger(__name__)


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


async def merchant_for_feed_token(session: Any, token: str) -> Merchant | None:
    """The account a feed token belongs to, found by the token's peppered hash.

    Rows from before tokens were hashed still hold the plaintext: they are found by
    it once and upgraded (hash + encrypted copy, plaintext cleared) on the spot."""
    from sqlalchemy import select

    from app.core.crypto import lookup_hashes
    from app.models.merchant import CALENDAR_TOKEN_PURPOSE

    hashes = lookup_hashes(token, purpose=CALENDAR_TOKEN_PURPOSE)
    merchant = await session.scalar(select(Merchant).where(Merchant.calendar_token_hash.in_(hashes)).limit(1))
    if merchant is None:
        merchant = await session.scalar(select(Merchant).where(Merchant.calendar_token_legacy == token).limit(1))
    if merchant is not None and (merchant.calendar_token_legacy or merchant.calendar_token_hash != hashes[0]):
        merchant.calendar_token = token
        try:
            await session.commit()
        except Exception as exc:  # noqa: BLE001 — the feed still answers; the upgrade retries next time
            await session.rollback()
            await logger.awarning("calendar_token_upgrade_failed", error=str(exc)[:200])
    return merchant


async def feed(token: str, item_id: str | None = None) -> tuple[str, str] | None:
    """(file name, iCalendar text) for a feed token, or None if unknown."""
    if not token or len(token) > 64:
        return None
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        merchant = await merchant_for_feed_token(session, token)
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
