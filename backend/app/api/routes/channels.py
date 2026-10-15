"""Chat channels: the owner's view (WhatsApp, Facebook Page, Instagram) and Meta's webhook."""

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
from app.core.entitlements import channel_states
from app.core.plans import CHANNEL_INSTAGRAM, CHANNEL_MESSENGER, CHANNEL_WHATSAPP
from app.db.session import get_db
from app.models import Merchant
from app.services import channel_service, meta_channels

router = APIRouter(tags=["channels"])


def _view(merchant: Merchant) -> dict[str, Any]:
    ent = entitlements(merchant)
    return {
        **channel_service.channel_view(merchant),
        **meta_channels.view(merchant),
        "active": sorted(ent.channels),
        # Per channel: included (tier) / addon (bought) / available (can buy) / unavailable.
        "status": channel_states(merchant),
        "platform": {**channel_service.platform_status(), **meta_channels.platform_status()},
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


# ------------------------------------------------------------------ Instagram + WhatsApp Cloud API
class InstagramIn(BaseModel):
    account_id: str = Field(min_length=3, max_length=40, pattern=r"^\d+$")
    page_token: str = Field(min_length=20, max_length=600)


class WhatsAppCloudIn(BaseModel):
    phone_number_id: str = Field(min_length=3, max_length=40, pattern=r"^\d+$")
    access_token: str = Field(min_length=20, max_length=1000)


async def _save_meta(db: AsyncSession, merchant: Merchant, kind: str, stored: dict[str, Any] | None) -> dict[str, Any]:
    config = channel_service.settings_of(merchant)
    if stored is None:
        config.pop(kind, None)
    else:
        config[kind] = stored
    merchant.channel_settings = config
    await db.commit()
    await db.refresh(merchant)
    return _view(merchant)


async def _connect_meta(db: AsyncSession, merchant: Merchant, kind: str, channel: str, key: str, connect) -> dict[str, Any]:
    if not entitlements(merchant).has_channel(channel):
        raise HTTPException(status_code=403, detail="This channel is an add-on — get it on the Add-ons page")
    if await meta_channels.taken(db, kind, key, merchant.id):
        raise HTTPException(status_code=409, detail="That account is already connected to another business")
    try:
        stored = await connect()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _save_meta(db, merchant, kind, stored)


@router.put("/api/channels/instagram")
async def connect_instagram(data: InstagramIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await _connect_meta(
        db, merchant, meta_channels.INSTAGRAM, CHANNEL_INSTAGRAM, data.account_id,
        lambda: meta_channels.connect_instagram(data.account_id, data.page_token.strip()),
    )


@router.delete("/api/channels/instagram")
async def disconnect_instagram(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await _save_meta(db, merchant, meta_channels.INSTAGRAM, None)


@router.put("/api/channels/whatsapp-cloud")
async def connect_whatsapp_cloud(data: WhatsAppCloudIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await _connect_meta(
        db, merchant, meta_channels.WHATSAPP_CLOUD, CHANNEL_WHATSAPP, data.phone_number_id,
        lambda: meta_channels.connect_whatsapp_cloud(data.phone_number_id, data.access_token.strip()),
    )


@router.delete("/api/channels/whatsapp-cloud")
async def disconnect_whatsapp_cloud(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await _save_meta(db, merchant, meta_channels.WHATSAPP_CLOUD, None)


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
    payload = payload if isinstance(payload, dict) else {}
    # Messenger (object "page"), Instagram ("instagram"), WhatsApp Cloud ("whatsapp_business_account").
    accepted = await channel_service.handle_messenger(payload) + await meta_channels.handle(payload)
    return {"ok": True, "accepted": accepted}
