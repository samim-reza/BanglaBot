"""The dashboard's aggregate SQL: one single-row query per table, always scoped to one account.

Every statement filters ``merchant_id`` first (indexed on both tables) and the time range
second, and returns counts through ``COUNT(*) FILTER (WHERE …)`` — the rows are never
loaded into Python. Test traffic (portal browser calls ``web`` / text tests ``chat``,
records with source ``test``) is never counted.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Time, and_, cast, exists, extract, false, func, literal, not_, or_, select
from sqlalchemy.sql import ColumnElement, Select

from app.models import CallLog, Order, OrderStatus
from app.services.dashboard.hours import Hours

INBOUND = "inbound"
OUTBOUND = "outbound"
#: Billable phone directions / chat channels (the same split as the usage meter).
VOICE_DIRECTIONS = (INBOUND, OUTBOUND)
CHAT_DIRECTIONS = ("widget", "whatsapp", "messenger", "instagram")
REAL_DIRECTIONS = (*VOICE_DIRECTIONS, *CHAT_DIRECTIONS)
#: Final call statuses of a call nobody spoke on (``app.services.calls.policy.FAILED_CALL_STATUSES``).
UNANSWERED_STATUSES = ("no-answer", "busy", "failed", "canceled")
#: Record sources written by the agent (calls and chats); manual / import / test records are the owner's.
AGENT_SOURCES = ("inbound_call", "outbound_call", "website_chat", "whatsapp", "messenger", "instagram")
#: Record kinds that are a message or a lead, not a booking / order.
LEAD_KINDS = ("lead", "message")

URGENT_OUTCOMES = ("transfer", "emergency")
NO_ANSWER_OUTCOMES = ("no_answer", "auto_dropped", "diverted", "voicemail")
CANCEL_OUTCOMES = ("cancelled", "not_interested")
REVIEW_OUTCOMES = ("transfer", "wrong_number", "relay", "unclear", "lead", "emergency")


def in_hours(local: ColumnElement, hours: Hours, closed: list[tuple[date, date]] | None = None) -> ColumnElement:
    """``local`` (a business-local timestamp) falls inside ``hours`` — one OR of ≤ 7 weekday ranges —
    and not on a closure date (``closed``: the business's (start, end) days, both included)."""
    if not hours:
        return false()
    weekday = extract("isodow", local)
    clock = cast(local, Time)
    open_now = or_(*[and_(weekday == day, clock >= opens, clock < closes) for day, (opens, closes) in hours.items()])
    if not closed:
        return open_now
    day_of = cast(local, Date)
    return and_(open_now, not_(or_(*[day_of.between(start, end) for start, end in closed])))


def local_time(tz: str) -> ColumnElement:
    """``call_logs.created_at`` on the business's wall clock (``timezone(zone, timestamptz)``)."""
    return func.timezone(literal(tz), CallLog.created_at)


def call_stats(
    merchant_id: str, start: datetime, end: datetime, *, tz: str, hours: Hours, outbound: bool, closed: list[tuple[date, date]] | None = None
) -> Select:
    """One row: what the agent did on calls and chats in [start, end).

    - ``calls_answered``  inbound calls that reached the agent (not busy / failed / no-answer / canceled);
    - ``chats_handled``   chats on a real channel where the customer wrote something;
    - ``after_hours``     answered inbound calls outside ``hours`` or on a closure day (business-local);
    - ``transfers_urgent`` conversations ending in a transfer to a person or an emergency;
    - ``voice_secs`` / ``avg_secs`` phone seconds (inbound + outbound) / average of calls that lasted;
    - ``out_*``           outbound calls placed and how they ended (only when ``outbound``).
    """
    answered = and_(CallLog.direction == INBOUND, CallLog.call_status.not_in(UNANSWERED_STATUSES))
    voice = CallLog.direction.in_(VOICE_DIRECTIONS)
    chat = and_(CallLog.direction.in_(CHAT_DIRECTIONS), CallLog.transcript.like("%Customer:%"))
    columns: list[ColumnElement] = [
        func.count().filter(answered).label("calls_answered"),
        func.count().filter(chat).label("chats_handled"),
        func.count().filter(and_(answered, not_(in_hours(local_time(tz), hours, closed)))).label("after_hours"),
        func.count().filter(CallLog.outcome.in_(URGENT_OUTCOMES)).label("transfers_urgent"),
        func.coalesce(func.sum(CallLog.duration_secs).filter(voice), 0).label("voice_secs"),
        func.avg(CallLog.duration_secs).filter(and_(voice, CallLog.duration_secs > 0)).label("avg_secs"),
    ]
    if outbound:
        placed = CallLog.direction == OUTBOUND
        no_answer = or_(CallLog.outcome.in_(NO_ANSWER_OUTCOMES), CallLog.call_status.in_(UNANSWERED_STATUSES))
        columns += [
            func.count().filter(placed).label("out_calls"),
            func.count().filter(and_(placed, CallLog.outcome == "confirmed")).label("out_confirmed"),
            func.count().filter(and_(placed, CallLog.outcome.in_(CANCEL_OUTCOMES))).label("out_cancelled"),
            func.count().filter(and_(placed, no_answer)).label("out_no_answer"),
            func.count().filter(and_(placed, CallLog.outcome == "rescheduled")).label("out_rescheduled"),
            func.count().filter(and_(placed, CallLog.outcome.in_(REVIEW_OUTCOMES))).label("out_needs_review"),
        ]
    return select(*columns).where(
        CallLog.merchant_id == merchant_id,
        CallLog.created_at >= start,
        CallLog.created_at < end,
        CallLog.direction.in_(REAL_DIRECTIONS),
    )


def record_stats(merchant_id: str, start: datetime, end: datetime) -> Select:
    """One row: records the agent created in [start, end).

    - ``bookings`` / ``bookings_value`` bookings and orders (any kind but lead / message — or a lead
      with a time, i.e. a site visit) that are not cancelled, and the sum of their amounts;
    - ``messages_leads`` messages and leads without a time.
    """
    lead_kind = Order.kind.in_(LEAD_KINDS)
    booking = and_(Order.status != OrderStatus.cancelled, or_(not_(lead_kind), Order.scheduled_at.is_not(None)))
    lead = and_(lead_kind, Order.scheduled_at.is_(None))
    return select(
        func.count().filter(booking).label("bookings"),
        func.coalesce(func.sum(Order.total_amount).filter(booking), 0).label("bookings_value"),
        func.count().filter(lead).label("messages_leads"),
    ).where(
        Order.merchant_id == merchant_id,
        Order.created_at >= start,
        Order.created_at < end,
        Order.source.in_(AGENT_SOURCES),
    )


def ran_outbound(merchant_id: str, since: datetime) -> Select:
    """Whether the account placed any outbound call since ``since`` (an EXISTS, no rows read)."""
    return select(
        exists().where(CallLog.merchant_id == merchant_id, CallLog.direction == OUTBOUND, CallLog.created_at >= since)
    )


__all__ = [
    "AGENT_SOURCES",
    "CHAT_DIRECTIONS",
    "LEAD_KINDS",
    "UNANSWERED_STATUSES",
    "VOICE_DIRECTIONS",
    "call_stats",
    "in_hours",
    "local_time",
    "ran_outbound",
    "record_stats",
]
