"""Real-estate helpers: listings (catalog), viewing availability, lead scoring, spoken property words."""

from __future__ import annotations

import re
from typing import Any

from app.flows.context import CallContext, CatalogEntry
from app.flows.scheduling import Availability, window_from_config
from app.flows.steps import lang_text
from app.verticals.common import schedule_phrase

KIND_PROPERTY = "property"
KIND_LEAD = "lead"

PROPERTY_TYPES = ["land", "flat", "house", "commercial"]
TIMELINES = ["now", "1-3 months", "3-6 months", "later"]

TYPE_WORDS = {
    "land": {"bn": "জমি", "en": "land"},
    "flat": {"bn": "ফ্ল্যাট", "en": "apartment"},
    "house": {"bn": "বাড়ি", "en": "house"},
    "commercial": {"bn": "কমার্শিয়াল স্পেস", "en": "commercial space"},
}
INTENT_WORDS = {
    "buy": {"bn": "কেনা", "en": "buying"},
    "rent": {"bn": "ভাড়া", "en": "renting"},
    "sell": {"bn": "বিক্রি", "en": "selling"},
}

CONFIG_DEFAULTS: dict[str, Any] = {
    "visit_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
    "visit_start": "10:00",
    "visit_end": "18:00",
    "visit_slot_minutes": 60,
    "visit_capacity": 1,
    "booking_horizon_days": 14,
    "lead_minutes": 120,
}

#: Lead details copied from the slots to the record.
LEAD_KEYS = ("intent", "property_type", "location", "budget", "budget_max", "size", "asking_price", "timeline")


def realty_config(ctx: CallContext) -> dict[str, Any]:
    merged = dict(CONFIG_DEFAULTS)
    merged.update({key: value for key, value in ctx.config.items() if value is not None})
    return merged


def visit_capacity(ctx: CallContext) -> int:
    return int(realty_config(ctx).get("visit_capacity") or 1)


def visit_availability(ctx: CallContext) -> Availability | None:
    config = realty_config(ctx)
    window = window_from_config(
        {
            "days": config.get("visit_days") or [],
            "start": config.get("visit_start"),
            "end": config.get("visit_end"),
            "slot_minutes": config.get("visit_slot_minutes") or 60,
            "capacity": config.get("visit_capacity") or 1,
        },
        default_step=60,
    )
    if window is None:
        return None
    return Availability(
        windows=[window],
        item_id=None,
        horizon_days=int(config.get("booking_horizon_days") or 14),
        lead_minutes=int(config.get("lead_minutes") if config.get("lead_minutes") is not None else 120),
        busy=ctx.busy_for(None),
    )


def word(table: dict[str, dict[str, str]], key: Any, language: str) -> str:
    entry = table.get(str(key or ""))
    return lang_text(entry, language) if entry else str(key or "")


def number(value: Any) -> float | None:
    try:
        parsed = float(re.sub(r"[^\d.]", "", str(value)))
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def lead_score(slots: dict[str, Any]) -> str:
    """hot / warm / cold — decided in code, never by the model."""
    if slots.get("intent") == "sell":
        return "warm"
    if slots.get("wants_visit") is True or slots.get("timeline") == "now":
        return "hot"
    if slots.get("timeline") in ("1-3 months",) or slots.get("budget"):
        return "warm"
    return "cold"


def chosen_property(slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
    found = ctx.find_items(slots.get("property"), KIND_PROPERTY) if slots.get("property") else []
    return found[0] if len(found) == 1 else None


def matching_listings(slots: dict[str, Any], ctx: CallContext, limit: int = 4) -> list[CatalogEntry]:
    """Listings of the right kind for the caller (type, sale/rent, budget). Area fit is the model's call."""
    wanted = "rent" if slots.get("intent") == "rent" else "sale"
    ptype = slots.get("property_type")
    budget = number(slots.get("budget_max"))
    out: list[CatalogEntry] = []
    for item in ctx.items(KIND_PROPERTY):
        if str(item.get("listing_type", "sale")) != wanted:
            continue
        if ptype and item.get("property_type") and item.get("property_type") != ptype:
            continue
        price = number(item.get("price"))
        if budget and price and price > budget * 1.25:
            continue
        out.append(item)
    return out[:limit]


def interest_phrase(slots: dict[str, Any], ctx: CallContext, language: str) -> str:
    """What the caller is interested in: "the 3-bed family home" / "a house in Maple Grove"."""
    item = chosen_property(slots, ctx)
    if item is not None:
        return item.name if language == "bn" else f"the {item.name}"
    ptype = word(TYPE_WORDS, slots.get("property_type"), language) if slots.get("property_type") else ""
    area = slots.get("location") or ""
    if language == "bn":
        return " ".join(part for part in (area, ptype) if part) or "একটি প্রপার্টি"
    return " ".join(part for part in (ptype, f"in {area}" if area else "") if part) or "a property"


def listing_facts(ctx: CallContext) -> list[str]:
    lines = [f"Listings (ref: title — for sale/rent, type, area, size, price in {ctx.currency}, details):"]
    for item in ctx.items(KIND_PROPERTY):
        parts = [f"{item.ref}: {item.name}", f"— {item.get('listing_type', 'sale')}", str(item.get("property_type", ""))]
        for key in ("location", "size"):
            if item.get(key):
                parts.append(f"; {item.get(key)}")
        if item.get("price"):
            unit = " per month" if item.get("listing_type") == "rent" else ""
            parts.append(f"; price {item.get('price')} {ctx.currency}{unit}")
        if item.get("price_note"):
            parts.append(f"({item.get('price_note')})")
        if item.get("bedrooms"):
            parts.append(f"; {item.get('bedrooms')} bed")
        if item.get("features"):
            parts.append(f"; {item.get('features')}")
        lines.append("- " + " ".join(part for part in parts if part))
    if len(lines) == 1:
        lines.append("- (no listings added yet — collect the caller's needs; an agent will call back with options)")
    availability = visit_availability(ctx)
    if availability:
        lines.append(f"Viewings: {schedule_phrase(availability, 'en', ctx)}.")
    return lines


__all__ = [
    "CONFIG_DEFAULTS",
    "INTENT_WORDS",
    "KIND_LEAD",
    "KIND_PROPERTY",
    "LEAD_KEYS",
    "PROPERTY_TYPES",
    "TIMELINES",
    "TYPE_WORDS",
    "chosen_property",
    "interest_phrase",
    "lead_score",
    "listing_facts",
    "matching_listings",
    "number",
    "realty_config",
    "visit_availability",
    "visit_capacity",
    "word",
]
