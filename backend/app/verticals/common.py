"""Booking pieces shared by the clinic, real-estate and home-service engines.

``plan_booking`` turns what the caller asked for (a date, maybe a preferred
time or window) into ONE concrete proposal — the slot the backend reads back —
or clears the date and leaves a *notice* ("Dr. Karim doesn't sit on Friday;
Saturday or Monday?") that the next question is prefixed with. Notices are
stored as data (code + params) because ``derive`` has no language; they are
rendered at instruction time.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.flows.context import CallContext
from app.flows.scheduling import Availability, pick_slot
from app.flows.timefmt import PART_TARGETS, date_phrase, days_phrase, parse_date, parse_time, time_phrase
from app.verticals.notices import (
    NOTICE,
    clear_notice,
    closed_notice,
    closure_sentence,
    join_and,
    join_or,
    notice,
    render_notice,
    with_notice,
)
from app.voice.languages import normalize_language, spoken_amount


def money(amount: Any, ctx: CallContext, language: str) -> str:
    """An amount in the account's currency, the way it is said on the phone."""
    return spoken_amount(amount or 0, ctx.currency, language)


def window_phrase(start: Any, end: Any, language: str) -> str:
    """``6 PM to 9 PM``."""
    s, e = parse_time(start), parse_time(end)
    if s is None or e is None:
        return ""
    return f"{time_phrase(s, 'en')} to {time_phrase(e, 'en')}"


def schedule_phrase(availability: Availability, language: str, ctx: CallContext | None = None) -> str:
    """``Monday, Wednesday and Friday 10 AM to 4 PM``."""
    if not availability.windows:
        return ""
    window = availability.windows[0]
    days = days_phrase(availability.working_days(), language)
    hours = window_phrase(window.start.strftime("%H:%M"), window.end.strftime("%H:%M"), language)
    return f"{days} {hours}".strip()


def slot_start(slots: dict[str, Any]) -> datetime | None:
    raw = slots.get("slot")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def when_phrase(start: datetime, ctx: CallContext, language: str, *, window_label: str = "", on: bool = False) -> str:
    """``tomorrow at 6:20 PM`` (or a window label instead of the clock).

    ``on=True`` reads "on Monday, October 5 at 9 AM" (for "… is coming {when}");
    relative days stay "tomorrow at 9 AM"."""
    lang = normalize_language(language)
    delta = (start.date() - ctx.today).days
    if delta == 0:
        day = "today"
    elif delta == 1:
        # "tomorrow, Friday" — callers who think in weekdays shouldn't have to work out what "tomorrow" is.
        day = date_phrase(start.date(), ctx.today, lang, month_first=ctx.month_first)
    else:
        day = date_phrase(start.date(), ctx.today, lang, month_first=ctx.month_first)
        if on:
            day = f"on {day}"
    if window_label:
        return f"{day} {window_label}"
    return f"{day} {time_phrase(start.time(), lang, at=True)}"


def _part_of(start: datetime, window_key: str = "") -> str:
    """morning / afternoon / evening of a slot (its window's own name when it has one)."""
    if window_key in ("morning", "afternoon", "evening"):
        return window_key
    return "morning" if start.hour < 12 else ("afternoon" if start.hour < 17 else "evening")


def plan_booking(
    slots: dict[str, Any],
    ctx: CallContext,
    availability: Availability | None,
    *,
    date_key: str = "date",
    pref_key: str = "time_pref",
    window_key: str = "",
    who: str = "",
    who_notice: str = "closed_day_doctor",
) -> None:
    """Validate ``slots[date_key]`` and propose a slot (``slot``/``serial``/``window``),
    or clear the date and leave a notice explaining why."""
    for key in ("slot", "serial", "window"):
        slots.pop(key, None)
    raw = slots.get(date_key)
    if not raw or availability is None:
        return
    day = parse_date(raw, ctx.today)
    if day is None:
        slots.pop(date_key, None)
        notice(slots, "date_unclear")
        return
    slots[date_key] = day.isoformat()
    if day < ctx.today:
        slots.pop(date_key, None)
        notice(slots, "date_past")
        return
    if (day - ctx.today).days > availability.horizon_days:
        slots.pop(date_key, None)
        notice(slots, "date_too_far", days=availability.horizon_days)
        return
    closure = availability.closure_on(day)
    if closure is not None:
        slots.pop(date_key, None)
        nxt = availability.next_days(now=ctx.now, booked=ctx.booked, start=day + timedelta(days=1), limit=1)
        closed_notice(slots, ctx, closure, next_day=nxt[0] if nxt else None, who=who)
        return
    if not any(window.open_on(day) for window in availability.windows):
        slots.pop(date_key, None)
        nxt = availability.next_days(now=ctx.now, booked=ctx.booked, start=ctx.today, limit=2)
        open_days = availability.working_days()
        if who:
            notice(slots, who_notice, who=who, weekday=day, open=open_days, next=nxt)
        else:
            notice(slots, "closed_day", weekday=day, open=open_days, next=nxt)
        return
    free = availability.free(day, now=ctx.now, booked=ctx.booked)
    if not free:
        slots.pop(date_key, None)
        nxt = availability.next_days(now=ctx.now, booked=ctx.booked, start=day + timedelta(days=1), limit=2)
        notice(slots, "day_full", day=day, next=nxt)
        return
    pref = slots.get(pref_key) if pref_key else None
    chosen = pick_slot(free, pref, window_key=str(slots.get(window_key) or "") if window_key else "")
    if chosen is None:
        return
    slots["slot"] = chosen.start.isoformat()
    slots["serial"] = chosen.serial
    if chosen.window.key:
        slots["window"] = chosen.window.key
    if slots.get(NOTICE):
        return  # a sharper notice is already set ("that time was just taken")
    wanted = (str(slots.get(window_key) or "") if window_key else "") or (str(pref) if pref and str(pref) in PART_TARGETS else "")
    if wanted and _part_of(chosen.start, chosen.window.key) != wanted:
        notice(slots, "window_moved", pref=wanted)
    target = parse_time(pref) if pref and str(pref) not in PART_TARGETS else None
    if target is not None:
        gap = abs((chosen.start.hour * 60 + chosen.start.minute) - (target.hour * 60 + target.minute))
        if gap >= 10:
            notice(slots, "pref_moved", pref=target.strftime("%H:%M"))


__all__ = [
    "NOTICE",
    "clear_notice",
    "closed_notice",
    "closure_sentence",
    "join_and",
    "join_or",
    "money",
    "notice",
    "plan_booking",
    "render_notice",
    "schedule_phrase",
    "slot_start",
    "when_phrase",
    "window_phrase",
    "with_notice",
]
