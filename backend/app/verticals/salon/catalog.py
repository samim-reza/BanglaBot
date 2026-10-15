"""Salon & spa catalog helpers: services and staff (two catalog kinds), who offers what, booking records.

A service may list the staff who do it, and a staff member may list their services;
when neither side says, anyone can do anything.
"""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext, CatalogEntry
from app.flows.timefmt import normalize_days
from app.verticals.common import join_and, join_or
from app.voice.languages import normalize_language

KIND_SERVICE = "service"
KIND_STAFF = "staff"
KIND_BOOKING = "booking"
#: ``slots["staff"]`` when the caller has no preference.
ANY = "any"
DEFAULT_DURATION = 60

CONFIG_DEFAULTS: dict[str, Any] = {
    "booking_horizon_days": 30,
    "lead_minutes": 60,
    "slot_minutes": 15,
    # Used only when no staff are listed: the salon's own hours, one client at a time.
    "open_days": ["tue", "wed", "thu", "fri", "sat"],
    "open_time": "10:00",
    "close_time": "19:00",
}


def salon_config(ctx: CallContext) -> dict[str, Any]:
    merged = dict(CONFIG_DEFAULTS)
    merged.update({key: value for key, value in ctx.config.items() if value is not None})
    return merged


def _norm(text: Any) -> str:
    return " ".join(str(text or "").lower().split())


def _names(value: Any) -> set[str]:
    items = value if isinstance(value, list) else str(value or "").split(",")
    return {_norm(item) for item in items if _norm(item)}


def _same(a: str, b: str) -> bool:
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


def offers(person: CatalogEntry, service: CatalogEntry) -> bool:
    """Does this staff member do this service?"""
    by_service = _names(service.get("staff"))
    by_person = _names(person.get("services"))
    if any(_same(_norm(person.name), name) for name in by_service) or any(_same(_norm(service.name), name) for name in by_person):
        return True
    return not by_service and not by_person


def staff_for(service: CatalogEntry | None, ctx: CallContext) -> list[CatalogEntry]:
    staff = ctx.items(KIND_STAFF)
    return staff if service is None else [person for person in staff if offers(person, service)]


def chosen_service(slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
    found = ctx.find_items(slots.get("service"), KIND_SERVICE) if slots.get("service") else []
    return found[0] if len(found) == 1 else None


def staff_by_ref(ref: Any, ctx: CallContext) -> CatalogEntry | None:
    wanted = str(ref or "")
    return next((person for person in ctx.items(KIND_STAFF) if person.ref == wanted), None) if wanted and wanted != ANY else None


def assigned_staff(slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
    """Who does it: the one asked for, or — for "anyone" — whoever the proposed time belongs to."""
    return staff_by_ref(slots.get("staff"), ctx) or staff_by_ref(slots.get("window"), ctx)


def duration(service: CatalogEntry | None) -> int:
    try:
        minutes = int(float(service.get("duration_minutes") or 0)) if service else 0
    except (TypeError, ValueError):
        minutes = 0
    return minutes if minutes > 0 else DEFAULT_DURATION


def longest(person: CatalogEntry | None, ctx: CallContext) -> int:
    """The longest service this person does — how long one of their existing bookings may last."""
    services = [s for s in ctx.items(KIND_SERVICE) if person is None or offers(person, s)]
    return max([duration(s) for s in services] or [DEFAULT_DURATION])


def price(service: CatalogEntry | None) -> float:
    try:
        return max(0.0, float(service.get("price") or 0)) if service else 0.0
    except (TypeError, ValueError):
        return 0.0


def with_article(name: str, language: str) -> str:
    """"a haircut" / "an eyebrow threading" (English only)."""
    if normalize_language(language) != "en" or not name:
        return name
    return f"{'an' if name[:1].lower() in 'aeiou' else 'a'} {name}"


def services_phrase(ctx: CallContext, language: str) -> str:
    return join_and([item.name for item in ctx.items(KIND_SERVICE)][:6], language)


def staff_phrase(people: list[CatalogEntry], language: str) -> str:
    return join_or([person.name for person in people][:4], language)


def record_service(record: Any, ctx: CallContext) -> CatalogEntry | None:
    details = getattr(record, "details", None)
    details = details if isinstance(details, dict) else {}
    wanted = str(details.get("service_id") or "")
    found = next((item for item in ctx.items(KIND_SERVICE) if wanted and item.id == wanted), None)
    if found is None and details.get("service"):
        matches = ctx.find_items(details.get("service"), KIND_SERVICE)
        found = matches[0] if len(matches) == 1 else None
    return found


def record_staff(record: Any, ctx: CallContext) -> CatalogEntry | None:
    item = ctx.item_by_id(getattr(record, "catalog_item_id", None))
    return item if item is not None and item.kind == KIND_STAFF else None


def service_facts(ctx: CallContext) -> list[str]:
    lines = [f"Services (ref: name — minutes, price in {ctx.currency}, who does it, notes):"]
    for item in ctx.items(KIND_SERVICE):
        who = ", ".join(person.name for person in staff_for(item, ctx)) or "anyone"
        parts = [f"{item.ref}: {item.name}", f"— {duration(item)} min"]
        if item.get("price"):
            parts.append(f"; {item.get('price')}")
        parts.append(f"; by {who}")
        if item.get("notes"):
            parts.append(f"; {item.get('notes')}")
        lines.append("- " + " ".join(parts))
    if len(lines) == 1:
        lines.append("- (no services added yet — take a message: say the salon will call back)")
    return lines


def staff_facts(ctx: CallContext) -> list[str]:
    people = ctx.items(KIND_STAFF)
    if not people:
        config = salon_config(ctx)
        days = ", ".join(normalize_days(config.get("open_days") or [])) or "every day"
        return [f"Opening hours: {days} {config.get('open_time')}–{config.get('close_time')} (no staff list: anyone available)."]
    lines = ["Staff (ref: name — days, hours, notes):"]
    for person in people:
        days = ", ".join(normalize_days(person.get("days") or [])) or "every day"
        parts = [f"{person.ref}: {person.name}", f"— {days} {person.get('start_time', '?')}–{person.get('end_time', '?')}"]
        if person.get("notes"):
            parts.append(f"; {person.get('notes')}")
        lines.append("- " + " ".join(parts))
    return lines


__all__ = [
    "ANY",
    "CONFIG_DEFAULTS",
    "KIND_BOOKING",
    "KIND_SERVICE",
    "KIND_STAFF",
    "assigned_staff",
    "chosen_service",
    "duration",
    "longest",
    "offers",
    "price",
    "record_service",
    "record_staff",
    "salon_config",
    "service_facts",
    "services_phrase",
    "staff_by_ref",
    "staff_facts",
    "staff_for",
    "staff_phrase",
    "with_article",
]
