"""Clinic catalog helpers: doctors, their schedules, titles and departments; appointment records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.flows.context import CallContext, CatalogEntry
from app.flows.scheduling import Availability, window_from_config
from app.verticals.common import join_and, schedule_phrase

KIND_DOCTOR = "doctor"
KIND_APPOINTMENT = "appointment"


def doctor_availability(item: CatalogEntry | None, ctx: CallContext) -> Availability | None:
    if item is None:
        return None
    window = window_from_config(
        {
            "days": item.get("days") or [],
            "start": item.get("start_time"),
            "end": item.get("end_time"),
            "slot_minutes": item.get("slot_minutes") or 15,
            "max_patients": item.get("max_patients") or 0,
        },
        default_step=15,
    )
    if window is None:
        return None
    config = ctx.config
    return Availability(
        windows=[window],
        item_id=item.id,
        horizon_days=int(config.get("booking_horizon_days") or 14),
        lead_minutes=int(config.get("lead_minutes") if config.get("lead_minutes") is not None else 30),
        busy=ctx.busy_for(item.id),
        closures=ctx.closures_for(item.id),
    )


def doctor_title(item: CatalogEntry | None, language: str) -> str:
    if item is None:
        return ""
    name = item.name.strip()
    if name.lower().startswith(("dr", "prof")):
        return name
    return f"Dr. {name}"


def departments(ctx: CallContext, language: str) -> str:
    seen: list[str] = []
    for item in ctx.items(KIND_DOCTOR):
        specialty = str(item.get("specialty", "") or "").strip()
        if specialty and specialty not in seen:
            seen.append(specialty)
    return join_and(seen[:6], language) or join_and([doctor_title(i, language) for i in ctx.items(KIND_DOCTOR)][:4], language)


def chosen_doctor(slots: dict[str, Any], ctx: CallContext) -> CatalogEntry | None:
    ref = slots.get("doctor")
    if ref:
        found = ctx.find_items(ref, KIND_DOCTOR)
        if len(found) == 1:
            return found[0]
    return None


def doctor_facts(ctx: CallContext) -> list[str]:
    lines = ["Doctors (ref: name — department, degrees, days, hours, minutes per patient, fee):"]
    for item in ctx.items(KIND_DOCTOR):
        availability = doctor_availability(item, ctx)
        schedule = schedule_phrase(availability, "en", ctx) if availability else "schedule not set"
        parts = [f"{item.ref}: {item.name}"]
        if item.get("specialty"):
            parts.append(f"— {item.get('specialty')}")
        if item.get("degrees"):
            parts.append(f"({item.get('degrees')})")
        parts.append(f"; {schedule}")
        if item.get("slot_minutes"):
            parts.append(f"; ~{item.get('slot_minutes')} min per patient")
        if item.get("fee"):
            parts.append(f"; fee {item.get('fee')} {ctx.currency}")
        if item.get("online"):
            parts.append("; offers online visits")
        if item.get("notes"):
            parts.append(f"; {item.get('notes')}")
        lines.append("- " + " ".join(parts))
    if len(lines) == 1:
        lines.append("- (no doctors added yet — take a message: say the clinic will call back)")
    return lines


def record_start(record: Any) -> datetime | None:
    value = getattr(record, "scheduled_at", None)
    return value if isinstance(value, datetime) else None


def record_serial(record: Any) -> Any:
    details = getattr(record, "details", None)
    return details.get("serial") if isinstance(details, dict) else None


def uses_serials(ctx: CallContext) -> bool:
    """Queue (serial) numbers are said on the call: on for South Asian accounts unless switched off."""
    configured = ctx.config.get("queue_numbers")
    if isinstance(configured, bool):
        return configured
    return ctx.region.code in ("IN", "PK")


def serial_words(value: Any, language: str) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value or "")


__all__ = [
    "KIND_APPOINTMENT",
    "KIND_DOCTOR",
    "chosen_doctor",
    "departments",
    "doctor_availability",
    "doctor_facts",
    "doctor_title",
    "record_serial",
    "record_start",
    "serial_words",
    "uses_serials",
]
