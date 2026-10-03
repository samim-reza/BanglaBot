"""Telnyx webhooks: inbound calls, status, recordings, AMD, SMS receipts, and the media stream.

Voice callbacks are TeXML's Twilio-style form posts (CallSid, CallStatus, ...);
messaging receipts are Telnyx JSON events.
"""

from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import parse_qsl

import structlog
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import Response
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import verify_media_stream_token
from app.db.session import AsyncSessionLocal
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND
from app.models import CallLog, Merchant, Order
from app.services import call_service, telnyx
from app.voice import prepared
from app.voice.bridge import CallBridge
from app.voice.twiml import say_twiml, stream_twiml

router = APIRouter(prefix="/telnyx", tags=["telnyx"])
logger = structlog.get_logger(__name__)


async def _verified_body(request: Request) -> bytes:
    raw = await request.body()
    settings = get_settings()
    if settings.enforce_webhook_signatures:
        if not settings.telnyx_public_key:
            raise HTTPException(status_code=500, detail="TELNYX_PUBLIC_KEY is not configured")
        signature = request.headers.get("telnyx-signature-ed25519") or ""
        timestamp = request.headers.get("telnyx-timestamp") or ""
        if not telnyx.verify_signature(raw, signature, timestamp):
            raise HTTPException(status_code=401, detail="Invalid Telnyx signature")
    return raw


async def _form_dict(request: Request) -> dict[str, str]:
    """A TeXML callback's fields (form body, or the query string on a GET)."""
    raw = await _verified_body(request)
    values = {str(key): str(value) for key, value in request.query_params.items()}
    values.update({key: value for key, value in parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True)})
    telnyx.remember_account_sid(values.get("AccountSid"))
    return values


@router.post("/status/{order_id}")
async def status_callback(order_id: str, request: Request):
    values = await _form_dict(request)
    call_status = values.get("CallStatus", "")
    try:
        duration = int(float(values.get("CallDuration") or 0))
    except ValueError:
        duration = 0
    async with AsyncSessionLocal() as session:
        await call_service.apply_status_callback(session, order_id, values.get("CallSid", ""), call_status, duration)
    return Response(status_code=204)


@router.post("/amd/{order_id}")
async def amd_callback(order_id: str, request: Request):
    """Async answering-machine detection: hang up on voicemail so the order stays callable."""
    values = await _form_dict(request)
    async with AsyncSessionLocal() as session:
        await call_service.apply_amd_callback(session, order_id, values.get("CallSid", ""), values.get("AnsweredBy", ""))
    return Response(status_code=204)


@router.post("/recording/{order_id}")
async def recording_callback(order_id: str, request: Request):
    values = await _form_dict(request)
    recording_sid = values.get("RecordingSid", "")
    if recording_sid:
        async with AsyncSessionLocal() as session:
            await call_service.apply_recording_callback(session, order_id, values.get("CallSid", ""), recording_sid)
    return Response(status_code=204)


@router.post("/recording-log/{call_log_id}")
async def log_recording_callback(call_log_id: str, request: Request):
    """Recording of an inbound call (started from the media stream)."""
    values = await _form_dict(request)
    recording_sid = values.get("RecordingSid", "")
    if recording_sid:
        async with AsyncSessionLocal() as session:
            await call_service.apply_log_recording_callback(session, call_log_id, recording_sid)
    return Response(status_code=204)


@router.post("/inbound")
async def inbound_call(request: Request):
    """Voice webhook of the platform's TeXML application: route the call to the account
    whose inbound number was dialed and connect it to that account's agent."""
    values = await _form_dict(request)
    async with AsyncSessionLocal() as session:
        texml = await call_service.answer_inbound_call(
            session,
            to_number=values.get("To", "") or values.get("Called", ""),
            from_number=values.get("From", "") or values.get("Caller", ""),
            call_sid=values.get("CallSid", ""),
        )
    return Response(content=texml, media_type="application/xml")


@router.post("/texml/{order_id}")
async def texml_fallback(order_id: str, request: Request):
    """Same TeXML the call was created with (for a manual redirect / debugging)."""
    await _form_dict(request)
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


async def _sms_event(request: Request, message_id: str = "") -> Response:
    raw = await _verified_body(request)
    from app.services import sms_service

    try:
        event = json.loads(raw or b"{}")
    except ValueError:
        return Response(status_code=204)
    data = event.get("data") if isinstance(event, dict) else None
    if not isinstance(data, dict) or data.get("event_type") not in ("message.sent", "message.finalized"):
        return Response(status_code=204)
    payload = data.get("payload") or {}
    recipients = payload.get("to") or []
    status = str((recipients[0] or {}).get("status") or "") if recipients and isinstance(recipients[0], dict) else ""
    errors = payload.get("errors") or []
    error = ""
    if errors and isinstance(errors[0], dict):
        error = str(errors[0].get("detail") or errors[0].get("title") or errors[0].get("code") or "")
    await sms_service.apply_status(message_id, status, error, provider_sid=str(payload.get("id") or ""))
    return Response(status_code=204)


@router.post("/sms-status/{message_id}")
async def sms_status(message_id: str, request: Request):
    """Delivery receipt for an SMS we sent (per-message webhook URL)."""
    return await _sms_event(request, message_id)


@router.post("/sms-events")
async def sms_events(request: Request):
    """The messaging profile's webhook: receipts for texts sent without a per-message URL."""
    return await _sms_event(request)


@router.websocket("/media")
async def media_stream(websocket: WebSocket):
    """Media stream of a phone call (Telnyx) or of a browser test call (Twilio-style frames)."""
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
    custom = start_payload.get("custom_parameters") or start_payload.get("customParameters") or {}
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
    telnyx.remember_account_sid(start_payload.get("user_id"))
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
    # Telnyx: the call_control_id is the TeXML CallSid. The outbound create call may
    # not have returned it, so record it now.
    stream_call_sid = str(start_payload.get("call_control_id") or start_payload.get("callSid") or "")
    if stream_call_sid and not web and stream_call_sid != call_sid:
        asyncio.create_task(call_service.remember_call_sid(call_log_id, stream_call_sid))
    call_sid = stream_call_sid or call_sid
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
        stream_sid=start.get("stream_id") or start_payload.get("streamSid") or call_log_id,
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
