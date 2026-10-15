"""The owner's plan: current tier + add-ons, usage against limits, renewal, and changes.

Change rules (no proration):

* no running subscription, a different billing interval, or an ended period →
  pay the full new amount; a new period starts when it is paid;
* more expensive (upgrade / more add-ons) → pay the difference in recurring
  price (+ any one-off add-ons) now; it applies when paid, period dates unchanged;
* cheaper (downgrade / fewer add-ons) → nothing to pay; it applies when the
  current period ends (the renewal is charged at the new price);
* same price, different selection → applies now, nothing to pay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.addons import CATALOG, PERIOD_ONCE, quantities
from app.core.datetime_utils import utcnow
from app.core.entitlements import entitlements
from app.models import Merchant, Subscription
from app.services import audit_service, checkout_port, usage_service
from app.services import subscription_service as subs
from app.services.pricing import Quote, QuoteError, build_quote, money

CHANGE_NEW = "new"
CHANGE_UPGRADE = "upgrade"
CHANGE_DOWNGRADE = "downgrade"
CHANGE_SWAP = "swap"
CHANGE_SAME = "same"


@dataclass(frozen=True)
class Change:
    kind: str
    due_now: Decimal
    #: "on_payment" | "period_end" | "now"
    effective: str
    effective_at: datetime | None = None

    def as_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "due_now": float(self.due_now), "effective": self.effective, "effective_at": self.effective_at}


def owned_once(merchant: Any) -> set[str]:
    return {key for key in quantities(getattr(merchant, "addons", None) or {}) if CATALOG[key].period == PERIOD_ONCE}


def quote_for(merchant: Merchant, tier: str, interval: str, addons: dict[str, int]) -> Quote:
    try:
        return build_quote(tier, interval, addons, vertical=merchant.vertical, owned_once=owned_once(merchant))
    except QuoteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def decide(current: Subscription | None, quote: Quote, now: datetime) -> Change:
    running = (
        current is not None
        and current.status == subs.STATUS_ACTIVE
        and current.interval == quote.interval
        and current.current_period_end is not None
        and current.current_period_end > now
    )
    if not running:
        return Change(CHANGE_NEW, quote.total, "on_payment")
    assert current is not None
    same = current.tier == quote.tier.key and quantities(current.addons or {}) == quote.addons
    if same and not quote.once:
        return Change(CHANGE_SAME, Decimal("0.00"), "now", now)
    old, new = money(current.recurring_amount), quote.recurring
    if new > old:
        return Change(CHANGE_UPGRADE, money(new - old + quote.one_time), "on_payment")
    if quote.once:
        raise HTTPException(status_code=422, detail="Buy one-off services on their own, without lowering your plan")
    if new < old:
        return Change(CHANGE_DOWNGRADE, Decimal("0.00"), "period_end", current.current_period_end)
    return Change(CHANGE_SWAP, Decimal("0.00"), "now", now)


async def view(db: AsyncSession, merchant: Merchant) -> dict[str, Any]:
    ent = entitlements(merchant)
    current = await subs.current(db, merchant.id)
    usage = await usage_service.month_usage(db, merchant)
    return {
        "tier": ent.plan.as_json(),
        "addons": [{**CATALOG[key].as_json(), "quantity": qty} for key, qty in ent.addons.items()],
        "entitlements": ent.as_json(),
        "usage": {key: usage.get(key) for key in ("period_start", "minutes", "calls", "chats", "sms", "minutes_left", "overage_minutes")},
        "limits": ent.as_json()["limits"],
        "subscription": subs.serialize(current) if current else None,
        "renewal": {
            "status": current.status,
            "renews_at": None if current.cancel_at_period_end else current.current_period_end,
            "ends_at": current.current_period_end if current.cancel_at_period_end else None,
            "amount": float(money((current.scheduled_change or {}).get("recurring_amount") or current.recurring_amount)),
            "interval": current.interval,
        } if current else None,
    }


async def quote_change(db: AsyncSession, merchant: Merchant, tier: str, interval: str, addons: dict[str, int]) -> dict[str, Any]:
    quote = quote_for(merchant, tier, interval, addons)
    change = decide(await subs.current(db, merchant.id), quote, utcnow())
    return {"quote": quote.as_json(), "change": change.as_json()}


async def _checkout(db: AsyncSession, merchant: Merchant, sub: Subscription, quote: Quote) -> dict[str, Any]:
    db.add(sub)
    if sub.amount <= 0:
        await subs.activate(db, sub, now=utcnow(), provider="free", payment_ref="")
        return {"checkout_url": None, "subscription_id": sub.id}
    try:
        checkout = await checkout_port.create_checkout(
            db, merchant_id=merchant.id, subscription_id=sub.id, amount=sub.amount, currency=sub.currency,
            description=f"{quote.tier.name} plan ({quote.interval}ly)", return_path=checkout_port.OWNER_RETURN_PATH,
        )
    except checkout_port.PaymentsUnavailable as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    sub.payment_provider, sub.payment_ref = checkout.provider, checkout.payment_id
    return {"checkout_url": checkout.url, "subscription_id": sub.id}


async def change(db: AsyncSession, merchant: Merchant, tier: str, interval: str, addons: dict[str, int], *, request: Any = None) -> dict[str, Any]:
    now = utcnow()
    quote = quote_for(merchant, tier, interval, addons)
    current = await subs.current(db, merchant.id)
    decision = decide(current, quote, now)
    out: dict[str, Any] = {"quote": quote.as_json(), "change": decision.as_json(), "checkout_url": None, "subscription_id": None}
    if decision.kind == CHANGE_SAME:
        raise HTTPException(status_code=409, detail="That's your current plan")
    if decision.kind == CHANGE_NEW:
        same = current is not None and current.tier == quote.tier.key and quantities(current.addons or {}) == quote.addons
        kind = subs.KIND_RENEWAL if same and current.interval == quote.interval else subs.KIND_CHANGE
        sub = subs.from_quote(merchant.id, quote, kind=kind, replaces_id=current.id if current else None)
        out.update(await _checkout(db, merchant, sub, quote))
    elif decision.kind == CHANGE_UPGRADE:
        assert current is not None
        sub = subs.from_quote(merchant.id, quote, kind=subs.KIND_CHANGE, amount=decision.due_now,
                              period=(current.current_period_start, current.current_period_end), replaces_id=current.id)
        out.update(await _checkout(db, merchant, sub, quote))
    elif decision.kind == CHANGE_DOWNGRADE:
        assert current is not None
        current.scheduled_change = {**quote.selection(), "recurring_amount": str(quote.recurring)}
    else:  # swap: same price, applies now
        assert current is not None
        current.tier, current.addons, current.scheduled_change = quote.tier.key, dict(quote.addons), {}
        current.line_items = [item.as_json() for item in quote.items]
        subs.apply_to_merchant(merchant, quote.tier.key, dict(quote.addons))
    audit_service.stage(
        db, action="plan.change_requested", actor_type=audit_service.ACTOR_MERCHANT, actor_id=merchant.id, target_type="merchant",
        target_id=merchant.id, merchant_id=merchant.id, request=request,
        meta={"kind": decision.kind, "tier": quote.tier.key, "interval": quote.interval, "due_now": str(decision.due_now)},
    )
    await db.commit()
    return out


async def renew(db: AsyncSession, merchant: Merchant, *, request: Any = None) -> dict[str, Any]:
    """Pay for the next period now (the scheduled downgrade, when there is one, else the same selection)."""
    current = await subs.current(db, merchant.id)
    if current is None:
        raise HTTPException(status_code=409, detail="No plan to renew — choose one")
    selection = dict(current.scheduled_change or {}) or {"tier": current.tier, "interval": current.interval, "addons": current.addons}
    quote = quote_for(merchant, str(selection.get("tier")), str(selection.get("interval") or current.interval), dict(selection.get("addons") or {}))
    sub = subs.from_quote(merchant.id, quote, kind=subs.KIND_RENEWAL, amount=quote.recurring, replaces_id=current.id)
    out = {"quote": quote.as_json(), **await _checkout(db, merchant, sub, quote)}
    audit_service.stage(db, action="plan.renewal_requested", actor_type=audit_service.ACTOR_MERCHANT, actor_id=merchant.id,
                        target_type="subscription", target_id=sub.id, merchant_id=merchant.id, request=request)
    await db.commit()
    return out


async def set_cancel(db: AsyncSession, merchant: Merchant, cancel: bool, *, request: Any = None) -> dict[str, Any]:
    """Cancel at the period end (or undo it): the account keeps its tier until then."""
    current = await subs.current(db, merchant.id)
    if current is None or current.status != subs.STATUS_ACTIVE:
        raise HTTPException(status_code=409, detail="No active plan")
    current.cancel_at_period_end = bool(cancel)
    audit_service.stage(db, action="plan.cancelled" if cancel else "plan.resumed", actor_type=audit_service.ACTOR_MERCHANT,
                        actor_id=merchant.id, target_type="subscription", target_id=current.id, merchant_id=merchant.id, request=request)
    await db.commit()
    return subs.serialize(current)


__all__ = ["Change", "change", "decide", "quote_change", "renew", "set_cancel", "view"]
