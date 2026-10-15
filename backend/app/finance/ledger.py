"""The cost ledger: priced usage lines and their one-shot batch insert into ``usage_events``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_id
from app.finance.prices import ZERO
from app.models.usage import UsageEvent

#: Categories a call's own meter writes (SMS / payment lines arrive separately).
CALL_CATEGORIES = ("telephony", "stt", "tts", "llm")
COST_PLACES = Decimal("0.000001")
QTY_PLACES = Decimal("0.0001")


@dataclass
class LedgerLine:
    category: str
    provider: str
    sku: str
    unit: str
    quantity: Decimal
    #: USD per single unit actually charged.
    unit_cost: Decimal
    cost_usd: Decimal
    list_cost_usd: Decimal
    free_tier: bool = False
    cache_hit: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def savings(self) -> Decimal:
        return max(ZERO, self.list_cost_usd - self.cost_usd)

    @property
    def cache_savings(self) -> Decimal:
        return self.savings if self.cache_hit else ZERO

    @property
    def free_tier_savings(self) -> Decimal:
        return self.savings if self.free_tier and not self.cache_hit else ZERO

    def as_json(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "provider": self.provider,
            "sku": self.sku,
            "unit": self.unit,
            "quantity": str(self.quantity.quantize(QTY_PLACES)),
            "unit_cost": str(self.unit_cost),
            "cost_usd": str(self.cost_usd.quantize(COST_PLACES)),
            "list_cost_usd": str(self.list_cost_usd.quantize(COST_PLACES)),
            "free_tier": self.free_tier,
            "cache_hit": self.cache_hit,
            "meta": dict(self.meta),
        }


def totals(lines: list[LedgerLine]) -> dict[str, Any]:
    by_category: dict[str, Decimal] = {}
    for line in lines:
        by_category[line.category] = by_category.get(line.category, ZERO) + line.cost_usd
    return {
        "cost_usd": sum((line.cost_usd for line in lines), ZERO),
        "list_cost_usd": sum((line.list_cost_usd for line in lines), ZERO),
        "cache_savings_usd": sum((line.cache_savings for line in lines), ZERO),
        "free_tier_savings_usd": sum((line.free_tier_savings for line in lines), ZERO),
        "by_category": by_category,
    }


def event_rows(lines: list[LedgerLine], *, merchant_id: str, call_log_id: str | None, occurred_at: datetime) -> list[dict[str, Any]]:
    """Insert-ready dicts for ``usage_events`` (ids made here, money rounded to 6 places)."""
    return [
        {
            "id": new_id(),
            "merchant_id": str(merchant_id or ""),
            "call_log_id": call_log_id,
            "occurred_at": occurred_at,
            "category": line.category,
            "provider": line.provider[:32],
            "sku": line.sku[:120],
            "unit": line.unit[:16],
            "quantity": line.quantity.quantize(QTY_PLACES),
            "unit_cost": line.unit_cost,
            "cost_usd": line.cost_usd.quantize(COST_PLACES),
            "list_cost_usd": line.list_cost_usd.quantize(COST_PLACES),
            "free_tier": line.free_tier,
            "cache_hit": line.cache_hit,
            "meta": dict(line.meta),
        }
        for line in lines
    ]


async def already_metered(db: AsyncSession, call_log_id: str) -> bool:
    """A call's lines are written once; a second flush for it is a no-op."""
    found = await db.scalar(
        select(UsageEvent.id).where(UsageEvent.call_log_id == call_log_id, UsageEvent.category.in_(CALL_CATEGORIES)).limit(1)
    )
    return found is not None


async def insert_lines(db: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """One multi-row INSERT for every line of a flush (caller commits)."""
    if not rows:
        return 0
    await db.execute(insert(UsageEvent), rows)
    return len(rows)


async def prune(db: AsyncSession, *, retention_days: int, now: datetime | None = None) -> int:
    """Delete ledger lines past retention (rollups keep the totals). Caller commits."""
    if retention_days <= 0:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=int(retention_days))
    result = await db.execute(delete(UsageEvent).where(UsageEvent.occurred_at < cutoff))
    return int(getattr(result, "rowcount", 0) or 0)


__all__ = ["CALL_CATEGORIES", "LedgerLine", "already_metered", "event_rows", "insert_lines", "prune", "totals"]
