"""Subscriptions: create from a quote, activate on a payment, renew, sweep ended periods.

Simple, proration-free rules (the change decisions live in ``plan_service``):

* a purchase writes a ``pending`` row; the "paid" payment event activates it,
  applies its tier + add-ons to the account and cancels the row it replaces;
* a new period starts at activation (a renewal paid early starts when the old
  period ends); an upgrade keeps the current period's dates;
* when a period ends the sweep marks the row ``past_due`` (renewal needed) — or
  ``cancelled`` when the owner cancelled — and applies a scheduled downgrade;
* pending rows nobody paid for are cancelled after ``STALE_PENDING_DAYS``.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.addons import CATALOG, PERIOD_ONCE, quantities, stored
from app.core.cursor import decode_cursor, encode_cursor, page_size
from app.core.datetime_utils import utcnow
from app.core.plans import CHANNEL_WEB_CHAT, get_plan
from app.db.base import new_id
from app.models import Merchant, Subscription
from app.services import audit_service, checkout_port
from app.services.pricing import Quote, money

logger = structlog.get_logger(__name__)

STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_PAST_DUE = "past_due"
STATUS_CANCELLED = "cancelled"
STATUSES = (STATUS_PENDING, STATUS_ACTIVE, STATUS_PAST_DUE, STATUS_CANCELLED)
KIND_SIGNUP = "signup"
KIND_CHANGE = "change"
KIND_RENEWAL = "renewal"
KIND_MANUAL = "manual"
KINDS = (KIND_SIGNUP, KIND_CHANGE, KIND_RENEWAL, KIND_MANUAL)
STALE_PENDING_DAYS = 7


# --------------------------------------------------------------------------- periods
def add_months(start: datetime, months: int) -> datetime:
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))


def period_end(start: datetime, interval: str, trial_days: int = 0) -> datetime:
    if trial_days:
        return start + timedelta(days=int(trial_days))
    return add_months(start, 12 if interval == "year" else 1)


# --------------------------------------------------------------------------- rows
def from_quote(
    merchant_id: str,
    quote: Quote,
    *,
    kind: str,
    amount: Decimal | None = None,
    period: tuple[datetime | None, datetime | None] = (None, None),
    replaces_id: str | None = None,
) -> Subscription:
    """A ``pending`` row for ``quote``; ``amount`` = what this purchase charges (default: the total)."""
    return Subscription(
        id=new_id(),
        merchant_id=merchant_id,
        tier=quote.tier.key,
        addons=dict(quote.addons),
        interval=quote.interval,
        amount=money(quote.total if amount is None else amount),
        recurring_amount=quote.recurring,
        currency=quote.currency,
        status=STATUS_PENDING,
        kind=kind,
        current_period_start=period[0],
        current_period_end=period[1],
        cancel_at_period_end=False,
        scheduled_change={},
        line_items=[item.as_json() for item in quote.items],
        once_addons=dict(quote.once),
        payment_provider="",
        payment_ref="",
        replaces_id=replaces_id,
    )


async def current(db: AsyncSession, merchant_id: str) -> Subscription | None:
    """The account's running subscription (active, or past due awaiting renewal)."""
    return await db.scalar(
        select(Subscription)
        .where(Subscription.merchant_id == merchant_id, Subscription.status.in_((STATUS_ACTIVE, STATUS_PAST_DUE)))
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )


def apply_to_merchant(merchant: Merchant, tier: str, addons: dict[str, int], once: dict[str, int] | None = None) -> None:
    """The account's tier and add-ons become the subscription's (one-offs bought before are kept)."""
    owned = quantities(getattr(merchant, "addons", None) or {})
    kept = {key: qty for key, qty in owned.items() if key in CATALOG and CATALOG[key].period == PERIOD_ONCE}
    merchant.plan = tier
    merchant.addons = stored({**kept, **(once or {}), **addons})
    from app.core.addons import entitlements

    if getattr(merchant, "widget_enabled", False) and not entitlements(merchant).has_channel(CHANNEL_WEB_CHAT):
        merchant.widget_enabled = False


