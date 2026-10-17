"""Cross-account views: records, call logs and call recordings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.routes.admin.common import _merchants
from app.db.session import get_db
from app.models import CallLog, Merchant, Order
from app.schemas.admin import AdminCallPage, AdminOrderPage
from app.services import order_service

router = APIRouter()


@router.get("/orders", response_model=AdminOrderPage)
async def admin_orders(
    merchant_id: str = Query(default=""),
    status: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await order_service.list_orders(
        db,
        merchant_id=merchant_id or None,
        status=order_service.parse_status(status),
        search="",
        page=page,
        page_size=page_size,
    )
    merchants = await _merchants(db, {row.merchant_id for row in rows})
    names = await order_service.catalog_names(db, {str(row.catalog_item_id or "") for row in rows})
    items = []
    for row in rows:
        merchant = merchants.get(row.merchant_id)
        payload = order_service.serialize_order(row, merchant=merchant, names=names)
        payload["merchant_name"] = merchant.business_name if merchant else ""
        items.append(payload)
    return AdminOrderPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/calls", response_model=AdminCallPage)
async def admin_calls(
    merchant_id: str = Query(default=""),
    direction: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CallLog)
    if merchant_id:
        stmt = stmt.where(CallLog.merchant_id == merchant_id)
    if direction:
        stmt = stmt.where(CallLog.direction == direction)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(await db.scalars(stmt.order_by(CallLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
    merchants = await _merchants(db, {row.merchant_id for row in rows})
    order_ids = {row.order_id for row in rows if row.order_id}
    orders: dict[str, Order] = {}
    if order_ids:
        for order in await db.scalars(select(Order).where(Order.id.in_(order_ids))):
            orders[order.id] = order
    items = []
    for row in rows:
        payload = order_service.serialize_call_log(row)
        order = orders.get(row.order_id or "")
        merchant = merchants.get(row.merchant_id)
        payload.update(
            {
                "merchant_id": row.merchant_id,
                "merchant_name": merchant.business_name if merchant else "",
                "customer_name": order.customer_name if order else "",
                "order_ref": order.order_ref if order else "",
            }
        )
        items.append(payload)
    return AdminCallPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/recordings/{log_id}")
async def admin_recording(log_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services.call_service import fetch_recording
    from app.services.calls import retention

    log = await db.get(CallLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Call log not found")
    retention.ensure_available(log, await db.get(Merchant, log.merchant_id))
    content, media_type = await fetch_recording(log)
    return Response(content=content, media_type=media_type)
