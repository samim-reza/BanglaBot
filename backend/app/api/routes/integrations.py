"""Add-on integrations of an account: SMS confirmations and calendar sync."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.addons import entitlements
from app.core.config import get_settings
from app.core.plans import FEATURE_GOOGLE_CALENDAR
from app.db.session import get_db
from app.models import CatalogItem, Merchant, Message, Order
from app.services import calendar_service, sms_service
from app.services.context_service import invalidate_catalog

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def _base(request: Request) -> str:
    public = str(get_settings().public_base_url or "").rstrip("/")
    return public or str(request.base_url).rstrip("/")


def _message(row: Message) -> dict[str, Any]:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "kind": row.kind,
        "to_number": row.to_number,
        "body": row.body,
        "status": row.status,
        "error": row.error,
        "segments": row.segments,
        "created_at": row.created_at,
    }


async def _summary(request: Request, merchant: Merchant, db: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    calendar = calendar_service.settings_of(merchant)
    google = calendar.get("google") or {}
    base = _base(request)
    items = []
    from app.verticals import vertical_for

    vertical = vertical_for(merchant)
    if vertical.catalog_kind:
        rows = await db.scalars(
            select(CatalogItem)
            .where(CatalogItem.merchant_id == merchant.id, CatalogItem.kind == vertical.catalog_kind)
            .order_by(CatalogItem.sort_order, CatalogItem.created_at)
        )
        items = [
            {
                "id": row.id,
                "name": row.name,
                "feed_url": f"{base}/api/public/calendar/{merchant.calendar_token}.ics?item={row.id}" if merchant.calendar_token else "",
                "calendar_ics": (row.data or {}).get("calendar_ics", ""),
                "google_calendar_id": (row.data or {}).get("google_calendar_id", ""),
            }
            for row in rows
        ]
    from app.services.usage_service import month_start

    month_sms = int(
        await db.scalar(
            select(func.count(Message.id)).where(
                Message.merchant_id == merchant.id,
                Message.created_at >= month_start(),
                Message.status.in_(("sent", "delivered", "queued")),
            )
        )
        or 0
    )
    return {
        "sms": {
            "settings": sms_service.settings_of(merchant),
            "platform_ready": sms_service.platform_ready(),
            "sender": settings.twilio_messaging_service_sid and "Messaging Service" or (settings.twilio_sms_from or settings.twilio_from_number or ""),
            "sent_this_month": month_sms,
        },
        "calendar": {
            "feed_url": f"{base}/api/public/calendar/{merchant.calendar_token}.ics" if merchant.calendar_token else "",
            "public": bool(settings.public_base_url),
            "busy_ics_urls": list(calendar.get("busy_ics_urls") or []),
            "items": items,
            "google": {
                "available": calendar_service.google_available(),
                "included": entitlements(merchant).has_feature(FEATURE_GOOGLE_CALENDAR),
                "connected": bool(google.get("refresh_token_enc")),
                "email": google.get("email", ""),
                "calendar_id": google.get("calendar_id", "primary"),
                "check_busy": bool(google.get("check_busy", True)),
                "redirect_uri": calendar_service.redirect_uri(),
            },
        },
    }


@router.get("")
async def summary(request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await _summary(request, merchant, db)


# ------------------------------------------------------------------------------- SMS
class SmsSettingsIn(BaseModel):
    enabled: bool | None = None
    on_booking: bool | None = None
    on_change: bool | None = None
    reminder_hours: int | None = Field(default=None, ge=0, le=168)


@router.patch("/sms")
async def update_sms(
    data: SmsSettingsIn, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    current = sms_service.settings_of(merchant)
    current.update({key: value for key, value in data.model_dump(exclude_unset=True).items() if value is not None})
    merchant.sms_settings = current
    await db.commit()
    await db.refresh(merchant)
    return await _summary(request, merchant, db)


class SmsTestIn(BaseModel):
    to: str = Field(min_length=6, max_length=32)


@router.post("/sms/test")
async def test_sms(data: SmsTestIn, merchant: Merchant = Depends(get_current_merchant)):
    body = f"{merchant.business_name}: this is a test text from your voice agent. SMS confirmations are working."
    message = await sms_service.send(merchant, data.to, body, kind="test")
    return _message(message)


@router.get("/messages")
async def messages(
    order_id: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Message).where(Message.merchant_id == merchant.id)
    if order_id:
        stmt = stmt.where(Message.order_id == order_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = await db.scalars(stmt.order_by(Message.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [_message(row) for row in rows], "total": total, "page": page, "page_size": page_size}


class SendSmsIn(BaseModel):
    #: Empty = the standard confirmation text for this record.
    body: str = Field(default="", max_length=640)


@router.post("/messages/order/{order_id}")
async def send_record_sms(
    order_id: str, data: SendSmsIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    record = await db.get(Order, order_id)
    if record is None or record.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Record not found")
    if not record.customer_phone:
        raise HTTPException(status_code=422, detail="This record has no phone number")
    body = data.body.strip()
    if not body:
        item = await db.get(CatalogItem, record.catalog_item_id) if record.catalog_item_id else None
        kind = "cancellation" if record.status.value == "cancelled" else ("lead" if record.kind in ("lead", "message") and not record.scheduled_at else "confirmation")
        body = sms_service.compose(kind, record, merchant, item_name=item.name if item else "")
    if not body:
        raise HTTPException(status_code=422, detail="Nothing to send — write a message")
    message = await sms_service.send(merchant, record.customer_phone, body, kind="manual", order_id=record.id)
    return _message(message)


# ------------------------------------------------------------------------------- calendar
class CalendarIn(BaseModel):
    busy_ics_urls: list[str] | None = None

    @field_validator("busy_ics_urls")
    @classmethod
    def _urls(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        out: list[str] = []
        for raw in value[:10]:
            url = str(raw or "").strip()
            if not url:
                continue
            if not url.lower().startswith(("https://", "http://", "webcal://")):
                raise ValueError("calendar links must start with https:// (or webcal://)")
            out.append(url[:1000])
        return out


@router.patch("/calendar")
async def update_calendar(
    data: CalendarIn, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    config = calendar_service.settings_of(merchant)
    if data.busy_ics_urls is not None:
        config["busy_ics_urls"] = data.busy_ics_urls
    merchant.calendar_settings = config
    await db.commit()
    await db.refresh(merchant)
    calendar_service.invalidate_busy(merchant.id)
    return await _summary(request, merchant, db)


@router.post("/calendar/feed-token")
async def rotate_feed(request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    """Issue (or replace) the secret in the calendar feed URLs — old subscriptions stop updating."""
    merchant.calendar_token = calendar_service.new_token()
    await db.commit()
    await db.refresh(merchant)
    return await _summary(request, merchant, db)


class CalendarCheckIn(BaseModel):
    url: str = Field(min_length=8, max_length=1000)


@router.post("/calendar/check")
async def check_calendar(data: CalendarCheckIn, merchant: Merchant = Depends(get_current_merchant)):
    """Fetch an iCal link once and report how many busy times it has in the next 2 weeks."""
    from datetime import datetime, timedelta

    from app.flows.timefmt import business_tz

    tz = business_tz(merchant.timezone)
    now = datetime.now(tz)
    try:
        busy = await calendar_service.fetch_ics_busy(data.url, window_start=now, window_end=now + timedelta(days=14), timezone_name=str(tz))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}
    return {"ok": True, "busy_count": len(busy), "next": [(start.isoformat(), end.isoformat()) for start, end in busy[:5]]}


class ItemCalendarIn(BaseModel):
    calendar_ics: str | None = Field(default=None, max_length=1000)
    google_calendar_id: str | None = Field(default=None, max_length=300)


@router.put("/calendar/items/{item_id}")
async def item_calendar(
    item_id: str, data: ItemCalendarIn, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    item = await db.get(CatalogItem, item_id)
    if item is None or item.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    values = dict(item.data or {})
    for key, value in data.model_dump(exclude_unset=True).items():
        text = str(value or "").strip()
        if text:
            if key == "calendar_ics" and not text.lower().startswith(("https://", "http://", "webcal://")):
                raise HTTPException(status_code=422, detail="calendar links must start with https:// (or webcal://)")
            values[key] = text
        else:
            values.pop(key, None)
    item.data = values
    await db.commit()
    invalidate_catalog(merchant.id)
    calendar_service.invalidate_busy(merchant.id)
    return await _summary(request, merchant, db)


# ------------------------------------------------------------------------------- Google
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
