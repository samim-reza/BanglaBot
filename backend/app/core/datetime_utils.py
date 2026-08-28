"""UTC helpers. Merchants are in Bangladesh, so "today" is an Asia/Dhaka day."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MERCHANT_TIMEZONE = "Asia/Dhaka"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def today_bounds_utc() -> tuple[datetime, datetime]:
    """Start and end (exclusive) of the current Asia/Dhaka day, as aware UTC datetimes."""
    tz = ZoneInfo(MERCHANT_TIMEZONE)
    local_today = datetime.now(tz).date()
    start = datetime.combine(local_today, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
