"""Platform admin: login from settings, merchants CRUD, cross-merchant views."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ADMIN_ROLE, require_admin
from app.api.routes.auth import apply_settings, merchant_out
from app.core.config import get_settings
from app.core.datetime_utils import today_bounds_utc
from app.core.security import hash_password, sign_token
from app.db.session import get_db
from app.models import CallLog, Merchant, Order, OrderStatus
from app.schemas.admin import (
    AdminCallPage,
    AdminLoginRequest,
    AdminOrderPage,
    AdminOverview,
    AdminTokenResponse,
    MerchantAdminUpdate,
    MerchantCreate,
)
from app.schemas.merchant import MerchantOut
from app.services import order_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(data: AdminLoginRequest):
    settings = get_settings()
    username_ok = hmac.compare_digest(data.username.strip(), settings.admin_username)
    password_ok = hmac.compare_digest(data.password, settings.admin_password)
    if not (username_ok and password_ok):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return AdminTokenResponse(token=sign_token({"sub": settings.admin_username, "role": ADMIN_ROLE}))


@router.get("/overview", response_model=AdminOverview)
async def overview(_: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    start, end = today_bounds_utc()

    async def count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    today_calls = CallLog.created_at >= start, CallLog.created_at < end
    return AdminOverview(
        merchants=await count(select(func.count(Merchant.id))),
        active_merchants=await count(select(func.count(Merchant.id)).where(Merchant.active.is_(True))),
        orders=await count(select(func.count(Order.id))),
        calls_today=await count(select(func.count(CallLog.id)).where(*today_calls)),
        confirmed_today=await count(select(func.count(CallLog.id)).where(*today_calls, CallLog.outcome == "confirmed")),
        cancelled_today=await count(select(func.count(CallLog.id)).where(*today_calls, CallLog.outcome == "cancelled")),
        orders_today=await count(select(func.count(Order.id)).where(Order.created_at >= start, Order.created_at < end)),
        pending_orders=await count(select(func.count(Order.id)).where(Order.status == OrderStatus.pending)),
        calling_orders=await count(select(func.count(Order.id)).where(Order.status == OrderStatus.calling)),
        needs_review_orders=await count(select(func.count(Order.id)).where(Order.status == OrderStatus.needs_review)),
    )


# ------------------------------------------------------------------ merchants
@router.get("/merchants", response_model=list[MerchantOut])
async def list_merchants(_: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(Merchant).order_by(Merchant.created_at.desc()))
    return [merchant_out(row) for row in rows]


@router.post("/merchants", response_model=MerchantOut, status_code=201)
async def create_merchant(data: MerchantCreate, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(select(Merchant.id).where(Merchant.username == data.username.strip()))
    if exists:
        raise HTTPException(status_code=409, detail="Username is already taken")
    merchant = Merchant(
        business_name=data.business_name.strip(),
        username=data.username.strip(),
        password_hash=hash_password(data.password),
        owner_name=data.owner_name.strip(),
        phone=data.phone.strip(),
        email=data.email.strip(),
        support_phone=data.support_phone.strip(),
        language=data.language,
        supported_languages=[data.language] + [code for code in ("bn", "en") if code != data.language],
    )
    db.add(merchant)
    await db.commit()
    await db.refresh(merchant)
    return merchant_out(merchant)


async def _merchant_or_404(db: AsyncSession, merchant_id: str) -> Merchant:
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.get("/merchants/{merchant_id}", response_model=MerchantOut)
async def get_merchant(merchant_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return merchant_out(await _merchant_or_404(db, merchant_id))


@router.patch("/merchants/{merchant_id}", response_model=MerchantOut)
async def update_merchant(
    merchant_id: str, data: MerchantAdminUpdate, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    merchant = await _merchant_or_404(db, merchant_id)
    settings_part = data.model_dump(exclude_unset=True, exclude={"password", "active"})
    apply_settings(merchant, MerchantAdminUpdate.model_validate(settings_part))
    if data.password:
        merchant.password_hash = hash_password(data.password)
    if data.active is not None:
        merchant.active = data.active
    await db.commit()
    await db.refresh(merchant)
    return merchant_out(merchant)


@router.delete("/merchants/{merchant_id}", status_code=204)
async def delete_merchant(merchant_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    merchant = await _merchant_or_404(db, merchant_id)
    calling = await db.scalar(
        select(func.count(Order.id)).where(Order.merchant_id == merchant.id, Order.status == OrderStatus.calling)
    )
    if calling:
        raise HTTPException(status_code=409, detail="Merchant has a call in progress")
    logs = await db.scalars(select(CallLog).where(CallLog.merchant_id == merchant.id))
    for log in logs:
        await db.delete(log)
    orders = await db.scalars(select(Order).where(Order.merchant_id == merchant.id))
    for order in orders:
        await db.delete(order)
    await db.delete(merchant)
    await db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ orders / calls
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
    names = await _merchant_names(db, {row.merchant_id for row in rows})
    items = []
    for row in rows:
        payload = order_service.serialize_order(row)
        payload["merchant_name"] = names.get(row.merchant_id, "")
        items.append(payload)
    return AdminOrderPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/calls", response_model=AdminCallPage)
async def admin_calls(
    merchant_id: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CallLog)
    if merchant_id:
        stmt = stmt.where(CallLog.merchant_id == merchant_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(await db.scalars(stmt.order_by(CallLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
    names = await _merchant_names(db, {row.merchant_id for row in rows})
    order_ids = {row.order_id for row in rows if row.order_id}
    orders: dict[str, Order] = {}
    if order_ids:
        for order in await db.scalars(select(Order).where(Order.id.in_(order_ids))):
            orders[order.id] = order
    items = []
    for row in rows:
        payload = order_service.serialize_call_log(row)
        order = orders.get(row.order_id or "")
        payload.update(
            {
                "merchant_id": row.merchant_id,
                "merchant_name": names.get(row.merchant_id, ""),
                "customer_name": order.customer_name if order else "",
                "order_ref": order.order_ref if order else "",
            }
        )
        items.append(payload)
    return AdminCallPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/recordings/{log_id}")
async def admin_recording(log_id: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.services.call_service import fetch_recording

    log = await db.get(CallLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Call log not found")
    content, media_type = await fetch_recording(log)
    return Response(content=content, media_type=media_type)


async def _merchant_names(db: AsyncSession, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = await db.execute(select(Merchant.id, Merchant.business_name).where(Merchant.id.in_(ids)))
    return {merchant_id: name for merchant_id, name in rows}
