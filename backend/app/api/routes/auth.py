"""Account owner: login, workspace (account + its business engine), settings."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.addons import entitlements
from app.core.config import get_settings
from app.core.plans import CHANNEL_WEB_CHAT
from app.core.regions import regions_json
from app.core.security import issue_merchant_token
from app.db.session import get_db
from app.flows.context import DIRECTION_INBOUND, DIRECTION_OUTBOUND, CallContext
from app.models import Merchant
from app.schemas.auth import ChangePasswordRequest, FlowPreview, LoginRequest, MerchantLoginResponse
from app.schemas.merchant import MerchantOut, MerchantSettingsUpdate
from app.services import auth_service, usage_service
from app.verticals import flow_for, vertical_for
from app.verticals.forms import FieldError, clean_config
from app.voice.languages import normalize_language

router = APIRouter(prefix="/api/auth", tags=["auth"])


def merchant_out(merchant: Merchant) -> MerchantOut:
    from app.core.addons import quantities
    from app.services.channel_service import channel_view

    out = MerchantOut.model_validate(merchant)
    return out.model_copy(update={"addons": quantities(getattr(merchant, "addons", None)), "channels": channel_view(merchant)})


def apply_settings(merchant: Merchant, data: MerchantSettingsUpdate) -> None:
    changes = data.model_dump(exclude_unset=True)
    if str(changes.get("webhook_url") or "").strip():
        from app.core.addons import entitlements

        if not entitlements(merchant).api_webhooks:
            raise HTTPException(status_code=403, detail="Webhooks are part of the Growth plan and above")
    config = changes.pop("vertical_config", None)
    widget = changes.pop("widget_settings", None)
    for key, value in changes.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        setattr(merchant, key, value)
    if config is not None:
        try:
            cleaned = clean_config(vertical_for(merchant), config)
        except FieldError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        merged = dict(merchant.vertical_config or {})
        merged.update(cleaned)
        for key, value in config.items():
            if value in (None, "") and key in merged:
                merged.pop(key)
        merchant.vertical_config = merged
    if widget is not None:
        merchant.widget_settings = widget
    if merchant.widget_enabled and not merchant.widget_key:
        merchant.widget_key = secrets.token_urlsafe(18)
    if merchant.webhook_url and not merchant.webhook_secret:
        merchant.webhook_secret = secrets.token_hex(24)
    if merchant.language not in (merchant.supported_languages or []):
        merchant.supported_languages = [merchant.language] + [
            code for code in (merchant.supported_languages or []) if code != merchant.language
        ]


@router.post("/login", response_model=MerchantLoginResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    merchant = await auth_service.login(db, request, username=data.username, password=data.password)
    return MerchantLoginResponse(token=issue_merchant_token(merchant), merchant=merchant_out(merchant))


@router.post("/logout-all")
async def logout_all(request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    """Sign out every session of this account; ``token`` keeps this browser signed in."""
    return {"ok": True, "token": await auth_service.sign_out_everywhere(db, request, merchant)}


@router.get("/me", response_model=MerchantOut)
async def me(merchant: Merchant = Depends(get_current_merchant)):
    return merchant_out(merchant)


@router.get("/workspace")
async def workspace(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    """Everything the portal needs to render itself for this account's business engine."""
    vertical = vertical_for(merchant)
    settings = get_settings()
    return {
        "merchant": merchant_out(merchant).model_dump(mode="json"),
        "vertical": vertical.as_json(),
        "config": vertical.config(merchant),
        "regions": regions_json(),
        "usage": await usage_service.month_usage(db, merchant),
        # Channels, features and limits from the plan + add-ons.
        "entitlements": entitlements(merchant).as_json(),
        "public_base_url": settings.public_base_url or "",
        "telephony": {
            "configured": bool(settings.telnyx_api_key and settings.telnyx_texml_app_id and settings.telnyx_from_number),
            "platform_number": settings.telnyx_from_number or "",
        },
    }


@router.patch("/me", response_model=MerchantOut)
async def update_me(
    data: MerchantSettingsUpdate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    if data.widget_enabled and not entitlements(merchant).has_channel(CHANNEL_WEB_CHAT):
        raise HTTPException(status_code=403, detail="The website chatbot is an add-on — request it on the Add-ons page")
    apply_settings(merchant, data)
    await db.commit()
    await db.refresh(merchant)
    return merchant_out(merchant)


@router.post("/me/widget-key", response_model=MerchantOut)
async def rotate_widget_key(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    """New embed key: the old snippet stops working (e.g. it was copied to the wrong site)."""
    merchant.widget_key = secrets.token_urlsafe(18)
    await db.commit()
    await db.refresh(merchant)
    return merchant_out(merchant)


@router.post("/me/webhook-secret", response_model=MerchantOut)
async def rotate_webhook_secret(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    merchant.webhook_secret = secrets.token_hex(24)
    await db.commit()
    await db.refresh(merchant)
    return merchant_out(merchant)


@router.post("/me/webhook-test")
async def test_webhook(merchant: Merchant = Depends(get_current_merchant)):
    from app.services.webhook_service import send_test_event

    if not merchant.webhook_url:
        raise HTTPException(status_code=422, detail="Set a webhook URL first")
    return await send_test_event(merchant)


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Other sessions are signed out; ``token`` keeps this browser signed in."""
    token = await auth_service.change_password(db, request, merchant, current=data.current_password, new=data.new_password)
    return {"ok": True, "token": token}


@router.get("/flow-preview", response_model=FlowPreview)
async def flow_preview(merchant: Merchant = Depends(get_current_merchant)):
    """The steps the agent takes, for both call directions this account has."""
    language = normalize_language(merchant.language)
    steps: list[str] = []
    sections: dict[str, list[str]] = {}
    for direction in (DIRECTION_INBOUND, DIRECTION_OUTBOUND):
        if direction not in vertical_for(merchant).flows:
            continue
        flow = flow_for(merchant, direction)
        ctx = CallContext(merchant=merchant, direction=direction)
        sections[direction] = flow.preview_steps(ctx, language)
    steps = sections.get(DIRECTION_OUTBOUND) or sections.get(DIRECTION_INBOUND) or []
    return FlowPreview(steps=steps, sections=sections)
