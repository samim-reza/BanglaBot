"""Platform admin endpoints: manage merchant accounts and see all data."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models import (
    AuditLog,
    CallLog,
    Invoice,
    Merchant,
    Order,
    OrderStatus,
    Plan,
    PlatformAdmin,
    Subscription,
    SupportTicket,
)
from app.schemas.billing import AdminSubscriptionUpdate
from app.schemas.common import Page
from app.schemas.merchant import MerchantCreate, MerchantOut, MerchantUpdate
from app.schemas.order import OrderOut, OrderUpdate
from app.schemas.platform import AdminMerchantOut, AuditLogOut, MerchantOption
from app.services import audit_service, billing_service, order_service

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_admin)]
)


async def _admin_merchant_items(
    db: AsyncSession, merchants: list[Merchant]
) -> list[AdminMerchantOut]:
    """Enrich a page of merchants with plan/usage info in batched queries (no N+1)."""
    ids = [m.id for m in merchants]
    subs_by_merchant: dict[str, Subscription] = {}
    if ids:
        rows = await db.execute(
            select(Subscription)
            .where(Subscription.merchant_id.in_(ids))
            .order_by(Subscription.created_at)
        )
        for sub in rows.scalars():
            subs_by_merchant[sub.merchant_id] = sub  # ordered ascending — latest wins
    plan_keys = {sub.plan_key for sub in subs_by_merchant.values()}
    plans_by_key: dict[str, Plan] = {}
    if plan_keys:
        rows = await db.execute(select(Plan).where(Plan.key.in_(plan_keys)))
        plans_by_key = {plan.key: plan for plan in rows.scalars()}
    calls_by_merchant: dict[str, int] = {}
    windows = [
        and_(
            CallLog.merchant_id == sub.merchant_id,
            CallLog.created_at >= sub.current_period_start,
            CallLog.created_at < sub.current_period_end,
        )
        for sub in subs_by_merchant.values()
    ]
    if windows:
        rows = await db.execute(
            select(CallLog.merchant_id, func.count())
            .where(or_(*windows))
            .group_by(CallLog.merchant_id)
        )
        calls_by_merchant = {merchant_id: int(count) for merchant_id, count in rows.all()}
    items = []
    for merchant in merchants:
        sub = subs_by_merchant.get(merchant.id)
        plan = plans_by_key.get(sub.plan_key) if sub else None
        items.append(
            AdminMerchantOut(
                **MerchantOut.model_validate(merchant).model_dump(),
                plan_key=sub.plan_key if sub else None,
                plan_name_bn=plan.name_bn if plan else None,
                sub_status=sub.status if sub else None,
                calls_used=calls_by_merchant.get(merchant.id, 0),
                call_limit=(plan.max_calls_per_month + sub.bonus_calls) if sub and plan else 0,
            )
        )
    return items


@router.get("/stats")
async def platform_stats(db: AsyncSession = Depends(get_db)):
    counts = await order_service.status_counts(db)
    total_merchants = (await db.execute(select(func.count()).select_from(Merchant))).scalar_one()
    active_merchants = (
        await db.execute(select(func.count()).select_from(Merchant).where(Merchant.active))
    ).scalar_one()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    calls, secs = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(CallLog.duration_secs), 0)).where(
                CallLog.created_at >= month_start
            )
        )
    ).one()
    open_tickets = (
        await db.execute(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status != "closed")
        )
    ).scalar_one()
    due_invoices = (
        await db.execute(
            select(func.count()).select_from(Invoice).where(Invoice.status == "due")
        )
    ).scalar_one()
    plan_rows = await db.execute(
        select(Plan.key, Plan.name_bn, func.count())
        .select_from(Subscription)
        .join(Plan, Plan.key == Subscription.plan_key)
        .where(Subscription.status.in_(("trialing", "active")))
        .group_by(Plan.key, Plan.name_bn)
        .order_by(Plan.key)
    )
    log_rows = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8))
    return {
        "merchants": {"total": int(total_merchants), "active": int(active_merchants)},
        "orders": counts,
        "calls_month": {"calls": int(calls), "minutes": -(-int(secs) // 60)},
        "mrr": await billing_service.mrr(db),
        "open_tickets": int(open_tickets),
        "due_invoices": int(due_invoices),
        "plans": [
            {"key": key, "name_bn": name_bn, "count": int(count)}
            for key, name_bn, count in plan_rows.all()
        ],
        "recent_logs": [AuditLogOut.model_validate(log) for log in log_rows.scalars()],
    }


@router.get("/merchants", response_model=Page[AdminMerchantOut])
async def list_merchants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(Merchant))).scalar_one()
    rows = await db.execute(
        select(Merchant)
        .order_by(Merchant.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = await _admin_merchant_items(db, list(rows.scalars()))
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/merchants/options", response_model=list[MerchantOption])
async def merchant_options(db: AsyncSession = Depends(get_db)):
    """All merchants as a light id/name list — feeds the admin filter dropdowns."""
    rows = await db.execute(select(Merchant).order_by(Merchant.business_name))
    return list(rows.scalars())


@router.post("/merchants", response_model=MerchantOut, status_code=201)
async def create_merchant(
    body: MerchantCreate,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    exists = (
        await db.execute(select(Merchant).where(Merchant.username == body.username))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "এই ইউজারনেম আগে থেকেই আছে")
    settings_row = await billing_service.get_settings_row(db)
    data = body.model_dump()
    data["password_hash"] = hash_password(data.pop("password"))
    merchant = Merchant(**data)
    db.add(merchant)
    try:
        await db.flush()
        await billing_service.start_trial(db, merchant, settings_row)
        audit_service.record(
            db,
            actor_role="admin",
            actor_id=admin.id,
            actor_name=admin.name,
            action="merchant_created",
            detail=f"{admin.name} নতুন মার্চেন্ট তৈরি করেছেন: {merchant.business_name}",
            merchant_id=merchant.id,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "এই ইউজারনেম আগে থেকেই আছে")
    await db.refresh(merchant)
    return merchant


@router.patch("/merchants/{merchant_id}", response_model=MerchantOut)
async def update_merchant(
    merchant_id: str,
    body: MerchantUpdate,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    merchant = await db.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(404, "মার্চেন্ট পাওয়া যায়নি")
    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:
            merchant.password_hash = hash_password(password)
    for field, value in data.items():
        setattr(merchant, field, value)
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="merchant_updated",
        detail=f"{admin.name} মার্চেন্ট আপডেট করেছেন: {merchant.business_name}",
        merchant_id=merchant.id,
    )
    await db.commit()
    await db.refresh(merchant)
    return merchant


@router.patch("/merchants/{merchant_id}/subscription", response_model=AdminMerchantOut)
async def update_merchant_subscription(
    merchant_id: str,
    body: AdminSubscriptionUpdate,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    merchant = await db.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(404, "মার্চেন্ট পাওয়া যায়নি")
    plan = None
    if body.plan_key is not None:
        plan = await billing_service.get_plan(db, body.plan_key)
        if not plan:
            raise HTTPException(404, "প্ল্যান পাওয়া যায়নি")
    if body.status is not None and body.status not in (
        "trialing",
        "active",
        "past_due",
        "canceled",
    ):
        raise HTTPException(400, "অবৈধ স্ট্যাটাস")
    now = datetime.now(timezone.utc)
    changes = []
    sub = await billing_service.get_subscription(db, merchant.id)
    if not sub:
        settings_row = await billing_service.get_settings_row(db)
        sub = Subscription(
            merchant_id=merchant.id,
            plan_key=plan.key if plan else settings_row.trial_plan_key,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)
        changes.append("নতুন সাবস্ক্রিপশন তৈরি হয়েছে")
    if body.plan_key is not None and plan:
        sub.plan_key = plan.key
        changes.append(f"প্ল্যান: {plan.name_bn}")
    if body.status is not None:
        sub.status = body.status
        sub.canceled_at = now if body.status == "canceled" else None
        changes.append(f"স্ট্যাটাস: {body.status}")
        # Reactivating a lapsed subscription starts a fresh period — otherwise
        # the lazy renewal would back-bill every dead month since it expired.
        if body.status in ("trialing", "active"):
            period_end = sub.current_period_end
            if period_end is not None and period_end.tzinfo is None:
                period_end = period_end.replace(tzinfo=timezone.utc)
            if period_end is not None and period_end < now:
                sub.current_period_start = now
                sub.current_period_end = now + timedelta(days=30)
                changes.append("নতুন মেয়াদ শুরু হয়েছে")
    if body.extend_days:
        sub.current_period_end = sub.current_period_end + timedelta(days=body.extend_days)
        changes.append(f"মেয়াদ বেড়েছে {body.extend_days} দিন")
    if body.bonus_calls is not None:
        sub.bonus_calls = body.bonus_calls
        changes.append(f"বোনাস কল: {body.bonus_calls}")
    if body.bonus_minutes is not None:
        sub.bonus_minutes = body.bonus_minutes
        changes.append(f"বোনাস মিনিট: {body.bonus_minutes}")
    if body.note is not None:
        sub.note = body.note
        changes.append("নোট আপডেট হয়েছে")
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="subscription_updated",
        detail=f"{merchant.business_name}-এর সাবস্ক্রিপশন আপডেট — "
        + (", ".join(changes) or "কোনো পরিবর্তন নেই"),
        merchant_id=merchant.id,
    )
    await db.commit()
    return (await _admin_merchant_items(db, [merchant]))[0]


@router.get("/orders", response_model=Page[OrderOut])
async def all_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: OrderStatus | None = None,
    merchant_id: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    items, total = await order_service.paginate_orders(
        db, merchant_id=merchant_id, status=status, search=search, page=page, page_size=page_size
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.patch("/orders/{order_id}", response_model=OrderOut)
async def update_order(
    order_id: str,
    body: OrderUpdate,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "অর্ডার পাওয়া যায়নি")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(order, field, value)
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="order_updated",
        detail=f"{admin.name} অর্ডার আপডেট করেছেন: {order.order_ref or order.id[:8]}",
        merchant_id=order.merchant_id,
    )
    await db.commit()
    await db.refresh(order)
    return order
