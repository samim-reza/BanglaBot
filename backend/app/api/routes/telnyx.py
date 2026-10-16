"""Telnyx webhooks: inbound calls, status, recordings, AMD, SMS receipts, and the media stream.

Voice callbacks are TeXML's Twilio-style form posts (CallSid, CallStatus, ...);
messaging receipts are Telnyx JSON events. Every webhook URL ends in an HMAC
signature (``services.telnyx_urls``) checked before anything else; the unsigned
forms are refused in production (ENFORCE_WEBHOOK_SIGNATURES overrides). The media socket is
authorized by the signed media token in its start frame.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from urllib.parse import parse_qsl

import structlog
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import Response
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import boot_guard, verify_media_stream_token
from app.db.session import AsyncSessionLocal
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND
from app.models import CallLog, Merchant, Order
from app.services import call_service, telnyx, telnyx_urls
from app.voice import prepared
from app.voice.bridge import CallBridge
from app.voice.twiml import say_twiml, stream_twiml

router = APIRouter(prefix="/telnyx", tags=["telnyx"])
logger = structlog.get_logger(__name__)

#: Recording ids go into Telnyx API paths: plain tokens only.
_RECORDING_SID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
#: The media socket's first frames must arrive this fast (unauthenticated until then).
MEDIA_HANDSHAKE_SECONDS = 10.0


def _guard_path(request: Request, kind: str, value: str | None, sig: str | None) -> bool:
    """First thing every webhook does: a signed path must carry a valid signature
    (constant-time); unsigned paths are refused in production (ENFORCE_WEBHOOK_SIGNATURES
    overrides). True when the path was signed."""
    if sig is not None:
        if not telnyx_urls.verify(kind, value, sig):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
        return True
    if boot_guard.webhook_signatures_enforced(get_settings()):
        raise HTTPException(status_code=403, detail="Unsigned webhook URL")
    logger.warning("telnyx_unsigned_webhook", path=request.url.path, hint="point Telnyx at the signed URL: python -m scripts.telnyx_route")
    return False


async def _verified_body(request: Request) -> bytes:
    """The raw body; Telnyx's Ed25519 signature is checked whenever TELNYX_PUBLIC_KEY is set."""
    raw = await request.body()
    if get_settings().telnyx_public_key:
        signature = request.headers.get("telnyx-signature-ed25519") or ""
        timestamp = request.headers.get("telnyx-timestamp") or ""
        if not telnyx.verify_signature(raw, signature, timestamp):
            raise HTTPException(status_code=401, detail="Invalid Telnyx signature")
    return raw


async def _form_dict(request: Request, *, signed: bool = False) -> dict[str, str]:
    """A TeXML callback's fields (form body, or the query string on a GET)."""
    raw = await _verified_body(request)
    values = {str(key): str(value) for key, value in request.query_params.items()}
    values.update({key: value for key, value in parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True)})
    if signed or get_settings().telnyx_public_key:
        # Only an authenticated callback may teach us the platform's account id.
        telnyx.remember_account_sid(values.get("AccountSid"))
    return values


def _duration(value: str | None) -> int:
    """CallDuration as whole seconds; garbage (negative, inf, nan, text) reads as 0."""
    try:
        seconds = float(value or 0)
    except ValueError:
        return 0
    if seconds != seconds or not 0 <= seconds <= 86_400:
        return 0
    return int(seconds)


def _recording_sid(value: str | None) -> str:
    sid = str(value or "").strip()
    return sid if _RECORDING_SID.match(sid) else ""


@router.post("/status/{order_id}/{sig}")
@router.post("/status/{order_id}")
async def status_callback(order_id: str, request: Request, sig: str | None = None):
    signed = _guard_path(request, telnyx_urls.STATUS, order_id, sig)
    values = await _form_dict(request, signed=signed)
    call_status = values.get("CallStatus", "")
    duration = _duration(values.get("CallDuration"))
    async with AsyncSessionLocal() as session:
        await call_service.apply_status_callback(session, order_id, values.get("CallSid", ""), call_status, duration)
    return Response(status_code=204)


@router.post("/amd/{order_id}/{sig}")
@router.post("/amd/{order_id}")
async def amd_callback(order_id: str, request: Request, sig: str | None = None):
    """Async answering-machine detection: hang up on voicemail so the order stays callable."""
    signed = _guard_path(request, telnyx_urls.AMD, order_id, sig)
    values = await _form_dict(request, signed=signed)
    async with AsyncSessionLocal() as session:
        await call_service.apply_amd_callback(session, order_id, values.get("CallSid", ""), values.get("AnsweredBy", ""))
    return Response(status_code=204)


