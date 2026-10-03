"""Bookable time: sessions, slots, serial numbers and what is still free.

One model covers every vertical:

- a **doctor chamber** is a session on some weekdays ("Sat/Mon/Wed 17:00–21:00")
  cut into ``step_minutes`` slots; the slot's position is the patient's
  **serial number** (how Bangladeshi chambers book), its start the
  approximate time to arrive;
- a **home-service visit** is a named window ("morning 09:00–12:00") with one
  slot (``step_minutes=0``) and a ``capacity`` = how many teams are out;
- a **site visit** is a day window cut into hourly slots, capacity 1 (one broker).

``booked`` maps :func:`slot_key` → number of live bookings in that slot. It is
a snapshot taken when the call starts; the store re-checks the slot under a
lock when the booking is actually written, so the snapshot only has to be
good enough to *offer* times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any, Iterable, Mapping

from app.flows.timefmt import PART_TARGETS, normalize_days, parse_time, weekday_key


@dataclass(frozen=True)
class Window:
    """A bookable session on some weekdays (empty ``days`` = every day)."""

    start: time
    end: time
    days: frozenset[str] = frozenset()
    #: Slot length; 0 = the whole window is one slot (arrival windows).
    step_minutes: int = 0
    #: Bookings one slot can take.
    capacity: int = 1
    #: Cap on slots per session (a doctor's max patients); 0 = no cap.
    max_slots: int = 0
    #: Optional name ("morning") so a caller can ask for it.
    key: str = ""

    def open_on(self, day: date) -> bool:
        return not self.days or weekday_key(day) in self.days


@dataclass(frozen=True)
class Slot:
    start: datetime  # aware, business-local
    window: Window
    #: 1-based position inside its session = the serial number.
    serial: int = 1
    #: Bookings already in it (from the snapshot).
    taken: int = 0

    @property
    def free(self) -> bool:
        return self.taken < max(1, self.window.capacity)


def slot_key(item_id: str | None, start: datetime) -> str:
    """Stable key for a slot: resource + UTC minute (both sides of the snapshot use it)."""
    return f"{item_id or ''}@{start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M')}"


# ------------------------------------------------------------------ building windows
def window_from_config(data: Mapping[str, Any], *, default_step: int = 0, default_capacity: int = 1) -> Window | None:
    """``{"days": [...], "start": "17:00", "end": "21:00", "slot_minutes": 15, ...}`` → Window."""
    start = parse_time(data.get("start"))
    end = parse_time(data.get("end"))
    if start is None or end is None or end <= start:
        return None
    try:
        step = int(data.get("slot_minutes", default_step) or 0)
        capacity = int(data.get("capacity", default_capacity) or default_capacity)
        max_slots = int(data.get("max_patients", data.get("max_slots", 0)) or 0)
    except (TypeError, ValueError):
        return None
    return Window(
        start=start,
        end=end,
        days=frozenset(normalize_days(data.get("days") or [])),
        step_minutes=max(0, step),
        capacity=max(1, capacity),
        max_slots=max(0, max_slots),
        key=str(data.get("key") or ""),
    )


# ------------------------------------------------------------------ enumerating
def slots_on(windows: Iterable[Window], day: date, tz: tzinfo, *, item_id: str | None = None, booked: Mapping[str, int] | None = None) -> list[Slot]:
    """Every slot on ``day`` (free or not), in time order."""
    booked = booked or {}
    out: list[Slot] = []
    for window in windows:
        if not window.open_on(day):
            continue
        start = datetime.combine(day, window.start, tzinfo=tz)
        end = datetime.combine(day, window.end, tzinfo=tz)
        if window.step_minutes <= 0:
            out.append(Slot(start=start, window=window, serial=1, taken=int(booked.get(slot_key(item_id, start), 0))))
            continue
        step = timedelta(minutes=window.step_minutes)
        serial = 1
        current = start
        while current + step <= end + timedelta(seconds=1):
            if window.max_slots and serial > window.max_slots:
                break
            out.append(Slot(start=current, window=window, serial=serial, taken=int(booked.get(slot_key(item_id, current), 0))))
            serial += 1
            current += step
    out.sort(key=lambda slot: slot.start)
    return out


def slot_end(slot: Slot) -> datetime:
    if slot.window.step_minutes > 0:
        return slot.start + timedelta(minutes=slot.window.step_minutes)
    return datetime.combine(slot.start.date(), slot.window.end, tzinfo=slot.start.tzinfo)


def overlaps_busy(slot: Slot, busy: Iterable[tuple[datetime, datetime]]) -> bool:
    """The slot overlaps a busy time imported from the business's calendar."""
    start, end = slot.start, slot_end(slot)
    return any(b_start < end and b_end > start for b_start, b_end in busy)


