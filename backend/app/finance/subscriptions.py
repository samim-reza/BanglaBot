"""Plan revenue from billing's ``subscriptions`` table (preferred over the account's current plan).

Per account, the latest activated subscription whose period overlaps the month
sets the month's recurring revenue: ``recurring_amount`` (÷ 12 for a yearly
interval, converted to USD), add-ons included. Accounts without such a row are
left to :func:`app.finance.revenue.recurring` (admin-assigned plans, trials).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.periods import Month
from app.finance.pricebook_defaults import FX_USD
from app.finance.prices import dec


def monthly_usd(row: Any) -> Decimal:
    amount = dec(getattr(row, "recurring_amount", 0))
    if str(getattr(row, "interval", "month") or "month") == "year":
        amount = amount / 12
    rate = FX_USD.get(str(getattr(row, "currency", "USD") or "USD").upper(), Decimal(1))
    return amount * rate


def pick(rows: list[Any]) -> dict[str, dict[str, Any]]:
    """``rows`` newest-activated first per account → the override per account (pure)."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        merchant_id = str(row.merchant_id)
        if merchant_id in out:
            continue
        out[merchant_id] = {"plan": str(row.tier or ""), "plan_usd": monthly_usd(row), "addons_usd": Decimal(0), "source": "subscription"}
    return out


async def subscription_revenue(db: AsyncSession, merchant_ids: list[str], month: Month) -> dict[str, dict[str, Any]]:
    """``{merchant_id: {"plan", "plan_usd", "addons_usd"}}``; empty when billing isn't installed."""
    if db is None or not merchant_ids:
        return {}
    try:
        from app.models.subscription import Subscription
    except ImportError:
        return {}
    rows = await db.scalars(
        select(Subscription)
        .where(
            Subscription.merchant_id.in_(merchant_ids),
            Subscription.activated_at.is_not(None),
            Subscription.activated_at < month.end_at,
            or_(Subscription.current_period_end.is_(None), Subscription.current_period_end > month.start_at),
        )
        .order_by(Subscription.merchant_id, Subscription.activated_at.desc())
    )
    return pick(list(rows))


__all__ = ["monthly_usd", "pick", "subscription_revenue"]
