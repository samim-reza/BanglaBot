"""The scheduled auto-call: stored on the merchant row (survives restarts), fired by
``run_scheduler`` in the app lifespan, optionally repeating daily."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.db.session import AsyncSessionLocal
from app.models import Merchant
from app.services.dialer.batch import start_batch

logger = structlog.get_logger(__name__)

#: How often the scheduler looks for a due auto-call.
SCHEDULER_INTERVAL_SECONDS = 30.0


def next_daily(scheduled_for: datetime, now: datetime) -> datetime:
    """Same wall-clock time on the first day strictly after ``now``."""
    candidate = scheduled_for
    while candidate <= now:
        candidate += timedelta(days=1)
    return candidate


async def set_schedule(db: AsyncSession, merchant: Merchant, at: datetime, repeat_daily: bool) -> None:
    now = utcnow()
    if at <= now:
        if not repeat_daily:
            raise HTTPException(status_code=422, detail="Pick a time in the future")
        at = next_daily(at, now)
    merchant.auto_call_at = at
    merchant.auto_call_repeat_daily = bool(repeat_daily)
    await db.commit()
    await db.refresh(merchant)


async def clear_schedule(db: AsyncSession, merchant: Merchant) -> None:
    merchant.auto_call_at = None
    merchant.auto_call_repeat_daily = False
    await db.commit()
    await db.refresh(merchant)


async def fire_due_schedules(now: datetime | None = None) -> int:
    """Start a batch for every merchant whose auto-call time has arrived."""
    now = now or utcnow()
    max_late = timedelta(minutes=max(0, int(get_settings().auto_call_max_late_minutes)))
    fired = 0
    async with AsyncSessionLocal() as session:
        due = list(
            await session.scalars(
                select(Merchant).where(Merchant.auto_call_at.is_not(None), Merchant.auto_call_at <= now, Merchant.active.is_(True))
            )
        )
        for merchant in due:
            scheduled_for = merchant.auto_call_at
            # Re-arm (or clear) before dialing so a failure below can't refire every tick.
            merchant.auto_call_at = next_daily(scheduled_for, now) if merchant.auto_call_repeat_daily else None
            await session.commit()
            if scheduled_for is not None and now - scheduled_for > max_late:
                await logger.awarning("auto_call_skipped_late", merchant_id=merchant.id, scheduled_for=scheduled_for.isoformat())
                continue
            try:
                await start_batch(session, merchant, source="scheduled")
                fired += 1
            except HTTPException as exc:
                await logger.awarning("auto_call_not_started", merchant_id=merchant.id, detail=exc.detail)
    return fired


async def run_scheduler(interval: float = SCHEDULER_INTERVAL_SECONDS) -> None:
    """Lifespan task: poll for due auto-calls until cancelled."""
    await logger.ainfo("auto_call_scheduler_started", interval=interval)
    while True:
        try:
            await fire_due_schedules()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            await logger.awarning("auto_call_scheduler_tick_failed", error=str(exc))
        await asyncio.sleep(interval)
