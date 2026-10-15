"""Payments: the public pay page (dummy links), the Stripe webhook, the owner's
"mark as paid" and the owner's payment settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.models import Merchant, Order, Payment
from app.schemas.payments import MarkPaidOut, PaymentOut, PaymentSettingsIn, PaymentSettingsOut, PayPageOut, WebhookAck
from app.services import audit_service
from app.services.payments import link as owner_link
from app.services.payments import pay_page, registry, service
from app.services.payments.base import STATUS_PAID, PaymentError, WebhookSignatureError, money
from app.services.tenancy import owned

router = APIRouter(tags=["payments"])

TOKEN = Path(min_length=20, max_length=1024)


def payment_out(payment: Payment) -> PaymentOut:
    return PaymentOut(
        id=payment.id, kind=payment.kind, provider=payment.provider, amount=str(money(payment.amount)), currency=payment.currency,
        status=payment.status, url=payment.url or "", created_at=payment.created_at, paid_at=payment.paid_at,
        expires_at=payment.expires_at, hold_until=payment.hold_until,
    )


# ------------------------------------------------------------------ public pay page (dummy)
@router.get("/api/public/pay/{token}", response_model=PayPageOut)
async def pay_page_view(request: Request, token: str = TOKEN, db: AsyncSession = Depends(get_db)):
    await rate_limit(request, "pay-view", max_hits=60, per_seconds=60)
    try:
        return await pay_page.pay_view(db, token)
    except PaymentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/public/pay/{token}/complete", response_model=PayPageOut)
async def pay_page_complete(request: Request, token: str = TOKEN, db: AsyncSession = Depends(get_db)):
    """Test phase only: the dummy page's "Pay" button. No money moves."""
    await rate_limit(request, "pay-complete", max_hits=10, per_seconds=60)
    try:
        return await pay_page.complete_dummy(db, token)
    except PaymentError as exc:
        raise HTTPException(status_code=409 if str(exc) != pay_page.INVALID else 404, detail=str(exc)) from exc


# ------------------------------------------------------------------ Stripe webhook
@router.post("/api/payments/stripe/webhook", response_model=WebhookAck)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    provider = registry.webhook_provider("stripe")
    if provider is None:
        raise HTTPException(status_code=503, detail="Stripe is not configured")
    body = await request.body()
    try:
        event = await provider.handle_webhook(body, request.headers)
    except WebhookSignatureError as exc:
        raise HTTPException(status_code=400, detail="Invalid signature") from exc
    except PaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if event is None:
        return WebhookAck(status="ignored")
    payment, changed = await service.apply_event(db, event)
    await db.commit()
    if payment is not None and changed and payment.status == STATUS_PAID:
        await service.after_paid(payment)
    return WebhookAck(status=payment.status if payment is not None else "unmatched")


# ------------------------------------------------------------------ owner
@router.post("/api/orders/{order_id}/mark-paid", response_model=MarkPaidOut)
async def mark_paid(order_id: str, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    record = await owned(db, Order, order_id, merchant, detail="Record not found")
    try:
        payment = await service.mark_record_paid(db, merchant, record, actor_id=str(merchant.id))
    except PaymentError as exc:
        raise HTTPException(status_code=422, detail="Nothing to pay on this record" if str(exc) == "nothing to pay" else str(exc)) from exc
    audit_service.stage(
        db, action="order.marked_paid", actor_type="merchant", actor_id=merchant.id, target_type="order", target_id=record.id,
        merchant_id=merchant.id, request=request, meta={"amount": str(payment.amount), "currency": payment.currency, "provider": payment.provider},
    )
    await db.commit()
    await service.after_paid(payment)
    status = getattr(record.status, "value", record.status)
    return MarkPaidOut(order_id=record.id, status=str(status), payment_status=record.payment_status, payment=payment_out(payment))


def _settings_out(merchant: Merchant) -> PaymentSettingsOut:
    config = owner_link.settings_of(merchant)
    return PaymentSettingsOut(**config, platform_provider=registry.platform_provider().name)


@router.get("/api/payments/settings", response_model=PaymentSettingsOut)
async def get_payment_settings(merchant: Merchant = Depends(get_current_merchant)):
    return _settings_out(merchant)


@router.put("/api/payments/settings", response_model=PaymentSettingsOut)
async def update_payment_settings(
    data: PaymentSettingsIn, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    try:
        merchant.payment_settings = owner_link.updated_settings(merchant, data.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_service.stage(
        db, action="merchant.payment_settings_changed", actor_type="merchant", actor_id=merchant.id, target_type="merchant",
        target_id=merchant.id, merchant_id=merchant.id, request=request, meta={"provider": merchant.payment_settings.get("provider")},
    )
    await db.commit()
    await db.refresh(merchant)
    return _settings_out(merchant)
