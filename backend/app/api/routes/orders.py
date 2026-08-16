"""Merchant-facing order endpoints (all scoped to the logged-in merchant)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core import cache
from app.db.session import get_db
from app.models import CallLog, Merchant, Order, OrderStatus
from app.schemas.common import Page
from app.schemas.order import OrderCreate, OrderDetail, OrderOut, OrderUpdate
from app.services import audit_service, entitlement_service, order_service, recording_service
from app.services.call_service import reconcile_stale_calls, start_confirmation_call

router = APIRouter(prefix="/api/orders", tags=["orders"])


async def _own_order(db: AsyncSession, merchant: Merchant, order_id: str) -> Order:
    order = await db.get(Order, order_id)
    if not order or order.merchant_id != merchant.id:
        raise HTTPException(404, "অর্ডার পাওয়া যায়নি")
    return order


@router.get("", response_model=Page[OrderOut])
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: OrderStatus | None = None,
    search: str | None = None,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    # Settle any order stuck in "calling" whose status webhook got lost.
    await reconcile_stale_calls(db, merchant)
    items, total = await order_service.paginate_orders(
        db, merchant_id=merchant.id, status=status, search=search, page=page, page_size=page_size
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    body: OrderCreate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    order = Order(merchant_id=merchant.id, **body.model_dump())
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@router.get("/stats")
async def order_stats(
    merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    await reconcile_stale_calls(db, merchant)
    return await order_service.status_counts(db, merchant_id=merchant.id)


@router.get("/insights")
async def order_insights(
    days: int = Query(30, ge=7, le=90),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    # Cached until a call starts/finishes for this merchant (see call_service),
    # with a short TTL so the daily rollover can't be stale for long.
    cache_key = f"insights:{merchant.id}:{days}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached
    data = await order_service.call_insights(db, merchant.id, days=days)
    await cache.set_json(cache_key, data, 120)
    return data


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order(
    order_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    await reconcile_stale_calls(db, merchant)
    order = await _own_order(db, merchant, order_id)
    logs = await order_service.get_call_logs(db, order.id)
    detail = OrderDetail.model_validate(order)
    detail.call_logs = logs  # type: ignore[assignment]
    return detail


@router.patch("/{order_id}", response_model=OrderOut)
async def update_order(
    order_id: str,
    body: OrderUpdate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    order = await _own_order(db, merchant, order_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(order, field, value)
    await db.commit()
    await db.refresh(order)
    return order


@router.delete("/{order_id}", status_code=204)
async def delete_order(
    order_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    order = await _own_order(db, merchant, order_id)
    # Detach call logs instead of deleting them: they stay in the usage metering
    # window, so deleting orders cannot reset the monthly call quota.
    for log in await order_service.get_call_logs(db, order.id):
        log.order_id = None
    await db.delete(order)
    await db.commit()


@router.get("/recordings/{log_id}")
async def play_recording(
    log_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    log = await db.get(CallLog, log_id)
    if not log or log.merchant_id != merchant.id or not log.recording_sid:
        raise HTTPException(404, "রেকর্ডিং পাওয়া যায়নি")
    return await recording_service.stream_recording(log.recording_sid)


@router.post("/{order_id}/call", response_model=OrderOut)
async def call_to_confirm(
    order_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    await reconcile_stale_calls(db, merchant)
    order = await _own_order(db, merchant, order_id)
    if order.status in (OrderStatus.confirmed, OrderStatus.cancelled):
        raise HTTPException(409, "এই অর্ডারের ফলাফল ইতিমধ্যে চূড়ান্ত")
    await entitlement_service.check_can_call(db, merchant)
    audit_service.record(
        db,
        actor_role="merchant",
        actor_id=merchant.id,
        actor_name=merchant.business_name,
        action="call_started",
        detail=f"{order.customer_name}-কে কনফার্মেশন কল শুরু হয়েছে ({order.customer_phone})",
        merchant_id=merchant.id,
    )
    await start_confirmation_call(db, order, merchant)
    await db.refresh(order)
    return order
