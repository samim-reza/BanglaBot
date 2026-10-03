"""Builds a :class:`~app.flows.context.CallContext` from the database.

Three read-only queries, run while the phone rings (outbound), in the inbound
webhook, or when a test call opens — never on the answer path:

- the account's active catalog (doctors / listings / services) with short refs;
- the booking snapshot: live records per slot over the booking horizon;
- for inbound calls, the caller's own upcoming records (by phone number).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import memo
from app.core.regions import normalize_phone, region_of
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.scheduling import slot_key
from app.flows.timefmt import business_tz, local_now
from app.models import CatalogItem, Merchant, Order, OrderStatus
from app.verticals import vertical_for

#: Statuses whose scheduled time is still taken.
LIVE_STATUSES = (OrderStatus.pending, OrderStatus.calling, OrderStatus.confirmed)
REF_PREFIX = {"doctor": "D", "property": "P", "service": "S"}


def merchant_timezone(merchant: Merchant) -> str:
    return str(getattr(merchant, "timezone", "") or region_of(merchant).timezone)


async def load_catalog(db: AsyncSession, merchant: Merchant) -> list[CatalogEntry]:
    vertical = vertical_for(merchant)
    if not vertical.catalog_kind:
        return []
    cached = memo.get(f"catalog:{merchant.id}")
    if cached is not None:
        return list(cached)
    rows = await db.scalars(
        select(CatalogItem)
        .where(CatalogItem.merchant_id == merchant.id, CatalogItem.kind == vertical.catalog_kind, CatalogItem.active.is_(True))
        .order_by(CatalogItem.sort_order, CatalogItem.created_at)
    )
    prefix = REF_PREFIX.get(vertical.catalog_kind, "I")
    entries = [
        CatalogEntry(id=row.id, ref=f"{prefix}{index}", kind=row.kind, name=row.name, data=dict(row.data or {}))
        for index, row in enumerate(rows, start=1)
    ]
    memo.put(f"catalog:{merchant.id}", entries)
    return list(entries)


def invalidate_catalog(merchant_id: str) -> None:
    memo.drop(f"catalog:{merchant_id}")


async def load_live_records(db: AsyncSession, merchant: Merchant, *, days: int) -> list[Order]:
    """Every live scheduled record from yesterday to the end of the booking horizon —
    ONE query that feeds both the booking snapshot and the caller's own records."""
    now = local_now(business_tz(merchant_timezone(merchant)))
    rows = await db.scalars(
        select(Order).where(
            Order.merchant_id == merchant.id,
            Order.scheduled_at.is_not(None),
            Order.scheduled_at >= now - timedelta(days=1),
            Order.scheduled_at <= now + timedelta(days=days + 1),
            Order.status.in_(LIVE_STATUSES),
        )
    )
    return list(rows)


def booked_index(records: list[Order]) -> dict[str, int]:
    """slot key → live bookings, counted per resource AND account-wide (shared capacity)."""
    booked: dict[str, int] = {}
    for row in records:
        if row.scheduled_at is None:
            continue
        for key in {slot_key(row.catalog_item_id, row.scheduled_at), slot_key(None, row.scheduled_at)}:
            booked[key] = booked.get(key, 0) + 1
    return booked


def caller_records(records: list[Order], merchant: Merchant, caller_number: str) -> list[Order]:
    if not caller_number:
        return []
    region = region_of(merchant)
    target = normalize_phone(caller_number, region)
    now = local_now(business_tz(merchant_timezone(merchant)))
    mine = [
        row for row in records
        if row.scheduled_at is not None and row.scheduled_at >= now - timedelta(hours=2)
        and normalize_phone(row.customer_phone, region) == target
    ]
    return sorted(mine, key=lambda row: row.scheduled_at)[:5]


async def load_booked(db: AsyncSession, merchant: Merchant, *, days: int) -> dict[str, int]:
    """slot key → live bookings, counted per resource AND account-wide (shared capacity)."""
    now = local_now(business_tz(merchant_timezone(merchant)))
    rows = await db.execute(
        select(Order.catalog_item_id, Order.scheduled_at).where(
            Order.merchant_id == merchant.id,
            Order.scheduled_at.is_not(None),
            Order.scheduled_at >= now - timedelta(days=1),
            Order.scheduled_at <= now + timedelta(days=days + 1),
            Order.status.in_(LIVE_STATUSES),
        )
    )
    booked: dict[str, int] = {}
    for item_id, start in rows:
        keys = {slot_key(item_id, start), slot_key(None, start)}
        for key in keys:
            booked[key] = booked.get(key, 0) + 1
    return booked


async def load_caller_records(db: AsyncSession, merchant: Merchant, caller_number: str) -> list[Order]:
    """The caller's open records (upcoming appointments / bookings), soonest first."""
    if not caller_number:
        return []
    region = region_of(merchant)
    target = normalize_phone(caller_number, region)
    now = local_now(business_tz(merchant_timezone(merchant)))
    rows = await db.scalars(
        select(Order)
        .where(
            Order.merchant_id == merchant.id,
            Order.status.in_(LIVE_STATUSES),
            or_(Order.scheduled_at.is_(None), Order.scheduled_at >= now - timedelta(hours=2)),
        )
        .order_by(Order.scheduled_at.asc().nulls_last())
        .limit(300)
    )
    return [row for row in rows if normalize_phone(row.customer_phone, region) == target][:5]


async def build_context(
    db: AsyncSession,
    merchant: Merchant,
    *,
    record: Any | None = None,
    direction: str,
    caller_number: str = "",
    test: bool = False,
) -> CallContext:
    vertical = vertical_for(merchant)
    horizon = int(vertical.config(merchant).get("booking_horizon_days") or 14)
    catalog = await load_catalog(db, merchant)
    booked: dict[str, int] = {}
    callers: list[Order] = []
    busy: dict = {}
    if vertical.scheduled:
        from app.services import calendar_service

        live = await load_live_records(db, merchant, days=max(horizon, 30))
        booked = booked_index(live)
        if direction == DIRECTION_INBOUND:
            callers = caller_records(live, merchant, caller_number)
        busy = await calendar_service.busy_for(merchant, catalog, days=horizon)
    return CallContext(
        merchant=merchant,
        record=record,
        direction=direction,
        caller_number=caller_number,
        catalog=catalog,
        booked=booked,
        busy=busy,
        caller_records=callers,
        now=local_now(business_tz(merchant_timezone(merchant))),
        test=test,
    )


__all__ = [
    "booked_index",
    "build_context",
    "caller_records",
    "invalidate_catalog",
    "load_booked",
    "load_caller_records",
    "load_catalog",
    "load_live_records",
    "merchant_timezone",
]
