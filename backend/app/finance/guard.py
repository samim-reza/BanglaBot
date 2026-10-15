"""Cost guard: a daily USD spend cap per provider.

``over_cap(provider)`` is synchronous and cheap, for the provider chains to
skip a provider that has spent its cap today (UTC) and fall through to the next
one. Spend is counted in-process as ledger lines are written
(``record_spend``) and re-read from ``usage_daily`` by the finance jobs
(``refresh``), so several workers converge within one job interval.

Caps: ``PROVIDER_DAILY_CAPS_USD`` ("openai=5,deepgram=3"), overridden per
provider by the admin console (``platform_settings["finance.caps"]``,
``{"caps": {"openai": "5"}}``; null removes a provider's cap). A cap of 0
blocks the provider.

Integration (provider layer): ``RoutedLLM.complete`` should treat
``guard.over_cap(client.link.provider)`` like an exhausted quota (skip, try the
next link); ``open_stt`` / the TTS fallback chain likewise per provider name.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance import settings_store
from app.finance.config import get_finance_settings, parse_caps
from app.finance.prices import ZERO, dec
from app.models.usage import UsageDaily

CAPS_KEY = "finance.caps"

_spend: dict[str, Decimal] = {}
_day: date | None = None
_admin_caps: dict[str, Decimal | None] = {}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _roll(today: date | None = None) -> None:
    global _day
    current = today or _today()
    if _day != current:
        _spend.clear()
        _day = current


def caps() -> dict[str, Decimal]:
    """Effective caps: env defaults, then the admin's per-provider overrides."""
    merged: dict[str, Decimal] = dict(parse_caps(get_finance_settings().provider_daily_caps_usd))
    for provider, cap in _admin_caps.items():
        if cap is None:
            merged.pop(provider, None)
        else:
            merged[provider] = cap
    return merged


def record_spend(lines: Iterable[Any], *, today: date | None = None) -> None:
    """Count freshly written ledger lines (anything with ``provider`` + ``cost_usd``)."""
    _roll(today)
    for line in lines:
        provider = str(getattr(line, "provider", "") or "").lower()
        if provider:
            _spend[provider] = _spend.get(provider, ZERO) + dec(getattr(line, "cost_usd", 0))


def spent_today(provider: str) -> Decimal:
    _roll()
    return _spend.get(str(provider or "").lower(), ZERO)


def over_cap(provider: str) -> bool:
    """True when ``provider`` has a cap and today's spend reached it."""
    name = str(provider or "").lower()
    cap = caps().get(name)
    if cap is None:
        return False
    return spent_today(name) >= cap


def status() -> list[dict[str, Any]]:
    _roll()
    limits = caps()
    names = sorted(set(limits) | set(_spend))
    return [
        {
            "provider": name,
            "cap_usd": str(limits[name]) if name in limits else None,
            "spent_today_usd": str(_spend.get(name, ZERO).quantize(Decimal("0.000001"))),
            "over_cap": name in limits and _spend.get(name, ZERO) >= limits[name],
        }
        for name in names
    ]


def parse_admin_caps(raw: Any) -> dict[str, Decimal | None]:
    stored = raw.get("caps") if isinstance(raw, dict) else None
    out: dict[str, Decimal | None] = {}
    for provider, value in (stored or {}).items():
        name = str(provider).strip().lower()
        if not name:
            continue
        if value is None:
            out[name] = None
            continue
        amount = dec(value, Decimal(-1))
        if amount >= 0:
            out[name] = amount
    return out


async def refresh(db: AsyncSession) -> None:
    """Reload the admin caps and today's spend per provider from the rollups."""
    global _admin_caps
    _admin_caps = parse_admin_caps(await settings_store.get_value(db, CAPS_KEY, {}))
    today = _today()
    rows = await db.execute(
        select(UsageDaily.provider, func.coalesce(func.sum(UsageDaily.cost_usd), 0)).where(UsageDaily.day == today).group_by(UsageDaily.provider)
    )
    _roll(today)
    _spend.clear()
    for provider, cost in rows.all():
        _spend[str(provider).lower()] = dec(cost)


async def set_caps(db: AsyncSession, changes: dict[str, Any], *, updated_by: str = "") -> dict[str, Decimal | None]:
    """Merge per-provider caps (None removes one) into the stored ones; caller commits."""
    global _admin_caps
    current = parse_admin_caps(await settings_store.get_value(db, CAPS_KEY, {}))
    current.update(parse_admin_caps({"caps": changes}))
    await settings_store.put_value(db, CAPS_KEY, {"caps": {k: (None if v is None else str(v)) for k, v in current.items()}}, updated_by=updated_by)
    _admin_caps = current
    return current


def reset() -> None:
    """Tests: forget spend and admin caps."""
    global _day, _admin_caps
    _spend.clear()
    _day = None
    _admin_caps = {}


__all__ = ["CAPS_KEY", "caps", "over_cap", "parse_admin_caps", "record_spend", "refresh", "reset", "set_caps", "spent_today", "status"]
