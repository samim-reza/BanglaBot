"""Home-service helpers: services (catalog), arrival windows, the service area, booking records."""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext, CatalogEntry
from app.flows.scheduling import Availability, window_from_config
from app.flows.timefmt import normalize_days
from app.verticals.common import join_and, money, slot_start, when_phrase, window_phrase

KIND_SERVICE = "service"
KIND_BOOKING = "booking"

DEFAULT_WINDOWS = [
    {"key": "morning", "start": "09:00", "end": "12:00"},
    {"key": "afternoon", "start": "12:00", "end": "15:00"},
    {"key": "evening", "start": "15:00", "end": "18:00"},
]

CONFIG_DEFAULTS: dict[str, Any] = {
    "service_areas": [],
    "working_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
    "time_windows": DEFAULT_WINDOWS,
    "teams": 3,
    "booking_horizon_days": 7,
    "lead_minutes": 60,
}


def service_config(ctx: CallContext) -> dict[str, Any]:
    """The account's settings over the defaults (same merge as ``Vertical.config``)."""
    merged = dict(CONFIG_DEFAULTS)
    merged.update({key: value for key, value in ctx.config.items() if value is not None})
    return merged


def teams(ctx: CallContext) -> int:
    return int(service_config(ctx).get("teams") or 1)


def service_availability(ctx: CallContext) -> Availability:
    config = service_config(ctx)
    days = normalize_days(config.get("working_days") or [])
    windows = []
    for raw in config.get("time_windows") or DEFAULT_WINDOWS:
        if not isinstance(raw, dict):
            continue
        window = window_from_config({**raw, "days": days, "slot_minutes": 0, "capacity": config.get("teams") or 1})
        if window is not None:
            windows.append(window)
    return Availability(
        windows=windows,
        item_id=None,
        horizon_days=int(config.get("booking_horizon_days") or 7),
        lead_minutes=int(config.get("lead_minutes") if config.get("lead_minutes") is not None else 60),
        busy=ctx.busy_for(None),
    )


def window_label(key: str, ctx: CallContext, language: str) -> str:
    for raw in service_config(ctx).get("time_windows") or DEFAULT_WINDOWS:
        if isinstance(raw, dict) and raw.get("key") == key:
            span = window_phrase(raw.get("start"), raw.get("end"), language)
            return f"between {span.replace(' to ', ' and ')}"
    return ""


def service_areas(ctx: CallContext) -> list[str]:
    return [str(item) for item in service_config(ctx).get("service_areas") or [] if str(item).strip()]


def area_ok(area: Any, ctx: CallContext) -> bool:
    areas = [name.strip().lower() for name in service_areas(ctx)]
    if not areas:
        return True
    text = " ".join(str(area or "").lower().split())
    return bool(text) and any(name in text or text in name for name in areas)


def chosen_service(slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
    found = ctx.find_items(slots.get("service"), KIND_SERVICE) if slots.get("service") else []
    return found[0] if len(found) == 1 else None


def services_phrase(ctx: CallContext, language: str) -> str:
    return join_and([item.name for item in ctx.items(KIND_SERVICE)][:6], language)


def price_parts(service: CatalogEntry | None, ctx: CallContext, language: str) -> dict[str, str]:
    """Spoken visit charge and usual range of a service ({} when it has no visit charge)."""
    if service is None or not service.get("visit_charge"):
        return {}
    parts = {"visit": money(service.get("visit_charge"), ctx, language)}
    low, high = service.get("price_from"), service.get("price_to")
    if low and high:
        parts.update(low=money(low, ctx, language), high=money(high, ctx, language))
    return parts


def visit_when(slots: dict[str, Any], ctx: CallContext, language: str, *, on: bool = False) -> str:
    """The proposed visit: "tomorrow between 9 AM and 12 PM"."""
    start = slot_start(slots)
    if start is None:
        return ""
    return when_phrase(start, ctx, language, window_label=window_label(str(slots.get("window") or ""), ctx, language), on=on)


def record_when(record: Any, ctx: CallContext, language: str) -> str:
    """An existing booking's visit, read the same way."""
    start = getattr(record, "scheduled_at", None)
    if start is None:
        return ""
    details = getattr(record, "details", None)
    key = str(details.get("time_window") or "") if isinstance(details, dict) else ""
    return when_phrase(start.astimezone(ctx.now.tzinfo), ctx, language, window_label=window_label(key, ctx, language), on=True)


def record_service(record: Any, ctx: CallContext) -> CatalogEntry | None:
    return ctx.item_by_id(getattr(record, "catalog_item_id", None))


def service_facts(ctx: CallContext) -> list[str]:
    lines = [f"Services (ref: name — category, visit charge, usual price range in {ctx.currency}, notes):"]
    for item in ctx.items(KIND_SERVICE):
        parts = [f"{item.ref}: {item.name}"]
        if item.get("category"):
            parts.append(f"— {item.get('category')}")
        if item.get("visit_charge"):
            parts.append(f"; visit charge {item.get('visit_charge')}")
        if item.get("price_from") and item.get("price_to"):
            parts.append(f"; usually {item.get('price_from')}–{item.get('price_to')}")
        if item.get("duration"):
            parts.append(f"; takes {item.get('duration')}")
        if item.get("notes"):
            parts.append(f"; {item.get('notes')}")
        lines.append("- " + " ".join(parts))
    if len(lines) == 1:
        lines.append("- (no services added yet — take the request; the team will call back)")
    return lines


def area_facts(ctx: CallContext) -> list[str]:
    config = service_config(ctx)
    areas = service_areas(ctx)
    windows = ", ".join(
        f"{raw.get('key')} {raw.get('start')}–{raw.get('end')}" for raw in config.get("time_windows") or DEFAULT_WINDOWS if isinstance(raw, dict)
    )
    days = ", ".join(normalize_days(config.get("working_days") or [])) or "every day"
    return [
        f"Service areas: {', '.join(areas)}." if areas else "Service areas: anywhere in the city.",
        f"Arrival windows: {windows}; working days: {days}.",
    ]


__all__ = [
    "CONFIG_DEFAULTS",
    "DEFAULT_WINDOWS",
    "KIND_BOOKING",
    "KIND_SERVICE",
    "area_facts",
    "area_ok",
    "chosen_service",
    "price_parts",
    "record_service",
    "record_when",
    "service_areas",
    "service_availability",
    "service_config",
    "service_facts",
    "services_phrase",
    "teams",
    "visit_when",
    "window_label",
]
