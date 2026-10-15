"""Monthly revenue per account: its tier + monthly add-ons + overage minutes (USD).

Plan revenue comes from billing's ``subscriptions`` table when the account has an
activated subscription covering the month (:mod:`app.finance.subscriptions`), else
from the account itself (``app.core.addons.entitlements`` list prices, i.e. what it
is on *now* — admin-assigned plans, trials). Overage is always computed from the
month's phone minutes. ``use_subscription_source(fn)`` swaps the subscription
reader: ``await fn(db, merchant_ids, month)`` → ``{merchant_id: {"plan", "plan_usd",
"addons_usd"}}``; ``None`` restores the default.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.periods import Month
from app.finance.prices import ZERO, dec
from app.finance.subscriptions import subscription_revenue

MONEY = Decimal("0.01")
SubscriptionSource = Callable[[AsyncSession, list[str], Month], Awaitable[dict[str, dict[str, Any]]]]
_source: SubscriptionSource = subscription_revenue


def use_subscription_source(source: SubscriptionSource | None) -> None:
    """Replace where subscription revenue is read from (None = the subscriptions table)."""
    global _source
    _source = source or subscription_revenue


@dataclass(frozen=True)
class Recurring:
    plan: str
    plan_usd: Decimal
    addons_usd: Decimal
    #: Minutes the month includes; None = no limit (no overage).
    included_minutes: int | None
    overage_rate: Decimal


@dataclass(frozen=True)
class AccountRevenue:
    merchant_id: str
    plan: str
    plan_usd: Decimal
    addons_usd: Decimal
    minutes: Decimal
    overage_minutes: Decimal
    overage_usd: Decimal

    @property
    def total_usd(self) -> Decimal:
        return (self.plan_usd + self.addons_usd + self.overage_usd).quantize(MONEY)

    def as_json(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "plan_usd": str(self.plan_usd.quantize(MONEY)),
            "addons_usd": str(self.addons_usd.quantize(MONEY)),
            "overage_minutes": str(self.overage_minutes),
            "overage_usd": str(self.overage_usd.quantize(MONEY)),
            "revenue_usd": str(self.total_usd),
        }


def recurring(merchant: Any) -> Recurring:
    """What the account pays per month before overage (0 while disabled)."""
    from app.core.addons import CATALOG, entitlements

    ent = entitlements(merchant)
    plan = ent.plan
    key = str(getattr(plan, "key", "") or "")
    if not getattr(merchant, "active", True):
        return Recurring(key, ZERO, ZERO, None, ZERO)
    addons = ZERO
    for addon_key, qty in dict(getattr(ent, "addons", {}) or {}).items():
        addon = CATALOG.get(addon_key)
        if addon is not None and getattr(addon, "period", "month") == "month":
            addons += dec(addon.price) * int(qty or 0)
    included = getattr(ent, "minutes", None)
    return Recurring(key, dec(getattr(plan, "price_month", 0)), addons, included, dec(getattr(plan, "overage_per_minute", 0)))


def account_revenue(merchant: Any, minutes_used: Decimal, override: dict[str, Any] | None = None) -> AccountRevenue:
    base = recurring(merchant)
    plan, plan_usd, addons_usd = base.plan, base.plan_usd, base.addons_usd
    if override:
        plan = str(override.get("plan") or plan)
        plan_usd = dec(override.get("plan_usd"), plan_usd)
        addons_usd = dec(override.get("addons_usd"), addons_usd)
    used = max(ZERO, dec(minutes_used))
    overage = max(ZERO, used - Decimal(base.included_minutes)) if base.included_minutes is not None else ZERO
    if not getattr(merchant, "active", True):
        overage = ZERO
    return AccountRevenue(str(merchant.id), plan, plan_usd, addons_usd, used, overage, overage * base.overage_rate)


async def revenue_for(db: AsyncSession, merchants: list[Any], month: Month, minutes_by_account: dict[str, Decimal]) -> dict[str, AccountRevenue]:
    """``{merchant_id: AccountRevenue}`` for the month (accounts created after it earn nothing)."""
    live = [m for m in merchants if _existed(m, month)]
    overrides: dict[str, dict[str, Any]] = {}
    if live:
        overrides = await _source(db, [str(m.id) for m in live], month) or {}
    return {str(m.id): account_revenue(m, minutes_by_account.get(str(m.id), ZERO), overrides.get(str(m.id))) for m in live}


def _existed(merchant: Any, month: Month) -> bool:
    created = getattr(merchant, "created_at", None)
    if created is None:
        return True
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created < month.end_at


__all__ = ["AccountRevenue", "Recurring", "account_revenue", "recurring", "revenue_for", "use_subscription_source"]
