"""Opening hours, order times ("as soon as possible" / a later time) and table capacity.

Tables are counted in covers (guests) per slot. The booking snapshot and the
commit lock count *reservations*, not guests, so a slot's capacity for a party
of ``n`` is ``covers // n`` reservations — exact when the tables in a slot are
about the same size, slightly generous for mixed sizes.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from app.flows.context import CallContext
from app.flows.scheduling import Availability, Window, window_from_config
from app.flows.timefmt import parse_date, parse_time
from app.verticals.common import schedule_phrase, when_phrase
from app.verticals.restaurant.config import conf, whole

ASAP = "asap"
#: How far ahead an order may be placed.
ORDER_DAYS = 7
UNLIMITED = 999


def opening_window(ctx: CallContext, *, step: int = 0, capacity: int = 1) -> Window | None:
    config = conf(ctx)
    return window_from_config(
        {
            "days": config.get("open_days") or [],
            "start": config.get("open_time"),
            "end": config.get("close_time"),
            "slot_minutes": step,
            "capacity": capacity,
        }
    )


def hours_phrase(ctx: CallContext, language: str) -> str:
    """``every day 11 AM to 10 PM`` / ``Monday to Saturday 5 PM to 11 PM``."""
    window = opening_window(ctx)
    return schedule_phrase(Availability(windows=[window]), language, ctx) if window else ""


def _bounds(window: Window, day: date, tz: Any) -> tuple[datetime, datetime]:
    return datetime.combine(day, window.start, tzinfo=tz), datetime.combine(day, window.end, tzinfo=tz)


def is_open(ctx: CallContext, at: datetime) -> bool:
    window = opening_window(ctx)
    if window is None:
        return True  # hours not set: never refuse
    if not window.open_on(at.date()):
        return False
    start, end = _bounds(window, at.date(), at.tzinfo)
    return start <= at < end


def next_opening(ctx: CallContext, after: datetime) -> datetime | None:
    window = opening_window(ctx)
    if window is None:
        return None
    for offset in range(0, 8):
        day = after.date() + timedelta(days=offset)
        if not window.open_on(day):
            continue
        start, end = _bounds(window, day, after.tzinfo)
        if after < start:
            return start
        if after < end:
            return after
    return None


# ---- orders --------------------------------------------------------------------------------------
def lead_minutes(slots: dict[str, Any], ctx: CallContext) -> int:
    config = conf(ctx)
    key = "delivery_minutes" if slots.get("fulfillment") == "delivery" else "prep_minutes"
    return max(0, whole(config.get(key), 20))


def can_do_asap(slots: dict[str, Any], ctx: CallContext) -> bool:
    assert ctx.now is not None
    window = opening_window(ctx)
    if window is None:
        return True
    ready = ctx.now + timedelta(minutes=lead_minutes(slots, ctx))
    return is_open(ctx, ctx.now) and ready <= _bounds(window, ctx.today, ctx.now.tzinfo)[1] + timedelta(minutes=30)


def parse_order_time(value: Any, ctx: CallContext) -> str | datetime | None:
    """``asap`` / ``"19:30"`` (today) / ``"2026-10-03 12:30"`` → ``ASAP`` or a business-local datetime."""
    text = " ".join(re.sub(r"^(\d{4}-\d{1,2}-\d{1,2})t", r"\1 ", str(value or "").strip().lower()).split())
    if not text:
        return None
    if text in (ASAP, "now", "as soon as possible", "soon", "earliest"):
        return ASAP
    parts = text.split(" ", 1)
    day = parse_date(parts[0], ctx.today) if len(parts) == 2 else None
    clock = parse_time(parts[1] if day is not None else text)
    if clock is None:
        return None
    assert ctx.now is not None
    return datetime.combine(day or ctx.today, clock.replace(second=0, microsecond=0), tzinfo=ctx.now.tzinfo)


def order_time_ok(at: datetime, ctx: CallContext) -> bool:
    assert ctx.now is not None
    if at < ctx.now - timedelta(minutes=5) or (at.date() - ctx.today).days > ORDER_DAYS:
        return False
    window = opening_window(ctx)
    if window is None:
        return True
    if not window.open_on(at.date()):
        return False
    start, end = _bounds(window, at.date(), at.tzinfo)
    return start <= at <= end


def ready_at(slots: dict[str, Any], ctx: CallContext) -> datetime:
    """When the order is ready (pickup) or arrives (delivery)."""
    assert ctx.now is not None
    earliest = ctx.now + timedelta(minutes=lead_minutes(slots, ctx))
    raw = slots.get("order_time")
    if raw and raw != ASAP:
        try:
            wanted = datetime.fromisoformat(str(raw))
        except ValueError:
            return earliest
        return max(wanted, earliest)
    return earliest


def ready_phrase(slots: dict[str, Any], ctx: CallContext, language: str, *, minutes_line: str) -> str:
    """``in about 20 minutes`` (asap; ``minutes_line`` has ``{minutes}``) or ``today at 7:30 PM``."""
    from app.skills.base import render

    if slots.get("order_time") in (None, "", ASAP):
        return render(minutes_line, {"minutes": lead_minutes(slots, ctx)})
    return when_phrase(ready_at(slots, ctx), ctx, language)


# ---- tables --------------------------------------------------------------------------------------
def party_size(slots: dict[str, Any]) -> int:
    return max(1, whole(slots.get("party_size"), 2))


def table_capacity(ctx: CallContext, party: int) -> int:
    covers = whole(conf(ctx).get("covers_per_slot"), 0)
    if covers <= 0:
        return UNLIMITED
    return max(1, covers // max(1, party))


def table_availability(slots: dict[str, Any], ctx: CallContext) -> Availability | None:
    config = conf(ctx)
    step = max(15, whole(config.get("slot_minutes"), 30))
    window = opening_window(ctx, step=step, capacity=table_capacity(ctx, party_size(slots)))
    if window is None:
        window = Window(start=time(12, 0), end=time(22, 0), step_minutes=step, capacity=table_capacity(ctx, party_size(slots)))
    return Availability(
        windows=[window],
        item_id=None,
        horizon_days=max(1, whole(config.get("booking_horizon_days"), 14)),
        lead_minutes=max(0, whole(config.get("lead_minutes"), 60)),
        busy=ctx.busy_for(None),
    )


__all__ = [
    "ASAP",
    "can_do_asap",
    "hours_phrase",
    "is_open",
    "lead_minutes",
    "next_opening",
    "opening_window",
    "order_time_ok",
    "parse_order_time",
    "party_size",
    "ready_at",
    "ready_phrase",
    "table_availability",
    "table_capacity",
]
