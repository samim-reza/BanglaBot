"""Platform admin endpoints: team, audit logs, all call logs and settings."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models import AuditLog, CallCost, CallLog, Merchant, Order, PlatformAdmin
from app.schemas.common import Page
from app.schemas.platform import (
    AdminCallOut,
    AdminUserCreate,
    AdminUserOut,
    AdminUserPatch,
    AuditLogOut,
    SettingsOut,
    SettingsUpdate,
)
from app.services import audit_service, billing_service, recording_service

router = APIRouter(
    prefix="/api/admin", tags=["admin-platform"], dependencies=[Depends(get_current_admin)]
)

BD_TZ = ZoneInfo("Asia/Dhaka")


def _bd_day_bound(value: str | None, *, exclusive_end: bool = False) -> datetime | None:
    """YYYY-MM-DD → UTC-aware midnight boundary of that Dhaka calendar day."""
    if not value:
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "তারিখের ফরম্যাট YYYY-MM-DD হতে হবে")
    if exclusive_end:
        day += timedelta(days=1)
    return datetime.combine(day, time.min, tzinfo=BD_TZ)


@router.get("/team", response_model=list[AdminUserOut])
async def list_team(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(PlatformAdmin).order_by(PlatformAdmin.created_at))
    return list(rows.scalars())


@router.post("/team", response_model=AdminUserOut, status_code=201)
async def create_admin(
    body: AdminUserCreate,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    exists = (
        await db.execute(select(PlatformAdmin).where(PlatformAdmin.username == body.username))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "এই ইউজারনেম আগে থেকেই আছে")
    new_admin = PlatformAdmin(
        username=body.username, name=body.name, password_hash=hash_password(body.password)
    )
    db.add(new_admin)
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="admin_created",
        detail=f"{admin.name} নতুন অ্যাডমিন যোগ করেছেন: {body.name} ({body.username})",
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "এই ইউজারনেম আগে থেকেই আছে")
    await db.refresh(new_admin)
    return new_admin


@router.patch("/team/{admin_id}", response_model=AdminUserOut)
async def update_admin(
    admin_id: str, body: AdminUserPatch, db: AsyncSession = Depends(get_db)
):
    target = await db.get(PlatformAdmin, admin_id)
    if not target:
        raise HTTPException(404, "অ্যাডমিন পাওয়া যায়নি")
    if body.name is not None:
        target.name = body.name
    if body.password:
        target.password_hash = hash_password(body.password)
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/team/{admin_id}", status_code=204)
async def delete_admin(
    admin_id: str,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(PlatformAdmin, admin_id)
    if not target:
        raise HTTPException(404, "অ্যাডমিন পাওয়া যায়নি")
    if target.id == admin.id:
        raise HTTPException(400, "নিজের অ্যাকাউন্ট মুছে ফেলা যায় না")
    total = (await db.execute(select(func.count()).select_from(PlatformAdmin))).scalar_one()
    if total <= 1:
        raise HTTPException(400, "শেষ অ্যাডমিন মুছে ফেলা যায় না")
    await db.delete(target)
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="admin_deleted",
        detail=f"{admin.name} অ্যাডমিন মুছে ফেলেছেন: {target.name} ({target.username})",
    )
    await db.commit()


@router.get("/logs", response_model=Page[AuditLogOut])
async def list_logs(
    actor_role: str | None = None,
    action: str | None = None,
    merchant_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog)
    if actor_role:
        query = query.where(AuditLog.actor_role == actor_role)
    if action:
        query = query.where(AuditLog.action == action)
    if merchant_id:
        query = query.where(AuditLog.merchant_id == merchant_id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await db.execute(
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=list(rows.scalars()), total=total, page=page, page_size=page_size)


@router.get("/calls", response_model=Page[AdminCallOut])
async def list_calls(
    merchant_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    start = _bd_day_bound(date_from)
    end = _bd_day_bound(date_to, exclusive_end=True)
    query = (
        select(CallLog, Merchant.business_name, Order.order_ref)
        .join(Merchant, Merchant.id == CallLog.merchant_id)
        # Outer join: logs whose order was deleted (order_id NULL) must stay
        # visible — they still count toward usage.
        .outerjoin(Order, Order.id == CallLog.order_id)
    )
    if merchant_id:
        query = query.where(CallLog.merchant_id == merchant_id)
    if start:
        query = query.where(CallLog.created_at >= start)
    if end:
        query = query.where(CallLog.created_at < end)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await db.execute(
        query.order_by(CallLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        AdminCallOut(
            id=log.id,
            merchant_id=log.merchant_id,
            merchant_name=merchant_name,
            order_id=log.order_id,
            order_ref=order_ref,
            call_status=log.call_status,
            outcome=log.outcome,
            duration_secs=log.duration_secs,
            transcript=log.transcript,
            recording_sid=log.recording_sid,
            created_at=log.created_at,
        )
        for log, merchant_name, order_ref in rows.all()
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/calls/summary")
async def calls_summary(
    merchant_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Per-merchant call volume and platform cost for the picked window."""
    start = _bd_day_bound(date_from)
    end = _bd_day_bound(date_to, exclusive_end=True)

    log_query = select(
        CallLog.merchant_id,
        func.count(),
        func.coalesce(func.sum(CallLog.duration_secs), 0),
        func.coalesce(func.sum(CallLog.billed_secs), 0),
    ).group_by(CallLog.merchant_id)
    # call_costs.created_at is backdated to the call's own timestamp, so the
    # same window filters both tables consistently.
    cost_query = select(
        CallCost.merchant_id, func.coalesce(func.sum(CallCost.total_bdt), 0)
    ).group_by(CallCost.merchant_id)
    if merchant_id:
        log_query = log_query.where(CallLog.merchant_id == merchant_id)
        cost_query = cost_query.where(CallCost.merchant_id == merchant_id)
    if start:
        log_query = log_query.where(CallLog.created_at >= start)
        cost_query = cost_query.where(CallCost.created_at >= start)
    if end:
        log_query = log_query.where(CallLog.created_at < end)
        cost_query = cost_query.where(CallCost.created_at < end)

    usage = {
        mid: {"calls": int(calls), "duration_secs": int(dur), "billed_secs": int(billed)}
        for mid, calls, dur, billed in (await db.execute(log_query)).all()
    }
    costs = {mid: float(total) for mid, total in (await db.execute(cost_query)).all()}

    ids = set(usage) | set(costs)
    names: dict[str, str] = {}
    if ids:
        rows = await db.execute(
            select(Merchant.id, Merchant.business_name).where(Merchant.id.in_(ids))
        )
        names = dict(rows.all())

    merchants = [
        {
            "merchant_id": mid,
            "merchant_name": names.get(mid, "—"),
            "calls": usage.get(mid, {}).get("calls", 0),
            "duration_secs": usage.get(mid, {}).get("duration_secs", 0),
            "billed_secs": usage.get(mid, {}).get("billed_secs", 0),
            "cost_bdt": round(costs.get(mid, 0.0), 2),
        }
        for mid in ids
    ]
    merchants.sort(key=lambda row: (-row["cost_bdt"], -row["calls"], row["merchant_name"]))
    return {
        "merchants": merchants,
        "totals": {
            "calls": sum(row["calls"] for row in merchants),
            "duration_secs": sum(row["duration_secs"] for row in merchants),
            "billed_secs": sum(row["billed_secs"] for row in merchants),
            "cost_bdt": round(sum(row["cost_bdt"] for row in merchants), 2),
        },
    }


