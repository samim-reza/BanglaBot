"""Custom engine catalog: generic bookable resources (a room, a class, a consultation …) and their hours."""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext, CatalogEntry
from app.flows.scheduling import Availability, window_from_config
from app.verticals.common import join_and, schedule_phrase

KIND_RESOURCE = "resource"
KIND_BOOKING = "booking"
KIND_LEAD = "lead"


def resources(ctx: CallContext) -> list[CatalogEntry]:
    return ctx.items(KIND_RESOURCE)


def availability(item: CatalogEntry | None, ctx: CallContext) -> Availability | None:
    if item is None:
        return None
    window = window_from_config(
        {
            "days": item.get("days") or [],
            "start": item.get("start_time"),
            "end": item.get("end_time"),
            "slot_minutes": item.get("slot_minutes") or 30,
            "capacity": item.get("capacity") or 1,
        },
        default_step=30,
    )
    if window is None:
        return None
    config = ctx.config
    return Availability(
        windows=[window],
        item_id=item.id,
        horizon_days=int(config.get("booking_horizon_days") or 14),
        lead_minutes=int(config.get("lead_minutes") if config.get("lead_minutes") is not None else 60),
        busy=ctx.busy_for(item.id),
    )


def chosen(slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
    ref = slots.get("resource")
    if ref:
        found = ctx.find_items(ref, KIND_RESOURCE)
        if len(found) == 1:
            return found[0]
    return None


def names(ctx: CallContext, language: str, items: list[CatalogEntry] | None = None) -> str:
    return join_and([item.name for item in (items if items is not None else resources(ctx))][:5], language)


def resource_facts(ctx: CallContext) -> list[str]:
    lines = ["What can be booked (ref: name — hours, price, details):"]
    for item in resources(ctx):
        hours = availability(item, ctx)
        parts = [f"{item.ref}: {item.name} — {schedule_phrase(hours, 'en', ctx) if hours else 'hours not set'}"]
        if item.get("price"):
            parts.append(f"; price {item.get('price')} {ctx.currency}")
        if item.get("description"):
            parts.append(f"; {item.get('description')}")
        lines.append("- " + "".join(parts))
    if len(lines) == 1:
        lines.append("- (nothing bookable by phone — take a message for the team)")
    return lines


__all__ = ["KIND_BOOKING", "KIND_LEAD", "KIND_RESOURCE", "availability", "chosen", "names", "resource_facts", "resources"]
