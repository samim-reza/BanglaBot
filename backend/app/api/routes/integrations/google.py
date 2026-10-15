"""Google Calendar connection: OAuth connect / callback, calendar choice, disconnect."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.api.routes.integrations.summary import _summary
from app.core.addons import entitlements
from app.core.config import get_settings
from app.core.plans import FEATURE_GOOGLE_CALENDAR
from app.db.session import get_db
from app.models import Merchant
from app.services import calendar_service

router = APIRouter()


@router.get("/google/connect")
async def google_connect(merchant: Merchant = Depends(get_current_merchant)):
    if not calendar_service.google_available():
        raise HTTPException(status_code=503, detail="Google Calendar is not set up on this server (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)")
    if not entitlements(merchant).has_feature(FEATURE_GOOGLE_CALENDAR):
        raise HTTPException(status_code=403, detail="Two-way Google Calendar is on Growth and Pro, or as an add-on")
    return {"url": calendar_service.auth_url(merchant.id)}


def _portal(status: str) -> RedirectResponse:
    origin = (get_settings().frontend_origin.split(",")[0] or "http://localhost:3000").strip().rstrip("/")
    return RedirectResponse(f"{origin}/settings?tab=calendar&google={status}", status_code=302)


@router.get("/google/callback")
async def google_callback(code: str = Query(default=""), state: str = Query(default=""), error: str = Query(default=""), db: AsyncSession = Depends(get_db)):
    """Google's redirect after consent (public — authorised by the signed ``state``)."""
    if error or not code:
        return _portal("denied")
    try:
        merchant_id = calendar_service.merchant_from_state(state)
    except Exception:  # noqa: BLE001
        return _portal("expired")
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        return _portal("expired")
    try:
        google = await calendar_service.exchange_code(code)
    except Exception as exc:  # noqa: BLE001
        import structlog

        await structlog.get_logger(__name__).awarning("google_connect_failed", error=str(exc)[:200])
        return _portal("failed")
    google.pop("_access_token", None)
    google.pop("_expires_in", None)
    config = calendar_service.settings_of(merchant)
    config["google"] = google
    merchant.calendar_settings = config
    if not merchant.calendar_token:
        merchant.calendar_token = secrets.token_urlsafe(24)
    await db.commit()
    calendar_service.invalidate_busy(merchant.id)
    return _portal("connected")


@router.get("/google/calendars")
async def google_calendars(merchant: Merchant = Depends(get_current_merchant)):
    try:
        return {"items": await calendar_service.list_calendars(merchant)}
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Google Calendar error: {str(exc)[:160]}") from exc


class GoogleIn(BaseModel):
    calendar_id: str | None = Field(default=None, max_length=300)
    check_busy: bool | None = None


@router.patch("/google")
async def google_update(
    data: GoogleIn, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    config = calendar_service.settings_of(merchant)
    google = dict(config.get("google") or {})
    if not google.get("refresh_token_enc"):
        raise HTTPException(status_code=409, detail="Connect Google Calendar first")
    if data.calendar_id:
        google["calendar_id"] = data.calendar_id.strip()
    if data.check_busy is not None:
        google["check_busy"] = bool(data.check_busy)
    config["google"] = google
    merchant.calendar_settings = config
    await db.commit()
    await db.refresh(merchant)
    calendar_service.invalidate_busy(merchant.id)
    return await _summary(request, merchant, db)


@router.delete("/google")
async def google_disconnect(request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await calendar_service.revoke(merchant)
    config = calendar_service.settings_of(merchant)
    config.pop("google", None)
    merchant.calendar_settings = config
    await db.commit()
    await db.refresh(merchant)
    calendar_service.invalidate_busy(merchant.id)
    return await _summary(request, merchant, db)
