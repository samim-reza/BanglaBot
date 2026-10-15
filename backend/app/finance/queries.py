"""The aggregate reads every finance report shares: costs from ``usage_daily``,
minutes / calls / chats from ``call_logs``. Grouped in SQL, small results."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.periods import Month
from app.finance.prices import ZERO, dec
from app.models import CallLog
from app.models.usage import UsageDaily

#: Billable phone minutes / billable chats (same directions as the plan usage meter).
VOICE_DIRECTIONS = ("outbound", "inbound")
CHAT_DIRECTIONS = ("widget", "whatsapp", "messenger", "instagram")
MONEY = ("cost_usd", "list_cost_usd", "cache_savings_usd", "free_tier_savings_usd")


def _cost_columns() -> list[Any]:
    return [func.coalesce(func.sum(getattr(UsageDaily, name)), 0).label(name) for name in MONEY] + [
        func.coalesce(func.sum(UsageDaily.events), 0).label("events"),
        func.coalesce(func.sum(UsageDaily.quantity), 0).label("quantity"),
    ]


async def costs(db: AsyncSession, month: Month, *, group: Iterable[str] = (), merchant_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Summed costs for ``month`` grouped by ``usage_daily`` columns (e.g. ``["provider"]``)."""
    keys = [getattr(UsageDaily, name) for name in group]
    stmt = select(*keys, *_cost_columns()).where(UsageDaily.day >= month.start, UsageDaily.day < month.end)
    if merchant_ids is not None:
        stmt = stmt.where(UsageDaily.merchant_id.in_(merchant_ids or [""]))
    if keys:
        stmt = stmt.group_by(*keys)
    result = await db.execute(stmt)
    rows = []
    for row in result.mappings().all():
        item = {key: row[key] for key in group}
        item.update({name: dec(row[name]) for name in MONEY})
        item["events"] = int(row["events"] or 0)
        item["quantity"] = dec(row["quantity"])
        rows.append(item)
    return rows


def money_totals(rows: Iterable[dict[str, Any]]) -> dict[str, Decimal]:
    out = {name: ZERO for name in MONEY}
    for row in rows:
        for name in MONEY:
            out[name] += dec(row.get(name))
    return out


async def activity(db: AsyncSession, month: Month, merchant_ids: list[str] | None = None) -> dict[str, dict[str, int]]:
    """``{merchant_id: {"seconds", "calls", "chats"}}`` for phone calls and real chats in ``month``."""
    voice = CallLog.direction.in_(VOICE_DIRECTIONS)
    chat = CallLog.direction.in_(CHAT_DIRECTIONS) & CallLog.transcript.like("%Customer:%")
    stmt = (
        select(
            CallLog.merchant_id,
            func.coalesce(func.sum(case((voice, CallLog.duration_secs), else_=0)), 0),
            func.coalesce(func.sum(case((voice, 1), else_=0)), 0),
            func.coalesce(func.sum(case((chat, 1), else_=0)), 0),
        )
        .where(CallLog.created_at >= month.start_at, CallLog.created_at < month.end_at)
        .group_by(CallLog.merchant_id)
    )
    if merchant_ids is not None:
        stmt = stmt.where(CallLog.merchant_id.in_(merchant_ids or [""]))
    result = await db.execute(stmt)
    return {str(mid): {"seconds": int(secs or 0), "calls": int(calls or 0), "chats": int(chats or 0)} for mid, secs, calls, chats in result.all()}


def minutes(seconds: int) -> Decimal:
    return (Decimal(int(seconds or 0)) / 60).quantize(Decimal("0.1"))


__all__ = ["CHAT_DIRECTIONS", "MONEY", "VOICE_DIRECTIONS", "activity", "costs", "minutes", "money_totals"]
