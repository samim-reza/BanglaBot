"""Merchant-scoped orders: list, create, detail, edit, delete, call, recordings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.models import CallLog, Merchant
from app.schemas.order import OrderCreate, OrderDetailOut, OrderOut, OrderPage, OrderStats, OrderUpdate
from app.services import call_service, order_service

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=OrderPage)
async def list_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status: str = Query(default=""),
    search: str = Query(default=""),
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
    )
    return OrderPage(items=[order_service.serialize_order(row) for row in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    data: OrderCreate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.create_order(db, merchant, data)
    return order_service.serialize_order(order)


@router.get("/stats", response_model=OrderStats)
async def stats(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await call_service.reconcile_stale_calls(db, merchant)
    return OrderStats(**await order_service.order_stats(db, merchant.id))


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
    payload = order_service.serialize_order(order)
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
    order = await order_service.update_order(db, order, data)
    return order_service.serialize_order(order)


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
    await call_service.start_confirmation_call(db, order, merchant)
    return order_service.serialize_order(order)
