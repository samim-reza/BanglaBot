"""Finance reports for the admin console: overview, breakdowns, per-call costs, forecast.

Costs come from the ``usage_daily`` rollups (never the raw ledger, except for
one call's lines); revenue from :mod:`app.finance.revenue`. Money is returned
as floats rounded for display (6 places for costs, 2 for revenue); the CSV
export keeps exact decimals.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance import queries
from app.finance.ledger import LedgerLine, totals
from app.finance.periods import Month
from app.finance.pricebook import split_sku
from app.finance.prices import ZERO, dec
from app.finance.revenue import AccountRevenue, revenue_for
from app.models import CallLog, Merchant
from app.models.usage import UsageEvent

BREAKDOWNS = ("category", "provider", "model", "vertical", "account")
#: Categories that make up the cost of a phone minute (SMS and payment fees excluded).
MINUTE_CATEGORIES = ("telephony", "stt", "tts", "llm")
PLATFORM = "platform"


def usd(value: Any, places: int = 6) -> float:
    return round(float(dec(value)), places)


def margin(revenue: Decimal, cost: Decimal) -> tuple[float, float | None]:
    value = revenue - cost
    return usd(value, 2), (round(float(value / revenue * 100), 1) if revenue > 0 else None)


def per_minute(cost: Decimal, minutes: Decimal) -> float | None:
    return usd(cost / minutes, 4) if minutes > 0 else None


async def all_merchants(db: AsyncSession) -> list[Merchant]:
    return list(await db.scalars(select(Merchant)))


def _activity_totals(activity: dict[str, dict[str, int]]) -> dict[str, int]:
    return {key: sum(row[key] for row in activity.values()) for key in ("seconds", "calls", "chats")}


def _revenue_total(revenue: dict[str, AccountRevenue]) -> Decimal:
    return sum((row.total_usd for row in revenue.values()), ZERO)


async def overview(db: AsyncSession, month: Month, *, now: datetime | None = None) -> dict[str, Any]:
    by_category = await queries.costs(db, month, group=["category"])
    money = queries.money_totals(by_category)
    activity = await queries.activity(db, month)
    revenue = await revenue_for(db, await all_merchants(db), month, {mid: queries.minutes(row["seconds"]) for mid, row in activity.items()})
    revenue_usd = _revenue_total(revenue)
    acts = _activity_totals(activity)
    minutes = queries.minutes(acts["seconds"])
    minute_cost = sum((row["cost_usd"] for row in by_category if row["category"] in MINUTE_CATEGORIES), ZERO)
    margin_usd, margin_pct = margin(revenue_usd, money["cost_usd"])
    return {
        **month.as_json(),
        "fraction_elapsed": round(month.elapsed_fraction(now), 4),
        "cost_usd": usd(money["cost_usd"]),
        "list_cost_usd": usd(money["list_cost_usd"]),
        "revenue_usd": usd(revenue_usd, 2),
        "margin_usd": margin_usd,
        "margin_pct": margin_pct,
        "minutes": float(minutes),
        "calls": acts["calls"],
        "chats": acts["chats"],
        "cost_per_minute_usd": per_minute(minute_cost, minutes),
        "cache_savings_usd": usd(money["cache_savings_usd"]),
        "free_tier_savings_usd": usd(money["free_tier_savings_usd"]),
        "accounts": len(revenue),
        "paying_accounts": sum(1 for row in revenue.values() if row.total_usd > 0),
        "by_category": [
            {"category": row["category"], "cost_usd": usd(row["cost_usd"]), "list_cost_usd": usd(row["list_cost_usd"])}
            for row in sorted(by_category, key=lambda r: r["cost_usd"], reverse=True)
        ],
    }


def _item(key: str, label: str, row: dict[str, Any], total: Decimal, **extra: Any) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "cost_usd": usd(row["cost_usd"]),
        "list_cost_usd": usd(row["list_cost_usd"]),
        "cache_savings_usd": usd(row["cache_savings_usd"]),
        "free_tier_savings_usd": usd(row["free_tier_savings_usd"]),
        "share_pct": round(float(row["cost_usd"] / total * 100), 1) if total > 0 else 0.0,
        "events": int(row.get("events", 0)),
        **extra,
    }


def _merge(into: dict[str, Any], row: dict[str, Any]) -> None:
    for name in (*queries.MONEY, "quantity"):
        into[name] = into.get(name, ZERO) + dec(row.get(name))
    into["events"] = into.get("events", 0) + int(row.get("events", 0))


async def _names(db: AsyncSession, ids: list[str]) -> dict[str, tuple[str, str]]:
    if not ids:
        return {}
    rows = await db.execute(select(Merchant.id, Merchant.business_name, Merchant.vertical).where(Merchant.id.in_(ids)))
    return {str(mid): (str(name or ""), str(vertical or "")) for mid, name, vertical in rows.all()}


async def breakdown(db: AsyncSession, month: Month, by: str, *, limit: int = 50) -> dict[str, Any]:
    """Cost grouped one way: category | provider | model | vertical | account (top ``limit``)."""
    if by not in BREAKDOWNS:
        raise ValueError(f"by must be one of {', '.join(BREAKDOWNS)}")
    items: list[dict[str, Any]] = []
    if by in ("category", "provider"):
        rows = await queries.costs(db, month, group=[by])
        total = queries.money_totals(rows)["cost_usd"]
        items = [_item(str(row[by]), str(row[by]), row, total) for row in rows]
    elif by == "model":
        rows = await queries.costs(db, month, group=["category", "provider", "sku"])
        total = queries.money_totals(rows)["cost_usd"]
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            key = (str(row["category"]), str(row["provider"]), split_sku(str(row["sku"]))[0])
            _merge(merged.setdefault(key, {}), row)
        items = [_item(f"{p}:{m}", m, row, total, category=c, provider=p) for (c, p, m), row in merged.items()]
    else:
        rows = await queries.costs(db, month, group=["merchant_id"])
        total = queries.money_totals(rows)["cost_usd"]
        names = await _names(db, [str(row["merchant_id"]) for row in rows if row["merchant_id"]])
        if by == "account":
            items = [_item(str(row["merchant_id"]) or PLATFORM, names.get(str(row["merchant_id"]), ("", ""))[0] or PLATFORM, row, total) for row in rows]
        else:
            verticals: dict[str, dict[str, Any]] = {}
            for row in rows:
                vertical = names.get(str(row["merchant_id"]), ("", ""))[1] or PLATFORM
                _merge(verticals.setdefault(vertical, {}), row)
            items = [_item(key, key, row, total) for key, row in verticals.items()]
    items.sort(key=lambda item: item["cost_usd"], reverse=True)
    return {**month.as_json(), "by": by, "total_cost_usd": usd(total), "items": items[: max(1, min(100, limit))]}


def _line(event: UsageEvent) -> LedgerLine:
    return LedgerLine(
        event.category, event.provider, event.sku, event.unit, dec(event.quantity), dec(event.unit_cost), dec(event.cost_usd),
        dec(event.list_cost_usd), bool(event.free_tier), bool(event.cache_hit), dict(event.meta or {}),
    )


async def call_costs(db: AsyncSession, call_log_id: str) -> dict[str, Any] | None:
    """Every priced line of one call / chat (None when the call doesn't exist)."""
    log = await db.get(CallLog, call_log_id)
    if log is None:
        return None
    events = list(await db.scalars(select(UsageEvent).where(UsageEvent.call_log_id == call_log_id).order_by(UsageEvent.category, UsageEvent.provider, UsageEvent.sku)))
    lines = [_line(event) for event in events]
    sums = totals(lines)
    return {
        "call_log_id": log.id,
        "merchant_id": log.merchant_id,
        "direction": log.direction,
        "flow": log.flow,
        "duration_secs": int(log.duration_secs or 0),
        "created_at": log.created_at,
        "metered": bool(lines),
        "lines": [{**line.as_json(), "cost_usd": usd(line.cost_usd), "list_cost_usd": usd(line.list_cost_usd)} for line in lines],
        "cost_usd": usd(sums["cost_usd"]),
        "list_cost_usd": usd(sums["list_cost_usd"]),
        "cache_savings_usd": usd(sums["cache_savings_usd"]),
        "free_tier_savings_usd": usd(sums["free_tier_savings_usd"]),
        "by_category": {key: usd(value) for key, value in sums["by_category"].items()},
    }


def project(value: Decimal, fraction: float) -> Decimal:
    """Month-end value from the run rate so far (unchanged once the month is over)."""
    if fraction <= 0:
        return ZERO
    return value if fraction >= 1 else value / Decimal(str(fraction))


async def forecast(db: AsyncSession, month: Month, *, now: datetime | None = None) -> dict[str, Any]:
    fraction = month.elapsed_fraction(now)
    by_category = await queries.costs(db, month, group=["category"])
    cost_mtd = queries.money_totals(by_category)["cost_usd"]
    activity = await queries.activity(db, month)
    merchants = await all_merchants(db)
    minutes_mtd = {mid: queries.minutes(row["seconds"]) for mid, row in activity.items()}
    minutes_end = {mid: project(value, fraction).quantize(Decimal("0.1")) for mid, value in minutes_mtd.items()}
    revenue_mtd = _revenue_total(await revenue_for(db, merchants, month, minutes_mtd))
    revenue_end = _revenue_total(await revenue_for(db, merchants, month, minutes_end))
    cost_end = project(cost_mtd, fraction)
    margin_usd, margin_pct = margin(revenue_end, cost_end)
    return {
        **month.as_json(),
        "fraction_elapsed": round(fraction, 4),
        "cost_mtd_usd": usd(cost_mtd),
        "cost_forecast_usd": usd(cost_end),
        "revenue_mtd_usd": usd(revenue_mtd, 2),
        "revenue_forecast_usd": usd(revenue_end, 2),
        "margin_forecast_usd": margin_usd,
        "margin_forecast_pct": margin_pct,
        "minutes_mtd": float(sum(minutes_mtd.values(), ZERO)),
        "minutes_forecast": float(sum(minutes_end.values(), ZERO)),
        "by_category": [
            {"category": row["category"], "cost_mtd_usd": usd(row["cost_usd"]), "cost_forecast_usd": usd(project(row["cost_usd"], fraction))}
            for row in sorted(by_category, key=lambda r: r["cost_usd"], reverse=True)
        ],
    }


__all__ = ["BREAKDOWNS", "breakdown", "call_costs", "forecast", "margin", "overview", "per_minute", "project", "usd"]
