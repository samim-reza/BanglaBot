"""Notices: why the date / time the caller asked for can't be had ("Dr. Karim doesn't sit on Friday …").

Stored in the slots as data (code + params) because ``derive`` has no language, and
rendered when the next line is spoken (``with_notice`` prefixes it).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.flows.closures import Closure, span_phrase
from app.flows.context import CallContext
from app.flows.steps import lang_text
from app.flows.timefmt import WEEKDAY_EN, date_phrase, days_phrase, parse_time, short_date_phrase, time_phrase, weekday_key
from app.voice.languages import normalize_language

NOTICE = "_notice"

_NOTICES: dict[str, dict[str, str]] = {
    "date_unclear": {
        "en": "Sorry, I didn't catch the date.",
    },
    "date_past": {
        "en": "That date has already passed.",
    },
    "date_too_far": {
        "en": "We take bookings for the next {days} days only.",
    },
    "closed_day": {
        "en": "We're closed on {weekday}. We're open {open} — for example {next}.",
    },
    "closed_day_doctor": {
        "en": "{who} doesn't see patients on {weekday}; only {open} — for example {next}.",
    },
    "closed_day_resource": {
        "en": "{who} isn't available on {weekday}; only {open} — for example {next}.",
    },
    "closed_day_person": {
        "en": "{who} isn't in on {weekday}; {who} works {open} — for example {next}.",
    },
    "closed_date": {
        "en": "We're closed {span}{label} — the next open day is {next}.",
    },
    "closed_date_none": {
        "en": "We're closed {span}{label}.",
    },
    "closed_date_person": {
        "en": "{who} isn't available {span}{label} — the next available day is {next}.",
    },
    "closed_date_person_none": {
        "en": "{who} isn't available {span}{label}.",
    },
    "day_full": {
        "en": "Sorry, {day} is fully booked. {next} has openings.",
    },
    "day_full_none": {
        "en": "Sorry, the next few days are fully booked.",
    },
    "order_cancel_request": {
        "en": "I'll pass your request to cancel order {ref} to the team right away.",
    },
    "order_status": {
        "en": "Your order {ref} — {items}, {total} — is {status}.",
    },
    "slot_taken": {
        "en": "Sorry, that time was just taken by someone else.",
    },
    "pref_moved": {
        "en": "{pref} isn't free, so here is the nearest open time.",
    },
    "ready_moved": {
        "en": "The earliest we can have it ready is {time}.",
    },
    "window_moved": {
        "en": "Sorry, the {pref} is fully booked, so here is the next open time.",
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
        if key == "span" and isinstance(value, (list, tuple)) and len(value) == 2:
            rendered[key] = span_phrase(value[0], value[1], ctx.today, month_first=ctx.month_first)
        elif key == "label":
            rendered[key] = f" for {value}" if value else ""
        elif key == "open" and isinstance(value, list):
            rendered[key] = days_phrase(value, lang)
        elif key == "weekday" and isinstance(value, date):
            rendered[key] = WEEKDAY_EN[weekday_key(value)]
        elif key == "pref" and isinstance(value, str) and parse_time(value) is not None:
            rendered[key] = time_phrase(parse_time(value), lang)  # type: ignore[arg-type]
        elif isinstance(value, date):
            rendered[key] = date_phrase(value, ctx.today, lang, month_first=ctx.month_first)
        elif isinstance(value, list) and value and all(isinstance(v, date) for v in value):
            rendered[key] = join_or([short_date_phrase(v, ctx.today, lang, month_first=ctx.month_first) for v in value], lang)
        else:
            rendered[key] = str(value)
    if (code == "day_full" or code.startswith("closed_date")) and not params.get("next"):
        code = code if code.endswith("_none") else f"{code}_none"
    template = lang_text(_NOTICES.get(code, {}), lang)
    try:
        return template.format(**rendered)
    except (KeyError, IndexError, ValueError):
        return template


def closed_notice(slots: dict[str, Any], ctx: CallContext, closure: Closure, *, next_day: date | None = None, who: str = "") -> None:
    """Explain a closure: "We're closed on Thursday, November 26 for Thanksgiving — the next open day is …"
    (a person's own closure: "Dr. Lee is away …")."""
    if closure.item_id and not who:
        item = ctx.item_by_id(closure.item_id)
        who = item.name if item is not None else ""
    params: dict[str, Any] = {"span": [closure.start, closure.end], "label": closure.label, "next": next_day}
    if closure.item_id and who:
        notice(slots, "closed_date_person", who=who, **params)
    else:
        notice(slots, "closed_date", **params)


def closure_sentence(ctx: CallContext, closure: Closure, *, next_day: date | None = None, who: str = "") -> str:
    """The closure notice as a sentence of its own (for lines that don't carry a notice)."""
    holder: dict[str, Any] = {}
    closed_notice(holder, ctx, closure, next_day=next_day, who=who)
    return render_notice(holder, ctx, "en")


def with_notice(slots: dict[str, Any], ctx: CallContext, language: str, line: str) -> str:
    lead = render_notice(slots, ctx, language)
    return f"{lead} {line}".strip() if lead else line


def join_or(parts: list[str], language: str) -> str:
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return f"{', '.join(parts[:-1])} or {parts[-1]}"


def join_and(parts: list[str], language: str) -> str:
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


__all__ = [
    "NOTICE",
    "clear_notice",
    "closed_notice",
    "closure_sentence",
    "join_and",
    "join_or",
    "notice",
    "render_notice",
    "with_notice",
]
