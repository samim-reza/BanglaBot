"""Calendar months for finance reports (UTC): ``"2026-10"`` → ``[2026-10-01, 2026-11-01)``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass(frozen=True)
class Month:
    start: date
    end: date  # first day of the next month (exclusive)

    @property
    def key(self) -> str:
        return self.start.strftime("%Y-%m")

    @property
    def start_at(self) -> datetime:
        return datetime.combine(self.start, time.min, tzinfo=timezone.utc)

    @property
    def end_at(self) -> datetime:
        return datetime.combine(self.end, time.min, tzinfo=timezone.utc)

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    def elapsed_fraction(self, now: datetime | None = None) -> float:
        """0 before the month, 1 after it, the share of the month gone in between."""
        stamp = now or datetime.now(timezone.utc)
        total = (self.end_at - self.start_at).total_seconds()
        gone = (stamp - self.start_at).total_seconds()
        return max(0.0, min(1.0, gone / total))

    def as_json(self) -> dict[str, str]:
        return {"month": self.key, "period_start": self.start.isoformat(), "period_end": self.end.isoformat()}


def month_of(day: date) -> Month:
    start = day.replace(day=1)
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return Month(start, end)


def parse_month(value: str | None, *, now: datetime | None = None) -> Month:
    """``"YYYY-MM"`` (empty = this month, UTC); ``ValueError`` for anything else."""
    text = str(value or "").strip()
    if not text:
        return month_of((now or datetime.now(timezone.utc)).date())
    match = _MONTH.match(text)
    if not match or not 1 <= int(match.group(2)) <= 12 or not 2000 <= int(match.group(1)) <= 2100:
        raise ValueError("month must look like 2026-10")
    return month_of(date(int(match.group(1)), int(match.group(2)), 1))


__all__ = ["Month", "month_of", "parse_month"]
