"""SMS integration: settings, a test text, the message log, and texting one record."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.api.routes.integrations.summary import _summary
from app.db.session import get_db
from app.models import CatalogItem, Merchant, Message, Order
from app.services import sms_service
from app.services.tenancy import owned

router = APIRouter()


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
    record = await owned(db, Order, order_id, merchant, detail="Record not found")
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