@router.post("/recording/{order_id}/{sig}")
@router.post("/recording/{order_id}")
async def recording_callback(order_id: str, request: Request, sig: str | None = None):
    signed = _guard_path(request, telnyx_urls.RECORDING, order_id, sig)
    values = await _form_dict(request, signed=signed)
    recording_sid = _recording_sid(values.get("RecordingSid"))
    if recording_sid:
        async with AsyncSessionLocal() as session:
            await call_service.apply_recording_callback(session, order_id, values.get("CallSid", ""), recording_sid)
    return Response(status_code=204)


@router.post("/recording-log/{call_log_id}/{sig}")
@router.post("/recording-log/{call_log_id}")
async def log_recording_callback(call_log_id: str, request: Request, sig: str | None = None):
    """Recording of an inbound call (started from the media stream)."""
    signed = _guard_path(request, telnyx_urls.RECORDING_LOG, call_log_id, sig)
    values = await _form_dict(request, signed=signed)
    recording_sid = _recording_sid(values.get("RecordingSid"))
    if recording_sid:
        async with AsyncSessionLocal() as session:
            await call_service.apply_log_recording_callback(session, call_log_id, recording_sid)
    return Response(status_code=204)


@router.get("/inbound/{sig}", status_code=204)
async def inbound_check(sig: str):
    """204 when ``sig`` is this server's inbound signature (scripts/telnyx_route.py checks before repointing)."""
    if not telnyx_urls.verify(telnyx_urls.INBOUND, None, sig):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    return Response(status_code=204)


@router.post("/inbound/{sig}")
@router.post("/inbound")
async def inbound_call(request: Request, sig: str | None = None):
    """Voice webhook of the platform's TeXML application: route the call to the account
    whose inbound number was dialed and connect it to that account's agent."""
    signed = _guard_path(request, telnyx_urls.INBOUND, None, sig)
    values = await _form_dict(request, signed=signed)
    async with AsyncSessionLocal() as session:
        texml = await call_service.answer_inbound_call(
            session,
            to_number=values.get("To", "") or values.get("Called", ""),
            from_number=values.get("From", "") or values.get("Caller", ""),
            call_sid=values.get("CallSid", ""),
        )
    return Response(content=texml, media_type="application/xml")


@router.post("/texml/{order_id}/{sig}")
async def texml_fallback(order_id: str, sig: str, request: Request):
    """Same TeXML the call was created with (for a manual redirect / debugging). Signed
    only: the answer carries a media token for the order's call."""
    signed = _guard_path(request, telnyx_urls.TEXML, order_id, sig)
    await _form_dict(request, signed=signed)
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


@router.post("/sms-status/{message_id}/{sig}")
@router.post("/sms-status/{message_id}")
async def sms_status(message_id: str, request: Request, sig: str | None = None):
    """Delivery receipt for an SMS we sent (per-message webhook URL)."""
    _guard_path(request, telnyx_urls.SMS_STATUS, message_id, sig)
    return await _sms_event(request, message_id)


@router.post("/sms-events/{sig}")
@router.post("/sms-events")
async def sms_events(request: Request, sig: str | None = None):
    """The messaging profile's webhook: receipts for texts sent without a per-message URL."""
    _guard_path(request, telnyx_urls.SMS_EVENTS, None, sig)
    return await _sms_event(request)


@router.websocket("/media")
async def media_stream(websocket: WebSocket):
    """Media stream of a phone call (Telnyx) or of a browser test call (Twilio-style frames)."""
    await websocket.accept()
    try:
        # Unauthenticated until the start frame's token checks out: no idle sockets, no odd frames.
        first = await asyncio.wait_for(websocket.receive_json(), MEDIA_HANDSHAKE_SECONDS)
        start = await asyncio.wait_for(websocket.receive_json(), MEDIA_HANDSHAKE_SECONDS) if isinstance(first, dict) and first.get("event") == "connected" else None
    except (asyncio.TimeoutError, ValueError):
        await websocket.close(code=1008)
        return
    if not isinstance(start, dict) or start.get("event") != "start":
        await websocket.close(code=1002)
        return
    start_payload = start.get("start") if isinstance(start.get("start"), dict) else {}
    custom = start_payload.get("custom_parameters") or start_payload.get("customParameters") or {}
    if not isinstance(custom, dict):
        await websocket.close(code=1008)
        return
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
    prepared.mark_media_started(call_log_id)
    if prepared.call_ended(call_log_id):
        # Telnyx re-opened the stream of a call the agent already ended: don't greet again.
        await logger.ainfo("media_reconnect_after_end", call_log_id=call_log_id)
        await websocket.close()
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
            if log.call_status == "completed":
                # Finished on another worker (or before a restart): never restart its conversation.
                await logger.ainfo("media_reconnect_after_end", call_log_id=call_log_id)
                await websocket.close()
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
