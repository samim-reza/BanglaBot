"""Originates Twilio confirmation calls, applies status callbacks, and settles
orders whose callback never arrived. Also the DB-backed ``CallStore`` the
bridge writes outcomes / transcripts through."""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from typing import Any

import httpx
import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client as TwilioClient

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.db.session import AsyncSessionLocal
from app.flows.base import OUTCOME_VOICEMAIL, UNANSWERED_OUTCOMES
from app.models import CallLog, Merchant, Order, OrderStatus
from app.voice.twiml import PublicUrlMissing, amd_callback_url, dial_twiml, recording_callback_url, status_callback_url, stream_twiml

logger = structlog.get_logger(__name__)

#: Twilio statuses meaning the call is still live (leave the order alone).
LIVE_CALL_STATUSES = frozenset({"queued", "initiated", "ringing", "in-progress"})
FAILED_CALL_STATUSES = frozenset({"no-answer", "busy", "failed", "canceled"})
#: Extra seconds past ``time_limit`` before a "calling" order counts as stale.
STALE_CALL_GRACE_SECONDS = 120


# ---------------------------------------------------------------------- helpers
def call_time_limit(merchant: Merchant) -> int:
    configured = int(getattr(merchant, "max_call_seconds", 0) or 0)
    return configured if configured > 0 else int(get_settings().voice_max_call_seconds)


def twilio_client() -> TwilioClient:
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise HTTPException(status_code=500, detail="Twilio credentials are not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN)")
    return TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)


def normalize_bd_phone(phone: str) -> str:
    """``01712345678`` → ``+8801712345678``; other E.164 numbers pass through."""
    raw = str(phone or "").strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+"):
        return "+" + re.sub(r"\D", "", digits[1:])
    digits = re.sub(r"\D", "", digits)
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("880") and len(digits) == 13:
        return "+" + digits
    if digits.startswith("01") and len(digits) == 11:
        return "+88" + digits
    if digits.startswith("1") and len(digits) == 10:
        return "+880" + digits
    return "+" + digits if digits else raw


# ------------------------------------------------------------- start the call
async def start_confirmation_call(db: AsyncSession, order: Order, merchant: Merchant) -> CallLog:
    settings = get_settings()
    if order.status == OrderStatus.calling:
        raise HTTPException(status_code=409, detail="A call is already in progress for this order")
    if order.status in (OrderStatus.confirmed, OrderStatus.cancelled):
        raise HTTPException(status_code=409, detail=f"Order is already {order.status.value}")
    if not settings.twilio_from_number:
        raise HTTPException(status_code=500, detail="TWILIO_FROM_NUMBER is not configured")
    try:
        status_url = status_callback_url(order.id)
        recording_url = recording_callback_url(order.id)
    except PublicUrlMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    client = twilio_client()
    to_number = normalize_bd_phone(order.customer_phone)

    log = CallLog(order_id=order.id, merchant_id=merchant.id, call_status="initiated", language=merchant.language or "bn")
    db.add(log)
    await db.flush()
    twiml = stream_twiml(order_id=order.id, call_log_id=log.id)
    time_limit = call_time_limit(merchant)

    extra: dict[str, Any] = {}
    if settings.voice_machine_detection:
        # Asynchronous AMD: the call connects immediately; Twilio posts AnsweredBy
        # a few seconds in and /twilio/amd hangs up on a machine.
        extra.update(
            machine_detection="Enable",
            async_amd="true",
            async_amd_status_callback=amd_callback_url(order.id),
            async_amd_status_callback_method="POST",
            machine_detection_timeout=15,
        )

    def _create() -> str:
        call = client.calls.create(
            to=to_number,
            from_=settings.twilio_from_number,
            twiml=twiml,
            status_callback=status_url,
            status_callback_event=["completed"],
            status_callback_method="POST",
            record=True,
            recording_status_callback=recording_url,
            recording_status_callback_event=["completed"],
            recording_status_callback_method="POST",
            time_limit=time_limit,
            **extra,
        )
        return str(call.sid)

    try:
        call_sid = await asyncio.to_thread(_create)
    except Exception as exc:  # noqa: BLE001 — Twilio errors and network failures alike
        # Drops the pending CallLog; the order row itself was not modified yet.
        await db.rollback()
        await db.refresh(order)
        detail = exc.msg if isinstance(exc, TwilioRestException) and exc.msg else str(exc)
        await logger.awarning("twilio_call_create_failed", order_id=order.id, error=detail)
        raise HTTPException(status_code=502, detail=f"Twilio could not place the call: {detail}") from exc

    log.twilio_call_sid = call_sid
    order.status = OrderStatus.calling
    order.call_attempts = int(order.call_attempts or 0) + 1
    order.last_call_at = utcnow()
    await db.commit()
    await db.refresh(order)
    await db.refresh(log)
    asyncio.create_task(_warm_call_lines(order, merchant))
    await logger.ainfo("confirmation_call_started", order_id=order.id, call_sid=call_sid, to=to_number)
    return log


