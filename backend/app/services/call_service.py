"""Call lifecycle: place outbound calls, answer inbound ones, open test calls,
apply Twilio callbacks, settle records whose callback never arrived — and the
DB-backed ``CallStore`` the agent writes outcomes, bookings and transcripts through."""

from __future__ import annotations

import asyncio
from datetime import timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client as TwilioClient

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.core.regions import Region, normalize_phone, region_of
from app.db.session import AsyncSessionLocal
from app.flows.base import OUTCOME_STATUS, OUTCOME_VOICEMAIL, UNANSWERED_OUTCOMES, CommitAction, CommitResult
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND, CallContext
from app.models import CallLog, Merchant, Order, OrderStatus
from app.verticals import flow_for, vertical_for
from app.voice import prepared
from app.voice.twiml import (
    PublicUrlMissing,
    amd_callback_url,
    dial_twiml,
    log_recording_callback_url,
    recording_callback_url,
    say_twiml,
    status_callback_url,
    stream_twiml,
)

logger = structlog.get_logger(__name__)

#: Twilio statuses meaning the call is still live (leave the record alone).
LIVE_CALL_STATUSES = frozenset({"queued", "initiated", "ringing", "in-progress"})
FAILED_CALL_STATUSES = frozenset({"no-answer", "busy", "failed", "canceled"})
#: Extra seconds past ``time_limit`` before a "calling" record counts as stale.
STALE_CALL_GRACE_SECONDS = 120
#: Statuses a scheduled slot stays taken in.
LIVE_RECORD_STATUSES = (OrderStatus.pending, OrderStatus.calling, OrderStatus.confirmed)
#: Record columns a commit may set.
RECORD_COLUMNS = (
    "kind", "customer_name", "customer_phone", "address", "items_summary", "total_amount",
    "catalog_item_id", "scheduled_at", "order_ref",
)


# ---------------------------------------------------------------------- helpers
def call_time_limit(merchant: Merchant, *, inbound: bool = False) -> int:
    configured = int(getattr(merchant, "max_call_seconds", 0) or 0)
    if configured > 0:
        return configured
    settings = get_settings()
    return int(settings.voice_max_inbound_call_seconds if inbound else settings.voice_max_call_seconds)


def twilio_client() -> TwilioClient:
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise HTTPException(status_code=500, detail="Twilio credentials are not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN)")
    return TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)


# ------------------------------------------------------------- outbound
async def start_outbound_call(db: AsyncSession, order: Order, merchant: Merchant) -> CallLog:
    settings = get_settings()
    if order.status == OrderStatus.calling:
        raise HTTPException(status_code=409, detail="A call is already in progress for this record")
    if order.status in (OrderStatus.confirmed, OrderStatus.cancelled) and order.kind == "order":
        raise HTTPException(status_code=409, detail=f"Order is already {order.status.value}")
    if order.status == OrderStatus.cancelled:
        raise HTTPException(status_code=409, detail="This record is cancelled")
    if not settings.twilio_from_number:
        raise HTTPException(status_code=500, detail="TWILIO_FROM_NUMBER is not configured")
    try:
        status_url = status_callback_url(order.id)
        recording_url = recording_callback_url(order.id)
    except PublicUrlMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    client = twilio_client()
    to_number = normalize_phone(order.customer_phone, region_of(merchant))
    flow = flow_for(merchant, DIRECTION_OUTBOUND)

    log = CallLog(
        order_id=order.id,
        merchant_id=merchant.id,
        call_status="initiated",
        language=merchant.language or "en",
        direction=DIRECTION_OUTBOUND,
        flow=flow.key,
    )
    db.add(log)
    await db.flush()
    twiml = stream_twiml(call_log_id=log.id, order_id=order.id)
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

    # The context (catalog, booked slots) is read now, while nothing waits on it.
    from app.services.context_service import build_context

    ctx = await build_context(db, merchant, record=order, direction=DIRECTION_OUTBOUND)
    try:
        call_sid = await asyncio.to_thread(_create)
    except Exception as exc:  # noqa: BLE001 — Twilio errors and network failures alike
        # Drops the pending CallLog; the record itself was not modified yet.
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
    # Everything the media websocket needs, in memory: when the customer answers,
    # the greeting must not wait for a database round-trip.
    ctx.record = order
    prepared.put_call_snapshot(log.id, prepared.CallSnapshot(merchant=merchant, order=order, ctx=ctx, call_sid=call_sid))
    asyncio.create_task(_warm_call_lines(ctx, merchant))
    await logger.ainfo("outbound_call_started", order_id=order.id, call_sid=call_sid, to=to_number, flow=flow.key)
    return log


