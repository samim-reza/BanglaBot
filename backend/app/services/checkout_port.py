"""Checkout for subscriptions: a pending ``payments`` row with a link from the platform provider.

Uses the payments workstream's ``service.create_payment(kind="subscription",
subscription_id=...)``; when that payment is marked paid (Stripe webhook / dummy
pay page) its ``on_paid("subscription", ...)`` hook runs
:func:`app.services.subscription_service.on_payment_paid` in the same
transaction. Imports are lazy so the signup routes answer 503 instead of failing
at import time while payments aren't installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

KIND_SUBSCRIPTION = "subscription"
#: Where the provider sends the buyer back (the portal / website adds these pages).
SIGNUP_RETURN_PATH = "/signup/complete"
OWNER_RETURN_PATH = "/plan"


class PaymentsUnavailable(RuntimeError):
    """No payment provider can make a link right now; safe to show."""


@dataclass(frozen=True)
class Checkout:
    url: str
    provider: str
    provider_ref: str
    payment_id: str
    expires_at: datetime | None = None


def frontend_base() -> str:
    raw = str(get_settings().frontend_origin or "")
    return next((part.strip() for part in raw.split(",") if part.strip()), "http://localhost:3000").rstrip("/")


def return_url(path: str, reference: str) -> str:
    return f"{frontend_base()}{path}?reference={reference}"


async def create_checkout(
    db: AsyncSession,
    *,
    merchant_id: str,
    subscription_id: str,
    amount: Decimal,
    currency: str,
    description: str,
    return_path: str,
) -> Checkout:
    """Add a pending ``payments`` row to ``db`` (flushed) and return its link (the caller commits)."""
    try:
        from app.services.payments.base import PaymentError
        from app.services.payments.service import create_payment
    except ImportError as exc:
        raise PaymentsUnavailable("Online payment isn't available yet") from exc
    try:
        payment = await create_payment(
            db,
            merchant_id=merchant_id,
            amount=amount,
            currency=currency,
            description=description[:200],
            kind=KIND_SUBSCRIPTION,
            subscription_id=subscription_id,
            metadata={"subscription_id": subscription_id},
            success_url=return_url(return_path, subscription_id),
        )
    except PaymentError as exc:
        # The provider's own wording (keys, account state) stays in the log, not the public answer.
        structlog.get_logger(__name__).warning("checkout_unavailable", error=str(exc)[:300])
        raise PaymentsUnavailable("Online payment isn't available right now — please try again shortly") from exc
    return Checkout(
        url=str(payment.url or ""), provider=str(payment.provider or ""), provider_ref=str(payment.provider_ref or ""),
        payment_id=str(payment.id), expires_at=payment.expires_at,
    )


def event_fields(payment_or_event: Any) -> dict[str, Any]:
    """What the subscription side needs from a paid ``payments`` row or a ``PaymentEvent``."""
    meta = getattr(payment_or_event, "meta", None) or getattr(payment_or_event, "metadata", None) or {}
    subscription_id = getattr(payment_or_event, "subscription_id", None) or (meta.get("subscription_id") if isinstance(meta, dict) else None)
    return {
        "subscription_id": str(subscription_id or ""),
        "payment_id": str(getattr(payment_or_event, "id", "") or getattr(payment_or_event, "reference", "") or ""),
        "provider": str(getattr(payment_or_event, "provider", "") or ""),
        "status": str(getattr(payment_or_event, "status", "") or ""),
        "amount": getattr(payment_or_event, "amount", None),
        "currency": str(getattr(payment_or_event, "currency", "") or ""),
    }


__all__ = ["OWNER_RETURN_PATH", "SIGNUP_RETURN_PATH", "Checkout", "PaymentsUnavailable", "create_checkout", "event_fields", "return_url"]