async def _warm_call_lines(order: Order, merchant: Merchant) -> None:
    """Synthesize the greeting and every scripted line while the phone rings."""
    try:
        from app.flows.ecommerce import DEFAULT_FLOW
        from app.voice.audio import sentence_units
        from app.voice.languages import normalize_supported
        from app.voice.tts import get_tts, tts_configured

        if not tts_configured():
            return
        tts = get_tts()
        for language in normalize_supported(merchant.language, merchant.supported_languages):
            lines = sentence_units(DEFAULT_FLOW.prefetch_lines(order, merchant, language))
            await tts.warm(lines, language=language, persona=merchant.voice_persona)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("call_line_warm_failed", order_id=order.id, error=str(exc))
    # The confirmation question is composed by the model now, while the phone
    # rings, so the first caller turn can be answered straight from the cache.
    try:
        from app.voice import prepared

        await prepared.prepare_call_lines(order, merchant)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("call_line_prepare_failed", order_id=order.id, error=str(exc))


# ----------------------------------------------------------- Twilio callbacks
def _settle_from_call_status(order: Order, log: CallLog | None, call_status: str) -> None:
    """Map a final Twilio status onto an order still in ``calling``."""
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
        # The bridge already wrote the final status when the outcome landed;
        # a lingering "calling" here means that write raced the callback.
        from app.flows.base import OUTCOME_STATUS

        order.status = OrderStatus(OUTCOME_STATUS.get(outcome, "needs_review"))


async def apply_status_callback(db: AsyncSession, order_id: str, call_sid: str, call_status: str, duration: int) -> None:
    order = await db.get(Order, order_id)
    log = None
    if call_sid:
        log = await db.scalar(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
    if log is None and order is not None:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order.id).order_by(CallLog.created_at.desc()).limit(1)
        )
    if log is not None:
        log.call_status = call_status or log.call_status
        if duration:
            log.duration_secs = int(duration)
    if order is not None and call_status in FAILED_CALL_STATUSES | {"completed"}:
        _settle_from_call_status(order, log, call_status)
    await db.commit()
    await logger.ainfo("twilio_status_applied", order_id=order_id, call_sid=call_sid, call_status=call_status, duration=duration)


MACHINE_ANSWERS = ("machine_start", "machine_end_beep", "machine_end_silence", "machine_end_other", "fax")


def is_machine_answer(answered_by: str) -> bool:
    return str(answered_by or "").strip().lower() in MACHINE_ANSWERS


async def apply_amd_callback(db: AsyncSession, order_id: str, call_sid: str, answered_by: str) -> bool:
    """Twilio's answering-machine verdict. Returns True when the call was hung up."""
    log = None
    if call_sid:
        log = await db.scalar(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
    if log is None:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order_id).order_by(CallLog.created_at.desc()).limit(1)
        )
    if not is_machine_answer(answered_by):
        await logger.ainfo("twilio_amd_human", order_id=order_id, call_sid=call_sid, answered_by=answered_by)
        return False
    if log is not None and not log.outcome:
        log.outcome = OUTCOME_VOICEMAIL
        await db.commit()
    sid = call_sid or (log.twilio_call_sid if log is not None else "")
    if sid:
        try:
            await complete_call(sid)
        except Exception as exc:  # noqa: BLE001 — the status callback will still settle the order
            await logger.awarning("twilio_amd_hangup_failed", order_id=order_id, call_sid=sid, error=str(exc))
    await logger.ainfo("twilio_amd_voicemail_hangup", order_id=order_id, call_sid=sid, answered_by=answered_by)
    return True


async def fetch_call_details(call_sid: str) -> dict[str, Any]:
    """Live Twilio view of one call: status, answered_by, forwarded_from."""
    settings = get_settings()
    if not call_sid or not settings.twilio_account_sid or not settings.twilio_auth_token:
        return {}

    def _fetch() -> dict[str, Any]:
        call = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token).calls(call_sid).fetch()
        return {
            "status": str(call.status or ""),
            "answered_by": str(call.answered_by or ""),
            "forwarded_from": str(call.forwarded_from or ""),
        }

    return await asyncio.to_thread(_fetch)


