"""Chat channels: the owner's view (WhatsApp number, Facebook Page) and Meta's webhook."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.addons import entitlements
from app.core.config import get_settings
from app.core.plans import CHANNEL_MESSENGER
from app.db.session import get_db
from app.models import Merchant
from app.services import channel_service

router = APIRouter(tags=["channels"])


def _view(merchant: Merchant) -> dict[str, Any]:
    ent = entitlements(merchant)
    return {
        **channel_service.channel_view(merchant),
        "active": sorted(ent.channels),
        "platform": channel_service.platform_status(),
    }


@router.get("/api/channels")
async def channels(merchant: Merchant = Depends(get_current_merchant)):
    return _view(merchant)


class MessengerIn(BaseModel):
    page_id: str = Field(min_length=3, max_length=40, pattern=r"^\d+$")
    page_token: str = Field(min_length=20, max_length=600)


@router.put("/api/channels/messenger")
async def connect_messenger(data: MessengerIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    if not entitlements(merchant).has_channel(CHANNEL_MESSENGER):
        raise HTTPException(status_code=403, detail="The Messenger bot is an add-on — request it on the Add-ons page")
    try:
        stored = await channel_service.connect_messenger(data.page_id, data.page_token.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    config = channel_service.settings_of(merchant)
    config["messenger"] = stored
    merchant.channel_settings = config
    await db.commit()
    await db.refresh(merchant)
    return _view(merchant)


@router.delete("/api/channels/messenger")
async def disconnect_messenger(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    config = channel_service.settings_of(merchant)
    config.pop("messenger", None)
    merchant.channel_settings = config
    await db.commit()
    await db.refresh(merchant)
    return _view(merchant)


# ------------------------------------------------------------------ Meta webhook (public)
@router.get("/api/meta/webhook")
async def meta_verify(
    mode: str = Query(default="", alias="hub.mode"),
    token: str = Query(default="", alias="hub.verify_token"),
    challenge: str = Query(default="", alias="hub.challenge"),
):
    """Meta's one-time check when the webhook URL is saved in the app dashboard."""
    expected = str(get_settings().meta_verify_token or "")
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/api/meta/webhook")
async def meta_events(request: Request):
    body = await request.body()
    if not channel_service.verify_signature(body, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return {"ok": True}
    accepted = await channel_service.handle_messenger(payload if isinstance(payload, dict) else {})
    return {"ok": True, "accepted": accepted}