async def activate(db: AsyncSession, sub: Subscription, *, now: datetime, provider: str, payment_ref: str) -> Subscription:
    """Start ``sub`` (idempotent), apply it to the account, retire the row it replaces."""
    if sub.status != STATUS_PENDING:
        return sub
    replaced = await db.get(Subscription, sub.replaces_id) if sub.replaces_id else None
    if sub.current_period_start is None or sub.current_period_end is None:
        start = now
        if sub.kind == KIND_RENEWAL and replaced is not None and replaced.current_period_end and replaced.current_period_end > now:
            start = replaced.current_period_end
        sub.current_period_start = start
        sub.current_period_end = period_end(start, sub.interval, get_plan(sub.tier).trial_days)
    sub.status = STATUS_ACTIVE
    sub.activated_at = now
    sub.payment_provider = str(provider or "")[:16]
    sub.payment_ref = str(payment_ref or "")[:255]
    if replaced is not None and replaced.status in (STATUS_ACTIVE, STATUS_PAST_DUE):
        replaced.status = STATUS_CANCELLED
        replaced.cancelled_at = now
    merchant = await db.get(Merchant, sub.merchant_id)
    if merchant is not None:
        apply_to_merchant(merchant, sub.tier, dict(sub.addons or {}), dict(sub.once_addons or {}))
    return sub


async def on_payment_paid(db: AsyncSession, payment: Any, *, now: datetime | None = None) -> Subscription | None:
    """The payments service's "paid" handler for ``kind="subscription"`` rows (or a ``PaymentEvent``
    whose metadata names the subscription). Stages the changes; the caller commits."""
    info = checkout_port.event_fields(payment)
    sub = await db.get(Subscription, info["subscription_id"]) if info["subscription_id"] else None
    if sub is None:
        await logger.awarning("subscription_payment_unmatched", payment=info["payment_id"])
        return None
    if sub.status != STATUS_PENDING:
        return sub
    if info["amount"] is not None and money(info["amount"]) != money(sub.amount):
        await logger.awarning("subscription_amount_mismatch", subscription=sub.id, paid=str(info["amount"]), due=str(sub.amount))
        return None
    if info["currency"] and info["currency"].upper() != str(sub.currency or "USD").upper():
        await logger.awarning("subscription_currency_mismatch", subscription=sub.id)
        return None
    moment = now or utcnow()
    await activate(db, sub, now=moment, provider=info["provider"], payment_ref=info["payment_id"])
    from app.services import signup_service

    await signup_service.on_subscription_active(db, sub, now=moment)
    audit_service.stage(
        db, action="subscription.activated", target_type="subscription", target_id=sub.id, merchant_id=sub.merchant_id,
        meta={"tier": sub.tier, "amount": str(sub.amount), "kind": sub.kind, "provider": sub.payment_provider},
    )
    return sub


def register_payment_handler() -> bool:
    """Hook ``on_payment_paid`` into the payments service (``on_paid("subscription", ...)``)."""
    try:
        from app.services.payments.base import KIND_SUBSCRIPTION
        from app.services.payments.service import on_paid
    except ImportError:
        return False
    on_paid(KIND_SUBSCRIPTION, on_payment_paid)
    return True


