"""Public endpoints: health, website data (solutions, plans), talk-to-sales, and the chat widget."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.addons import entitlements
from app.core.addons import public_catalog as addon_catalog
from app.core.plans import CHANNEL_WEB_CHAT, PLANS
from app.core.ratelimit import limit
from app.core.redis import redis_health
from app.core.regions import regions_json
from app.db.session import AsyncSessionLocal
from app.flows.context import DIRECTION_INBOUND
from app.models import CallLog, Merchant, SalesInquiry
from app.verticals import VERTICALS, flow_for
from app.voice import text_session

router = APIRouter(tags=["public"])

_WIDGET_JS = Path(__file__).resolve().parents[2] / "static" / "widget.js"
#: Widget responses are read by any website the business embeds them on.
_CORS = {"Access-Control-Allow-Origin": "*"}


@router.get("/health")
async def health():
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name, "redis": await redis_health()}


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
        "demo_widget_key": await _demo_widget_key(),
    }


async def _demo_widget_key() -> str:
    """The website's "try it" chat: the widget of the configured demo account."""
    username = get_settings().demo_widget_username
    if not username:
        return ""
    async with AsyncSessionLocal() as session:
        merchant = await session.scalar(select(Merchant).where(Merchant.username == username))
    if merchant is None or not merchant.active or not merchant.widget_enabled:
        return ""
    return merchant.widget_key


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
    limit(request, "contact", max_hits=5, per_seconds=3600)
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
async def calendar_feed(token: str, item: str = ""):
    """An account's bookings as an iCalendar feed (subscribe from Google / Outlook / Apple)."""
    from app.services import calendar_service

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
    if not key or len(key) > 64:
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
async def widget_config(key: str):
    merchant = await _widget_merchant(key)
    if merchant is None:
        return _json({"enabled": False})
    look = dict(merchant.widget_settings or {})
    return _json(
        {
            "enabled": True,
            "title": look.get("title") or merchant.business_name,
            "subtitle": look.get("subtitle") or "",
            "color": look.get("color") or "#0f766e",
            "position": look.get("position") or "right",
        }
    )


@router.post("/api/public/widget/{key}/start")
async def widget_start(key: str, request: Request):
    limit(request, f"widget-start:{key}", max_hits=30, per_seconds=3600)
    merchant = await _widget_merchant(key)
    if merchant is None:
        return _json({"detail": "Chat is not available."}, 404)
    settings = get_settings()
    if not settings.openai_api_key:
        return _json({"detail": "Chat is not available right now."}, 503)
    from app.services.call_service import DbCallStore
    from app.services.context_service import build_context

    async with AsyncSessionLocal() as session:
        flow = flow_for(merchant, DIRECTION_INBOUND)
        log = CallLog(
            order_id=None,
            merchant_id=merchant.id,
            call_status="in-progress",
            language=merchant.language or "en",
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
    limit(request, f"widget-say:{key}", max_hits=120, per_seconds=600)
    data = await _body(request)
    chat = text_session.get(str(data.get("session_id") or ""))
    if chat is None or getattr(chat.merchant, "widget_key", None) != key:
        return _json({"detail": "This chat has ended — start a new one."}, 404)
    try:
        payload = _SayIn.model_validate({"text": data.get("text", "")})
    except ValidationError:
        return _json({"detail": "Please type a message (up to 600 characters)."}, 422)
    messages = await chat.say(payload.text)
    return _json({"messages": messages, "ended": chat.ended})


class _SayIn(BaseModel):
    text: str = Field(min_length=1, max_length=600)