async def _warm_call_lines(ctx: CallContext, merchant: Merchant) -> None:
    """Synthesize the greeting and every scripted line while the phone rings."""
    try:
        from app.voice.audio import sentence_units
        from app.voice.languages import ack_lines, normalize_language
        from app.voice.llm import warm_connection
        from app.voice.tts import get_tts, normalize_persona, tts_configured, voice_for

        settings = get_settings()
        asyncio.create_task(warm_connection(settings.openai_api_key))
        if not tts_configured():
            return
        tts = get_tts()
        language = normalize_language(merchant.language)
        flow = flow_for(merchant, ctx.direction)
        persona = normalize_persona(merchant.voice_persona)
        voice = voice_for(persona, language, region_of(merchant).accent)
        lines = sentence_units(list(flow.prefetch_lines(ctx, language)) + list(ack_lines(language)))
        await tts.warm(lines, language=language, persona=persona, voice=voice)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("call_line_warm_failed", error=str(exc))
    # E-commerce: the confirmation question is composed by the model now, while
    # the phone rings, so the first caller turn is answered from the cache.
    if ctx.record is not None and vertical_for(merchant).key == "ecommerce" and ctx.direction == DIRECTION_OUTBOUND:
        try:
            await prepared.prepare_call_lines(ctx.record, merchant)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("call_line_prepare_failed", error=str(exc))


# ------------------------------------------------------------- inbound
async def find_inbound_merchant(db: AsyncSession, to_number: str) -> Merchant | None:
    """The account that answers calls to ``to_number`` (or the dev fallback account)."""
    from app.core import memo

    target = normalize_phone(to_number, "INTL")
    known = memo.get(f"inbound:{target}")
    if known:
        merchant = await db.get(Merchant, known)
        if merchant is not None and merchant.active and normalize_phone(merchant.inbound_number, region_of(merchant)) == target:
            return merchant
    rows = await db.scalars(select(Merchant).where(Merchant.inbound_number != "", Merchant.active.is_(True)))
    for merchant in rows:
        if normalize_phone(merchant.inbound_number, region_of(merchant)) == target:
            memo.put(f"inbound:{target}", merchant.id, ttl=600)
            return merchant
    fallback = get_settings().default_inbound_username
    if fallback:
        merchant = await db.scalar(select(Merchant).where(Merchant.username == fallback))
        if merchant is not None and merchant.active:
            return merchant
    return None


async def answer_inbound_call(db: AsyncSession, *, to_number: str, from_number: str, call_sid: str) -> str:
    """TwiML for an inbound call: connect the media stream to the account's agent."""
    merchant = await find_inbound_merchant(db, to_number)
    if merchant is None:
        await logger.awarning("inbound_call_unrouted", to=to_number, call_sid=call_sid)
        return say_twiml("Sorry, this number is not in service.")
    flow = flow_for(merchant, DIRECTION_INBOUND)
    log = CallLog(
        order_id=None,
        merchant_id=merchant.id,
        twilio_call_sid=call_sid,
        call_status="in-progress",
        language=merchant.language or "en",
        direction=DIRECTION_INBOUND,
        flow=flow.key,
        caller_number=from_number,
    )
    db.add(log)
    await db.flush()
    from app.services.context_service import build_context

    ctx = await build_context(db, merchant, direction=DIRECTION_INBOUND, caller_number=from_number)
    await db.commit()
    prepared.put_call_snapshot(log.id, prepared.CallSnapshot(merchant=merchant, order=None, ctx=ctx, call_sid=call_sid, direction=DIRECTION_INBOUND))
    asyncio.create_task(_warm_call_lines(ctx, merchant))
    await logger.ainfo("inbound_call_answered", merchant_id=merchant.id, flow=flow.key, call_sid=call_sid, caller=from_number)
    return stream_twiml(call_log_id=log.id)


async def start_call_recording(call_sid: str, call_log_id: str) -> None:
    """Record an inbound call (outbound calls are recorded from ``calls.create``)."""
    settings = get_settings()
    if not call_sid or not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.voice_record_inbound:
        return
    try:
        callback = log_recording_callback_url(call_log_id)
    except PublicUrlMissing:
        return

    def _start() -> None:
        TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token).calls(call_sid).recordings.create(
            recording_status_callback=callback,
            recording_status_callback_event=["completed"],
            recording_status_callback_method="POST",
        )

    try:
        await asyncio.to_thread(_start)
    except Exception as exc:  # noqa: BLE001 — a missing recording never breaks the call
        await logger.ainfo("inbound_recording_start_failed", call_log_id=call_log_id, error=str(exc))


