"""Payments: create links, record what became of them, keep bookings in step.

- ``create_payment`` — a pending ``payments`` row + its link (bookings, subscriptions, add-ons).
- ``after_commit`` — after an agent booking: an online payment gets its link (before the SMS).
- ``apply_event`` / ``mark_paid`` — a provider event / a pay-page click / the owner's "mark paid".
- ``on_paid(kind, handler)`` — billing registers what a paid subscription / add-on switches on.

Every function taking ``db`` leaves the commit to the caller; call ``after_paid``
once the commit went through.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.db.base import new_id
from app.models import Merchant, Order, Payment
from app.services.payments import records
from app.services.payments.base import (
    KIND_ORDER,
    PAYMENT_KINDS,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PAID,
    STATUS_PENDING,
    STATUS_REFUNDED,
    PaymentError,
    PaymentEvent,
    PaymentProvider,
    currency_code,
    money,
)
from app.services.payments.registry import get_provider

logger = structlog.get_logger(__name__)

PROVIDER_MANUAL = "manual"
PaidHandler = Callable[[AsyncSession, Payment], Awaitable[None]]
_paid_handlers: dict[str, list[PaidHandler]] = {}

#: Session factory for the fire-and-forget entry points (tests swap in a fake).
session_factory: Any = None


def sessions() -> Any:
    if session_factory is not None:
        return session_factory
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal


def on_paid(kind: str, handler: PaidHandler) -> None:
    """Run ``handler(db, payment)`` inside the transaction that marks a ``kind`` payment paid."""
    handlers = _paid_handlers.setdefault(kind, [])
    if handler not in handlers:
        handlers.append(handler)


def _clean_meta(metadata: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in list((metadata or {}).items())[:20]:
        if value not in (None, ""):
            out[str(key)[:40]] = str(value)[:200]
    return out


async def create_payment(
    db: AsyncSession,
    *,
    merchant_id: str,
    amount: Decimal | float | str,
    currency: str,
    description: str,
    kind: str = KIND_ORDER,
    order_id: str | None = None,
    subscription_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    success_url: str | None = None,
    hold_minutes: int | None = None,
    provider: PaymentProvider | None = None,
    merchant: Any | None = None,
    now: datetime | None = None,
) -> Payment:
    """A pending payment with its link, added to ``db`` (flushed, not committed).
    Raises ``PaymentError`` (nothing added) when the amount is wrong or the provider fails."""
    if kind not in PAYMENT_KINDS:
        raise PaymentError(f"unknown payment kind {kind!r}")
    value = money(amount)
    if value <= 0:
        raise PaymentError("amount must be positive")
    code = currency_code(currency)
    chosen = provider or get_provider(merchant if kind == KIND_ORDER else None)
    stamp = now or utcnow()
    payment = Payment(
        id=new_id(), merchant_id=merchant_id, order_id=order_id, subscription_id=subscription_id, kind=kind,
        provider=chosen.name, amount=value, currency=code, status=STATUS_PENDING,
        description=str(description or "")[:200], meta=_clean_meta({**(metadata or {}), **({"return_url": success_url} if success_url else {})}), created_at=stamp, updated_at=stamp,
    )
    link = await chosen.create_link(
        reference=payment.id, amount=value, currency=code, description=payment.description,
        metadata={**payment.meta, "merchant_id": merchant_id, "kind": kind}, success_url=success_url,
    )
    payment.url = link.url
    payment.provider_ref = str(link.provider_ref or "")[:255]
    payment.expires_at = link.expires_at
    if hold_minutes:
        payment.hold_until = stamp + timedelta(minutes=int(hold_minutes))
    db.add(payment)
    await db.flush()
    return payment


def _describe(merchant: Any, record: Any) -> str:
    what = str(getattr(record, "items_summary", "") or getattr(record, "order_ref", "") or getattr(record, "kind", "") or "booking")
    return f"{getattr(merchant, 'business_name', '') or 'Payment'} - {what}"[:200]


async def after_commit(merchant_id: str, record_id: str, outcome: str = "") -> Payment | None:
    """After an agent commit: an online payment gets its link (so the confirmation text can
    carry it), pay-at-venue is noted on the record. Idempotent; never raises."""
    if not record_id:
        return None
    try:
        async with sessions()() as session:
            record = await session.get(Order, record_id, with_for_update=True)
            if record is None:
                return None
            if records.pays_at_venue(record):
                records.apply_at_venue(record)
                await session.commit()
                return None
            if not records.wants_link(record):
                return None
            merchant = await session.get(Merchant, record.merchant_id)
            if merchant is None:
                return None
            amount, currency = records.link_amount(record)
            payment = await create_payment(
                session, merchant=merchant, merchant_id=merchant.id, amount=amount, currency=currency,
                description=_describe(merchant, record), kind=KIND_ORDER, order_id=record.id,
                metadata={"order_id": record.id, "order_ref": record.order_ref or ""},
                hold_minutes=records.hold_minutes(record) if records.holds_slot(record) else None,
            )
            records.apply_link(record, payment)
            await session.commit()
        await logger.ainfo("payment_link_created", merchant_id=merchant_id, record_id=record_id, payment_id=payment.id, provider=payment.provider, outcome=outcome)
        return payment
    except Exception as exc:  # noqa: BLE001 — a missing link never breaks the call / SMS
        await logger.awarning("payment_link_failed", merchant_id=merchant_id, record_id=record_id, error=str(exc)[:200])
        return None


async def mark_paid(db: AsyncSession, payment: Payment, *, source: str, provider_ref: str = "", meta: dict[str, Any] | None = None, now: datetime | None = None) -> bool:
    """Mark ``payment`` (and its booking) paid and run the ``on_paid`` handlers.
    Idempotent: False when it was already paid or refunded."""
    if payment.status in (STATUS_PAID, STATUS_REFUNDED):
        return False
    stamp = now or utcnow()
    payment.status = STATUS_PAID
    payment.paid_at = stamp
    payment.updated_at = stamp
    if provider_ref and not payment.provider_ref:
        payment.provider_ref = provider_ref[:255]
    payment.meta = {**(payment.meta or {}), "paid_via": source, **_clean_meta(meta)}
    if payment.order_id:
        record = await db.get(Order, payment.order_id)
        if record is not None:
            records.apply_paid(record, payment, stamp)
    for handler in list(_paid_handlers.get(payment.kind, ())):
        await handler(db, payment)
    return True


async def find_payment(db: AsyncSession, event: PaymentEvent) -> Payment | None:
    if event.reference:
        payment = await db.get(Payment, event.reference)
        if payment is not None:
            return payment
    if event.provider_ref:
        payment = await db.scalar(select(Payment).where(Payment.provider == event.provider, Payment.provider_ref == event.provider_ref).limit(1))
        if payment is not None:
            return payment
    intent = str((event.meta or {}).get("payment_intent") or "")
    if intent:
        return await db.scalar(select(Payment).where(Payment.provider == event.provider, Payment.meta["payment_intent"].astext == intent).limit(1))
    return None


def _amount_matches(payment: Payment, event: PaymentEvent) -> bool:
    if event.amount is None:
        return True
    return money(event.amount) == money(payment.amount) and (not event.currency or event.currency == payment.currency)


async def apply_event(db: AsyncSession, event: PaymentEvent, *, now: datetime | None = None) -> tuple[Payment | None, bool]:
    """``(payment, changed)`` for a provider event; unknown payments are logged and ignored."""
    payment = await find_payment(db, event)
    if payment is None or payment.provider != event.provider:
        await logger.awarning("payment_event_unmatched", provider=event.provider, reference=event.reference, provider_ref=event.provider_ref, status=event.status)
        return None, False
    meta = {key: value for key, value in (event.meta or {}).items() if value}
    if event.status == STATUS_PAID:
        if not _amount_matches(payment, event):
            payment.meta = {**(payment.meta or {}), "amount_mismatch": f"{event.amount} {event.currency}"}
            await logger.awarning("payment_amount_mismatch", payment_id=payment.id, expected=str(payment.amount), got=str(event.amount))
            return payment, False
        return payment, await mark_paid(db, payment, source=event.provider, provider_ref=event.provider_ref, meta=meta, now=now)
    if event.status in (STATUS_FAILED, STATUS_EXPIRED):
        allowed = {STATUS_PENDING}
    elif event.status == STATUS_REFUNDED:
        allowed = {STATUS_PAID}
    else:
        return payment, False
    if payment.status not in allowed:
        return payment, False
    payment.status = event.status
    payment.updated_at = now or utcnow()
    payment.meta = {**(payment.meta or {}), **_clean_meta(meta)}
    if payment.order_id:
        record = await db.get(Order, payment.order_id)
        if record is not None and record.payment_ref == payment.id:
            records.apply_payment_status(record, event.status)
    return payment, True


async def mark_record_paid(db: AsyncSession, merchant: Any, record: Order, *, actor_id: str = "", now: datetime | None = None) -> Payment:
    """The owner says the booking is paid (cash at the venue, their own link, ...)."""
    current = await db.get(Payment, record.payment_ref) if record.payment_ref else None
    if current is not None and current.status == STATUS_PAID and record.payment_status == STATUS_PAID:
        return current
    if current is None or current.status != STATUS_PENDING or current.merchant_id != str(merchant.id):
        amount, currency = records.link_amount(record)
        stamp = now or utcnow()
        current = Payment(
            id=new_id(), merchant_id=str(merchant.id), order_id=record.id, kind=KIND_ORDER, provider=PROVIDER_MANUAL,
            amount=amount, currency=currency, status=STATUS_PENDING, description=_describe(merchant, record), meta={},
            created_at=stamp, updated_at=stamp,
        )
        db.add(current)
    await mark_paid(db, current, source="owner", meta={"marked_by": actor_id}, now=now)
    return current


async def after_paid(payment: Payment) -> None:
    """After the commit: mirror the booking to the calendar, book the processor fee. Never raises."""
    try:
        if payment.order_id:
            from app.services import notification_service

            notification_service.after_record_change(payment.order_id)
        from app.finance import recorder

        await recorder.record_payment_fee(payment)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("payment_after_paid_failed", payment_id=payment.id, error=str(exc)[:200])


__all__ = [
    "PROVIDER_MANUAL",
    "after_commit",
    "after_paid",
    "apply_event",
    "create_payment",
    "find_payment",
    "mark_paid",
    "mark_record_paid",
    "on_paid",
]
