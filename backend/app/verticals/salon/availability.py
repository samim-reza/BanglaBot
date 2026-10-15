"""Duration-aware salon times: a service fits only inside a person's hours and only where none of
their bookings overlaps it.

Each window is one staff member's working hours, keyed by their ref, so the slot the
backend proposes also says who does it (that is how "anyone is fine" gets a person).
Start times run on a grid (``slot_minutes``, 15 by default); a 90-minute colour may
start at 10:15 but never at 17:45 when the stylist leaves at 18:00.

The call's booking snapshot (``ctx.booked``) knows when existing bookings *start*, not
how long they last, so each is assumed to last as long as that person's longest
service — it may hide a time that was actually free, but never double-books. Calendar
busy times (``ctx.busy``) are exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from app.flows.context import CallContext
from app.flows.scheduling import Availability, Slot, window_from_config
from app.verticals.salon.catalog import ANY, KIND_STAFF, chosen_service, duration, longest, salon_config, staff_by_ref, staff_for

Interval = tuple[datetime, datetime]


def bookings_on(booked: Mapping[str, int], item_id: str | None, day: date, tz: Any) -> list[tuple[datetime, int]]:
    """(local start, count) of the snapshot's bookings for one resource around ``day``."""
    prefix = f"{item_id or ''}@"
    found: list[tuple[datetime, int]] = []
    for key, count in booked.items():
        if not key.startswith(prefix) or not count:
            continue
        try:
            start = datetime.strptime(key[len(prefix):], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).astimezone(tz)
        except ValueError:
            continue
        if abs((start.date() - day).days) <= 1:
            found.append((start, int(count)))
    return found


@dataclass
class StaffAvailability(Availability):
    #: Length of the service being booked.
    duration: int = 60
    #: Minutes between possible start times.
    grid: int = 15
    #: window key (staff ref, "" without a staff list) → (catalog item id, minutes one of their bookings may last, busy times).
    owners: dict[str, tuple[str | None, int, list[Interval]]] = field(default_factory=dict)

    def free(self, day: date, *, now: datetime, booked: Mapping[str, int]) -> list[Slot]:
        if day < now.date() or day > now.date() + timedelta(days=self.horizon_days):
            return []
        tz = now.tzinfo or timezone.utc
        earliest = now + timedelta(minutes=max(0, self.lead_minutes))
        length = timedelta(minutes=max(5, self.duration))
        step = timedelta(minutes=max(5, self.grid))
        out: list[Slot] = []
        for window in self.windows:
            if not window.open_on(day):
                continue
            item_id, held, busy = self.owners.get(window.key, (self.item_id, self.duration, self.busy))
            taken = bookings_on(booked, item_id, day, tz)
            hold = timedelta(minutes=max(held, 5))
            current = datetime.combine(day, window.start, tzinfo=tz)
            end = datetime.combine(day, window.end, tzinfo=tz)
            serial = 1
            while current + length <= end:
                stop = current + length
                overlapping = sum(count for start, count in taken if start < stop and start + hold > current)
                blocked = any(b_start < stop and b_end > current for b_start, b_end in busy)
                if current >= earliest and overlapping < max(1, window.capacity) and not blocked:
                    out.append(Slot(start=current, window=window, serial=serial))
                current += step
                serial += 1
        out.sort(key=lambda slot: slot.start)  # stable: on a tie the first-listed person wins
        return out

    def next_days(self, *, now: datetime, booked: Mapping[str, int], start: date | None = None, limit: int = 2) -> list[date]:
        day = start or now.date()
        last = now.date() + timedelta(days=max(0, self.horizon_days))
        found: list[date] = []
        while day <= last and len(found) < limit:
            if self.free(day, now=now, booked=booked):
                found.append(day)
            day += timedelta(days=1)
        return found


def booking_availability(slots: dict[str, Any], ctx: CallContext) -> StaffAvailability | None:
    """Free times for the chosen service with the chosen person (or anyone who does it)."""
    service = chosen_service(slots, ctx)
    if service is None:
        return None
    config = salon_config(ctx)
    wanted = str(slots.get("staff") or "")
    people = staff_for(service, ctx)
    if wanted and wanted != ANY:
        person = staff_by_ref(wanted, ctx)
        people = [person] if person is not None else []
    elif not people:
        people = ctx.items(KIND_STAFF)  # nobody is linked to this service: anyone on the team
    windows = []
    owners: dict[str, tuple[str | None, int, list[Interval]]] = {}
    for person in people:
        window = window_from_config(
            {"days": person.get("days") or [], "start": person.get("start_time"), "end": person.get("end_time"), "slot_minutes": 0, "key": person.ref}
        )
        if window is not None:
            windows.append(window)
            owners[person.ref] = (person.id, longest(person, ctx), ctx.busy_for(person.id))
    if not ctx.items(KIND_STAFF):
        window = window_from_config({"days": config.get("open_days") or [], "start": config.get("open_time"), "end": config.get("close_time"), "slot_minutes": 0})
        if window is not None:
            windows.append(window)
            owners[""] = (None, longest(None, ctx), ctx.busy_for(None))
    if not windows:
        return None
    return StaffAvailability(
        windows=windows,
        item_id=None,
        horizon_days=int(config.get("booking_horizon_days") or 30),
        lead_minutes=int(config.get("lead_minutes") if config.get("lead_minutes") is not None else 60),
        duration=duration(service),
        grid=int(config.get("slot_minutes") or 15),
        owners=owners,
    )


__all__ = ["StaffAvailability", "booking_availability", "bookings_on"]
