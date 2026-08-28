"""Twilio webhooks for the outbound call: status, recording, media stream, TwiML fallback."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import Response
from twilio.request_validator import RequestValidator

from app.core.config import get_settings
from app.core.security import verify_media_stream_token
from app.db.session import AsyncSessionLocal
from app.models import CallLog, Merchant, Order
from app.services import call_service
from app.voice.bridge import ConfirmationCallBridge
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


@router.post("/twiml/{order_id}")
async def twiml_fallback(order_id: str, request: Request):
    """Same TwiML the call was created with (for a manual redirect / debugging)."""
    values = await _form_dict(request)
    _validate_signature(request, values)
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id)
        log = None
        if order is not None:
            from sqlalchemy import select

            log = await session.scalar(
                select(CallLog).where(CallLog.order_id == order.id).order_by(CallLog.created_at.desc()).limit(1)
            )
    if order is None or log is None:
        return Response(content=say_twiml("Sorry, this call cannot be connected."), media_type="application/xml")
    return Response(content=stream_twiml(order_id=order.id, call_log_id=log.id), media_type="application/xml")


@router.websocket("/media")
async def media_stream(websocket: WebSocket):
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
    if not order_id or not call_log_id or not media_token:
        await websocket.close(code=1008)
        return
    try:
        verify_media_stream_token(media_token, order_id=order_id, call_log_id=call_log_id)
    except HTTPException:
        await websocket.close(code=1008)
        return
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id)
        merchant = await session.get(Merchant, order.merchant_id) if order is not None else None
        log = await session.get(CallLog, call_log_id)
    if order is None or merchant is None or log is None:
        await logger.awarning("twilio_media_unknown_call", order_id=order_id, call_log_id=call_log_id)
        await websocket.close(code=1008)
        return
    bridge = ConfirmationCallBridge(
        websocket,
        order=order,
        merchant=merchant,
        call_log_id=call_log_id,
        stream_sid=start_payload.get("streamSid"),
        call_sid=start_payload.get("callSid") or log.twilio_call_sid,
    )
    await bridge.run()
