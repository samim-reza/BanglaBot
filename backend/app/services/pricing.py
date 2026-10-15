"""Quotes: a tier + add-ons + billing interval → line items and totals (USD).

Yearly billing is the tier's ``price_year`` (default 10 × monthly, "2 months
free"); monthly add-ons bill 10 × their price a year too. One-off add-ons (setup)
are charged once and never renew. Selections are checked against the installed
catalog: visible and buyable online (self-serve), offered for the vertical and
the tier's product, not already included in the tier, quantities within rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.addons import CATALOG, PERIOD_ONCE, Addon
from app.core.plans import ANNUAL_MONTHS, PLANS, Plan

INTERVAL_MONTH = "month"
INTERVAL_YEAR = "year"
INTERVALS = (INTERVAL_MONTH, INTERVAL_YEAR)
CURRENCY = "USD"
CENT = Decimal("0.01")


class QuoteError(ValueError):
    """The selection can't be bought; the message is safe to show."""


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def tier_price(plan: Plan, interval: str) -> Decimal:
    return money(plan.yearly_price() if interval == INTERVAL_YEAR else plan.price_month)


def addon_price(addon: Addon, interval: str) -> Decimal:
    if addon.period == PERIOD_ONCE or interval != INTERVAL_YEAR:
        return money(addon.price)
    return money(Decimal(str(addon.price)) * ANNUAL_MONTHS)


@dataclass(frozen=True)
class LineItem:
    kind: str  # "tier" | "addon"
    key: str
    name: str
    quantity: int
    unit_price: Decimal
    #: "month" | "year" (renews) or "once"
    period: str

    @property
    def amount(self) -> Decimal:
        return money(self.unit_price * self.quantity)

    @property
    def recurring(self) -> bool:
        return self.period != PERIOD_ONCE

    def as_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "name": self.name,
            "quantity": self.quantity,
            "unit_price": float(self.unit_price),
            "period": self.period,
            "amount": float(self.amount),
        }


@dataclass(frozen=True)
class Quote:
    tier: Plan
    interval: str
    #: Recurring add-ons (renew with the tier): {key: quantity}.
    addons: dict[str, int]
    #: One-off add-ons bought now: {key: quantity}.
    once: dict[str, int]
    items: list[LineItem] = field(default_factory=list)
    currency: str = CURRENCY

    @property
    def recurring(self) -> Decimal:
        return money(sum((item.amount for item in self.items if item.recurring), Decimal(0)))

    @property
    def one_time(self) -> Decimal:
        return money(sum((item.amount for item in self.items if not item.recurring), Decimal(0)))

    @property
    def total(self) -> Decimal:
        return money(self.recurring + self.one_time)

    def selection(self) -> dict[str, Any]:
        return {"tier": self.tier.key, "interval": self.interval, "addons": dict(self.addons)}

    def as_json(self) -> dict[str, Any]:
        return {
            "tier": self.tier.key,
            "tier_name": self.tier.name,
            "interval": self.interval,
            "currency": self.currency,
            "items": [item.as_json() for item in self.items],
            "recurring": float(self.recurring),
            "one_time": float(self.one_time),
            "total": float(self.total),
        }


def _quantity(addon: Addon, raw: Any) -> int:
    try:
        qty = int(raw)
    except (TypeError, ValueError) as exc:
        raise QuoteError(f"{addon.name}: quantity must be a number") from exc
    if qty < 0:
        raise QuoteError(f"{addon.name}: quantity can't be negative")
    if qty > addon.limit:
        raise QuoteError(f"{addon.name}: at most {addon.limit}")
    return qty


def build_quote(
    tier_key: str,
    interval: str = INTERVAL_MONTH,
    addons: dict[str, Any] | None = None,
    *,
    vertical: str | None = None,
    self_serve: bool = True,
    owned_once: set[str] | frozenset[str] = frozenset(),
) -> Quote:
    """Price a selection. ``self_serve`` enforces what the public / owner may buy;
    ``owned_once`` = one-off add-ons already bought (not charged again)."""
    plan = PLANS.get(str(tier_key or "").strip().lower())
    if plan is None or (self_serve and not (plan.public and plan.checkout)):
        raise QuoteError("That plan isn't available")
    if not plan.offered_for(vertical):
        raise QuoteError(f"{plan.name} isn't offered for this business type")
    period = str(interval or INTERVAL_MONTH).strip().lower()
    if period not in INTERVALS:
        raise QuoteError("Billing must be monthly or yearly")
    items = [LineItem("tier", plan.key, plan.name, 1, tier_price(plan, period), period)]
    recurring: dict[str, int] = {}
    once: dict[str, int] = {}
    for key, raw in sorted((addons or {}).items(), key=lambda pair: (CATALOG[pair[0]].sort if pair[0] in CATALOG else 0, pair[0])):
        addon = CATALOG.get(str(key))
        if addon is None or (self_serve and not addon.visible):
            raise QuoteError(f"Unknown add-on: {key}")
        qty = _quantity(addon, raw)
        if qty == 0:
            continue
        if not addon.offered_for(plan.product, vertical):
            raise QuoteError(f"{addon.name} isn't available with {plan.name}")
        if (addon.channel and addon.channel in plan.channels) or (addon.feature and addon.feature in plan.includes):
            raise QuoteError(f"{addon.name} is already included in {plan.name}")
        if addon.period == PERIOD_ONCE:
            if addon.key in owned_once:
                continue
            once[addon.key] = qty
            items.append(LineItem("addon", addon.key, addon.name, qty, addon_price(addon, period), PERIOD_ONCE))
        else:
            recurring[addon.key] = qty
            items.append(LineItem("addon", addon.key, addon.name, qty, addon_price(addon, period), period))
    return Quote(tier=plan, interval=period, addons=recurring, once=once, items=items)


__all__ = [
    "CURRENCY",
    "INTERVALS",
    "INTERVAL_MONTH",
    "INTERVAL_YEAR",
    "LineItem",
    "Quote",
    "QuoteError",
    "addon_price",
    "build_quote",
    "money",
    "tier_price",
]
