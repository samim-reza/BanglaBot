"""Telnyx callbacks (call status, answering-machine verdict, recordings) and the
fallback that settles records whose status callback never arrived."""

from __future__ import annotations

from datetime import timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.flows.base import OUTCOME_STATUS, OUTCOME_VOICEMAIL, UNANSWERED_OUTCOMES
from app.models import CallLog, Merchant, Order, OrderStatus
from app.services import telnyx
from app.services.calls.control import complete_call
from app.services.calls.policy import FAILED_CALL_STATUSES, LIVE_CALL_STATUSES, STALE_CALL_GRACE_SECONDS, call_time_limit

logger = structlog.get_logger(__name__)

#: A status callback's CallDuration outside 1 s … 24 h is ignored (forged / garbage values).
MAX_CALLBACK_DURATION_SECS = 24 * 3600
MACHINE_ANSWERS = ("machine", "machine_start", "machine_end_beep", "machine_end_silence", "machine_end_other", "fax")


def _settle_from_call_status(order: Order, log: CallLog | None, call_status: str) -> None:
    """Map a final call status onto a record still in ``calling``."""
    if order.status != OrderStatus.calling:
        return
    outcome = (log.outcome if log else "") or ""
    if call_status in FAILED_CALL_STATUSES:
        order.status = OrderStatus.no_answer
    elif outcome in UNANSWERED_OUTCOMES:
        order.status = OrderStatus.no_answer
    elif not outcome:
        order.status = OrderStatus.needs_review
    else:
        # The agent already wrote the final status when the outcome landed;
        # a lingering "calling" here means that write raced the callback.
        order.status = OrderStatus(OUTCOME_STATUS.get(outcome) or "needs_review")


async def apply_status_callback(db: AsyncSession, order_id: str, call_sid: str, call_status: str, duration: int) -> None:
    order = await db.get(Order, order_id)
    log = None
    if call_sid:
        # Bound to the signed URL's order: a body CallSid can't reach another call's log.
        log = await db.scalar(select(CallLog).where(CallLog.twilio_call_sid == telnyx.sid_key(call_sid), CallLog.order_id == order_id))
    if log is None and order is not None:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order.id).order_by(CallLog.created_at.desc()).limit(1)
        )
    if log is not None:
        if call_sid and not log.twilio_call_sid:
            log.twilio_call_sid = telnyx.sid_key(call_sid)
        log.call_status = call_status or log.call_status
        if duration and 0 < int(duration) <= MAX_CALLBACK_DURATION_SECS:
            log.duration_secs = int(duration)
        if call_status in FAILED_CALL_STATUSES and not log.outcome:
            # Nobody answered (no-answer / busy / failed): the call never reached the agent.
            log.outcome = "no_answer"
    if order is not None and call_status in FAILED_CALL_STATUSES | {"completed"}:
        _settle_from_call_status(order, log, call_status)
    await db.commit()
    if log is not None and call_status in FAILED_CALL_STATUSES | {"completed"}:
        # The call is over. One that never reached the media stream (no answer, busy, a
        # voicemail hung up by AMD) has no bridge to free its line: without this the slot
        # stayed taken for STALE_SECONDS and the plan's lines read "all busy" (inbound too).
        from app.services import concurrency

        await concurrency.release(log.merchant_id, log.id)
    await logger.ainfo("call_status_applied", order_id=order_id, call_sid=call_sid, call_status=call_status, duration=duration)


def is_machine_answer(answered_by: str) -> bool:
    return str(answered_by or "").strip().lower() in MACHINE_ANSWERS


async def apply_amd_callback(db: AsyncSession, order_id: str, call_sid: str, answered_by: str) -> bool:
    """Telnyx's answering-machine verdict. Returns True when the call was hung up."""
    log = None
    if call_sid:
        # Bound to the signed URL's order: a body CallSid can't reach another call's log.
        log = await db.scalar(select(CallLog).where(CallLog.twilio_call_sid == telnyx.sid_key(call_sid), CallLog.order_id == order_id))
    if log is None:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order_id).order_by(CallLog.created_at.desc()).limit(1)
        )
    if not is_machine_answer(answered_by):
        await logger.ainfo("amd_human", order_id=order_id, call_sid=call_sid, answered_by=answered_by)
        return False
    if log is not None and not log.outcome:
        log.outcome = OUTCOME_VOICEMAIL
        await db.commit()
    # Only this order's call is hung up: its known SID, else the callback's (before the SID was stored).
    sid = (log.twilio_call_sid or call_sid) if log is not None else ""
    if sid:
        try:
            await complete_call(sid)
        except Exception as exc:  # noqa: BLE001 — the status callback will still settle the record
            await logger.awarning("amd_hangup_failed", order_id=order_id, call_sid=sid, error=str(exc))
    await logger.ainfo("amd_voicemail_hangup", order_id=order_id, call_sid=sid, answered_by=answered_by)
    return True


async def apply_recording_callback(db: AsyncSession, order_id: str, call_sid: str, recording_sid: str) -> None:
    log = None
    if call_sid:
        # Bound to the signed URL's order: a body CallSid can't reach another call's log.
        log = await db.scalar(select(CallLog).where(CallLog.twilio_call_sid == telnyx.sid_key(call_sid), CallLog.order_id == order_id))
    if log is None:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order_id).order_by(CallLog.created_at.desc()).limit(1)
        )
    if log is None:
        return
    log.recording_sid = recording_sid
    await db.commit()


async def apply_log_recording_callback(db: AsyncSession, call_log_id: str, recording_sid: str) -> None:
    log = await db.get(CallLog, call_log_id)
    if log is None:
        return
    log.recording_sid = recording_sid
    await db.commit()


async def reconcile_stale_calls(db: AsyncSession, merchant: Merchant) -> int:
    """Settle records stuck in ``calling`` whose status callback never arrived.

    A call cannot outlive its ``time_limit``, so a record still "calling" well
    past it is asked about from Telnyx and settled the way the callback would.
    """
    cutoff = utcnow() - timedelta(seconds=call_time_limit(merchant) + STALE_CALL_GRACE_SECONDS)
    rows = await db.scalars(
        select(Order).where(
            Order.merchant_id == merchant.id,
            Order.status == OrderStatus.calling,
            Order.last_call_at.is_not(None),
            Order.last_call_at < cutoff,
        )
    )
    stale = list(rows)
    if not stale:
        return 0
    can_ask = telnyx.configured() and bool(telnyx.account_sid())
    settled = 0
    for order in stale:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order.id).order_by(CallLog.created_at.desc()).limit(1)
        )
        call_status, duration = "", 0
        if can_ask and log is not None and log.twilio_call_sid:
            try:
                call = await telnyx.fetch_call(log.twilio_call_sid)
                call_status = call["status"]
                duration = call["duration"]
            except Exception as exc:  # noqa: BLE001 — a missing SID is settled as unknown
                await logger.awarning("call_fetch_failed", order_id=order.id, error=str(exc))
        if call_status in LIVE_CALL_STATUSES:
            continue
        if log is not None:
            if call_status:
                log.call_status = call_status
            if duration:
                log.duration_secs = duration
        _settle_from_call_status(order, log, call_status or "completed")
        settled += 1
        await logger.ainfo("stale_call_settled", order_id=order.id, call_status=call_status or "unknown", status=order.status.value)
    if settled:
        await db.commit()
    return settled
