"""The owner's plan: what they have, what a change costs, buying it, cancelling, renewing.

Manual sales keep the request → admin-approve flow in ``/api/addons``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.models import Merchant
from app.schemas.signup import PlanChangeIn, SelectionIn
from app.services import catalog_plans, plan_service, subscription_service

router = APIRouter(prefix="/api/plan", tags=["plan"])


@router.get("")
async def get_plan(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await catalog_plans.ensure_fresh()
    return await plan_service.view(db, merchant)


@router.post("/quote")
async def quote(data: SelectionIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await catalog_plans.ensure_fresh()
    return await plan_service.quote_change(db, merchant, data.tier, data.interval, data.addons)


@router.post("/change")
async def change(data: PlanChangeIn, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    """Upgrade / downgrade / add-ons. Answers ``checkout_url`` when something is due now."""
    await rate_limit(request, "plan-change", max_hits=10, per_seconds=3600, key=merchant.id)
    await catalog_plans.ensure_fresh()
    return await plan_service.change(db, merchant, data.tier, data.interval, data.addons, request=request)


@router.post("/renew")
async def renew(request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    await rate_limit(request, "plan-change", max_hits=10, per_seconds=3600, key=merchant.id)
    await catalog_plans.ensure_fresh()
    return await plan_service.renew(db, merchant, request=request)


@router.post("/cancel")
async def cancel(request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    """Cancel at the end of the current period."""
    return await plan_service.set_cancel(db, merchant, True, request=request)


@router.delete("/cancel")
async def resume(request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await plan_service.set_cancel(db, merchant, False, request=request)


@router.get("/subscriptions")
async def history(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str = Query(default="", max_length=200),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """The account's billing history, newest first."""
    try:
        return await subscription_service.list_subscriptions(db, limit=limit, cursor=cursor, merchant_id=merchant.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc
