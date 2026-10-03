"""Account records (orders / appointments / leads / bookings): list, create, detail,
edit, delete, call, bulk calling, recordings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.models import CallLog, Merchant
from app.schemas.order import (
    AutoCallScheduleUpdate,
    BulkCallStart,
    BulkCallStatus,
    OrderCreate,
    OrderDetailOut,
    OrderOut,
    OrderPage,
    OrderStats,
    OrderUpdate,
)
from app.services import call_service, dialer_service, order_service

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=OrderPage)
async def list_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status: str = Query(default=""),
    search: str = Query(default=""),
    kind: str = Query(default=""),
    upcoming: bool = Query(default=False),
    sort: str = Query(default="created", pattern="^(created|scheduled)$"),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    await call_service.reconcile_stale_calls(db, merchant)
    rows, total = await order_service.list_orders(
        db,
        merchant_id=merchant.id,
        status=order_service.parse_status(status),
        search=search,
        page=page,
        page_size=page_size,
        kind=kind,
        upcoming=upcoming,
        sort=sort,
    )
    items = await order_service.serialize_many(db, rows, merchant)
    return OrderPage(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    data: OrderCreate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.create_order(db, merchant, data)
    return (await order_service.serialize_many(db, [order], merchant))[0]


@router.get("/stats", response_model=OrderStats)
async def stats(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await call_service.reconcile_stale_calls(db, merchant)
    return OrderStats(**await order_service.order_stats(db, merchant.id))


# ----------------------------------------------------------- call everyone
@router.get("/call-all", response_model=BulkCallStatus)
async def bulk_call_status(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await call_service.reconcile_stale_calls(db, merchant)
    return await dialer_service.status_payload(db, merchant)


@router.post("/call-all", response_model=BulkCallStatus, status_code=202)
async def bulk_call_start(
    data: BulkCallStart | None = None,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Dial every order that still needs a call, a few at a time, in the background."""
    await call_service.reconcile_stale_calls(db, merchant)
    await dialer_service.start_batch(db, merchant, statuses=data.statuses if data else None)
    return await dialer_service.status_payload(db, merchant)


@router.post("/call-all/cancel", response_model=BulkCallStatus)
async def bulk_call_cancel(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await dialer_service.cancel_batch(merchant.id)
    return await dialer_service.status_payload(db, merchant)


@router.put("/call-all/schedule", response_model=BulkCallStatus)
async def set_auto_call(
    data: AutoCallScheduleUpdate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    await dialer_service.set_schedule(db, merchant, data.at, data.repeat_daily)
    return await dialer_service.status_payload(db, merchant)


@router.delete("/call-all/schedule", response_model=BulkCallStatus)
async def clear_auto_call(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await dialer_service.clear_schedule(db, merchant)
    return await dialer_service.status_payload(db, merchant)


@router.get("/recordings/{log_id}")
async def recording(
    log_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    log = await db.get(CallLog, log_id)
    if log is None or log.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Call log not found")
    content, media_type = await call_service.fetch_recording(log)
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{order_id}", response_model=OrderDetailOut)
async def order_detail(
    order_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    await call_service.reconcile_stale_calls(db, merchant)
    order = await order_service.get_order(db, merchant, order_id)
    logs = await order_service.order_call_logs(db, order.id)
    payload = (await order_service.serialize_many(db, [order], merchant))[0]
    payload["call_logs"] = [order_service.serialize_call_log(log) for log in logs]
    return payload


@router.patch("/{order_id}", response_model=OrderOut)
async def update_order(
    order_id: str,
    data: OrderUpdate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, merchant, order_id)
    order = await order_service.update_order(db, merchant, order, data)
    return (await order_service.serialize_many(db, [order], merchant))[0]


@router.delete("/{order_id}", status_code=204)
async def delete_order(
    order_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, merchant, order_id)
    await order_service.delete_order(db, order)
    return Response(status_code=204)


@router.post("/{order_id}/call", response_model=OrderOut)
async def call_order(
    order_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, merchant, order_id)
    await call_service.start_outbound_call(db, order, merchant)
    return (await order_service.serialize_many(db, [order], merchant))[0]