async def configure_inbound_webhook() -> None:
    """Point TWILIO_FROM_NUMBER's voice webhook at this server (opt-in, see settings)."""
    settings = get_settings()
    if not (settings.twilio_auto_configure_inbound and settings.twilio_from_number and settings.public_base_url):
        return
    from app.voice.twiml import public_base_url

    url = f"{public_base_url()}/twilio/inbound"
    number = normalize_phone(settings.twilio_from_number, "INTL")

    def _update() -> str:
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        found = client.incoming_phone_numbers.list(phone_number=number, limit=1)
        if not found:
            return "not_found"
        found[0].update(voice_url=url, voice_method="POST")
        return "updated"

    try:
        result = await asyncio.to_thread(_update)
        await logger.ainfo("twilio_inbound_webhook_configured", number=number, url=url, result=result)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("twilio_inbound_webhook_config_failed", error=str(exc))


# ------------------------------------------------------------- test calls (portal)
async def open_test_call(
    db: AsyncSession,
    merchant: Merchant,
    *,
    direction: str,
    record: Order | None = None,
    caller_number: str = "",
    mode: str = "web",
) -> tuple[CallLog, CallContext]:
    """A call from the portal's test console: browser voice (``web``) or text (``chat``)."""
    if direction == DIRECTION_OUTBOUND and record is None:
        raise HTTPException(status_code=422, detail="Pick a record for an outbound test call")
    flow = flow_for(merchant, direction)
    log = CallLog(
        order_id=record.id if record is not None else None,
        merchant_id=merchant.id,
        call_status="in-progress",
        language=merchant.language or "en",
        direction=mode,
        flow=flow.key,
        caller_number=caller_number,
    )
    db.add(log)
    await db.flush()
    from app.services.context_service import build_context

    ctx = await build_context(db, merchant, record=record, direction=direction, caller_number=caller_number, test=True)
    await db.commit()
    await db.refresh(log)
    return log, ctx


