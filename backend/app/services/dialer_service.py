"""Bulk dialer: "Call all" batches and the scheduled auto-call.

A batch dials every order that still needs a confirmation call, a few at a
time (``bulk_call_max_concurrent``), starting the next one as soon as a live
call settles. Batches are in-process state (one per merchant, the latest one
is kept for the progress view); the schedule itself lives on the merchant row
so it survives restarts and fires from ``run_scheduler`` in the app lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.db.session import AsyncSessionLocal
from app.models import Merchant, Order, OrderStatus
from app.models.order import CALLABLE_STATUSES
from app.services import call_service
from app.voice.twiml import PublicUrlMissing, status_callback_url

logger = structlog.get_logger(__name__)

#: What "everyone who needs a call" means unless the caller says otherwise.
#: ``needs_review`` is left out: those orders want a human look, not a retry.
DEFAULT_BATCH_STATUSES: tuple[OrderStatus, ...] = (OrderStatus.pending, OrderStatus.no_answer)
ACTIVE_STATES = frozenset({"queued", "running"})
#: How often a waiting batch re-checks for a free call slot.
SLOT_POLL_SECONDS = 3.0
#: How often the scheduler looks for a due auto-call.
SCHEDULER_INTERVAL_SECONDS = 30.0


@dataclass
class BulkCallRun:
    merchant_id: str
    order_ids: list[str]
    statuses: tuple[OrderStatus, ...]
    source: str = "manual"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: str = "queued"  # queued | running | done | cancelled | failed
    started: int = 0
    failed: int = 0
    skipped: int = 0
    error: str = ""
    created_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    @property
    def total(self) -> int:
        return len(self.order_ids)

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_STATES


#: Latest batch per merchant (finished ones stay until the next batch replaces them).
_runs: dict[str, BulkCallRun] = {}


# ------------------------------------------------------------------ queries
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


def current_run(merchant_id: str) -> BulkCallRun | None:
    return _runs.get(merchant_id)


def serialize_run(run: BulkCallRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "state": run.state,
        "source": run.source,
        "total": run.total,
        "started": run.started,
        "failed": run.failed,
        "skipped": run.skipped,
        "error": run.error,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
    }


async def status_payload(db: AsyncSession, merchant: Merchant) -> dict[str, Any]:
    settings = get_settings()
    return {
        "eligible": await count_eligible(db, merchant.id),
        "max_concurrent": settings.bulk_call_max_concurrent,
        "max_attempts": settings.bulk_call_max_attempts,
        "run": serialize_run(current_run(merchant.id)),
        "schedule": {"at": merchant.auto_call_at, "repeat_daily": bool(merchant.auto_call_repeat_daily)},
    }


# ------------------------------------------------------------------ batches
def preflight() -> None:
    """Fail the whole batch up front on the config errors every call would hit."""
    settings = get_settings()
    if not settings.twilio_from_number:
        raise HTTPException(status_code=500, detail="TWILIO_FROM_NUMBER is not configured")
    call_service.twilio_client()
    try:
        status_callback_url("preflight")
    except PublicUrlMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def start_batch(db: AsyncSession, merchant: Merchant, statuses=None, *, source: str = "manual") -> BulkCallRun:
    chosen = _normalize_statuses(statuses)
    existing = current_run(merchant.id)
    if existing is not None and existing.active:
        raise HTTPException(status_code=409, detail="A call-all run is already in progress")
    preflight()
    order_ids = await eligible_order_ids(db, merchant.id, chosen)
    if not order_ids:
        raise HTTPException(status_code=409, detail="Nothing needs a call right now")
    run = BulkCallRun(merchant_id=merchant.id, order_ids=order_ids, statuses=chosen, source=source)
    _runs[merchant.id] = run
    run.task = asyncio.create_task(_run_batch(run), name=f"bulk-call:{run.id}")
    await logger.ainfo("bulk_call_started", run_id=run.id, merchant_id=merchant.id, total=run.total, source=source)
    return run


async def cancel_batch(merchant_id: str) -> BulkCallRun | None:
    """Stop dialing new orders; calls already ringing are left to finish."""
    run = current_run(merchant_id)
    if run is None or not run.active:
        return run
    run.cancel_event.set()
    return run


async def _live_calls(merchant_id: str) -> int:
    """Orders mid-call for this merchant, after settling any stuck ones."""
    async with AsyncSessionLocal() as session:
        merchant = await session.get(Merchant, merchant_id)
        if merchant is not None:
            await call_service.reconcile_stale_calls(session, merchant)
        count = await session.scalar(
            select(func.count()).select_from(Order).where(Order.merchant_id == merchant_id, Order.status == OrderStatus.calling)
        )
        return int(count or 0)


class BatchAborted(Exception):
    """A per-call error that would hit every remaining order too."""


async def _dial_one(run: BulkCallRun, order_id: str) -> str:
    """Place one call from a fresh session. Returns started | skipped | failed."""
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id)
        merchant = await session.get(Merchant, run.merchant_id)
        if order is None or merchant is None or not merchant.active:
            return "skipped"
        # The row may have moved on (manual call, edit, delete) since the batch was queued.
        if order.status not in run.statuses:
            return "skipped"
        try:
            await call_service.start_outbound_call(session, order, merchant)
        except HTTPException as exc:
            if exc.status_code == 500:
                raise BatchAborted(str(exc.detail)) from exc
            await logger.awarning("bulk_call_order_failed", run_id=run.id, order_id=order_id, detail=exc.detail)
            return "failed"
        except Exception as exc:  # noqa: BLE001 — one bad number must not stop the batch
            await logger.awarning("bulk_call_order_failed", run_id=run.id, order_id=order_id, error=str(exc))
            return "failed"
        return "started"


async def _wait_for_slot(run: BulkCallRun) -> bool:
    """Block until fewer than ``max_concurrent`` calls are live. False when cancelled."""
    limit = max(1, int(get_settings().bulk_call_max_concurrent))
    while not run.cancel_event.is_set():
        try:
            live = await _live_calls(run.merchant_id)
        except Exception as exc:  # noqa: BLE001 — a DB hiccup just delays the next dial
            await logger.awarning("bulk_call_slot_check_failed", run_id=run.id, error=str(exc))
            live = limit
        if live < limit:
            return True
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(run.cancel_event.wait(), timeout=SLOT_POLL_SECONDS)
    return False


async def _run_batch(run: BulkCallRun) -> None:
    run.state = "running"
    gap = max(0.0, float(get_settings().bulk_call_gap_seconds))
    try:
        for order_id in run.order_ids:
            if not await _wait_for_slot(run):
                run.state = "cancelled"
                break
            result = await _dial_one(run, order_id)
            if result == "started":
                run.started += 1
            elif result == "failed":
                run.failed += 1
            else:
                run.skipped += 1
            if gap and result == "started":
                await asyncio.sleep(gap)
        else:
            run.state = "done"
    except asyncio.CancelledError:
        run.state = "cancelled"
    except BatchAborted as exc:
        run.state = "failed"
        run.error = str(exc)
    except Exception as exc:  # noqa: BLE001
        run.state = "failed"
        run.error = str(exc)
        await logger.awarning("bulk_call_crashed", run_id=run.id, error=str(exc))
    finally:
        run.finished_at = utcnow()
        await logger.ainfo(
            "bulk_call_finished",
            run_id=run.id,
            merchant_id=run.merchant_id,
            state=run.state,
            started=run.started,
            failed=run.failed,
            skipped=run.skipped,
            error=run.error,
        )


# ---------------------------------------------------------------- schedule
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