def free_slots(
    windows: Iterable[Window],
    day: date,
    *,
    now: datetime,
    item_id: str | None = None,
    booked: Mapping[str, int] | None = None,
    lead_minutes: int = 30,
    busy: Iterable[tuple[datetime, datetime]] = (),
) -> list[Slot]:
    """Slots on ``day`` that still take a booking, start at least ``lead_minutes`` from
    now and are not blocked by a busy time in the business's own calendar.

    A window slot (arrival window) stays bookable until its window *ends*.
    """
    tz = now.tzinfo or timezone.utc
    earliest = now + timedelta(minutes=max(0, lead_minutes))
    busy = list(busy)
    result: list[Slot] = []
    for slot in slots_on(windows, day, tz, item_id=item_id, booked=booked):
        if not slot.free or (busy and overlaps_busy(slot, busy)):
            continue
        cutoff = slot.start
        if slot.window.step_minutes <= 0:
            cutoff = datetime.combine(day, slot.window.end, tzinfo=tz) - timedelta(minutes=60)
        if cutoff < earliest:
            continue
        result.append(slot)
    return result


def open_days(
    windows: Iterable[Window],
    *,
    now: datetime,
    horizon_days: int,
    item_id: str | None = None,
    booked: Mapping[str, int] | None = None,
    start: date | None = None,
    limit: int = 2,
    lead_minutes: int = 30,
    busy: Iterable[tuple[datetime, datetime]] = (),
) -> list[date]:
    """The next days (from ``start``, default today) with at least one free slot."""
    windows = list(windows)
    busy = list(busy)
    first = start or now.date()
    last = now.date() + timedelta(days=max(0, horizon_days))
    found: list[date] = []
    day = first
    while day <= last and len(found) < limit:
        if free_slots(windows, day, now=now, item_id=item_id, booked=booked, lead_minutes=lead_minutes, busy=busy):
            found.append(day)
        day += timedelta(days=1)
    return found


# ------------------------------------------------------------------ choosing
def preference_time(pref: Any) -> time | None:
    """``"18:30"`` → 18:30; ``"evening"`` → 18:30; empty/unknown → None."""
    text = str(pref or "").strip().lower()
    if not text or text in ("any", "anytime", "earliest"):
        return None
    if text in PART_TARGETS:
        return PART_TARGETS[text]
    return parse_time(text)


def pick_slot(slots: list[Slot], pref: Any = None, *, window_key: str = "") -> Slot | None:
    """The slot to propose: the named window if asked, else nearest to the preferred
    time (never far *before* it), else the earliest."""
    if not slots:
        return None
    if window_key:
        named = [slot for slot in slots if slot.window.key == window_key]
        if named:
            return named[0]
    target = preference_time(pref)
    if target is None:
        return slots[0]

    def distance(slot: Slot) -> float:
        minutes = slot.start.hour * 60 + slot.start.minute - (target.hour * 60 + target.minute)
        # A caller who said "around 7" would rather come at 7:10 than at 6:10.
        return minutes if minutes >= 0 else -minutes * 1.5

    return min(slots, key=distance)


def alternatives(slots: list[Slot], chosen: Slot | None, *, count: int = 1) -> list[Slot]:
    """The next free slot(s) after ``chosen`` (or before it when none follow)."""
    if chosen is None:
        return slots[:count]
    later = [slot for slot in slots if slot.start > chosen.start]
    earlier = [slot for slot in reversed(slots) if slot.start < chosen.start]
    return (later + earlier)[:count]


@dataclass
class Availability:
    """What the flow knows about one resource's calendar during a call."""

    windows: list[Window] = field(default_factory=list)
    item_id: str | None = None
    horizon_days: int = 14
    lead_minutes: int = 30
    #: Busy times from the business's own calendar (never offered).
    busy: list[tuple[datetime, datetime]] = field(default_factory=list)

    def free(self, day: date, *, now: datetime, booked: Mapping[str, int]) -> list[Slot]:
        if day < now.date() or day > now.date() + timedelta(days=self.horizon_days):
            return []
        return free_slots(
            self.windows, day, now=now, item_id=self.item_id, booked=booked, lead_minutes=self.lead_minutes, busy=self.busy
        )

    def next_days(self, *, now: datetime, booked: Mapping[str, int], start: date | None = None, limit: int = 2) -> list[date]:
        return open_days(
            self.windows,
            now=now,
            horizon_days=self.horizon_days,
            item_id=self.item_id,
            booked=booked,
            start=start,
            limit=limit,
            lead_minutes=self.lead_minutes,
            busy=self.busy,
        )

    def working_days(self) -> list[str]:
        days: set[str] = set()
        for window in self.windows:
            days |= set(window.days) if window.days else {"sat", "sun", "mon", "tue", "wed", "thu", "fri"}
        return normalize_days(days)


__all__ = [
    "Availability",
    "Slot",
    "Window",
    "alternatives",
    "free_slots",
    "open_days",
    "overlaps_busy",
    "pick_slot",
    "preference_time",
    "slot_key",
    "slots_on",
    "window_from_config",
]
