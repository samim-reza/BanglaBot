"""Daily rollups: ledger lines summed per (account, UTC day, category, provider, SKU).

``aggregate`` is pure; ``upsert`` adds the sums onto ``usage_daily`` in one
``INSERT … ON CONFLICT DO UPDATE`` per flush, so dashboards never scan the ledger.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_id
from app.finance.ledger import COST_PLACES, QTY_PLACES, LedgerLine
from app.finance.prices import ZERO
from app.models.usage import UsageDaily

SUMMED = ("quantity", "cost_usd", "list_cost_usd", "cache_savings_usd", "free_tier_savings_usd", "events")


def day_of(at: datetime) -> date:
    stamp = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).date()


def aggregate(lines: list[LedgerLine], *, merchant_id: str, occurred_at: datetime) -> list[dict[str, Any]]:
    """One row per (category, provider, sku) of the flush's day, money rounded to 6 places."""
    day = day_of(occurred_at)
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for line in lines:
        key = (line.category, line.provider[:32], line.sku[:120])
        row = rows.get(key)
        if row is None:
            row = rows[key] = {
                "merchant_id": str(merchant_id or ""), "day": day, "category": key[0], "provider": key[1], "sku": key[2],
                "unit": line.unit[:16], "quantity": ZERO, "cost_usd": ZERO, "list_cost_usd": ZERO,
                "cache_savings_usd": ZERO, "free_tier_savings_usd": ZERO, "events": 0,
            }
        row["quantity"] += line.quantity
        row["cost_usd"] += line.cost_usd
        row["list_cost_usd"] += line.list_cost_usd
        row["cache_savings_usd"] += line.cache_savings
        row["free_tier_savings_usd"] += line.free_tier_savings
        row["events"] += 1
    for row in rows.values():
        row["quantity"] = Decimal(row["quantity"]).quantize(QTY_PLACES)
        for name in ("cost_usd", "list_cost_usd", "cache_savings_usd", "free_tier_savings_usd"):
            row[name] = Decimal(row[name]).quantize(COST_PLACES)
    return list(rows.values())


async def upsert(db: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """Add ``rows`` onto ``usage_daily`` (caller commits)."""
    if not rows:
        return 0
    stmt = pg_insert(UsageDaily).values([{"id": new_id(), **row} for row in rows])
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        constraint="uq_usage_daily_key",
        set_={**{name: getattr(UsageDaily, name) + getattr(excluded, name) for name in SUMMED}, "updated_at": datetime.now(timezone.utc)},
    )
    await db.execute(stmt)
    return len(rows)


__all__ = ["aggregate", "day_of", "upsert"]
