"""The custom engine's portal vocabulary and forms: records, bookable services (catalog), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.custom.catalog import KIND_BOOKING, KIND_RESOURCE


def summarize(record: Any, names: dict[str, str]) -> str:
    item = names.get(str(getattr(record, "catalog_item_id", "") or ""), "")
    return item or str(getattr(record, "items_summary", "") or "")


#: Keyword arguments of the custom :class:`~app.verticals.base.Vertical` (everything but its flows).
CUSTOM_SPEC: dict[str, Any] = dict(
    key="custom",
    label=L("Custom business"),
    description=L(
        "Your own setup: books what you offer, asks the questions you choose, and takes messages for your team.",
    ),
    record_kind=KIND_BOOKING,
    record_label=L("Booking"),
    record_label_plural=L("Bookings"),
    record_fields=(
        FieldSpec("customer_name", L("Name"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("catalog_item_id", L("Service"), "catalog", list_column=True),
        FieldSpec("scheduled_at", L("Date & time"), "datetime", list_column=True),
        FieldSpec("items_summary", L("Summary"), "textarea"),
        FieldSpec("notes", L("Notes"), "textarea"),
    ),
    catalog_kind=KIND_RESOURCE,
    catalog_label=L("Service"),
    catalog_label_plural=L("Services"),
    catalog_fields=(
        FieldSpec("name", L("Name"), required=True, placeholder="Meeting room / Yoga class / Consultation"),
        FieldSpec("description", L("Description"), "textarea"),
        FieldSpec("days", L("Days"), "days", required=True),
        FieldSpec("start_time", L("From"), "time", required=True, default="09:00"),
        FieldSpec("end_time", L("To"), "time", required=True, default="17:00"),
        FieldSpec("slot_minutes", L("Minutes per booking"), "number", default=30),
        FieldSpec("capacity", L("Bookings per time"), "number", default=1),
        FieldSpec("price", L("Price"), "money"),
    ),
    config_fields=(
        FieldSpec("booking_horizon_days", L("Book how many days ahead"), "number", default=14),
        FieldSpec("lead_minutes", L("Earliest booking (minutes from now)"), "number", default=60),
    ),
    config_defaults={"booking_horizon_days": 14, "lead_minutes": 60},
    status_labels={
        "pending": L("New"),
        "confirmed": L("Confirmed"),
        "cancelled": L("Cancelled"),
        "needs_review": L("Follow up"),
    },
    scheduled=True,
    summarize=summarize,
)

__all__ = ["CUSTOM_SPEC", "summarize"]