@router.get("/recordings/{log_id}")
async def play_recording(log_id: str, db: AsyncSession = Depends(get_db)):
    log = await db.get(CallLog, log_id)
    if not log or not log.recording_sid:
        raise HTTPException(404, "রেকর্ডিং পাওয়া যায়নি")
    return await recording_service.stream_recording(log.recording_sid)


@router.get("/settings", response_model=SettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    return await billing_service.get_settings_row(db)


@router.patch("/settings", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    admin: PlatformAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    settings_row = await billing_service.get_settings_row(db)
    data = body.model_dump(exclude_unset=True)
    if "trial_plan_key" in data:
        trial_plan = await billing_service.get_plan(db, data["trial_plan_key"])
        if not trial_plan or trial_plan.trial_days <= 0:
            raise HTTPException(400, "ট্রায়াল প্ল্যান সঠিক নয় — ট্রায়াল দিনসহ একটি প্ল্যান দিন")
    if "entitlement_mode" in data and data["entitlement_mode"] not in ("enforce", "observe"):
        raise HTTPException(400, "অবৈধ এনটাইটেলমেন্ট মোড")
    for field, value in data.items():
        setattr(settings_row, field, value)
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="settings_updated",
        detail=f"{admin.name} প্ল্যাটফর্ম সেটিংস আপডেট করেছেন",
    )
    await db.commit()
    await db.refresh(settings_row)
    from app.api.routes.public import PLATFORM_CACHE_KEY
    from app.core import cache

    await cache.delete(PLATFORM_CACHE_KEY)
    return settings_row
