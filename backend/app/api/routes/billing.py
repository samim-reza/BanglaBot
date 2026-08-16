"""Merchant-facing billing endpoints: summary, plan changes and invoices."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.models import Invoice, Merchant
from app.schemas.billing import BillingSummary, ChangePlanRequest, InvoiceOut, PlanOut
from app.schemas.common import Page
from app.services import billing_service

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/summary", response_model=BillingSummary)
async def summary(
    merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    return await billing_service.billing_summary(db, merchant)


@router.get("/plans", response_model=list[PlanOut])
async def plans(
    merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    return await billing_service.active_plans(db)


@router.post("/change-plan", response_model=BillingSummary)
async def change_plan(
    body: ChangePlanRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    plan = await billing_service.get_plan(db, body.plan_key)
    if not plan or not plan.active:
        raise HTTPException(404, "প্ল্যান পাওয়া যায়নি")
    if plan.trial_days > 0:
        raise HTTPException(400, "ট্রায়াল প্ল্যানে ফেরা যায় না")
    sub = await billing_service.get_subscription(db, merchant.id)
    if sub and sub.plan_key == plan.key and sub.status == "active":
        raise HTTPException(400, "এই প্ল্যানেই আছেন")
    # No self-service plan changes while money is owed: a past-due account (or
    # one with unpaid invoices) must be settled by the admin marking the
    # invoice paid — otherwise plan-hopping would grant service without payment.
    unpaid = (
        await db.execute(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.merchant_id == merchant.id, Invoice.status == "due")
        )
    ).scalar_one()
    if (sub and sub.status == "past_due") or unpaid:
        raise HTTPException(
            402,
            "বকেয়া ইনভয়েস পরিশোধ না হওয়া পর্যন্ত প্ল্যান পরিবর্তন করা যাবে না — "
            "বিকাশে পেমেন্ট করে সাপোর্টে জানান",
        )
    await billing_service.change_plan(db, merchant, plan)
    return await billing_service.billing_summary(db, merchant)


@router.get("/invoices", response_model=Page[InvoiceOut])
async def invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    total = (
        await db.execute(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.merchant_id == merchant.id)
        )
    ).scalar_one()
    rows = await db.execute(
        select(Invoice)
        .where(Invoice.merchant_id == merchant.id)
        .order_by(Invoice.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=list(rows.scalars()), total=total, page=page, page_size=page_size)
