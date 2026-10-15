"""One provider price: what a unit of usage costs us, and its paid list price."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any

CATEGORIES = ("telephony", "stt", "tts", "llm", "sms", "payment", "storage")
UNITS = ("minute", "char", "token", "segment", "usd", "txn", "message", "gb_month")
ZERO = Decimal("0")
MAX_PRICE = Decimal("1000000")


def dec(value: Any, default: Decimal = ZERO) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default
    return out if out.is_finite() else default


@dataclass(frozen=True)
class Price:
    provider: str
    sku: str
    category: str
    #: What the quantity counts (minute, char, token, segment, usd, txn, message).
    unit: str
    #: How many units ``unit_cost`` / ``list_price`` cover (1, 1000, 1_000_000; 100 for a % of usd).
    per: int
    #: USD per ``per`` units when paid.
    unit_cost: Decimal
    #: The paid list price per ``per`` units: the shadow cost of free-tier usage.
    list_price: Decimal
    #: Usage costs us nothing (free tier); ``list_price`` still shows what it would cost.
    free_tier: bool = False
    #: Telephony: seconds are billed in these increments (60 = per started minute); 0 = exact.
    increment_secs: int = 0
    note: str = ""

    @property
    def key(self) -> str:
        return price_key(self.provider, self.sku)

    def unit_rate(self) -> Decimal:
        """USD actually charged per single unit (0 on a free tier)."""
        return ZERO if self.free_tier else self.unit_cost / Decimal(self.per or 1)

    def list_rate(self) -> Decimal:
        return self.list_price / Decimal(self.per or 1)

    def cost(self, quantity: Decimal) -> tuple[Decimal, Decimal]:
        """``(cost_usd, list_cost_usd)`` of ``quantity`` units."""
        return quantity * self.unit_rate(), quantity * self.list_rate()

    def billed_minutes(self, seconds: float) -> Decimal:
        secs = max(0.0, float(seconds or 0))
        if self.increment_secs > 0 and secs > 0:
            secs = math.ceil(secs / self.increment_secs) * self.increment_secs
        return (Decimal(str(round(secs, 3))) / Decimal(60)).quantize(Decimal("0.0001"))

    def with_override(self, entry: dict[str, Any]) -> "Price":
        changes: dict[str, Any] = {}
        for name in ("unit_cost", "list_price"):
            if entry.get(name) is not None:
                changes[name] = dec(entry[name], getattr(self, name))
        if entry.get("free_tier") is not None:
            changes["free_tier"] = bool(entry["free_tier"])
        if entry.get("increment_secs") is not None:
            changes["increment_secs"] = max(0, int(entry["increment_secs"]))
        if entry.get("note") is not None:
            changes["note"] = str(entry["note"])[:200]
        return replace(self, **changes)

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "provider": self.provider,
            "sku": self.sku,
            "category": self.category,
            "unit": self.unit,
            "per": self.per,
            "unit_cost": str(self.unit_cost),
            "list_price": str(self.list_price),
            "free_tier": self.free_tier,
            "increment_secs": self.increment_secs,
            "note": self.note,
        }


def price_key(provider: str, sku: str) -> str:
    return f"{provider}|{sku}"


def P(provider: str, sku: str, category: str, unit: str, per: int, cost: str, *, listed: str | None = None,
      free: bool = False, increment: int = 0, note: str = "") -> Price:
    """Compact constructor for the default table."""
    return Price(provider, sku, category, unit, per, Decimal(cost), Decimal(listed if listed is not None else cost), free, increment, note)


__all__ = ["CATEGORIES", "MAX_PRICE", "P", "Price", "UNITS", "ZERO", "dec", "price_key"]
