"""Restaurant settings: record / catalog kinds and the vertical's defaults, read with defaults applied."""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext

KIND_MENU_ITEM = "menu_item"
KIND_ORDER = "order"
KIND_RESERVATION = "booking"
KIND_LEAD = "lead"
#: A sentence spoken before the next question (set by a skill's normalize, cleared on the next save).
LEAD = "_lead"

#: Vertical settings the flow reads (the portal's config form starts from these).
DEFAULTS: dict[str, Any] = {
    "open_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    "open_time": "11:00",
    "close_time": "22:00",
    "delivery": True,
    "delivery_fee": 0,
    "free_delivery_over": 0,
    "minimum_order": 0,
    "tax_rate": 0,
    "prep_minutes": 20,
    "delivery_minutes": 45,
    "max_party_size": 10,
    "covers_per_slot": 40,
    "slot_minutes": 30,
    "booking_horizon_days": 14,
    "lead_minutes": 60,
}


def conf(ctx: CallContext) -> dict[str, Any]:
    """The account's restaurant settings over the defaults (empty values fall back)."""
    merged = dict(DEFAULTS)
    merged.update({key: value for key, value in ctx.config.items() if value not in (None, "")})
    return merged


def num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def whole(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


__all__ = ["DEFAULTS", "KIND_LEAD", "LEAD", "KIND_MENU_ITEM", "KIND_ORDER", "KIND_RESERVATION", "conf", "num", "whole"]
