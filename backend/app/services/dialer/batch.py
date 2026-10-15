"""Running batches: start / cancel, the dial loop (a few calls at a time, the next one as
soon as a live call settles), and the in-process registry of the latest batch per account."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.db.session import AsyncSessionLocal
from app.models import Merchant, Order, OrderStatus
from app.services import call_service
from app.services.dialer.queries import _normalize_statuses, count_eligible, eligible_order_ids
from app.services.dialer.run import BulkCallRun, serialize_run
from app.voice.twiml import PublicUrlMissing, status_callback_url

logger = structlog.get_logger(__name__)

#: How often a waiting batch re-checks for a free call slot.
SLOT_POLL_SECONDS = 3.0

#: Latest batch per merchant (finished ones stay until the next batch replaces them).
_runs: dict[str, BulkCallRun] = {}


def current_run(merchant_id: str) -> BulkCallRun | None:
    return _runs.get(merchant_id)


async def status_payload(db: AsyncSession, merchant: Merchant) -> dict[str, Any]:
    settings = get_settings()
    return {
        "eligible": await count_eligible(db, merchant.id),
        "max_concurrent": settings.bulk_call_max_concurrent,
        "max_attempts": settings.bulk_call_max_attempts,
        "run": serialize_run(current_run(merchant.id)),
        "schedule": {"at": merchant.auto_call_at, "repeat_daily": bool(merchant.auto_call_repeat_daily)},
    }


def preflight() -> None:
    """Fail the whole batch up front on the config errors every call would hit."""
    call_service.require_telephony()
    try:
        status_callback_url("preflight")
    except PublicUrlMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def start_batch(db: AsyncSession, merchant: Merchant, statuses=None, *, source: str = "manual") -> BulkCallRun:
    chosen = _normalize_statuses(statuses)
    existing = current_run(merchant.id)
    if existing is not None and existing.active:
        raise HTTPException(status_code=409, detail="A call-all run is already in progress")
    call_service.require_voice(merchant)
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
            if exc.status_code == 429:
                # All of the account's lines are busy: leave this record for the next round.
                return "skipped"
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
