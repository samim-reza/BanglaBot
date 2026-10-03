"""Twilio webhooks: WhatsApp messages only (calls and SMS run on Telnyx)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from twilio.request_validator import RequestValidator

from app.core.config import get_settings
from app.voice.twiml import PublicUrlMissing, public_base_url

router = APIRouter(prefix="/twilio", tags=["twilio"])


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


@router.post("/whatsapp")
async def whatsapp_message(request: Request):
    """Incoming WhatsApp message on an account's Twilio WhatsApp sender → the agent's reply (TwiML)."""
    from app.services import channel_service

    values = await _form_dict(request)
    _validate_signature(request, values)
    twiml = await channel_service.handle_whatsapp(values)
    return Response(content=twiml, media_type="application/xml")