# ----------------------------------------------------------- Twilio callbacks
def _settle_from_call_status(order: Order, log: CallLog | None, call_status: str) -> None:
    """Map a final Twilio status onto a record still in ``calling``."""
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
        log = await db.scalar(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
    if log is None and order is not None:
        log = await db.scalar(
            select(CallLog).where(CallLog.order_id == order.id).order_by(CallLog.created_at.desc()).limit(1)
        )
    if log is not None:
        log.call_status = call_status or log.call_status
        if duration:
            log.duration_secs = int(duration)
        if call_status in FAILED_CALL_STATUSES and not log.outcome:
            # Nobody answered (no-answer / busy / failed): the call never reached the agent.
            log.outcome = "no_answer"
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
        except Exception as exc:  # noqa: BLE001 — the status callback will still settle the record
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


async def apply_log_recording_callback(db: AsyncSession, call_log_id: str, recording_sid: str) -> None:
    log = await db.get(CallLog, call_log_id)
    if log is None:
        return
    log.recording_sid = recording_sid
    await db.commit()


async def reconcile_stale_calls(db: AsyncSession, merchant: Merchant) -> int:
    """Settle records stuck in ``calling`` whose status callback never arrived.

    A call cannot outlive its ``time_limit``, so a record still "calling" well
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
async def redirect_call_to_human(call_sid: str, number: str, region: Region | str | None = None) -> bool:
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return False
    twiml = dial_twiml(normalize_phone(number, region), caller_id=settings.twilio_from_number)

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
def _note_line(existing: str, note: str) -> str:
    stamp = utcnow().strftime("%Y-%m-%d %H:%M")
    line = f"[{stamp}] {note}"
    return f"{existing}\n{line}".strip() if existing else line


def _amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


class DbCallStore:
    """Persists what the agent learns: outcomes, bookings, transcript, usage.

    ``order_id`` is the record the call is about; an inbound call starts with
    none and binds the record its first commit creates.
    """

    def __init__(self, *, order_id: str, call_log_id: str, merchant_id: str = "", currency: str = "", source: str = "") -> None:
        self.order_id = order_id or ""
        self.call_log_id = call_log_id
        self.merchant_id = merchant_id
        self.currency = currency
        self.source = source

    async def set_outcome(self, *, outcome: str, status: str, final_node: str, flow_data: dict[str, Any], note: str, language: str) -> None:
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, self.order_id) if self.order_id else None
            log = await session.get(CallLog, self.call_log_id)
            if order is not None:
                if status:
                    order.status = OrderStatus(status)
                order.flow_data = dict(flow_data or {})
                if note:
                    order.notes = _note_line(order.notes or "", note)
                order.updated_at = utcnow()
            if log is not None:
                log.outcome = outcome
                log.final_node = final_node or log.final_node
                log.language = language or log.language
            await session.commit()
            merchant_id = order.merchant_id if order is not None else (log.merchant_id if log is not None else "")
        if self.order_id:
            from app.services import notification_service

            notification_service.after_outcome(merchant_id, self.order_id, outcome)

    async def commit(self, action: CommitAction, *, final_node: str, flow_data: dict[str, Any], language: str) -> CommitResult:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                log = await session.get(CallLog, self.call_log_id)
                merchant_id = self.merchant_id or (log.merchant_id if log is not None else "")
                if action.capacity is not None:
                    item_id, start, capacity = action.capacity
                    # Serialize bookings into the same resource so two calls can't
                    # both take its last free slot.
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"{merchant_id}:{item_id or '*'}"}
                    )
                    stmt = select(func.count(Order.id)).where(
                        Order.merchant_id == merchant_id,
                        Order.scheduled_at == start.astimezone(timezone.utc),
                        Order.status.in_(LIVE_RECORD_STATUSES),
                    )
                    if item_id:
                        stmt = stmt.where(Order.catalog_item_id == item_id)
                    if action.record_id:
                        stmt = stmt.where(Order.id != action.record_id)
                    if int(await session.scalar(stmt) or 0) >= max(1, int(capacity)):
                        return CommitResult(ok=False, reason="slot_taken")
                record_id = action.record_id or ""
                record: Order | None = await session.get(Order, record_id) if record_id else None
                if record_id and record is None:
                    return CommitResult(ok=False, reason="not_found")
                if record is None:
                    record = Order(
                        merchant_id=merchant_id,
                        kind=str(action.fields.get("kind") or "order"),
                        source=self.source or "inbound_call",
                        customer_name=str(action.fields.get("customer_name") or "Caller")[:120],
                        customer_phone=str(action.fields.get("customer_phone") or "")[:32],
                        currency=self.currency,
                        status=OrderStatus(action.status),
                        details={},
                        flow_data={},
                    )
                    session.add(record)
                for key, value in action.fields.items():
                    if key == "details":
                        merged = dict(record.details or {})
                        merged.update({k: v for k, v in dict(value or {}).items() if v not in (None, "")})
                        record.details = merged
                    elif key == "scheduled_at" and value is not None:
                        record.scheduled_at = value.astimezone(timezone.utc)
                    elif key == "total_amount":
                        record.total_amount = _amount(value)
                    elif key in RECORD_COLUMNS and value is not None:
                        setattr(record, key, value)
                record.status = OrderStatus(action.status)
                record.flow_data = dict(flow_data or {})
                if action.note:
                    record.notes = _note_line(record.notes or "", action.note)
                record.updated_at = utcnow()
                await session.flush()
                if log is not None:
                    log.outcome = action.outcome
                    log.final_node = final_node or log.final_node
                    log.language = language or log.language
                    log.order_id = record.id
                new_id = record.id
        self.order_id = new_id
        from app.services import notification_service

        notification_service.after_outcome(merchant_id, new_id, action.outcome)
        return CommitResult(ok=True, record_id=new_id)

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
            for key in ("llm_prompt_tokens", "llm_completion_tokens", "llm_cached_tokens", "tts_chars", "tts_cache_hits"):
                if key in counters:
                    setattr(log, key, int(counters[key] or 0))
            # Twilio's status callback has the billed duration for outbound calls;
            # inbound / test calls only have ours.
            if counters.get("duration_secs") and not log.duration_secs:
                log.duration_secs = int(counters["duration_secs"])
            if log.direction in (DIRECTION_INBOUND, "web", "chat") and log.call_status == "in-progress":
                log.call_status = "completed"
            await session.commit()

    async def notify_finished(self) -> None:
        """Webhook add-on: tell the business's own system how the call ended."""
        from app.services.webhook_service import send_call_finished

        asyncio.create_task(send_call_finished(self.call_log_id))


__all__ = [
    "DbCallStore",
    "answer_inbound_call",
    "apply_amd_callback",
    "apply_log_recording_callback",
    "apply_recording_callback",
    "apply_status_callback",
    "call_time_limit",
    "complete_call",
    "configure_inbound_webhook",
    "fetch_call_details",
    "fetch_recording",
    "find_inbound_merchant",
    "is_machine_answer",
    "open_test_call",
    "reconcile_stale_calls",
    "redirect_call_to_human",
    "start_call_recording",
    "start_outbound_call",
]
