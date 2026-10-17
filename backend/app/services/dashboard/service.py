"""The owner dashboard's "Your agent this week": proof of what the agent did, from two aggregate queries.

Ranges are business-local: ``today`` runs from the account's local midnight to now,
``7d`` / ``30d`` are the rolling last 7 / 30 days. Outbound numbers (confirmation and
reminder calls) are only computed for accounts that place outbound calls.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone, tzinfo
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.flows.closures import from_config
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND
from app.flows.timefmt import business_tz
from app.schemas.dashboard import RANGES, DashboardSummary, OutboundSummary
from app.services.dashboard.hours import PEOPLE_KINDS, working_hours
from app.services.dashboard.queries import call_stats, ran_outbound, record_stats

#: How far back an outbound call still marks the account as one that places them.
OUTBOUND_LOOKBACK = timedelta(days=90)
_DAYS = {"7d": 7, "30d": 30}


def range_bounds(key: str, tz: tzinfo, now: datetime | None = None) -> tuple[datetime, datetime]:
    """[start, end) of a range key in the business's time zone (``end`` = now)."""
    if key not in RANGES:
        raise ValueError(f"unknown range: {key}")
    end = (now or datetime.now(timezone.utc)).astimezone(tz)
    if key == "today":
        return datetime.combine(end.date(), time.min, tzinfo=tz), end
    return end - timedelta(days=_DAYS[key]), end


def zone_name(merchant: Any) -> str:
    """The account's IANA zone as Postgres knows it ("UTC" when unset or unknown)."""
    from app.services.context_service import merchant_timezone

    return str(getattr(business_tz(merchant_timezone(merchant)), "key", "") or "UTC")


def inbound_first(vertical: Any) -> bool:
    return vertical.key != "ecommerce" and DIRECTION_INBOUND in vertical.directions


async def runs_outbound(db: AsyncSession, merchant: Any, vertical: Any, now: datetime) -> bool:
    """Order confirmations always; otherwise an account with a scheduled call run or a recent outbound call."""
    if DIRECTION_OUTBOUND not in vertical.directions:
        return False
    if vertical.key == "ecommerce" or getattr(merchant, "auto_call_at", None) is not None:
        return True
    return bool(await db.scalar(ran_outbound(merchant.id, now - OUTBOUND_LOOKBACK)))


def _int(value: Any) -> int:
    return int(value or 0)


def _avg(value: Any) -> int:
    return int(round(float(value))) if value is not None else 0


def _money(value: Any) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01")))


async def summary(db: AsyncSession, merchant: Any, range_key: str, *, now: datetime | None = None) -> DashboardSummary:
    from app.services.context_service import load_catalog
    from app.services.order_service import order_stats
    from app.verticals import vertical_for

    vertical = vertical_for(merchant)
    zone = zone_name(merchant)
    start, end = range_bounds(range_key, business_tz(zone), now)
    catalog = await load_catalog(db, merchant) if vertical.key in PEOPLE_KINDS else []
    hours, known = working_hours(vertical.key, vertical.config(merchant), catalog)
    outbound = await runs_outbound(db, merchant, vertical, end)
    closed = [
        (closure.start, closure.end)
        for closure in from_config(getattr(merchant, "vertical_config", None))
        if not closure.item_id and closure.end >= start.date() and closure.start <= end.date()
    ]

    calls = (await db.execute(call_stats(merchant.id, start, end, tz=zone, hours=hours, outbound=outbound, closed=closed))).one()
    records = (await db.execute(record_stats(merchant.id, start, end))).one()
    out = None
    if outbound:
        out = OutboundSummary(
            calls=_int(calls.out_calls),
            confirmed=_int(calls.out_confirmed),
            cancelled=_int(calls.out_cancelled),
            no_answer=_int(calls.out_no_answer),
            rescheduled=_int(calls.out_rescheduled),
            needs_review=_int(calls.out_needs_review),
            statuses=await order_stats(db, merchant.id),
        )
    return DashboardSummary(
        range=range_key,  # type: ignore[arg-type]
        start=start,
        end=end,
        timezone=zone,
        currency=str(getattr(merchant, "currency", "") or "USD").upper(),
        inbound_first=inbound_first(vertical),
        calls_answered=_int(calls.calls_answered),
        chats_handled=_int(calls.chats_handled),
        bookings=_int(records.bookings),
        bookings_value=_money(records.bookings_value),
        messages_leads=_int(records.messages_leads),
        after_hours=_int(calls.after_hours),
        hours_known=known,
        transfers_urgent=_int(calls.transfers_urgent),
        avg_call_secs=_avg(calls.avg_secs),
        minutes_used=round(_int(calls.voice_secs) / 60.0, 1),
        outbound=out,
    )


__all__ = ["OUTBOUND_LOOKBACK", "inbound_first", "range_bounds", "runs_outbound", "summary", "zone_name"]
