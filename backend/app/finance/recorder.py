"""Where usage enters the ledger: a finished call / chat, a payment processor fee.

Every entry point is failure-proof — metering never breaks a call or a
payment: errors are logged and the lines are lost, nothing is raised. A call's
lines are written once (``ledger.already_metered``), in one INSERT, together
with their daily rollup. ``schedule_call`` (from the call store's
``save_usage``) runs the flush in a detached task on its own session, so the
end of a call / chat never waits on it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.finance import guard, ledger, pricebook, rollup
from app.finance.ledger import LedgerLine
from app.finance.meter import CallMeter, meter_call

logger = structlog.get_logger(__name__)

#: Session factory for the detached writers (tests swap in a fake).
session_factory: Any = None
#: Running detached flushes (a strong reference, so they aren't garbage-collected mid-way).
_pending: set[asyncio.Task[Any]] = set()


def sessions() -> Any:
    if session_factory is not None:
        return session_factory
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal


async def flush(db: AsyncSession, lines: list[LedgerLine], *, merchant_id: str, call_log_id: str | None, occurred_at: datetime) -> int:
    """Ledger lines + their daily rollup, staged in ``db`` (caller commits)."""
    if not lines:
        return 0
    rows = ledger.event_rows(lines, merchant_id=merchant_id, call_log_id=call_log_id, occurred_at=occurred_at)
    await ledger.insert_lines(db, rows)
    await rollup.upsert(db, rollup.aggregate(lines, merchant_id=merchant_id, occurred_at=occurred_at))
    return len(rows)


async def record_call(
    db: AsyncSession, log: Any, counters: dict[str, Any], *, llm_stats: Any = None, stt_usage: Any = None, tts_usage: Any = None,
) -> int:
    """Meter one finished call / chat (``log`` is its CallLog, already committed) and commit
    the lines. Returns how many lines were written; never raises."""
    try:
        if await ledger.already_metered(db, log.id):
            return 0
        occurred = utcnow()
        book = await pricebook.current(db, occurred.date())
        seconds = max(int(getattr(log, "duration_secs", 0) or 0), int(counters.get("duration_secs") or 0))
        merchant = None
        if not llm_stats:
            from app.models import Merchant

            merchant = await db.get(Merchant, log.merchant_id)
        meter = meter_call(
            book, direction=str(log.direction or ""), seconds=seconds, language=str(log.language or ""), counters=counters,
            llm_stats=llm_stats, stt_usage=stt_usage, tts_usage=tts_usage, merchant=merchant,
        )
        if not meter.lines:
            return 0
        count = await flush(db, meter.lines, merchant_id=str(log.merchant_id), call_log_id=str(log.id), occurred_at=occurred)
        await db.commit()
        guard.record_spend(meter.lines)
        if meter.unpriced:
            await logger.ainfo("usage_unpriced", call_log_id=log.id, skus=sorted(set(meter.unpriced)))
        return count
    except Exception as exc:  # noqa: BLE001 — metering never breaks a call
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        await logger.awarning("usage_meter_failed", call_log_id=getattr(log, "id", ""), error=str(exc)[:200], error_type=type(exc).__name__)
        return 0


async def record_call_log(call_log_id: str, counters: dict[str, Any], *, llm_stats: Any = None, stt_usage: Any = None, tts_usage: Any = None) -> int:
    """``record_call`` on a session of its own, for the call log ``call_log_id``. Never raises."""
    try:
        from app.models import CallLog

        async with sessions()() as session:
            log = await session.get(CallLog, call_log_id)
            if log is None:
                return 0
            return await record_call(session, log, counters, llm_stats=llm_stats, stt_usage=stt_usage, tts_usage=tts_usage)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("usage_meter_failed", call_log_id=call_log_id, error=str(exc)[:200], error_type=type(exc).__name__)
        return 0


def schedule_call(call_log_id: str, counters: dict[str, Any], *, llm_stats: Any = None, stt_usage: Any = None, tts_usage: Any = None) -> None:
    """Meter a finished call in the background (no running loop: skipped). Never raises."""
    try:
        task = asyncio.get_running_loop().create_task(
            record_call_log(call_log_id, dict(counters), llm_stats=llm_stats, stt_usage=stt_usage, tts_usage=tts_usage)
        )
    except RuntimeError:
        return
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def record_payment_fee(payment: Any) -> int:
    """The processor's fee on a paid platform payment (Stripe). Never raises."""
    if getattr(payment, "provider", "") != "stripe" or getattr(payment, "status", "") != "paid":
        return 0
    try:
        async with sessions()() as session:
            occurred = utcnow()
            meter = CallMeter(await pricebook.current(session, occurred.date()))
            meter.add_payment_fee(payment.amount, payment.currency, meta={"payment_id": str(payment.id)})
            count = await flush(session, meter.lines, merchant_id=str(payment.merchant_id or ""), call_log_id=None, occurred_at=occurred)
            await session.commit()
        guard.record_spend(meter.lines)
        return count
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("payment_fee_meter_failed", payment_id=getattr(payment, "id", ""), error=str(exc)[:200])
        return 0


__all__ = ["flush", "record_call", "record_call_log", "record_payment_fee", "schedule_call"]
