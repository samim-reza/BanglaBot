"""Platform admin billing endpoints: plans and invoices across all merchants."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.api.routes.public import PLANS_CACHE_KEY
from app.core import cache
from app.db.session import get_db
from app.models import Invoice, Merchant, Plan
from app.schemas.billing import (
    AdminInvoiceOut,
    InvoiceGenerate,
    InvoiceOut,
    InvoicePatch,
    PlanCreate,
    PlanOut,
    PlanUpdate,
)
from app.schemas.common import Page
from app.services import audit_service, billing_service

router = APIRouter(
    prefix="/api/admin", tags=["admin-billing"], dependencies=[Depends(get_current_admin)]
)


def _admin_invoice_out(invoice: Invoice, merchant_name: str) -> AdminInvoiceOut:
    return AdminInvoiceOut(
        **InvoiceOut.model_validate(invoice).model_dump(), merchant_name=merchant_name
    )


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Plan).order_by(Plan.sort_order))
    return list(rows.scalars())


@router.post("/plans", response_model=PlanOut, status_code=201)
async def create_plan(body: PlanCreate, db: AsyncSession = Depends(get_db)):
    exists = (await db.execute(select(Plan).where(Plan.key == body.key))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "এই কী-এর প্ল্যান আগে থেকেই আছে")
    plan = Plan(**body.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    await cache.delete(PLANS_CACHE_KEY)
    return plan


@router.patch("/plans/{plan_id}", response_model=PlanOut)
async def update_plan(plan_id: str, body: PlanUpdate, db: AsyncSession = Depends(get_db)):
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "প্ল্যান পাওয়া যায়নি")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    await db.commit()
    await db.refresh(plan)
    await cache.delete(PLANS_CACHE_KEY)
    return plan


@router.get("/invoices", response_model=Page[AdminInvoiceOut])
async def list_invoices(
    status: str | None = None,
    merchant_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Invoice, Merchant.business_name).join(
        Merchant, Merchant.id == Invoice.merchant_id
    )
    if status:
        query = query.where(Invoice.status == status)
    if merchant_id:
        query = query.where(Invoice.merchant_id == merchant_id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await db.execute(
        query.order_by(Invoice.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [_admin_invoice_out(invoice, name) for invoice, name in rows.all()]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/invoices/generate", response_model=AdminInvoiceOut, status_code=201)
async def generate_invoice(body: InvoiceGenerate, db: AsyncSession = Depends(get_db)):
    merchant = await db.get(Merchant, body.merchant_id)
    if not merchant:
        raise HTTPException(404, "মার্চেন্ট পাওয়া যায়নি")
    sub = await billing_service.get_subscription(db, merchant.id)
    plan = await billing_service.get_plan(db, sub.plan_key) if sub else None
    if not sub or not plan:
        raise HTTPException(400, "মার্চেন্টের কোনো সাবস্ক্রিপশন বা প্ল্যান নেই")
    exists = (
        await db.execute(
            select(Invoice).where(
                Invoice.merchant_id == merchant.id,
                Invoice.period_start == sub.current_period_start,
            )
        )
    ).scalars().first()
    if exists:
        raise HTTPException(409, "এই পিরিয়ডের ইনভয়েস আগে থেকেই আছে")
    invoice = await billing_service.generate_invoice(
        db, merchant, sub, plan, sub.current_period_start, sub.current_period_end
    )
    if not invoice:
        raise HTTPException(400, "শূন্য মূল্যের প্ল্যানের ইনভয়েস তৈরি করা যায় না")
    audit_service.record(
        db,
        actor_role="admin",
        action="invoice_generated",
        detail=f"{merchant.business_name}-এর জন্য ইনভয়েস তৈরি হয়েছে: {invoice.number}",
        merchant_id=merchant.id,
    )
    await db.commit()
    await db.refresh(invoice)
    return _admin_invoice_out(invoice, merchant.business_name)


@router.patch("/invoices/{invoice_id}", response_model=AdminInvoiceOut)
async def update_invoice(
    invoice_id: str, body: InvoicePatch, db: AsyncSession = Depends(get_db)
):
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "ইনভয়েস পাওয়া যায়নি")
    merchant = await db.get(Merchant, invoice.merchant_id)
    data = body.model_dump(exclude_unset=True)
    if "payment_method" in data:
        invoice.payment_method = data["payment_method"] or ""
    if "status" in data and data["status"]:
        if data["status"] not in ("due", "paid", "void"):
            raise HTTPException(400, "অবৈধ স্ট্যাটাস")
        newly_paid = data["status"] == "paid" and invoice.status != "paid"
        invoice.status = data["status"]
        if newly_paid:
            invoice.paid_at = datetime.now(timezone.utc)
            sub = await billing_service.get_subscription(db, invoice.merchant_id)
            if sub and sub.status == "past_due":
                sub.status = "active"
            audit_service.record(
                db,
                actor_role="admin",
                action="invoice_paid",
                detail=(
                    f"ইনভয়েস {invoice.number} পরিশোধিত হিসেবে চিহ্নিত হয়েছে"
                ),
                merchant_id=invoice.merchant_id,
            )
    await db.commit()
    await db.refresh(invoice)
    return _admin_invoice_out(invoice, merchant.business_name if merchant else "")
