"""The account's call & chat log (inbound, outbound, tests, website chats)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.models import CallLog, Merchant, Order
from app.schemas.order import CallLogPage
from app.services import call_service, order_service

router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.get("", response_model=CallLogPage)
async def list_calls(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    direction: str = Query(default=""),
    outcome: str = Query(default=""),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CallLog).where(CallLog.merchant_id == merchant.id)
    if direction:
        stmt = stmt.where(CallLog.direction == direction)
    if outcome:
        stmt = stmt.where(CallLog.outcome == outcome)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(await db.scalars(stmt.order_by(CallLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
    names: dict[str, str] = {}
    ids = {row.order_id for row in rows if row.order_id}
    if ids:
        for order_id, name in await db.execute(select(Order.id, Order.customer_name).where(Order.id.in_(ids))):
            names[order_id] = name
    items = []
    for row in rows:
        payload = order_service.serialize_call_log(row)
        payload["customer_name"] = names.get(row.order_id or "", "")
        items.append(payload)
    return CallLogPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{log_id}/recording")
async def recording(log_id: str, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    log = await db.get(CallLog, log_id)
    if log is None or log.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Call not found")
    content, media_type = await call_service.fetch_recording(log)
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})
