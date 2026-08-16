"""Twilio webhooks: TwiML for outbound calls, status callbacks, media stream WS."""

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import Response
from loguru import logger
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import CallLog, Merchant, Order, OrderStatus
from app.services import voice_tiers
from app.services.call_service import apply_status_callback
from app.services.recording_service import save_recording
from app.voice import static_call
from app.voice.agent import run_call_agent

router = APIRouter(tags=["twilio"])


async def _verify_twilio_signature(request: Request) -> dict:
    """Reject webhook posts that don't carry a valid X-Twilio-Signature.

    Twilio signs the exact public URL it requested plus the POST params; we
    reconstruct the URL from PUBLIC_BASE_URL (the ngrok/production host) since
    the app itself sits behind the tunnel. Returns the parsed form either way.
    """
    form = dict(await request.form())
    settings = get_settings()
    if not (
        settings.twilio_validate_webhooks
        and settings.twilio_auth_token
        and settings.public_base_url
    ):
        return form
    url = settings.public_base_url.rstrip("/") + request.url.path
    if request.url.query:
        url += f"?{request.url.query}"
    signature = request.headers.get("X-Twilio-Signature", "")
    if not RequestValidator(settings.twilio_auth_token).validate(url, form, signature):
        logger.warning(f"Rejected unsigned Twilio webhook: {request.url.path}")
        raise HTTPException(403, "invalid twilio signature")
    return form


@router.post("/twilio/twiml/{order_id}")
async def twiml_for_order(order_id: str, request: Request, attempt: int = 1) -> Response:
    """Called by Twilio when the customer answers.

    AI tiers connect the audio to our media-stream agent; the static tier
    speaks the order summary and gathers a keypad digit instead.
    """
    await _verify_twilio_signature(request)
    base = get_settings().public_base_url.rstrip("/")

    async with AsyncSessionLocal() as db:
        order = await db.get(Order, order_id)
        merchant = await db.get(Merchant, order.merchant_id) if order else None
    if order and merchant and voice_tiers.get_tier(merchant.voice_tier).mode == "static":
        twiml = static_call.build_prompt_twiml(order, merchant, base, attempt)
        return Response(content=twiml, media_type="application/xml")

    ws_url = base.replace("https://", "wss://").replace("http://", "ws://") + "/twilio/ws"
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=ws_url)
    stream.parameter(name="order_id", value=order_id)
    connect.append(stream)
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")


@router.post("/twilio/gather/{order_id}")
async def gather_result(order_id: str, request: Request, attempt: int = 1) -> Response:
    """Keypad answer from a static call: record the outcome and speak the result."""
    form = await _verify_twilio_signature(request)
    digit = str(form.get("Digits", ""))
    call_sid = str(form.get("CallSid", ""))
    base = get_settings().public_base_url.rstrip("/")

    async with AsyncSessionLocal() as db:
        order = await db.get(Order, order_id)
        merchant = await db.get(Merchant, order.merchant_id) if order else None
        if not order or not merchant:
            response = VoiceResponse()
            response.hangup()
            return Response(content=str(response), media_type="application/xml")
        twiml, outcome = static_call.build_result_twiml(order, merchant, base, digit, attempt)
        if outcome:
            order.status = {
                "confirmed": OrderStatus.confirmed,
                "cancelled": OrderStatus.cancelled,
                "transfer": OrderStatus.needs_review,
            }[outcome]
            log = (
                await db.execute(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
            ).scalar_one_or_none()
            if log:
                log.outcome = outcome
                log.transcript = (
                    f"[স্ট্যাটিক কল] কাস্টমার {digit} চেপেছেন — ফলাফল: {outcome}"
                )
            await db.commit()
            logger.info(f"Static call {call_sid}: digit={digit} outcome={outcome}")
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status/{order_id}")
async def call_status(order_id: str, request: Request) -> Response:
    form = await _verify_twilio_signature(request)
    call_sid = str(form.get("CallSid", ""))
    call_status = str(form.get("CallStatus", ""))
    duration = int(form.get("CallDuration", 0) or 0)
    logger.info(f"Status callback: order={order_id} sid={call_sid} status={call_status}")
    async with AsyncSessionLocal() as db:
        await apply_status_callback(db, order_id, call_sid, call_status, duration)
    return Response(status_code=204)


@router.post("/twilio/recording/{order_id}")
async def recording_status(order_id: str, request: Request) -> Response:
    form = await _verify_twilio_signature(request)
    call_sid = str(form.get("CallSid", ""))
    recording_sid = str(form.get("RecordingSid", ""))
    logger.info(f"Recording callback: order={order_id} sid={call_sid} rec={recording_sid}")
    if call_sid and recording_sid:
        async with AsyncSessionLocal() as db:
            await save_recording(db, call_sid, recording_sid)
    return Response(status_code=204)


@router.websocket("/twilio/ws")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        await run_call_agent(websocket)
    except Exception as e:
        logger.exception(f"Voice agent error: {e}")
