"""Booking pieces shared by the clinic, real-estate and home-service engines.

``plan_booking`` turns what the caller asked for (a date, maybe a preferred
time or window) into ONE concrete proposal — the slot the backend reads back —
or clears the date and leaves a *notice* ("Dr. Karim doesn't sit on Friday;
Saturday or Monday?") that the next question is prefixed with. Notices are
stored as data (code + params) because ``derive`` has no language; they are
rendered at instruction time.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.flows.context import CallContext
from app.flows.scheduling import Availability, pick_slot
from app.flows.steps import lang_text
from app.flows.timefmt import (
    PART_TARGETS,
    WEEKDAY_BN,
    WEEKDAY_EN,
    date_phrase,
    days_phrase,
    parse_date,
    parse_time,
    short_date_phrase,
    time_phrase,
    weekday_key,
)
from app.voice.languages import normalize_language, spoken_amount

NOTICE = "_notice"

_NOTICES: dict[str, dict[str, str]] = {
    "date_unclear": {
        "bn": "দুঃখিত, তারিখটা ঠিক বুঝতে পারিনি।",
        "en": "Sorry, I didn't catch the date.",
    },
    "date_past": {
        "bn": "ওই তারিখটা তো পার হয়ে গেছে।",
        "en": "That date has already passed.",
    },
    "date_too_far": {
        "bn": "আমরা আগামী {days} দিনের মধ্যে বুকিং নিই।",
        "en": "We take bookings for the next {days} days only.",
    },
    "closed_day": {
        "bn": "{weekday} বন্ধ থাকে। {open} খোলা — যেমন {next}।",
        "en": "We're closed on {weekday}. We're open {open} — for example {next}.",
    },
    "closed_day_doctor": {
        "bn": "{who} {weekday} বসেন না, উনি {open} বসেন — যেমন {next}।",
        "en": "{who} doesn't see patients on {weekday}; only {open} — for example {next}.",
    },
    "day_full": {
        "bn": "দুঃখিত, {day} সব সময় বুক হয়ে গেছে। {next} খালি আছে।",
        "en": "Sorry, {day} is fully booked. {next} has openings.",
    },
    "day_full_none": {
        "bn": "দুঃখিত, সামনের কয়েক দিন সব সময় বুক হয়ে গেছে।",
        "en": "Sorry, the next few days are fully booked.",
    },
    "slot_taken": {
        "bn": "দুঃখিত, ওই সময়টা এইমাত্র অন্য কেউ নিয়ে নিয়েছেন।",
        "en": "Sorry, that time was just taken by someone else.",
    },
    "pref_moved": {
        "bn": "{pref} সময়টা খালি নেই, সবচেয়ে কাছের খালি সময় দিচ্ছি।",
        "en": "{pref} isn't free, so here is the nearest open time.",
    },
}


def notice(slots: dict[str, Any], code: str, **params: Any) -> None:
    slots[NOTICE] = {"code": code, "params": params}


def clear_notice(slots: dict[str, Any]) -> None:
    slots.pop(NOTICE, None)


def render_notice(slots: dict[str, Any], ctx: CallContext, language: str) -> str:
    entry = slots.get(NOTICE)
    if not isinstance(entry, dict):
        return ""
    lang = normalize_language(language)
    code = str(entry.get("code") or "")
    params = dict(entry.get("params") or {})
    rendered: dict[str, str] = {}
    for key, value in params.items():
        if key == "open" and isinstance(value, list):
            rendered[key] = days_phrase(value, lang, saturday_first=ctx.saturday_first)
        elif key == "weekday" and isinstance(value, date):
            rendered[key] = (WEEKDAY_BN if lang == "bn" else WEEKDAY_EN)[weekday_key(value)]
        elif key == "pref" and isinstance(value, str) and parse_time(value) is not None:
            rendered[key] = time_phrase(parse_time(value), lang)  # type: ignore[arg-type]
        elif isinstance(value, date):
            rendered[key] = date_phrase(value, ctx.today, lang, month_first=ctx.month_first)
        elif isinstance(value, list) and value and all(isinstance(v, date) for v in value):
            rendered[key] = join_or([short_date_phrase(v, ctx.today, lang, month_first=ctx.month_first) for v in value], lang)
        else:
            rendered[key] = str(value)
    if code == "day_full" and not params.get("next"):
        code = "day_full_none"
    template = lang_text(_NOTICES.get(code, {}), lang)
    try:
        return template.format(**rendered)
    except (KeyError, IndexError, ValueError):
        return template


def with_notice(slots: dict[str, Any], ctx: CallContext, language: str, line: str) -> str:
    lead = render_notice(slots, ctx, language)
    return f"{lead} {line}".strip() if lead else line


def join_or(parts: list[str], language: str) -> str:
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    word = "বা" if normalize_language(language) == "bn" else "or"
    return f"{', '.join(parts[:-1])} {word} {parts[-1]}"


def join_and(parts: list[str], language: str) -> str:
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    word = "আর" if normalize_language(language) == "bn" else "and"
    return f"{', '.join(parts[:-1])} {word} {parts[-1]}"


def money(amount: Any, ctx: CallContext, language: str) -> str:
    """An amount in the account's currency, the way it is said on the phone."""
    return spoken_amount(amount or 0, ctx.currency, language)