async def handle_paid(payment: Any) -> Subscription | None:
    """``on_payment_paid`` in its own session (for callers without one)."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        sub = await on_payment_paid(session, payment)
        await session.commit()
        return sub


# --------------------------------------------------------------------------- periods ending
async def sweep(db: AsyncSession, now: datetime | None = None, *, batch: int = 500) -> dict[str, int]:
    """Ended periods → past_due / cancelled (+ scheduled downgrades); stale pending → cancelled."""
    moment = now or utcnow()
    counts = {"past_due": 0, "cancelled": 0, "downgraded": 0, "stale": 0}
    ended = await db.scalars(
        select(Subscription).where(Subscription.status == STATUS_ACTIVE, Subscription.current_period_end <= moment).limit(batch)
    )
    for sub in list(ended):
        change = dict(sub.scheduled_change or {})
        if change.get("tier"):
            merchant = await db.get(Merchant, sub.merchant_id)
            if merchant is not None:
                apply_to_merchant(merchant, str(change["tier"]), dict(change.get("addons") or {}))
                counts["downgraded"] += 1
        if sub.cancel_at_period_end:
            sub.status, sub.cancelled_at = STATUS_CANCELLED, moment
            counts["cancelled"] += 1
        else:
            sub.status = STATUS_PAST_DUE
            counts["past_due"] += 1
    stale = await db.scalars(
        select(Subscription)
        .where(Subscription.status == STATUS_PENDING, Subscription.created_at < moment - timedelta(days=STALE_PENDING_DAYS))
        .limit(batch)
    )
    for sub in list(stale):
        sub.status, sub.cancelled_at = STATUS_CANCELLED, moment
        counts["stale"] += 1
    return counts


# --------------------------------------------------------------------------- views
def serialize(sub: Subscription) -> dict[str, Any]:
    return {
        "id": sub.id,
        "merchant_id": sub.merchant_id,
        "tier": sub.tier,
        "tier_name": get_plan(sub.tier).name,
        "addons": dict(sub.addons or {}),
        "once_addons": dict(sub.once_addons or {}),
        "interval": sub.interval,
        "amount": float(sub.amount or 0),
        "recurring_amount": float(sub.recurring_amount or 0),
        "currency": sub.currency,
        "status": sub.status,
        "kind": sub.kind,
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "cancel_at_period_end": bool(sub.cancel_at_period_end),
        "scheduled_change": dict(sub.scheduled_change or {}),
        "line_items": list(sub.line_items or []),
        "payment_provider": sub.payment_provider,
        "payment_ref": sub.payment_ref,
        "created_at": sub.created_at,
        "activated_at": sub.activated_at,
        "cancelled_at": sub.cancelled_at,
    }


async def list_subscriptions(
    db: AsyncSession, *, limit: int = 50, cursor: str = "", status: str = "", merchant_id: str = "", tier: str = "", kind: str = ""
) -> dict[str, Any]:
    """Newest first, keyset-paginated. Raises ``ValueError`` for a malformed cursor."""
    size = page_size(limit)
    stmt = select(Subscription)
    for column, value in ((Subscription.status, status), (Subscription.merchant_id, merchant_id),
                          (Subscription.tier, tier), (Subscription.kind, kind)):
        if value:
            stmt = stmt.where(column == value)
    if cursor:
        at, row_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Subscription.created_at, Subscription.id) < tuple_(at, row_id))
    rows = list(await db.scalars(stmt.order_by(Subscription.created_at.desc(), Subscription.id.desc()).limit(size + 1)))
    more = len(rows) > size
    rows = rows[:size]
    names: dict[str, str] = {}
    ids = sorted({row.merchant_id for row in rows})
    if ids:
        names = {str(mid): str(name) for mid, name in await db.execute(select(Merchant.id, Merchant.business_name).where(Merchant.id.in_(ids)))}
    return {
        "items": [{**serialize(row), "merchant_name": names.get(row.merchant_id, "")} for row in rows],
        "next_cursor": encode_cursor(rows[-1].created_at, rows[-1].id) if more and rows else None,
    }


register_payment_handler()

__all__ = [
    "KINDS",
    "STATUSES",
    "activate",
    "add_months",
    "apply_to_merchant",
    "current",
    "from_quote",
    "handle_paid",
    "list_subscriptions",
    "on_payment_paid",
    "period_end",
    "register_payment_handler",
    "serialize",
    "sweep",
]
