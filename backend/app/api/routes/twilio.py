"""Twilio webhooks: inbound calls, status, recordings, AMD, and the media stream."""

from __future__ import annotations

import asyncio
import time

import structlog
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import Response
from sqlalchemy import select
from twilio.request_validator import RequestValidator

from app.core.config import get_settings
from app.core.security import verify_media_stream_token
from app.db.session import AsyncSessionLocal
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND
from app.models import CallLog, Merchant, Order
from app.services import call_service
from app.voice import prepared
from app.voice.bridge import CallBridge
from app.voice.twiml import PublicUrlMissing, public_base_url, say_twiml, stream_twiml

router = APIRouter(prefix="/twilio", tags=["twilio"])
logger = structlog.get_logger(__name__)


async def _form_dict(request: Request) -> dict[str, str]:
    form = await request.form()
    return {str(key): str(value) for key, value in form.items()}


def _validate_signature(request: Request, values: dict[str, str]) -> None:
    settings = get_settings()
    if not settings.enforce_webhook_signatures:
        return
    if not settings.twilio_auth_token:
        raise HTTPException(status_code=500, detail="Twilio auth token is not configured")
    try:
        base = public_base_url()
    except PublicUrlMissing:
        base = f"{request.url.scheme}://{request.headers.get('host', '')}"
    url = f"{base}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    signature = request.headers.get("X-Twilio-Signature") or ""
    if not RequestValidator(settings.twilio_auth_token).validate(url, values, signature):
        raise HTTPException(status_code=401, detail="Invalid Twilio signature")


@router.post("/status/{order_id}")
async def status_callback(order_id: str, request: Request):
    values = await _form_dict(request)
    _validate_signature(request, values)
    call_status = values.get("CallStatus", "")
    try:
        duration = int(values.get("CallDuration") or 0)
    except ValueError:
        duration = 0
    async with AsyncSessionLocal() as session:
        await call_service.apply_status_callback(session, order_id, values.get("CallSid", ""), call_status, duration)
    return Response(status_code=204)


@router.post("/amd/{order_id}")
async def amd_callback(order_id: str, request: Request):
    """Async answering-machine detection: hang up on voicemail so the order stays callable."""
    values = await _form_dict(request)
    _validate_signature(request, values)
    async with AsyncSessionLocal() as session:
        await call_service.apply_amd_callback(session, order_id, values.get("CallSid", ""), values.get("AnsweredBy", ""))
    return Response(status_code=204)


@router.post("/recording/{order_id}")
async def recording_callback(order_id: str, request: Request):
    values = await _form_dict(request)
    _validate_signature(request, values)
    recording_sid = values.get("RecordingSid", "")
    if recording_sid:
        async with AsyncSessionLocal() as session:
            await call_service.apply_recording_callback(session, order_id, values.get("CallSid", ""), recording_sid)
    return Response(status_code=204)


@router.post("/sms-status/{message_id}")
async def sms_status(message_id: str, request: Request):
    """Delivery receipt for an SMS we sent."""
    values = await _form_dict(request)
    _validate_signature(request, values)
    from app.services import sms_service

    await sms_service.apply_status(message_id, values.get("MessageStatus", "") or values.get("SmsStatus", ""), values.get("ErrorCode", ""))
    return Response(status_code=204)


@router.post("/recording-log/{call_log_id}")
async def log_recording_callback(call_log_id: str, request: Request):
    """Recording of an inbound call (started from the media stream)."""
    values = await _form_dict(request)
    _validate_signature(request, values)
    recording_sid = values.get("RecordingSid", "")
    if recording_sid:
        async with AsyncSessionLocal() as session:
            await call_service.apply_log_recording_callback(session, call_log_id, recording_sid)
    return Response(status_code=204)


@router.post("/inbound")
async def inbound_call(request: Request):
    """Voice webhook of the platform's Twilio number(s): route the call to the account
    whose inbound number was dialed and connect it to that account's agent."""
    values = await _form_dict(request)
    _validate_signature(request, values)
    async with AsyncSessionLocal() as session:
        twiml = await call_service.answer_inbound_call(
            session,
            to_number=values.get("To", "") or values.get("Called", ""),
            from_number=values.get("From", "") or values.get("Caller", ""),
            call_sid=values.get("CallSid", ""),
        )
    return Response(content=twiml, media_type="application/xml")


