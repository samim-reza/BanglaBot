"""The price book: default prices plus admin overrides, versioned by ``effective_from``.

Overrides live in ``platform_settings["finance.pricebook"]`` as
``{"versions": [{"effective_from": "2026-11-01", "prices": {"groq|...:input":
{"unit_cost": "0.2", "free_tier": false}}, "note", "created_by", "created_at"}]}``.
The book for a date is the defaults with every version effective on or before
it applied in date order, so a usage line is always priced by the prices of
the day it happened.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import memo
from app.finance import settings_store
from app.finance.pricebook_defaults import DEFAULT_PRICES
from app.finance.prices import CATEGORIES, MAX_PRICE, UNITS, Price, dec, price_key

PRICEBOOK_KEY = "finance.pricebook"
DEFAULTS_EFFECTIVE_FROM = date(2026, 1, 1)
CACHE_TTL_SECONDS = 60.0
LLM_PARTS = ("input", "cached", "output")
MAX_VERSIONS = 200


class PriceBook:
    def __init__(self, prices: Iterable[Price], *, effective_from: date = DEFAULTS_EFFECTIVE_FROM, version: int = 0) -> None:
        self.prices: dict[str, Price] = {price.key: price for price in prices}
        self.effective_from = effective_from
        self.version = version

    def get(self, provider: str, sku: str) -> Price | None:
        return self.prices.get(price_key(provider, sku))

    def find(self, provider: str, sku: str) -> Price | None:
        """Exact SKU, else the longest known model the SKU's model starts with
        (``gpt-5.4-mini-2026-08:input`` → ``gpt-5.4-mini:input``)."""
        exact = self.get(provider, sku)
        if exact is not None:
            return exact
        model, part = split_sku(sku)
        best: Price | None = None
        for price in self.prices.values():
            if price.provider != provider:
                continue
            known_model, known_part = split_sku(price.sku)
            if known_part == part and model.startswith(known_model) and (best is None or len(known_model) > len(split_sku(best.sku)[0])):
                best = price
        return best

    def items(self) -> list[Price]:
        return sorted(self.prices.values(), key=lambda p: (CATEGORIES.index(p.category) if p.category in CATEGORIES else 99, p.provider, p.sku))

    def as_json(self) -> dict[str, Any]:
        return {"effective_from": self.effective_from.isoformat(), "version": self.version, "prices": [p.as_json() for p in self.items()]}


def split_sku(sku: str) -> tuple[str, str]:
    """``"openai/gpt-oss-120b:input"`` → ``("openai/gpt-oss-120b", "input")``; others → ``(sku, "")``."""
    model, sep, part = str(sku).rpartition(":")
    return (model, part) if sep and part in LLM_PARTS else (str(sku), "")


def defaults_book() -> PriceBook:
    return PriceBook(DEFAULT_PRICES)


def _new_price(key: str, entry: dict[str, Any]) -> Price | None:
    """A price the defaults don't know: needs category, unit and a cost."""
    provider, _, sku = key.partition("|")
    if not provider or not sku or entry.get("category") not in CATEGORIES or entry.get("unit") not in UNITS:
        return None
    cost = dec(entry.get("unit_cost"))
    return Price(
        provider=provider, sku=sku, category=entry["category"], unit=entry["unit"], per=max(1, int(entry.get("per") or 1)),
        unit_cost=cost, list_price=dec(entry.get("list_price"), cost), free_tier=bool(entry.get("free_tier")),
        increment_secs=max(0, int(entry.get("increment_secs") or 0)), note=str(entry.get("note") or "")[:200],
    )


def _version_date(version: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(version.get("effective_from") or ""))
    except ValueError:
        return None


def parse_versions(raw: Any) -> list[dict[str, Any]]:
    """Stored versions that make sense, oldest first."""
    versions = raw.get("versions") if isinstance(raw, dict) else None
    out = [v for v in versions or [] if isinstance(v, dict) and _version_date(v) and isinstance(v.get("prices"), dict)]
    return sorted(out, key=lambda v: _version_date(v) or DEFAULTS_EFFECTIVE_FROM)


