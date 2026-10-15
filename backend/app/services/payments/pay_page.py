"""The public pay page behind a dummy link: what is owed, and the "pay" button.

Everything is keyed by the signed token, so the page needs no session; the
token's amount must match the row, so a tampered token is just invalid.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.models import Merchant, Order, Payment
from app.services.payments import service
from app.services.payments.base import STATUS_PAID, STATUS_PENDING, PaymentError, money
from app.services.payments.dummy import PROVIDER as DUMMY
from app.services.payments.dummy import DummyProvider, read_pay_token

INVALID = "This payment link is invalid or has expired"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _expired(payment: Payment, now: datetime) -> bool:
    expires = _aware(payment.expires_at)
    return payment.status == STATUS_PENDING and expires is not None and expires <= now


def serialize(payment: Payment, merchant: Any | None, record: Any | None, *, now: datetime | None = None) -> dict[str, Any]:
    stamp = now or utcnow()
    ref = str(getattr(record, "order_ref", "") or "") or str(payment.id)[:8].upper()
    expired = _expired(payment, stamp)
    return {
        "reference": ref,
        "business": str(getattr(merchant, "business_name", "") or ""),
        "description": payment.description or "",
        "amount": str(money(payment.amount)),
        "currency": payment.currency,
        "status": "expired" if expired else payment.status,
        "kind": payment.kind,
        "provider": payment.provider,
        "expires_at": _aware(payment.expires_at),
        "paid_at": _aware(payment.paid_at),
        "can_complete": payment.provider == DUMMY and payment.status == STATUS_PENDING and not expired,
        # Where the buyer goes after paying (signup → /signup/complete, plan change → /plan).
        "return_url": str((payment.meta or {}).get("return_url") or ""),
    }


async def _load(db: AsyncSession, token: str) -> tuple[dict[str, Any], Payment]:
    claims = read_pay_token(token)
    payment = await db.get(Payment, claims["reference"])
    if payment is None or money(payment.amount) != claims["amount"] or payment.currency != claims["currency"]:
        raise PaymentError(INVALID)
    return claims, payment


async def _view(db: AsyncSession, payment: Payment, now: datetime | None = None) -> dict[str, Any]:
    merchant = await db.get(Merchant, payment.merchant_id)
    record = await db.get(Order, payment.order_id) if payment.order_id else None
    return serialize(payment, merchant, record, now=now)


async def pay_view(db: AsyncSession, token: str) -> dict[str, Any]:
    _, payment = await _load(db, token)
    return await _view(db, payment)


async def complete_dummy(db: AsyncSession, token: str, *, now: datetime | None = None) -> dict[str, Any]:
    """The dummy page's "pay" button: marks the payment paid (idempotent), commits."""
    stamp = now or utcnow()
    claims, payment = await _load(db, token)
    if payment.provider != DUMMY:
        raise PaymentError("This link is paid on the payment provider's page")
    if payment.status == STATUS_PAID:
        return await _view(db, payment, stamp)
    if payment.status != STATUS_PENDING or _expired(payment, stamp):
        raise PaymentError("This payment link has expired" if payment.status in (STATUS_PENDING, "expired") else f"This payment is {payment.status}")
    _, changed = await service.apply_event(db, DummyProvider.complete_event(claims), now=stamp)
    await db.commit()
    if changed:
        await service.after_paid(payment)
    return await _view(db, payment, stamp)


__all__ = ["INVALID", "complete_dummy", "pay_view", "serialize"]
