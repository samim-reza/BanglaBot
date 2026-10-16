"""Dates for scenario personas, relative to the pinned business-local "now"."""

from __future__ import annotations

from datetime import date, datetime, timedelta

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def next_weekday(now: datetime, weekday: str) -> date:
    """The first ``weekday`` strictly after today."""
    target = WEEKDAYS.index(weekday[:3].lower())
    ahead = (target - now.weekday()) % 7 or 7
    return now.date() + timedelta(days=ahead)


def say_day(now: datetime, weekday: str) -> str:
    """'Tuesday, October 20' for the first Tuesday after today."""
    day = next_weekday(now, weekday)
    return f"{day:%A}, {day:%B} {day.day}"


def pinned_now(tz) -> datetime:  # noqa: ANN001
    """A weekday morning: today 09:30 business time, or the next Monday when today is a weekend."""
    today = datetime.now(tz)
    if today.weekday() >= 5:
        today += timedelta(days=7 - today.weekday())
    return today.replace(hour=9, minute=30, second=0, microsecond=0)
