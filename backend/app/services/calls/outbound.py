"""Outbound calls: validate the record, take a line, place the call through Telnyx and
stash everything the media websocket needs in memory before the callee answers."""

from __future__ import annotations

import asyncio

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.core.regions import normalize_phone, region_of
from app.flows.context import DIRECTION_OUTBOUND
from app.models import CallLog, Merchant, Order, OrderStatus
from app.services import concurrency
from app.services import telnyx
from app.services.calls.policy import call_time_limit, require_telephony, require_voice
from app.services.calls.warmup import _warm_call_lines
from app.services.telnyx_urls import amd_callback_url, recording_callback_url, status_callback_url
from app.verticals import flow_for
from app.voice import prepared
from app.voice.twiml import PublicUrlMissing, stream_twiml

logger = structlog.get_logger(__name__)


async def start_outbound_call(db: AsyncSession, order: Order, merchant: Merchant) -> CallLog:
    settings = get_settings()
    require_voice(merchant)
    if order.status == OrderStatus.calling:
        raise HTTPException(status_code=409, detail="A call is already in progress for this record")
    if order.status in (OrderStatus.confirmed, OrderStatus.cancelled) and order.kind == "order":
        raise HTTPException(status_code=409, detail=f"Order is already {order.status.value}")
    if order.status == OrderStatus.cancelled:
        raise HTTPException(status_code=409, detail="This record is cancelled")
    require_telephony()
    try:
        status_url = status_callback_url(order.id)
        recording_url = recording_callback_url(order.id)
    except PublicUrlMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
    if not await concurrency.acquire(merchant, log.id):
        await db.rollback()
        await db.refresh(order)
        raise HTTPException(status_code=429, detail="All your lines are busy right now — try again when a call ends")
    twiml = stream_twiml(call_log_id=log.id, order_id=order.id)
    time_limit = call_time_limit(merchant)

    # Asynchronous AMD: the call connects immediately; Telnyx posts AnsweredBy
    # a few seconds in and /telnyx/amd hangs up on a machine.
    amd_url = amd_callback_url(order.id) if settings.voice_machine_detection else None

    # The context (catalog, booked slots) is read now, while nothing waits on it.
    from app.services.context_service import build_context

    ctx = await build_context(db, merchant, record=order, direction=DIRECTION_OUTBOUND)
    try:
        call_sid = await telnyx.create_call(
            to=to_number,
            texml=twiml,
            status_callback=status_url,
            recording_callback=recording_url,
            amd_callback=amd_url,
            time_limit=time_limit,
            from_number=telnyx.number_for(merchant),
        )
    except Exception as exc:  # noqa: BLE001 — Telnyx errors and network failures alike
        # Drops the pending CallLog; the record itself was not modified yet.
        await concurrency.release(merchant, log.id)
        await db.rollback()
        await db.refresh(order)
        detail = exc.detail if isinstance(exc, telnyx.TelnyxError) else str(exc)
        await logger.awarning("telnyx_call_create_failed", order_id=order.id, error=detail)
        raise HTTPException(status_code=502, detail=f"Telnyx could not place the call: {detail}") from exc

    log.twilio_call_sid = telnyx.sid_key(call_sid)
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
