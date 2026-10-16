"""The restaurant vertical's portal vocabulary and forms: records, the menu (catalog), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.restaurant.config import DEFAULTS, KIND_MENU_ITEM, KIND_ORDER

PROGRESS_OPTIONS = (
    ("received", L("Received")),
    ("preparing", L("Preparing")),
    ("ready", L("Ready for pickup")),
    ("out_for_delivery", L("Out for delivery")),
    ("completed", L("Completed")),
)


def summarize(record: Any, names: dict[str, str]) -> str:
    details = getattr(record, "details", None)
    details = details if isinstance(details, dict) else {}
    summary = str(getattr(record, "items_summary", "") or "")
    tag = details.get("fulfillment") or ("table" if details.get("type") == "reservation" else "")
    return " · ".join(part for part in (summary, str(tag or "")) if part)


#: Keyword arguments of the restaurant :class:`~app.verticals.base.Vertical` (everything but its flows).
RESTAURANT_SPEC: dict[str, Any] = dict(
    key="restaurant",
    label=L("Restaurant"),
    description=L(
        "Takes pickup and delivery orders from your menu, books tables, answers menu questions and order-status calls.",
    ),
    record_kind=KIND_ORDER,
    record_label=L("Order"),
    record_label_plural=L("Orders"),
    record_fields=(
        FieldSpec("customer_name", L("Name"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("items_summary", L("Items"), "textarea", list_column=True),
        FieldSpec("total_amount", L("Total"), "money", list_column=True),
        FieldSpec("scheduled_at", L("Ready / table time"), "datetime", list_column=True),
        FieldSpec("fulfillment", L("Pickup or delivery"), "select", options=(("pickup", L("Pickup")), ("delivery", L("Delivery")))),
        FieldSpec("address", L("Delivery address"), "textarea"),
        FieldSpec("progress", L("Kitchen status"), "select", options=PROGRESS_OPTIONS),
        FieldSpec("party_size", L("Guests (table)"), "number"),
        FieldSpec("notes", L("Notes"), "textarea"),
    ),
    catalog_kind=KIND_MENU_ITEM,
    catalog_label=L("Menu item"),
    catalog_label_plural=L("Menu"),
    catalog_fields=(
        FieldSpec("name", L("Name"), required=True, placeholder="Pepperoni Pizza"),
        FieldSpec("category", L("Category"), placeholder="Pizza"),
        FieldSpec("price", L("Price"), "money", required=True),
        FieldSpec("description", L("Description"), "textarea"),
        FieldSpec(
            "modifiers",
            L("Options"),
            "textarea",
            placeholder="Size*: Small | Medium +2 | Large +4; Extras+: Cheese +1 | Bacon +2",
            help=L("* = must choose one, + = several allowed."),
        ),
        FieldSpec("allergens", L("Allergens"), "list", placeholder="gluten, dairy"),
        FieldSpec("available", L("Available"), "bool", default=True),
        FieldSpec("aliases", L("Also called"), "list", placeholder="pepperoni, pep pizza"),
    ),
    config_fields=(
        FieldSpec("open_days", L("Open days"), "days", default=DEFAULTS["open_days"]),
        FieldSpec("open_time", L("Opens"), "time", default=DEFAULTS["open_time"]),
        FieldSpec("close_time", L("Closes"), "time", default=DEFAULTS["close_time"]),
        FieldSpec("delivery", L("We deliver"), "bool", default=True),
        FieldSpec("delivery_fee", L("Delivery fee"), "money", default=0),
        FieldSpec("free_delivery_over", L("Free delivery over"), "money", default=0, help=L("0 = never free")),
        FieldSpec("minimum_order", L("Delivery minimum"), "money", default=0),
        FieldSpec("tax_rate", L("Tax %"), "number", default=0),
        FieldSpec("prep_minutes", L("Pickup ready in (minutes)"), "number", default=DEFAULTS["prep_minutes"]),
        FieldSpec("delivery_minutes", L("Delivery takes (minutes)"), "number", default=DEFAULTS["delivery_minutes"]),
        FieldSpec("max_party_size", L("Largest table by phone"), "number", default=DEFAULTS["max_party_size"]),
        FieldSpec("covers_per_slot", L("Guests per time slot"), "number", default=DEFAULTS["covers_per_slot"], help=L("0 = no limit")),
        FieldSpec("slot_minutes", L("Reservation slot (minutes)"), "number", default=DEFAULTS["slot_minutes"]),
        FieldSpec("booking_horizon_days", L("Book how many days ahead"), "number", default=DEFAULTS["booking_horizon_days"]),
    ),
    config_defaults=dict(DEFAULTS),
    status_labels={
        "pending": L("New"),
        "confirmed": L("Confirmed"),
        "cancelled": L("Cancelled"),
        "needs_review": L("Needs review"),
    },
    scheduled=True,
    summarize=summarize,
)

__all__ = ["PROGRESS_OPTIONS", "RESTAURANT_SPEC", "summarize"]