async def apply_recording_callback(db: AsyncSession, order_id: str, call_sid: str, recording_sid: str) -> None:
    log = None
    if call_sid:
        log = await db.scalar(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
    if log is None:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order_id).order_by(CallLog.created_at.desc()).limit(1)
        )
    if log is None:
        return
    log.recording_sid = recording_sid
    await db.commit()


async def reconcile_stale_calls(db: AsyncSession, merchant: Merchant) -> int:
    """Settle orders stuck in ``calling`` whose status callback never arrived.

    A call cannot outlive its ``time_limit``, so an order still "calling" well
    past it is asked about from Twilio and settled the way the callback would.
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
    settings = get_settings()
    client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token) if settings.twilio_account_sid and settings.twilio_auth_token else None
    settled = 0
    for order in stale:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order.id).order_by(CallLog.created_at.desc()).limit(1)
        )
        call_status, duration = "", 0
        if client is not None and log is not None and log.twilio_call_sid:
            try:
                call = await asyncio.to_thread(client.calls(log.twilio_call_sid).fetch)
                call_status = str(call.status or "")
                duration = int(call.duration or 0)
            except Exception as exc:  # noqa: BLE001 — a missing SID is settled as unknown
                await logger.awarning("twilio_call_fetch_failed", order_id=order.id, error=str(exc))
        if call_status in LIVE_CALL_STATUSES:
            continue
        if log is not None:
            if call_status:
                log.call_status = call_status
            if duration:
                log.duration_secs = duration
        _settle_from_call_status(order, log, call_status or "completed")
        settled += 1
        await logger.ainfo("stale_call_settled", order_id=order.id, twilio_status=call_status or "unknown", status=order.status.value)
    if settled:
        await db.commit()
    return settled


# ------------------------------------------------------- live call control
async def redirect_call_to_human(call_sid: str, number: str) -> bool:
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return False
    twiml = dial_twiml(normalize_bd_phone(number), caller_id=settings.twilio_from_number)

    def _update() -> None:
        TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token).calls(call_sid).update(twiml=twiml)

    await asyncio.to_thread(_update)
    return True


async def complete_call(call_sid: str) -> None:
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return

    def _update() -> None:
        TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token).calls(call_sid).update(status="completed")

    await asyncio.to_thread(_update)


async def fetch_recording(log: CallLog) -> tuple[bytes, str]:
    """Download a call recording from Twilio (basic auth) for proxying to the UI."""
    settings = get_settings()
    if not log.recording_sid:
        raise HTTPException(status_code=404, detail="No recording for this call")
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise HTTPException(status_code=500, detail="Twilio credentials are not configured")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Recordings/{log.recording_sid}.mp3"
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = await client.get(url, auth=(settings.twilio_account_sid, settings.twilio_auth_token), follow_redirects=True)
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Recording not available yet")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Twilio recording fetch failed ({response.status_code})")
    return response.content, response.headers.get("content-type", "audio/mpeg")


# --------------------------------------------------------------- CallStore
class DbCallStore:
    """Persists what the bridge learns: outcome → order + call log, transcript, usage."""

    def __init__(self, *, order_id: str, call_log_id: str) -> None:
        self.order_id = order_id
        self.call_log_id = call_log_id

    async def set_outcome(self, *, outcome: str, status: str, final_node: str, flow_data: dict[str, Any], note: str, language: str) -> None:
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, self.order_id)
            log = await session.get(CallLog, self.call_log_id)
            if order is not None:
                order.status = OrderStatus(status)
                order.flow_data = dict(flow_data or {})
                if note:
                    stamp = utcnow().strftime("%Y-%m-%d %H:%M")
                    line = f"[{stamp}] {note}"
                    order.notes = f"{order.notes}\n{line}".strip() if order.notes else line
                order.updated_at = utcnow()
            if log is not None:
                log.outcome = outcome
                log.final_node = final_node or log.final_node
                log.language = language or log.language
            await session.commit()

    async def save_transcript(self, transcript: str, *, language: str, final_node: str) -> None:
        async with AsyncSessionLocal() as session:
            log = await session.get(CallLog, self.call_log_id)
            if log is None:
                return
            log.transcript = transcript
            log.language = language or log.language
            log.final_node = final_node or log.final_node
            await session.commit()

    async def save_usage(self, **counters: int) -> None:
        async with AsyncSessionLocal() as session:
            log = await session.get(CallLog, self.call_log_id)
            if log is None:
                return
            for key in ("llm_prompt_tokens", "llm_completion_tokens", "tts_chars", "tts_cache_hits"):
                if key in counters:
                    setattr(log, key, int(counters[key] or 0))
            await session.commit()
