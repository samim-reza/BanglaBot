"""iCalendar (RFC 5545) in both directions, dependency-free.

- :func:`build_calendar` — the account's bookings as a feed Google Calendar,
  Outlook and Apple Calendar can subscribe to ("Add calendar → From URL").
- :func:`busy_intervals` — the busy times in someone's calendar feed (e.g. a
  doctor's Google "secret address in iCal format"), so the agent never offers a
  time they are not free. Handles all-day events, TZID / UTC / floating times,
  ``TRANSP:TRANSPARENT`` (free) events, cancelled events, and the recurrence
  rules real calendars use (DAILY / WEEKLY with BYDAY, MONTHLY, INTERVAL,
  COUNT, UNTIL, EXDATE).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Iterable

from app.flows.timefmt import business_tz

# ------------------------------------------------------------------------------ export
_PRODID = "-//BanglaBot//Voice Agent Bookings//EN"


def _escape(text: str) -> str:
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts: list[str] = []
    current = b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class FeedEvent:
    uid: str
    start: datetime
    end: datetime
    summary: str
    description: str = ""
    location: str = ""
    status: str = "CONFIRMED"  # CONFIRMED | TENTATIVE | CANCELLED
    updated: datetime | None = None


def build_calendar(name: str, events: Iterable[FeedEvent], *, timezone_name: str = "UTC") -> str:
    now = _utc(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        f"X-WR-TIMEZONE:{timezone_name}",
        # Ask subscribers to refresh often (Google decides on its own, ~every few hours).
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
        "X-PUBLISHED-TTL:PT15M",
    ]
    for event in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event.uid}",
            f"DTSTAMP:{_utc(event.updated) if event.updated else now}",
            f"DTSTART:{_utc(event.start)}",
            f"DTEND:{_utc(event.end)}",
            f"SUMMARY:{_escape(event.summary)}",
            f"STATUS:{event.status}",
        ]
        if event.description:
            lines.append(f"DESCRIPTION:{_escape(event.description)}")
        if event.location:
            lines.append(f"LOCATION:{_escape(event.location)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


# ------------------------------------------------------------------------------ import
@dataclass
class _Prop:
    name: str
    params: dict[str, str]
    value: str


@dataclass
class _Event:
    props: dict[str, list[_Prop]] = field(default_factory=dict)

    def first(self, name: str) -> _Prop | None:
        values = self.props.get(name)
        return values[0] if values else None


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _parse_line(line: str) -> _Prop | None:
    if ":" not in line:
        return None
    head, value = line.split(":", 1)
    parts = head.split(";")
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, val = part.split("=", 1)
            params[key.upper()] = val.strip('"')
    return _Prop(parts[0].upper(), params, value)


def _events(text: str) -> list[_Event]:
    events: list[_Event] = []
    current: _Event | None = None
    depth = 0
    for line in _unfold(text):
        prop = _parse_line(line)
        if prop is None:
            continue
        if prop.name == "BEGIN":
            if prop.value.upper() == "VEVENT":
                current = _Event()
                depth = 0
            elif current is not None:
                depth += 1  # nested VALARM etc.
            continue
        if prop.name == "END":
            if prop.value.upper() == "VEVENT" and current is not None:
                events.append(current)
                current = None
            elif current is not None and depth:
                depth -= 1
            continue
        if current is not None and depth == 0:
            current.props.setdefault(prop.name, []).append(prop)
    return events


def _zone(name: str | None, fallback: tzinfo) -> tzinfo:
    if not name:
        return fallback
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 — Windows zone names etc.: use the business zone
        return fallback


def _when(prop: _Prop, fallback: tzinfo) -> tuple[datetime, bool]:
    """(aware datetime, all_day)."""
    value = prop.value.strip()
    if prop.params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        day = datetime.strptime(value[:8], "%Y%m%d").date()
        return datetime.combine(day, time.min, tzinfo=fallback), True
    if value.endswith("Z"):
        return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc), False
    naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    return naive.replace(tzinfo=_zone(prop.params.get("TZID"), fallback)), False


_DURATION_RE = re.compile(r"^(-)?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def _duration(value: str) -> timedelta | None:
    match = _DURATION_RE.match(value.strip())
    if not match:
        return None
    sign, weeks, days, hours, minutes, seconds = match.groups()
    delta = timedelta(
        weeks=int(weeks or 0), days=int(days or 0), hours=int(hours or 0), minutes=int(minutes or 0), seconds=int(seconds or 0)
    )
    return -delta if sign else delta


_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _occurrences(start: datetime, rule: str, window_end: datetime, exdates: set[datetime], limit: int = 2000) -> Iterable[datetime]:
    parts = dict(item.split("=", 1) for item in rule.split(";") if "=" in item)
    freq = parts.get("FREQ", "").upper()
    interval = max(1, int(parts.get("INTERVAL", "1") or 1))
    count = int(parts["COUNT"]) if parts.get("COUNT", "").isdigit() else None
    until: datetime | None = None
    if parts.get("UNTIL"):
        raw = parts["UNTIL"]
        try:
            if raw.endswith("Z"):
                until = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            elif "T" in raw:
                until = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").replace(tzinfo=start.tzinfo)
            else:
                until = datetime.combine(datetime.strptime(raw[:8], "%Y%m%d").date(), time.max, tzinfo=start.tzinfo)
        except ValueError:
            until = None
    byday = [_WEEKDAYS[d[-2:]] for d in parts.get("BYDAY", "").split(",") if d[-2:] in _WEEKDAYS]
    emitted = 0
    produced = 0
    if freq == "WEEKLY":
        days = sorted(set(byday or [start.weekday()]))
        week_start = start - timedelta(days=start.weekday())
        week = 0
        while produced < limit:
            base = week_start + timedelta(weeks=week * interval)
            for weekday in days:
                occurrence = base + timedelta(days=weekday)
                if occurrence < start:
                    continue
                if (until and occurrence > until) or occurrence > window_end:
                    return
                emitted += 1
                if occurrence not in exdates:
                    produced += 1
                    yield occurrence
                if count and emitted >= count:
                    return
            week += 1
        return
    step = {"DAILY": timedelta(days=interval)}.get(freq)
    occurrence = start
    index = 0
    while produced < limit:
        if freq == "MONTHLY":
            month = start.month - 1 + index * interval
            year = start.year + month // 12
            try:
                occurrence = start.replace(year=year, month=month % 12 + 1)
            except ValueError:  # the 31st in a short month: skipped, as RFC 5545 says
                index += 1
                continue
        elif freq == "YEARLY":
            try:
                occurrence = start.replace(year=start.year + index * interval)
            except ValueError:
                index += 1
                continue
        elif step is not None:
            occurrence = start + step * index
        else:
            return
        if (until and occurrence > until) or occurrence > window_end:
            return
        if byday and freq == "DAILY" and occurrence.weekday() not in byday:
            index += 1
            continue
        emitted += 1
        if occurrence not in exdates:
            produced += 1
            yield occurrence
        if count and emitted >= count:
            return
        index += 1


def busy_intervals(text: str, *, window_start: datetime, window_end: datetime, timezone_name: str | None = None) -> list[tuple[datetime, datetime]]:
    """Busy (start, end) intervals overlapping the window, sorted and merged."""
    fallback = business_tz(timezone_name)
    intervals: list[tuple[datetime, datetime]] = []
    for event in _events(text):
        if (event.first("STATUS") and event.first("STATUS").value.upper() == "CANCELLED") or (  # type: ignore[union-attr]
            event.first("TRANSP") and event.first("TRANSP").value.upper() == "TRANSPARENT"  # type: ignore[union-attr]
        ):
            continue
        dtstart = event.first("DTSTART")
        if dtstart is None:
            continue
        try:
            start, all_day = _when(dtstart, fallback)
        except ValueError:
            continue
        end: datetime | None = None
        if event.first("DTEND") is not None:
            try:
                end, _ = _when(event.first("DTEND"), fallback)  # type: ignore[arg-type]
            except ValueError:
                end = None
        elif event.first("DURATION") is not None:
            delta = _duration(event.first("DURATION").value)  # type: ignore[union-attr]
            end = start + delta if delta else None
        if end is None:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
        length = end - start
        if length <= timedelta(0):
            continue
        exdates: set[datetime] = set()
        for prop in event.props.get("EXDATE", []):
            for raw in prop.value.split(","):
                try:
                    exdates.add(_when(_Prop("EXDATE", prop.params, raw), fallback)[0])
                except ValueError:
                    pass
        rule = event.first("RRULE")
        starts = _occurrences(start, rule.value, window_end, exdates) if rule else [start]
        for occurrence in starts:
            occurrence_end = occurrence + length
            if occurrence_end > window_start and occurrence < window_end:
                intervals.append((occurrence, occurrence_end))
    return merge(intervals)


def merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


__all__ = ["FeedEvent", "build_calendar", "busy_intervals", "merge"]
