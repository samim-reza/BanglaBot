"""The integrations page in one payload: SMS settings and usage, calendar feed links,
per-item calendars, and the Google connection state."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.addons import entitlements
from app.core.config import get_settings
from app.core.plans import FEATURE_GOOGLE_CALENDAR
from app.db.session import get_db
from app.models import CatalogItem, Merchant, Message
from app.services import calendar_service, sms_service

router = APIRouter()


def _base(request: Request) -> str:
    public = str(get_settings().public_base_url or "").rstrip("/")
    return public or str(request.base_url).rstrip("/")

def _booked_kind(vertical: Any) -> str:
    """The catalog kind a record is booked against (a salon books the stylist, not the
    service): its feed and busy calendar are per item of THAT kind."""
    for spec in getattr(vertical, "record_fields", ()) or ():
        if spec.key == "catalog_item_id" and getattr(spec, "catalog_kind", ""):
            return str(spec.catalog_kind)
    return str(vertical.catalog_kind or "")


async def _summary(request: Request, merchant: Merchant, db: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    calendar = calendar_service.settings_of(merchant)
    google = calendar.get("google") or {}
    base = _base(request)
    items = []
    from app.verticals import vertical_for

    vertical = vertical_for(merchant)
    booked_kind = _booked_kind(vertical)
    if booked_kind:
        rows = await db.scalars(
            select(CatalogItem)
            .where(CatalogItem.merchant_id == merchant.id, CatalogItem.kind == booked_kind)
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
            "sender": settings.telnyx_sms_from or settings.telnyx_from_number or "",
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
