"""Unpaid holds and stale links: the payments sweep.

An online-required booking is ``pending`` with its slot taken until it is paid;
``release_expired_holds`` frees the slot (record → cancelled, payment →
expired) once ``hold_until`` passes. ``expire_stale_links`` closes links past
``expires_at`` without touching the booking. Both are idempotent (only
``pending`` payments move) and safe to run from several workers
(``FOR UPDATE SKIP LOCKED``).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.core.datetime_utils import utcnow
from app.models import Order, Payment
from app.services.payments import records
from app.services.payments.base import STATUS_EXPIRED, STATUS_PENDING
from app.services.payments.service import sessions

logger = structlog.get_logger(__name__)

BATCH = 200


def should_release(record: Any, payment: Payment) -> bool:
    """The booking still waits on exactly this payment."""
    return (
        records.holds_slot(record)
        and str(getattr(record, "payment_ref", "") or "") == str(payment.id)
        and getattr(record, "payment_status", "") == STATUS_PENDING
    )


async def release_expired_holds(*, now: datetime | None = None, limit: int = BATCH) -> list[tuple[str, str]]:
    """Release every unpaid booking whose hold ran out; ``[(merchant_id, record_id)]`` released."""
    stamp = now or utcnow()
    released: list[tuple[str, str]] = []
    async with sessions()() as session:
        rows = list(
            await session.scalars(
                select(Payment)
                .where(Payment.status == STATUS_PENDING, Payment.order_id.is_not(None), Payment.hold_until.is_not(None), Payment.hold_until <= stamp)
                .order_by(Payment.hold_until)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for payment in rows:
            payment.status = STATUS_EXPIRED
            payment.updated_at = stamp
            payment.meta = {**(payment.meta or {}), "expired_by": "hold"}
            record = await session.get(Order, payment.order_id)
            if record is None:
                continue
            if should_release(record, payment):
                records.apply_release(record, stamp)
                released.append((str(record.merchant_id), str(record.id)))
            elif record.payment_ref == payment.id and record.payment_status == STATUS_PENDING:
                records.apply_payment_status(record, STATUS_EXPIRED)
        if rows:
            await session.commit()
    if released:
        from app.services import notification_service

        for merchant_id, record_id in released:
            # Cancellation text (when the account sends them) + calendar mirror.
            notification_service.after_outcome(merchant_id, record_id, "cancelled")
        await logger.ainfo("payment_holds_released", count=len(released))
    return released


async def expire_stale_links(*, now: datetime | None = None, limit: int = BATCH) -> int:
    """Close pending links past ``expires_at`` (holds are the sweep above's job)."""
    stamp = now or utcnow()
    async with sessions()() as session:
        rows = list(
            await session.scalars(
                select(Payment)
                .where(Payment.status == STATUS_PENDING, Payment.hold_until.is_(None), Payment.expires_at.is_not(None), Payment.expires_at <= stamp)
                .order_by(Payment.expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for payment in rows:
            payment.status = STATUS_EXPIRED
            payment.updated_at = stamp
            payment.meta = {**(payment.meta or {}), "expired_by": "link"}
            if payment.order_id:
                record = await session.get(Order, payment.order_id)
                if record is not None and record.payment_ref == payment.id and record.payment_status == STATUS_PENDING:
                    records.apply_payment_status(record, STATUS_EXPIRED)
        if rows:
            await session.commit()
    return len(rows)


async def sweep(now: datetime | None = None) -> dict[str, int]:
    released = await release_expired_holds(now=now)
    expired = await expire_stale_links(now=now)
    return {"released": len(released), "expired": expired}


async def run_sweeper(interval: float | None = None) -> None:
    """Lifespan task: sweep every ``PAYMENT_SWEEP_INTERVAL_SECONDS`` until cancelled."""
    from app.services.payments.config import get_payment_settings

    every = max(15.0, float(interval or get_payment_settings().payment_sweep_interval_seconds))
    while True:
        await asyncio.sleep(every)
        try:
            await sweep()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            await logger.awarning("payment_sweep_failed", error=str(exc)[:200])


__all__ = ["expire_stale_links", "release_expired_holds", "run_sweeper", "should_release", "sweep"]
