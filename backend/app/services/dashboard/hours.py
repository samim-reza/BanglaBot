"""The business's working hours per weekday, for counting calls handled "after hours".

Derived from what the account already set up — no extra setting:

- clinic / dental / vet: the doctors' days and hours;
- salon: the staff's working hours (no staff list → the salon's opening hours);
- custom: the bookable resources' hours;
- restaurant: opening hours; home service: working days × arrival windows;
  real estate: viewing days and hours.

Several schedules on one weekday merge into one envelope (earliest start → latest end):
a call between two doctors' sessions is not "after hours". A schedule without days is
every day (the same rule the booking engine uses). When nothing is derivable the
default is Monday–Friday 9 AM–5 PM, business-local. The business's closure dates
(holidays) count as after hours all day.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Iterable, Mapping

from app.flows.closures import ITEM_KINDS
from app.flows.timefmt import WEEKDAY_KEYS, normalize_days, parse_time

#: ISO weekday (1 = Monday … 7 = Sunday) → (opens, closes), business-local.
Hours = dict[int, tuple[time, time]]

DEFAULT_HOURS: Hours = {day: (time(9, 0), time(17, 0)) for day in range(1, 6)}

#: Catalog kinds whose own hours are the business's hours, per vertical (the items a closure can name).
PEOPLE_KINDS: dict[str, str] = ITEM_KINDS


def _isodays(days: Iterable[Any] | None) -> list[int]:
    keys = normalize_days(days or [])
    return [WEEKDAY_KEYS.index(key) + 1 for key in keys] or list(range(1, 8))


def merge(windows: Iterable[tuple[Iterable[Any] | None, Any, Any]]) -> Hours:
    """``(days, start, end)`` schedules → one envelope per ISO weekday (bad / overnight ones skipped)."""
    hours: Hours = {}
    for days, raw_start, raw_end in windows:
        start, end = parse_time(raw_start), parse_time(raw_end)
        if start is None or end is None or end <= start:
            continue
        for day in _isodays(days):
            current = hours.get(day)
            hours[day] = (min(current[0], start), max(current[1], end)) if current else (start, end)
    return dict(sorted(hours.items()))


def _item_windows(catalog: Iterable[Any], kind: str) -> list[tuple[Any, Any, Any]]:
    return [
        (item.get("days") or [], item.get("start_time"), item.get("end_time"))
        for item in catalog
        if getattr(item, "kind", "") == kind
    ]


def _config_windows(vertical: str, config: Mapping[str, Any]) -> list[tuple[Any, Any, Any]]:
    if vertical in ("restaurant", "salon"):
        return [(config.get("open_days") or [], config.get("open_time"), config.get("close_time"))]
    if vertical == "home_service":
        windows = [raw for raw in config.get("time_windows") or [] if isinstance(raw, Mapping)]
        days = config.get("working_days") or []
        return [(days, raw.get("start"), raw.get("end")) for raw in windows]
    if vertical == "real_estate":
        return [(config.get("visit_days") or [], config.get("visit_start"), config.get("visit_end"))]
    return []


def working_hours(vertical: str, config: Mapping[str, Any], catalog: Iterable[Any] = ()) -> tuple[Hours, bool]:
    """(hours per ISO weekday, derived?) — ``derived`` is False when the 9–5 weekday default is used."""
    catalog = list(catalog)
    hours: Hours = {}
    kind = PEOPLE_KINDS.get(vertical)
    if kind:
        hours = merge(_item_windows(catalog, kind))
    if not hours:
        hours = merge(_config_windows(vertical, config))
    if not hours:
        return dict(DEFAULT_HOURS), False
    return hours, True


__all__ = ["DEFAULT_HOURS", "Hours", "PEOPLE_KINDS", "merge", "working_hours"]
