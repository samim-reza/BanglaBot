"""CSV exports for the finance console: daily usage rollups or per-account economics."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.accounts import rows_for
from app.finance.periods import Month
from app.models import Merchant
from app.models.usage import UsageDaily

EXPORTS = ("daily", "accounts")
DAILY_COLUMNS = (
    "day", "merchant_id", "business_name", "category", "provider", "sku", "unit", "quantity", "cost_usd", "list_cost_usd",
    "cache_savings_usd", "free_tier_savings_usd", "events",
)
ACCOUNT_COLUMNS = (
    "merchant_id", "business_name", "vertical", "plan", "active", "minutes", "calls", "chats", "cost_usd", "list_cost_usd",
    "revenue_usd", "margin_usd", "margin_pct", "cost_per_minute_usd", "cache_savings_usd", "free_tier_savings_usd",
)
#: Accounts / rollup rows read per database round trip while streaming.
CHUNK = 500
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n", "\uff1d", "\uff0b", "\uff0d", "\uff20")


def safe_cell(value: Any) -> Any:
    """Business names are user input: keep spreadsheets from running them as formulas
    (also behind leading spaces, and the full-width ＝ ＋ － ＠ some spreadsheets accept)."""
    if isinstance(value, str) and value.lstrip(" ").startswith(_FORMULA_START):
        return "'" + value
    return value


def _encode(row: list[Any]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerow([safe_cell(cell) for cell in row])
    return buffer.getvalue()


async def _names(db: AsyncSession) -> dict[str, str]:
    rows = await db.execute(select(Merchant.id, Merchant.business_name))
    return {str(mid): str(name or "") for mid, name in rows.all()}


async def daily_csv(db: AsyncSession, month: Month) -> AsyncIterator[str]:
    yield _encode(list(DAILY_COLUMNS))
    names = await _names(db)
    offset = 0
    while True:
        rows = list(
            await db.scalars(
                select(UsageDaily)
                .where(UsageDaily.day >= month.start, UsageDaily.day < month.end)
                .order_by(UsageDaily.day, UsageDaily.merchant_id, UsageDaily.category, UsageDaily.provider, UsageDaily.sku)
                .offset(offset)
                .limit(CHUNK)
            )
        )
        for row in rows:
            yield _encode([
                row.day.isoformat(), row.merchant_id, names.get(row.merchant_id, ""), row.category, row.provider, row.sku, row.unit,
                row.quantity, row.cost_usd, row.list_cost_usd, row.cache_savings_usd, row.free_tier_savings_usd, row.events,
            ])
        if len(rows) < CHUNK:
            return
        offset += CHUNK


async def accounts_csv(db: AsyncSession, month: Month) -> AsyncIterator[str]:
    yield _encode(list(ACCOUNT_COLUMNS))
    offset = 0
    while True:
        merchants = list(
            await db.scalars(select(Merchant).where(Merchant.created_at < month.end_at).order_by(Merchant.created_at, Merchant.id).offset(offset).limit(CHUNK))
        )
        for row in await rows_for(db, merchants, month):
            yield _encode([row[name] for name in ACCOUNT_COLUMNS])
        if len(merchants) < CHUNK:
            return
        offset += CHUNK


def stream(db: AsyncSession, month: Month, kind: str) -> AsyncIterator[str]:
    if kind not in EXPORTS:
        raise ValueError(f"kind must be one of {', '.join(EXPORTS)}")
    return daily_csv(db, month) if kind == "daily" else accounts_csv(db, month)


async def stream_own_session(month: Month, kind: str) -> AsyncIterator[str]:
    """``stream`` on a session of its own: a streaming response outlives the request's session."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        async for chunk in stream(session, month, kind):
            yield chunk


__all__ = ["ACCOUNT_COLUMNS", "DAILY_COLUMNS", "EXPORTS", "safe_cell", "stream", "stream_own_session"]
