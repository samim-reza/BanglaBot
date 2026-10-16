"""The salon & spa vertical's portal vocabulary and forms: bookings, two catalog kinds (services and
staff), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import CatalogKind, FieldSpec, L
from app.verticals.salon.catalog import CONFIG_DEFAULTS, KIND_BOOKING, KIND_SERVICE, KIND_STAFF

SERVICE_FIELDS = (
    FieldSpec("name", L("Service"), required=True, placeholder="Women's haircut"),
    FieldSpec("category", L("Category"), placeholder="Hair / Nails / Spa"),
    FieldSpec("duration_minutes", L("Duration (minutes)"), "number", required=True, default=60),
    FieldSpec("price", L("Price"), "money"),
    FieldSpec("staff", L("Who does it"), "list", help=L("Staff names, one per line; empty = anyone.")),
    FieldSpec("notes", L("Notes for the agent"), "textarea", placeholder="Includes wash and blow-dry."),
)

STAFF_FIELDS = (
    FieldSpec("name", L("Name"), required=True, placeholder="Maya"),
    FieldSpec("days", L("Working days"), "days", required=True),
    FieldSpec("start_time", L("Starts at"), "time", required=True, default="10:00"),
    FieldSpec("end_time", L("Ends at"), "time", required=True, default="18:00"),
    FieldSpec("services", L("Services"), "list", help=L("Service names, one per line; empty = everything.")),
    FieldSpec("notes", L("Notes for the agent"), "textarea", placeholder="Colour specialist."),
    FieldSpec(
        "calendar_ics",
        L("Busy calendar (iCal link)"),
        placeholder="https://calendar.google.com/calendar/ical/…/basic.ics",
        help=L("Optional. Busy times are never offered."),
    ),
)


def summarize(record: Any, names: dict[str, str]) -> str:
    details = getattr(record, "details", None) or {}
    service = details.get("service", "") if isinstance(details, dict) else ""
    person = names.get(str(getattr(record, "catalog_item_id", "") or ""), "") or (details.get("staff", "") if isinstance(details, dict) else "")
    return " · ".join(part for part in (str(service or "") or str(getattr(record, "items_summary", "") or ""), str(person or "")) if part)


#: Keyword arguments of the salon :class:`~app.verticals.base.Vertical` (everything but its flows).
SALON_SPEC: dict[str, Any] = dict(
    key="salon",
    label=L("Salon & spa"),
    description=L(
        "Answers the salon's phone: books services with the right stylist or therapist (or anyone free), fits each service into their hours, moves or cancels bookings, and can take a deposit.",
    ),
    record_kind=KIND_BOOKING,
    record_label=L("Booking"),
    record_label_plural=L("Bookings"),
    record_fields=(
        FieldSpec("customer_name", L("Client name"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("service", L("Service"), required=True, list_column=True),
        # The booked person is the record's catalog item: capacity is per person.
        FieldSpec("catalog_item_id", L("With"), "catalog", list_column=True, catalog_kind=KIND_STAFF),
        FieldSpec("scheduled_at", L("Date & time"), "datetime", required=True, list_column=True),
        FieldSpec("duration_minutes", L("Duration (minutes)"), "number"),
        FieldSpec("total_amount", L("Price"), "money"),
        FieldSpec("notes", L("Notes"), "textarea"),
    ),
    catalog_kind=KIND_SERVICE,
    catalog_label=L("Service"),
    catalog_label_plural=L("Services"),
    catalog_fields=SERVICE_FIELDS,
    catalog_kinds=(
        CatalogKind(KIND_SERVICE, L("Service"), L("Services"), SERVICE_FIELDS, ref_prefix="S"),
        CatalogKind(KIND_STAFF, L("Staff member"), L("Staff"), STAFF_FIELDS, ref_prefix="T"),
    ),
    config_fields=(
        FieldSpec("booking_horizon_days", L("Book how many days ahead"), "number", default=30),
        FieldSpec("lead_minutes", L("Earliest booking (minutes from now)"), "number", default=60),
        FieldSpec("slot_minutes", L("Start times every (minutes)"), "number", default=15),
        FieldSpec("open_days", L("Open days (no staff list)"), "days", default=CONFIG_DEFAULTS["open_days"]),
        FieldSpec("open_time", L("Opens at"), "time", default="10:00"),
        FieldSpec("close_time", L("Closes at"), "time", default="19:00"),
    ),
    config_defaults=dict(CONFIG_DEFAULTS),
    status_labels={
        "pending": L("Awaiting deposit"),
        "confirmed": L("Booked"),
        "cancelled": L("Cancelled"),
        "needs_review": L("Call back"),
    },
    scheduled=True,
    summarize=summarize,
)

__all__ = ["SALON_SPEC", "SERVICE_FIELDS", "STAFF_FIELDS", "summarize"]
