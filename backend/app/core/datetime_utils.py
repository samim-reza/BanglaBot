"""UTC helpers. Platform-wide "today" (admin overview) is a UTC day; each
account's own clock comes from its time zone (see flows/timefmt.py)."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

#: Kept for the dialer's legacy auto-call math and older call sites.
MERCHANT_TIMEZONE = "Asia/Dhaka"
PLATFORM_TIMEZONE = "UTC"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def today_bounds_utc(timezone_name: str = PLATFORM_TIMEZONE) -> tuple[datetime, datetime]:
    """Start and end (exclusive) of the current day in ``timezone_name``, as aware UTC datetimes."""
    tz = ZoneInfo(timezone_name)
    local_today = datetime.now(tz).date()
    start = datetime.combine(local_today, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