@router.post("/whatsapp")
async def whatsapp_message(request: Request):
    """Incoming WhatsApp message on an account's Twilio WhatsApp sender → the agent's reply (TwiML)."""
    from app.services import channel_service

    values = await _form_dict(request)
    _validate_signature(request, values)
    twiml = await channel_service.handle_whatsapp(values)
    return Response(content=twiml, media_type="application/xml")


@router.post("/twiml/{order_id}")
async def twiml_fallback(order_id: str, request: Request):
    """Same TwiML the call was created with (for a manual redirect / debugging)."""
    values = await _form_dict(request)
    _validate_signature(request, values)
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id)
        log = None
        if order is not None:
            log = await session.scalar(
                select(CallLog).where(CallLog.order_id == order.id).order_by(CallLog.created_at.desc()).limit(1)
            )
    if order is None or log is None:
        return Response(content=say_twiml("Sorry, this call cannot be connected."), media_type="application/xml")
    return Response(content=stream_twiml(call_log_id=log.id, order_id=order.id), media_type="application/xml")


@router.websocket("/media")
async def media_stream(websocket: WebSocket):
    """Media stream of a phone call (Twilio) or of a browser test call (same protocol)."""
    await websocket.accept()
    first = await websocket.receive_json()
    if first.get("event") != "connected":
        await websocket.close(code=1002)
        return
    start = await websocket.receive_json()
    if start.get("event") != "start":
        await websocket.close(code=1002)
        return
    start_payload = start.get("start") or {}
    custom = start_payload.get("customParameters") or {}
    order_id = str(custom.get("order_id") or "")
    call_log_id = str(custom.get("call_log_id") or "")
    media_token = str(custom.get("media_token") or "")
    if not call_log_id or not media_token:
        await websocket.close(code=1008)
        return
    try:
        verify_media_stream_token(media_token, order_id=order_id, call_log_id=call_log_id)
    except HTTPException:
        await websocket.close(code=1008)
        return
    accepted_at = time.monotonic()
    snapshot = prepared.get_call_snapshot(call_log_id)
    if snapshot is not None:
        merchant, order, ctx = snapshot.merchant, snapshot.order, snapshot.ctx
        direction, web, call_sid = snapshot.direction, snapshot.web, snapshot.call_sid
    else:
        # Not placed by this process (restart): rebuild from the database.
        async with AsyncSessionLocal() as session:
            log = await session.get(CallLog, call_log_id)
            merchant = await session.get(Merchant, log.merchant_id) if log is not None else None
            order = await session.get(Order, order_id) if order_id else None
            if log is None or merchant is None:
                await logger.awarning("media_unknown_call", call_log_id=call_log_id)
                await websocket.close(code=1008)
                return
            direction = DIRECTION_OUTBOUND if order is not None and log.direction == DIRECTION_OUTBOUND else DIRECTION_INBOUND
            web = log.direction == "web"
            call_sid = log.twilio_call_sid
            from app.services.context_service import build_context

            ctx = await build_context(session, merchant, record=order, direction=direction, caller_number=log.caller_number, test=web)
    logger.info(
        "media_bootstrap",
        call_log_id=call_log_id,
        source="snapshot" if snapshot is not None else "database",
        direction=direction,
        web=web,
        ms=int((time.monotonic() - accepted_at) * 1000),
    )
    call_sid = start_payload.get("callSid") or call_sid
    if direction == DIRECTION_INBOUND and call_sid and not web:
        asyncio.create_task(call_service.start_call_recording(call_sid, call_log_id))
    store = call_service.DbCallStore(
        order_id=str(getattr(order, "id", "") or ""),
        call_log_id=call_log_id,
        merchant_id=merchant.id,
        currency=merchant.currency,
        source="test" if web else ("inbound_call" if direction == DIRECTION_INBOUND else "outbound_call"),
    )
    bridge = CallBridge(
        websocket,
        merchant=merchant,
        order=order,
        call_log_id=call_log_id,
        stream_sid=start_payload.get("streamSid"),
        call_sid=call_sid,
        store=store,
        ctx=ctx,
        direction=direction,
        web=web,
    )
    try:
        await bridge.run()
    finally:
        prepared.pop_call_snapshot(call_log_id)