def build(versions: list[dict[str, Any]], at: date) -> PriceBook:
    prices = {price.key: price for price in DEFAULT_PRICES}
    applied = [v for v in versions if (_version_date(v) or at) <= at]
    for version in applied:
        for key, entry in version["prices"].items():
            if not isinstance(entry, dict):
                continue
            base = prices.get(key)
            price = base.with_override(entry) if base is not None else _new_price(key, entry)
            if price is not None:
                prices[key] = price
    effective = _version_date(applied[-1]) if applied else DEFAULTS_EFFECTIVE_FROM
    return PriceBook(prices.values(), effective_from=effective or DEFAULTS_EFFECTIVE_FROM, version=len(applied))


def validate_entries(entries: Iterable[dict[str, Any]], book: PriceBook | None = None) -> dict[str, dict[str, Any]]:
    """API entries (``provider``, ``sku`` + changed fields) → stored overrides; ``ValueError`` when wrong."""
    known = book or defaults_book()
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        key = price_key(str(entry.get("provider") or "").strip().lower(), str(entry.get("sku") or "").strip())
        clean = {name: entry[name] for name in ("unit_cost", "list_price", "free_tier", "increment_secs", "note", "category", "unit", "per") if entry.get(name) is not None}
        for name in ("unit_cost", "list_price"):
            if name in clean:
                value = dec(clean[name], dec(-1))
                if value < 0 or value > MAX_PRICE:
                    raise ValueError(f"{key}: {name} must be between 0 and {MAX_PRICE}")
                clean[name] = str(value)
        if key not in known.prices and _new_price(key, clean) is None:
            raise ValueError(f"{key}: a new price needs category ({', '.join(CATEGORIES)}), unit ({', '.join(UNITS)}) and unit_cost")
        out[key] = clean
    if not out:
        raise ValueError("no prices given")
    return out


async def load_versions(db: AsyncSession) -> list[dict[str, Any]]:
    return parse_versions(await settings_store.get_value(db, PRICEBOOK_KEY, {}))


async def current(db: AsyncSession, at: date | None = None) -> PriceBook:
    """The book in force on ``at`` (today, UTC), memoized for a minute."""
    day = at or datetime.now(timezone.utc).date()
    cache_key = f"finance:pricebook:{day.isoformat()}"
    cached = memo.get(cache_key)
    if isinstance(cached, PriceBook):
        return cached
    book = build(await load_versions(db), day)
    memo.put(cache_key, book, ttl=CACHE_TTL_SECONDS)
    return book


async def add_version(db: AsyncSession, *, effective_from: date, entries: Iterable[dict[str, Any]], note: str = "", updated_by: str = "") -> dict[str, Any]:
    """Stage a new version (a version on the same date is merged into); the caller commits."""
    versions = await load_versions(db)
    overrides = validate_entries(entries, build(versions, effective_from))
    stamp = datetime.now(timezone.utc).isoformat()
    same = next((v for v in versions if _version_date(v) == effective_from), None)
    if same is not None:
        same["prices"] = {**same["prices"], **overrides}
        same.update(note=str(note or same.get("note") or "")[:300], created_by=str(updated_by)[:80], created_at=stamp)
        version = same
    else:
        version = {"effective_from": effective_from.isoformat(), "prices": overrides, "note": str(note or "")[:300], "created_by": str(updated_by)[:80], "created_at": stamp}
        versions.append(version)
    versions = sorted(versions, key=lambda v: _version_date(v) or DEFAULTS_EFFECTIVE_FROM)[-MAX_VERSIONS:]
    await settings_store.put_value(db, PRICEBOOK_KEY, {"versions": versions}, updated_by=updated_by)
    memo.drop("finance:pricebook:")
    return version


__all__ = [
    "DEFAULTS_EFFECTIVE_FROM",
    "PRICEBOOK_KEY",
    "PriceBook",
    "add_version",
    "build",
    "current",
    "defaults_book",
    "load_versions",
    "parse_versions",
    "split_sku",
    "validate_entries",
]
