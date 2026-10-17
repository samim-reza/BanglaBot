"""``GET /api/dashboard/summary``: what the agent did for the business over a period."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RangeKey = Literal["today", "7d", "30d"]
RANGES: tuple[str, ...] = ("today", "7d", "30d")


class OutboundSummary(BaseModel):
    """Calls the business placed (confirmations, reminders) in the period, and how they ended."""

    calls: int = 0
    confirmed: int = 0
    #: Cancelled or not interested.
    cancelled: int = 0
    #: Nobody answered: no answer, busy, failed, voicemail, dropped.
    no_answer: int = 0
    rescheduled: int = 0
    #: Unclear, wrong number, relayed, transferred, lead, emergency.
    needs_review: int = 0
    #: Every record by status right now (pending, calling, confirmed, …, total) — the status tiles.
    statuses: dict[str, int] = {}


class DashboardSummary(BaseModel):
    range: RangeKey
    #: The period, [start, end) — ``today`` starts at the business's local midnight.
    start: datetime
    end: datetime
    timezone: str
    currency: str
    #: The account's agent mostly answers (False: outbound-first, e.g. order confirmations).
    inbound_first: bool
    calls_answered: int = 0
    chats_handled: int = 0
    #: Bookings / orders the agent created (not cancelled) and the sum of their amounts.
    bookings: int = 0
    bookings_value: float = 0.0
    messages_leads: int = 0
    #: Answered inbound calls outside working hours.
    after_hours: int = 0
    #: True when working hours come from the account's schedule; False = the weekday 9–5 default.
    hours_known: bool = False
    transfers_urgent: int = 0
    avg_call_secs: int = 0
    minutes_used: float = 0.0
    #: Present only for accounts that place outbound calls.
    outbound: OutboundSummary | None = None


__all__ = ["DashboardSummary", "OutboundSummary", "RANGES", "RangeKey"]
