"""Inbound calls: route the dialed number to its account, answer with the media stream,
record the call, and keep the TeXML app's voice webhook pointed at this server."""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.addons import entitlements
from app.core.config import get_settings
from app.core.plans import CHANNEL_VOICE
from app.core.regions import normalize_phone, region_of
from app.db.session import AsyncSessionLocal
from app.flows.context import DIRECTION_INBOUND
from app.models import CallLog, Merchant
from app.services import concurrency
from app.services import telnyx
from app.services.calls.warmup import _warm_call_lines
from app.services.telnyx_urls import log_recording_callback_url
from app.verticals import flow_for
from app.voice import prepared
from app.voice.languages import normalize_language
from app.voice.twiml import PublicUrlMissing, say_twiml, stream_twiml

logger = structlog.get_logger(__name__)


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
    return None


async def answer_inbound_call(db: AsyncSession, *, to_number: str, from_number: str, call_sid: str) -> str:
    """TeXML for an inbound call: connect the media stream to the account's agent."""
    merchant = await find_inbound_merchant(db, to_number)
    if merchant is None:
        await logger.awarning("inbound_call_unrouted", to=to_number, call_sid=call_sid)
        return say_twiml("Sorry, this number is not in service.")
    if not entitlements(merchant).has_channel(CHANNEL_VOICE):
        await logger.ainfo("inbound_call_not_entitled", merchant=merchant.id, call_sid=call_sid)
        return say_twiml("Sorry, this line is not taking calls right now.")
    flow = flow_for(merchant, DIRECTION_INBOUND)
    log = CallLog(
        order_id=None,
        merchant_id=merchant.id,
        twilio_call_sid=telnyx.sid_key(call_sid),
        call_status="in-progress",
        language=normalize_language(merchant.language),
        direction=DIRECTION_INBOUND,
        flow=flow.key,
        caller_number=from_number,
    )
    db.add(log)
    await db.flush()
    if not await concurrency.acquire(merchant, log.id):
        log.call_status = "busy"
        log.outcome = "busy"
        await db.commit()
        await logger.ainfo("inbound_call_busy", merchant_id=merchant.id, call_sid=call_sid)
        return say_twiml("Sorry, all our lines are busy right now. Please call again in a few minutes.")
    from app.services.context_service import build_context

    ctx = await build_context(db, merchant, direction=DIRECTION_INBOUND, caller_number=from_number)
    await db.commit()
    prepared.put_call_snapshot(log.id, prepared.CallSnapshot(merchant=merchant, order=None, ctx=ctx, call_sid=call_sid, direction=DIRECTION_INBOUND))
    asyncio.create_task(_warm_call_lines(ctx, merchant))
    asyncio.create_task(_release_if_no_media(merchant, log.id), name=f"{MEDIA_WATCHDOG}:{log.id}")
    await logger.ainfo("inbound_call_answered", merchant_id=merchant.id, flow=flow.key, call_sid=call_sid, caller=from_number)
    return stream_twiml(call_log_id=log.id)


#: An answered inbound call whose audio never connects gives its line back after this long.
NO_MEDIA_RELEASE_SECONDS = 60.0
#: Task name prefix of that per-call timer (a timer, not unfinished work).
MEDIA_WATCHDOG = "inbound-media-watchdog"


async def _release_if_no_media(merchant: Merchant, call_log_id: str, *, after: float | None = None) -> None:
    """Inbound calls have no status callback: if the media stream never opened, free the line (it would
    otherwise stay taken for hours) and mark the call as failed. Single-process check (one worker)."""
    if await prepared.wait_for_media(call_log_id, NO_MEDIA_RELEASE_SECONDS if after is None else after) or prepared.call_ended(call_log_id):
        return
    await concurrency.release(merchant, call_log_id)
    try:
        async with AsyncSessionLocal() as session:
            log = await session.get(CallLog, call_log_id)
            if log is not None and log.call_status == "in-progress" and not log.transcript:
                log.call_status = "failed"
                log.outcome = log.outcome or "no_media"
                await session.commit()
    except Exception as exc:  # noqa: BLE001 — freeing the line is what matters
        await logger.awarning("inbound_no_media_log_failed", call_log_id=call_log_id, error=str(exc))
    await logger.awarning("inbound_media_never_connected", call_log_id=call_log_id)


async def start_call_recording(call_sid: str, call_log_id: str) -> None:
    """Record an inbound call (outbound calls are recorded from the create request)."""
    settings = get_settings()
    if not call_sid or not settings.telnyx_api_key or not settings.voice_record_inbound:
        return
    try:
        callback = log_recording_callback_url(call_log_id)
    except PublicUrlMissing:
        return
    try:
        await telnyx.start_recording(call_sid, callback=callback)
    except Exception as exc:  # noqa: BLE001 — a missing recording never breaks the call
        await logger.ainfo("inbound_recording_start_failed", call_log_id=call_log_id, error=str(exc))


async def remember_call_sid(call_log_id: str, call_sid: str) -> None:
    """Store the call SID the media stream reported (outbound creates may not return one)."""
    try:
        async with AsyncSessionLocal() as session:
            log = await session.get(CallLog, call_log_id)
            if log is not None and log.twilio_call_sid != telnyx.sid_key(call_sid):
                log.twilio_call_sid = telnyx.sid_key(call_sid)
                await session.commit()
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("call_sid_store_failed", call_log_id=call_log_id, error=str(exc))


async def configure_inbound_webhook() -> None:
    """Point the TeXML application's voice webhook at this server's signed inbound URL (opt-in, see settings)."""
    settings = get_settings()
    if not (settings.telnyx_auto_configure_inbound and settings.telnyx_texml_app_id and settings.public_base_url):
        return
    from app.services import telnyx_urls

    url = telnyx_urls.inbound_url()
    try:
        await telnyx.point_app_at(url)
        await logger.ainfo("telnyx_inbound_webhook_configured", app_id=settings.telnyx_texml_app_id, url=telnyx_urls.mask(url))
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("telnyx_inbound_webhook_config_failed", error=str(exc))
