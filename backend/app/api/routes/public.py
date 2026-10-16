"""Public endpoints: health, website data (solutions, plans), talk-to-sales, and the chat widget."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.addons import entitlements
from app.core.addons import public_catalog as addon_catalog
from app.core.plans import CHANNEL_WEB_CHAT, PLANS
from app.core.ratelimit import rate_limit
from app.core.redis import redis_health
from app.core.regions import regions_json
from app.db.session import AsyncSessionLocal
from app.flows.context import DIRECTION_INBOUND
from app.models import CallLog, Merchant, SalesInquiry
from app.verticals import VERTICALS, flow_for
from app.voice import text_session
from app.voice.languages import normalize_language

router = APIRouter(tags=["public"])

_WIDGET_JS = Path(__file__).resolve().parents[2] / "static" / "widget.js"
#: Widget responses are read by any website the business embeds them on.
_CORS = {"Access-Control-Allow-Origin": "*"}
#: Embed keys are ``secrets.token_urlsafe`` strings: anything else never reaches the database.
_WIDGET_KEY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_WIDGET_COLOR = "#0f766e"
#: Visitor messages per chat; a new chat starts after that (bounds one session's LLM spend).
MAX_WIDGET_TURNS = 60


@router.get("/health")
async def health():
    settings = get_settings()
    # Status words only: error details (hosts, ports) stay in the admin console's health view.
    redis = await redis_health()
    return {"status": "ok", "service": settings.app_name, "redis": {"status": str(redis.get("status") or "unknown")}}


@router.get("/api/public/catalog")
async def public_catalog():
    """What the website shows: the four solutions, plans and regions."""
    return {
        "verticals": [
            {"key": v.key, "label": v.label, "description": v.description, "directions": v.directions}
            for v in VERTICALS.values()
        ],
        "plans": [plan.as_json() for plan in PLANS.values() if plan.public],
        "addons": addon_catalog(),
        "regions": regions_json(),
    }


# ------------------------------------------------------------------ talk to sales
class SalesInquiryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=40)
    company: str = Field(default="", max_length=160)
    business_type: str = Field(default="", max_length=40)
    country: str = Field(default="", max_length=60)
    monthly_calls: str = Field(default="", max_length=40)
    message: str = Field(default="", max_length=4000)
    #: Honeypot: real visitors never fill this hidden field.
    website: str = Field(default="", max_length=200)


@router.post("/api/public/contact", status_code=201)
async def contact_sales(data: SalesInquiryIn, request: Request):
    await rate_limit(request, "contact", max_hits=5, per_seconds=3600)
    if data.website:
        return {"ok": True}
    if not data.email.strip() and not data.phone.strip():
        raise HTTPException(status_code=422, detail="Please leave an email or a phone number so we can reach you.")
    async with AsyncSessionLocal() as session:
        session.add(
            SalesInquiry(
                name=data.name.strip(),
                email=data.email.strip(),
                phone=data.phone.strip(),
                company=data.company.strip(),
                business_type=data.business_type.strip(),
                country=data.country.strip(),
                monthly_calls=data.monthly_calls.strip(),
                message=data.message.strip(),
            )
        )
        await session.commit()
    return {"ok": True}


# ------------------------------------------------------------------ calendar feed
@router.get("/api/public/calendar/{token}.ics")
async def calendar_feed(token: str, request: Request, item: str = ""):
    """An account's bookings as an iCalendar feed (subscribe from Google / Outlook / Apple)."""
    from app.services import calendar_service

    # Generous: calendar services (Google, Outlook) poll many feeds from a few addresses.
    await rate_limit(request, "calendar-feed", max_hits=300, per_seconds=60)

    result = await calendar_service.feed(token, item or None)
    if result is None:
        return Response(status_code=404, content="Unknown calendar")
    filename, body = result
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "private, max-age=300"},
    )


# ------------------------------------------------------------------ chat widget
@router.get("/api/public/widget.js")
async def widget_script():
    return Response(
        content=_WIDGET_JS.read_text("utf-8"),
        media_type="application/javascript",
        headers={**_CORS, "Cache-Control": "public, max-age=300"},
    )


