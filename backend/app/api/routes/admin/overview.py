"""Admin login (env login only while there are no admin users), form choices and the
platform-wide overview counters."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.datetime_utils import today_bounds_utc
from app.core.plans import PLANS
from app.core.regions import regions_json
from app.db.session import get_db
from app.models import AddonRequest, CallLog, Merchant, Order, OrderStatus
from app.schemas.admin import AdminOverview, AdminTokenResponse
from app.schemas.admin_users import AdminLoginIn
from app.services import admin_auth_service
from app.verticals import VERTICALS

router = APIRouter()


@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(data: AdminLoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Admin users (2FA: 401 + ``X-2FA-Required: totp`` asks for ``code``); env login only while there are none."""
    token = await admin_auth_service.login(db, request, username=data.username, password=data.password, code=data.code)
    return AdminTokenResponse(token=token)


@router.get("/meta")
async def meta(_: dict = Depends(require_admin)):
    """Choices for the account forms: business engines, regions, plans."""
    return {
        "verticals": [v.as_json() for v in VERTICALS.values()],
        "regions": regions_json(),
        "plans": [plan.as_json() for plan in PLANS.values()],
    }


@router.get("/overview", response_model=AdminOverview)
async def overview(_: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    start, end = today_bounds_utc()

    async def count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    today_calls = CallLog.created_at >= start, CallLog.created_at < end
    by_vertical = {key: 0 for key in VERTICALS}
    for vertical, total in await db.execute(select(Merchant.vertical, func.count(Merchant.id)).group_by(Merchant.vertical)):
        by_vertical[str(vertical or "ecommerce")] = int(total)
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
        inbound_today=await count(select(func.count(CallLog.id)).where(*today_calls, CallLog.direction == "inbound")),
        booked_today=await count(select(func.count(CallLog.id)).where(*today_calls, CallLog.outcome == "booked")),
        minutes_today=round(
            float(
                await db.scalar(
                    select(func.coalesce(func.sum(CallLog.duration_secs), 0)).where(*today_calls, CallLog.direction.in_(("inbound", "outbound")))
                )
                or 0
            )
            / 60.0,
            1,
        ),
        by_vertical=by_vertical,
        pending_addon_requests=await count(select(func.count(AddonRequest.id)).where(AddonRequest.status == "pending")),
    )
