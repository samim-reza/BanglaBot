"""Calendar integration: busy-time iCal links, the feed token, a link check, and
per-catalog-item calendars."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.api.routes.integrations.summary import _summary
from app.db.session import get_db
from app.models import CatalogItem, Merchant
from app.services import calendar_service
from app.services.context_service import invalidate_catalog
from app.services.tenancy import owned

router = APIRouter()


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
    item = await owned(db, CatalogItem, item_id, merchant, detail="Catalog item not found")
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
