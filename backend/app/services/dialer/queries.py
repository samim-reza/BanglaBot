"""Which records a batch dials: callable status, not dialed too often, not a message,
and not already in the past."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.models import Order, OrderStatus
from app.models.order import CALLABLE_STATUSES

#: What "everyone who needs a call" means unless the caller says otherwise.
#: ``needs_review`` is left out: those orders want a human look, not a retry.
DEFAULT_BATCH_STATUSES: tuple[OrderStatus, ...] = (OrderStatus.pending, OrderStatus.no_answer)


def _normalize_statuses(statuses: list[OrderStatus] | tuple[OrderStatus, ...] | None) -> tuple[OrderStatus, ...]:
    chosen = tuple(dict.fromkeys(statuses or DEFAULT_BATCH_STATUSES))
    bad = [status.value for status in chosen if status not in CALLABLE_STATUSES]
    if bad:
        raise HTTPException(status_code=422, detail=f"cannot batch-call orders in status: {', '.join(bad)}")
    return chosen


def eligible_statement(merchant_id: str, statuses: tuple[OrderStatus, ...]):
    """Records a batch would dial: right status, not dialed too often, not a
    message, and — for appointments / bookings / viewings — not already past."""
    return select(Order).where(
        Order.merchant_id == merchant_id,
        Order.status.in_(statuses),
        Order.call_attempts < get_settings().bulk_call_max_attempts,
        Order.kind != "message",
        or_(Order.scheduled_at.is_(None), Order.scheduled_at > utcnow()),
    )


async def count_eligible(db: AsyncSession, merchant_id: str, statuses=None) -> int:
    stmt = eligible_statement(merchant_id, _normalize_statuses(statuses))
    return int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


async def eligible_order_ids(db: AsyncSession, merchant_id: str, statuses: tuple[OrderStatus, ...]) -> list[str]:
    # Oldest first: the customers who have waited longest are called first.
    rows = await db.scalars(eligible_statement(merchant_id, statuses).order_by(Order.created_at.asc()))
    return [order.id for order in rows]
