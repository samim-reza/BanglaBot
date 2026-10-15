"""Per-account economics for one month, cursor-paginated (newest accounts first):
minutes, calls, chats, cost, revenue, margin, cost per minute."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cursor import decode_cursor, encode_cursor, page_size
from app.finance import queries
from app.finance.periods import Month
from app.finance.prices import ZERO
from app.finance.reports import MINUTE_CATEGORIES, margin, per_minute, usd
from app.finance.revenue import AccountRevenue, revenue_for
from app.models import Merchant


def account_row(merchant: Any, activity: dict[str, int], costs: list[dict[str, Any]], revenue: AccountRevenue | None) -> dict[str, Any]:
    """One account's line (pure: inputs already aggregated)."""
    money = queries.money_totals(costs)
    minute_cost = sum((row["cost_usd"] for row in costs if row.get("category") in MINUTE_CATEGORIES), ZERO)
    minutes = queries.minutes(activity.get("seconds", 0))
    revenue_usd = revenue.total_usd if revenue is not None else ZERO
    margin_usd, margin_pct = margin(revenue_usd, money["cost_usd"])
    return {
        "merchant_id": str(merchant.id),
        "business_name": str(getattr(merchant, "business_name", "") or ""),
        "vertical": str(getattr(merchant, "vertical", "") or ""),
        "plan": revenue.plan if revenue is not None else str(getattr(merchant, "plan", "") or ""),
        "active": bool(getattr(merchant, "active", True)),
        "minutes": float(minutes),
        "calls": int(activity.get("calls", 0)),
        "chats": int(activity.get("chats", 0)),
        "cost_usd": usd(money["cost_usd"]),
        "list_cost_usd": usd(money["list_cost_usd"]),
        "revenue_usd": usd(revenue_usd, 2),
        "margin_usd": margin_usd,
        "margin_pct": margin_pct,
        "cost_per_minute_usd": per_minute(minute_cost, minutes),
        "cache_savings_usd": usd(money["cache_savings_usd"]),
        "free_tier_savings_usd": usd(money["free_tier_savings_usd"]),
        "revenue": revenue.as_json() if revenue is not None else None,
    }


async def rows_for(db: AsyncSession, merchants: list[Merchant], month: Month) -> list[dict[str, Any]]:
    ids = [str(m.id) for m in merchants]
    if not ids:
        return []
    activity = await queries.activity(db, month, ids)
    costs: dict[str, list[dict[str, Any]]] = {}
    for row in await queries.costs(db, month, group=["merchant_id", "category"], merchant_ids=ids):
        costs.setdefault(str(row["merchant_id"]), []).append(row)
    minutes = {mid: queries.minutes(row["seconds"]) for mid, row in activity.items()}
    revenue = await revenue_for(db, merchants, month, minutes)
    return [account_row(m, activity.get(str(m.id), {}), costs.get(str(m.id), []), revenue.get(str(m.id))) for m in merchants]


async def list_accounts(db: AsyncSession, month: Month, *, limit: int = 50, cursor: str = "") -> dict[str, Any]:
    """Accounts that existed in ``month``, newest first. ``ValueError`` for a bad cursor."""
    size = page_size(limit)
    stmt = select(Merchant).where(Merchant.created_at < month.end_at)
    if cursor:
        at, row_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Merchant.created_at, Merchant.id) < tuple_(at, row_id))
    merchants = list(await db.scalars(stmt.order_by(Merchant.created_at.desc(), Merchant.id.desc()).limit(size + 1)))
    more = len(merchants) > size
    merchants = merchants[:size]
    return {
        **month.as_json(),
        "items": await rows_for(db, merchants, month),
        "next_cursor": encode_cursor(merchants[-1].created_at, merchants[-1].id) if more and merchants else None,
    }


__all__ = ["account_row", "list_accounts", "rows_for"]
