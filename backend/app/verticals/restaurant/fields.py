"""The restaurant vertical's portal vocabulary and forms: records, the menu (catalog), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.restaurant.config import DEFAULTS, KIND_MENU_ITEM, KIND_ORDER

PROGRESS_OPTIONS = (
    ("received", L("Received", "গৃহীত")),
    ("preparing", L("Preparing", "তৈরি হচ্ছে")),
    ("ready", L("Ready for pickup", "পিকআপের জন্য রেডি")),
    ("out_for_delivery", L("Out for delivery", "ডেলিভারিতে")),
    ("completed", L("Completed", "সম্পন্ন")),
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
    label=L("Restaurant", "রেস্টুরেন্ট"),
    description=L(
        "Takes pickup and delivery orders from your menu, books tables, answers menu questions and order-status calls.",
        "মেনু থেকে পিকআপ ও ডেলিভারি অর্ডার নেয়, টেবিল বুক করে, মেনু ও অর্ডারের অবস্থা নিয়ে প্রশ্নের উত্তর দেয়।",
    ),
    record_kind=KIND_ORDER,
    record_label=L("Order", "অর্ডার"),
    record_label_plural=L("Orders", "অর্ডার"),
    record_fields=(
        FieldSpec("customer_name", L("Name", "নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("items_summary", L("Items", "আইটেম"), "textarea", list_column=True),
        FieldSpec("total_amount", L("Total", "মোট"), "money", list_column=True),
        FieldSpec("scheduled_at", L("Ready / table time", "রেডি / টেবিলের সময়"), "datetime", list_column=True),
        FieldSpec("fulfillment", L("Pickup or delivery", "পিকআপ না ডেলিভারি"), "select", options=(("pickup", L("Pickup", "পিকআপ")), ("delivery", L("Delivery", "ডেলিভারি")))),
        FieldSpec("address", L("Delivery address", "ডেলিভারির ঠিকানা"), "textarea"),
        FieldSpec("progress", L("Kitchen status", "কিচেনের অবস্থা"), "select", options=PROGRESS_OPTIONS),
        FieldSpec("party_size", L("Guests (table)", "অতিথি (টেবিল)"), "number"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_MENU_ITEM,
    catalog_label=L("Menu item", "মেনু আইটেম"),
    catalog_label_plural=L("Menu", "মেনু"),
    catalog_fields=(
        FieldSpec("name", L("Name", "নাম"), required=True, placeholder="Pepperoni Pizza"),
        FieldSpec("category", L("Category", "ক্যাটাগরি"), placeholder="Pizza"),
        FieldSpec("price", L("Price", "দাম"), "money", required=True),
        FieldSpec("description", L("Description", "বিবরণ"), "textarea"),
        FieldSpec(
            "modifiers",
            L("Options", "অপশন"),
            "textarea",
            placeholder="Size*: Small | Medium +2 | Large +4; Extras+: Cheese +1 | Bacon +2",
            help=L("* = must choose one, + = several allowed.", "* = একটি বাছাই বাধ্যতামূলক, + = একাধিক।"),
        ),
        FieldSpec("allergens", L("Allergens", "অ্যালার্জেন"), "list", placeholder="gluten, dairy"),
        FieldSpec("available", L("Available", "পাওয়া যাচ্ছে"), "bool", default=True),
        FieldSpec("aliases", L("Also called", "অন্য নাম"), "list", placeholder="pepperoni, pep pizza"),
    ),
    config_fields=(
        FieldSpec("open_days", L("Open days", "খোলার দিন"), "days", default=DEFAULTS["open_days"]),
        FieldSpec("open_time", L("Opens", "খোলে"), "time", default=DEFAULTS["open_time"]),
        FieldSpec("close_time", L("Closes", "বন্ধ হয়"), "time", default=DEFAULTS["close_time"]),
        FieldSpec("delivery", L("We deliver", "ডেলিভারি দিই"), "bool", default=True),
        FieldSpec("delivery_fee", L("Delivery fee", "ডেলিভারি চার্জ"), "money", default=0),
        FieldSpec("free_delivery_over", L("Free delivery over", "এর বেশি হলে ফ্রি ডেলিভারি"), "money", default=0, help=L("0 = never free", "০ = কখনো ফ্রি নয়")),
        FieldSpec("minimum_order", L("Delivery minimum", "ডেলিভারির সর্বনিম্ন অর্ডার"), "money", default=0),
        FieldSpec("tax_rate", L("Tax %", "ট্যাক্স %"), "number", default=0),
        FieldSpec("prep_minutes", L("Pickup ready in (minutes)", "পিকআপ রেডি (মিনিট)"), "number", default=DEFAULTS["prep_minutes"]),
        FieldSpec("delivery_minutes", L("Delivery takes (minutes)", "ডেলিভারি সময় (মিনিট)"), "number", default=DEFAULTS["delivery_minutes"]),
        FieldSpec("max_party_size", L("Largest table by phone", "ফোনে সর্বোচ্চ অতিথি"), "number", default=DEFAULTS["max_party_size"]),
        FieldSpec("covers_per_slot", L("Guests per time slot", "প্রতি সময়ে সর্বোচ্চ অতিথি"), "number", default=DEFAULTS["covers_per_slot"], help=L("0 = no limit", "০ = সীমা নেই")),
        FieldSpec("slot_minutes", L("Reservation slot (minutes)", "রিজার্ভেশন স্লট (মিনিট)"), "number", default=DEFAULTS["slot_minutes"]),
        FieldSpec("booking_horizon_days", L("Book how many days ahead", "কত দিন আগে পর্যন্ত বুকিং"), "number", default=DEFAULTS["booking_horizon_days"]),
    ),
    config_defaults=dict(DEFAULTS),
    status_labels={
        "pending": L("New", "নতুন"),
        "confirmed": L("Confirmed", "কনফার্মড"),
        "cancelled": L("Cancelled", "বাতিল"),
        "needs_review": L("Needs review", "রিভিউ দরকার"),
    },
    scheduled=True,
    summarize=summarize,
)

__all__ = ["PROGRESS_OPTIONS", "RESTAURANT_SPEC", "summarize"]