def window_phrase(start: Any, end: Any, language: str) -> str:
    """``সন্ধ্যা ছয়টা থেকে রাত নয়টা`` / ``6 PM to 9 PM``."""
    s, e = parse_time(start), parse_time(end)
    if s is None or e is None:
        return ""
    if normalize_language(language) == "bn":
        return f"{time_phrase(s, 'bn')} থেকে {time_phrase(e, 'bn')}"
    return f"{time_phrase(s, 'en')} to {time_phrase(e, 'en')}"


def schedule_phrase(availability: Availability, language: str, ctx: CallContext | None = None) -> str:
    """``শনি, সোম ও বুধবার সন্ধ্যা পাঁচটা থেকে রাত নয়টা`` / ``Monday, Wednesday and Friday 10 AM to 4 PM``."""
    if not availability.windows:
        return ""
    window = availability.windows[0]
    days = days_phrase(availability.working_days(), language, saturday_first=ctx.saturday_first if ctx else None)
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
    """``আগামীকাল, রবিবার সন্ধ্যা ছয়টা বিশ মিনিটে`` (or a window label instead of the clock).

    ``on=True`` reads "on Monday, October 5 at 9 AM" in English (for "… is coming {when}");
    relative days stay "tomorrow at 9 AM"."""
    lang = normalize_language(language)
    delta = (start.date() - ctx.today).days
    if lang == "en" and delta in (0, 1):
        day = "today" if delta == 0 else "tomorrow"
    else:
        day = date_phrase(start.date(), ctx.today, lang, month_first=ctx.month_first)
        if lang == "en" and on:
            day = f"on {day}"
    if window_label:
        return f"{day} {window_label}"
    return f"{day} {time_phrase(start.time(), lang, at=True)}"


def plan_booking(
    slots: dict[str, Any],
    ctx: CallContext,
    availability: Availability | None,
    *,
    date_key: str = "date",
    pref_key: str = "time_pref",
    window_key: str = "",
    who: str = "",
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
    if not any(window.open_on(day) for window in availability.windows):
        slots.pop(date_key, None)
        nxt = availability.next_days(now=ctx.now, booked=ctx.booked, start=ctx.today, limit=2)
        open_days = availability.working_days()
        if who:
            notice(slots, "closed_day_doctor", who=who, weekday=day, open=open_days, next=nxt)
        else:
            notice(slots, "closed_day", weekday=day, open=open_days, next=nxt)
        return
    free = availability.free(day, now=ctx.now, booked=ctx.booked)
    if not free:
        slots.pop(date_key, None)
        from datetime import timedelta

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
    target = parse_time(pref) if pref and str(pref) not in PART_TARGETS else None
    if target is not None:
        gap = abs((chosen.start.hour * 60 + chosen.start.minute) - (target.hour * 60 + target.minute))
        if gap > 30:
            notice(slots, "pref_moved", pref=target.strftime("%H:%M"))


__all__ = [
    "NOTICE",
    "clear_notice",
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
