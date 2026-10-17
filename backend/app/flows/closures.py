"""Holiday / closure dates: days the business — or one doctor, stylist or resource — takes no bookings.

Stored in the account's settings JSON, ``vertical_config["closures"]``::

    [{"start": "2026-11-26", "end": "2026-11-26", "label": "Thanksgiving", "item_id": ""}, …]

Dates are business-local calendar days, both ends included. ``item_id`` empty = the whole
business; otherwise one catalog item with its own hours (see :data:`ITEM_KINDS`). Ended
entries are dropped whenever the list is read for a call or saved from the portal.

Pure helpers, no I/O: parsing and validating the list, "is this day closed?", and the
phrases the agent uses ("from Thursday, December 24 to Saturday, December 26").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

from app.flows.timefmt import MONTH_EN, WEEKDAY_EN, parse_date, weekday_key

CONFIG_KEY = "closures"
MAX_CLOSURES = 100
MAX_LABEL = 60
#: How far ahead a closure may start or end (two years).
MAX_AHEAD_DAYS = 731
#: Upcoming closures listed in the agent's facts (the prompt stays small).
FACT_LIMIT = 8
#: Catalog kinds with their own hours — the items a closure may be limited to, per vertical.
ITEM_KINDS: dict[str, str] = {"clinic": "doctor", "dental": "doctor", "vet": "doctor", "salon": "staff", "custom": "resource"}


class ClosureError(ValueError):
    """An owner's closure list that can't be saved (the message says why)."""


@dataclass(frozen=True)
class Closure:
    start: date
    end: date
    label: str = ""
    #: Catalog item this closure is limited to ("" = the whole business).
    item_id: str = ""

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end

    def applies_to(self, item_id: str | None) -> bool:
        return not self.item_id or (bool(item_id) and self.item_id == item_id)

    def as_json(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "label": self.label, "item_id": self.item_id}


def _label(value: Any) -> str:
    return " ".join(str(value or "").split())


def parse(raw: Any, *, today: date | None = None) -> list[Closure]:
    """Stored entries → closures in date order; malformed ones are skipped, ended ones dropped (given ``today``)."""
    out: list[Closure] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, Mapping):
            continue
        start = parse_date(entry.get("start"))
        end = parse_date(entry.get("end")) or start
        if start is None or end is None or end < start or (today is not None and end < today):
            continue
        out.append(Closure(start, end, _label(entry.get("label"))[:MAX_LABEL], str(entry.get("item_id") or "")))
    out.sort(key=lambda closure: (closure.start, closure.end, closure.item_id))
    return out


def from_config(config: Mapping[str, Any] | None, *, today: date | None = None) -> list[Closure]:
    return parse((config or {}).get(CONFIG_KEY), today=today)


def clean(raw: Any, *, today: date, item_ids: Iterable[str] = ()) -> list[dict[str, str]]:
    """The portal's list → the stored form. Ended entries are dropped quietly; anything invalid
    raises :class:`ClosureError` (ISO dates, end ≥ start, ≤ 2 years ahead, label ≤ 60, known item)."""
    if not isinstance(raw, list):
        raise ClosureError("Closures must be a list.")
    known = set(item_ids)
    last = today + timedelta(days=MAX_AHEAD_DAYS)
    kept: list[Closure] = []
    for index, entry in enumerate(raw, start=1):
        if not isinstance(entry, Mapping):
            raise ClosureError(f"Closure {index}: expected a start date.")
        start_text, end_text = str(entry.get("start") or "").strip(), str(entry.get("end") or "").strip()
        start, end = _iso(start_text), _iso(end_text) if end_text else _iso(start_text)
        if start is None or end is None:
            raise ClosureError(f"Closure {index}: dates must be YYYY-MM-DD.")
        if end < start:
            raise ClosureError(f"Closure {index}: the end date is before the start date.")
        if end > last:
            raise ClosureError(f"Closure {index}: closures can be set up to two years ahead.")
        label = _label(entry.get("label"))
        if len(label) > MAX_LABEL:
            raise ClosureError(f"Closure {index}: keep the label to {MAX_LABEL} characters.")
        item_id = str(entry.get("item_id") or "").strip()
        if item_id and item_id not in known:
            raise ClosureError(f"Closure {index}: that team member or resource no longer exists.")
        if end >= today:
            kept.append(Closure(start, end, label, item_id))
    unique = list(dict.fromkeys(kept))
    if len(unique) > MAX_CLOSURES:
        raise ClosureError(f"Up to {MAX_CLOSURES} closures.")
    unique.sort(key=lambda closure: (closure.start, closure.end, closure.item_id))
    return [closure.as_json() for closure in unique]


def _iso(text: str) -> date | None:
    try:
        return date.fromisoformat(text) if len(text) == 10 else None
    except ValueError:
        return None


# ---------------------------------------------------------------- questions
def closure_on(closures: Iterable[Closure], day: date, item_id: str | None = None) -> Closure | None:
    """The closure that shuts ``day`` for ``item_id`` (the whole business's first), or None."""
    hits = [closure for closure in closures if closure.covers(day) and closure.applies_to(item_id)]
    return min(hits, key=lambda closure: (bool(closure.item_id), closure.start)) if hits else None


def relevant(closures: Iterable[Closure], *item_ids: str | None) -> list[Closure]:
    """The whole business's closures plus those of the given items."""
    wanted = {item for item in item_ids if item}
    return [closure for closure in closures if not closure.item_id or closure.item_id in wanted]


def blocked_start(closures: Iterable[Closure], start: Any, item_id: str | None = None, *, tz: Any = None) -> Closure | None:
    """The closure a booking at ``start`` (a datetime) would land in — the commit-time check."""
    if not isinstance(start, datetime):
        return None
    local = start.astimezone(tz) if tz is not None and start.tzinfo is not None else start
    return closure_on(closures, local.date(), item_id)


# ---------------------------------------------------------------- phrases
def day_phrase(day: date, *, month_first: bool = True, weekday: bool = True) -> str:
    """``Thursday, November 26`` (``Thursday, 26 November`` day-first)."""
    body = f"{MONTH_EN[day.month - 1]} {day.day}" if month_first else f"{day.day} {MONTH_EN[day.month - 1]}"
    return f"{WEEKDAY_EN[weekday_key(day)]}, {body}" if weekday else body


def span_phrase(start: date, end: date, today: date | None = None, *, month_first: bool = True) -> str:
    """How a closure is said after "We're closed": ``today`` / ``tomorrow`` / ``on Thursday, November 26`` /
    ``from Thursday, December 24 to Saturday, December 26``."""
    if start == end:
        delta = (start - today).days if today is not None else None
        if delta == 0:
            return "today"
        if delta == 1:
            return "tomorrow"
        return f"on {day_phrase(start, month_first=month_first)}"
    first = "today" if today is not None and start <= today else day_phrase(start, month_first=month_first)
    return f"from {first} to {day_phrase(end, month_first=month_first)}"


def _short(closure: Closure) -> str:
    start = f"{WEEKDAY_EN[weekday_key(closure.start)][:3]} {closure.start.isoformat()}"
    if closure.end == closure.start:
        return start
    return f"{start} to {WEEKDAY_EN[weekday_key(closure.end)][:3]} {closure.end.isoformat()}"


def facts_line(closures: Iterable[Closure], names: Mapping[str, str] | None = None) -> str:
    """One line for the agent's facts: ``Closed — no bookings on these dates: Thu 2026-11-26 (Thanksgiving); …
    Dr. Lee not available: …``."""
    names = names or {}
    business: list[str] = []
    away: dict[str, list[str]] = {}
    for closure in list(closures)[:FACT_LIMIT]:
        text = _short(closure) + (f" ({closure.label})" if closure.label else "")
        if not closure.item_id:
            business.append(text)
        elif closure.item_id in names:
            away.setdefault(names[closure.item_id], []).append(text)
    parts: list[str] = []
    if business:
        parts.append("Closed — no bookings on these dates: " + "; ".join(business) + ".")
    parts += [f"{who} not available: {'; '.join(days)}." for who, days in away.items()]
    return " ".join(parts)


def blocked_commit(action: Any, ctx: Any) -> Closure | None:
    """The closure a write would book into: a new or moved time (``scheduled_at``) on a closed day
    for the business or the booked item. Re-writing a record at its current time is never blocked."""
    start = (action.fields or {}).get("scheduled_at")
    item_id = (action.fields or {}).get("catalog_item_id") or None
    closure = blocked_start(ctx.closures_for(item_id), start, item_id, tz=getattr(ctx.now, "tzinfo", None))
    if closure is None or not action.record_id:
        return closure
    for record in (ctx.record, *ctx.caller_records):
        if record is not None and str(getattr(record, "id", "")) == str(action.record_id):
            return None if getattr(record, "scheduled_at", None) == start else closure
    return closure


def call_facts(ctx: Any) -> list[str]:
    """The closures line for a call's prompt (empty when none are coming up)."""
    closures = ctx.closures
    if not closures:
        return []
    line = facts_line(closures, {item.id: item.name for item in ctx.catalog})
    return [line] if line else []


__all__ = [
    "CONFIG_KEY",
    "FACT_LIMIT",
    "ITEM_KINDS",
    "MAX_AHEAD_DAYS",
    "MAX_CLOSURES",
    "MAX_LABEL",
    "Closure",
    "ClosureError",
    "blocked_commit",
    "blocked_start",
    "call_facts",
    "clean",
    "closure_on",
    "day_phrase",
    "facts_line",
    "from_config",
    "parse",
    "relevant",
    "span_phrase",
]