async def _widget_merchant(key: str) -> Merchant | None:
    if not _WIDGET_KEY.match(key or ""):
        return None
    async with AsyncSessionLocal() as session:
        merchant = await session.scalar(select(Merchant).where(Merchant.widget_key == key))
    if merchant is None or not merchant.active or not merchant.widget_enabled:
        return None
    if not entitlements(merchant).has_channel(CHANNEL_WEB_CHAT):
        return None
    return merchant


def _json(payload: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers=_CORS)


async def _body(request: Request) -> dict:
    try:
        data = json.loads((await request.body()).decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@router.get("/api/public/widget/{key}/config")
async def widget_config(key: str, request: Request):
    await rate_limit(request, "widget-config", max_hits=120, per_seconds=60)
    merchant = await _widget_merchant(key)
    if merchant is None:
        return _json({"enabled": False})
    look = dict(merchant.widget_settings or {})
    color = str(look.get("color") or "")
    return _json(
        {
            "enabled": True,
            "title": look.get("title") or merchant.business_name,
            "subtitle": look.get("subtitle") or "",
            # Re-checked on the way out: the widget writes it into a <style> block.
            "color": color if _HEX_COLOR.match(color) else DEFAULT_WIDGET_COLOR,
            "position": "left" if look.get("position") == "left" else "right",
        }
    )


@router.post("/api/public/widget/{key}/start")
async def widget_start(key: str, request: Request):
    # Per visitor across every site, then per site (a random key can't dodge the first).
    await rate_limit(request, "widget-start", max_hits=60, per_seconds=3600)
    if not _WIDGET_KEY.match(key or ""):
        return _json({"detail": "Chat is not available."}, 404)
    await rate_limit(request, f"widget-start:{key}", max_hits=30, per_seconds=3600)
    merchant = await _widget_merchant(key)
    if merchant is None:
        return _json({"detail": "Chat is not available."}, 404)
    from app.voice.providers.llm import llm_configured

    # Any configured link of the LLM chain (Groq / Gemini / OpenAI…), not only an OpenAI key.
    if not llm_configured(merchant):
        return _json({"detail": "Chat is not available right now."}, 503)
    from app.services.call_service import DbCallStore
    from app.services.context_service import build_context

    async with AsyncSessionLocal() as session:
        flow = flow_for(merchant, DIRECTION_INBOUND)
        log = CallLog(
            order_id=None,
            merchant_id=merchant.id,
            call_status="in-progress",
            language=normalize_language(merchant.language),
            direction="widget",
            flow=flow.key,
        )
        session.add(log)
        await session.flush()
        ctx = await build_context(session, merchant, direction=DIRECTION_INBOUND)
        await session.commit()
    ctx.channel = "chat"
    store = DbCallStore(order_id="", call_log_id=log.id, merchant_id=merchant.id, currency=merchant.currency, source="website_chat")
    chat = text_session.TextSession(merchant=merchant, ctx=ctx, flow=flow, store=store, call_log_id=log.id)
    text_session.register(chat)
    messages = await chat.start()
    return _json({"session_id": chat.id, "messages": messages})


@router.post("/api/public/widget/{key}/say")
async def widget_say(key: str, request: Request):
    await rate_limit(request, "widget-say", max_hits=240, per_seconds=600)
    if not _WIDGET_KEY.match(key or ""):
        return _json({"detail": "This chat has ended — start a new one."}, 404)
    await rate_limit(request, f"widget-say:{key}", max_hits=120, per_seconds=600)
    data = await _body(request)
    chat = text_session.get(str(data.get("session_id") or ""))
    if chat is None or getattr(chat.merchant, "widget_key", None) != key:
        return _json({"detail": "This chat has ended — start a new one."}, 404)
    turns = int(getattr(chat, "widget_turns", 0) or 0) + 1
    chat.widget_turns = turns
    if turns > MAX_WIDGET_TURNS:
        return _json({"detail": "This chat is very long — please start a new one.", "ended": True}, 429)
    try:
        payload = _SayIn.model_validate({"text": data.get("text", "")})
    except ValidationError:
        return _json({"detail": "Please type a message (up to 600 characters)."}, 422)
    messages = await chat.say(payload.text)
    return _json({"messages": messages, "ended": chat.ended})


class _SayIn(BaseModel):
    text: str = Field(min_length=1, max_length=600)
