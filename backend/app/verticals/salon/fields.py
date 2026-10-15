"""The salon & spa vertical's portal vocabulary and forms: bookings, two catalog kinds (services and
staff), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import CatalogKind, FieldSpec, L
from app.verticals.salon.catalog import CONFIG_DEFAULTS, KIND_BOOKING, KIND_SERVICE, KIND_STAFF

SERVICE_FIELDS = (
    FieldSpec("name", L("Service", "সার্ভিস"), required=True, placeholder="Women's haircut"),
    FieldSpec("category", L("Category", "ক্যাটাগরি"), placeholder="Hair / Nails / Spa"),
    FieldSpec("duration_minutes", L("Duration (minutes)", "সময় (মিনিট)"), "number", required=True, default=60),
    FieldSpec("price", L("Price", "দাম"), "money"),
    FieldSpec("staff", L("Who does it", "কে করেন"), "list", help=L("Staff names, one per line; empty = anyone.", "কর্মীদের নাম, প্রতি লাইনে একজন; খালি = যে কেউ।")),
    FieldSpec("notes", L("Notes for the agent", "এজেন্টের জন্য নোট"), "textarea", placeholder="Includes wash and blow-dry."),
)

STAFF_FIELDS = (
    FieldSpec("name", L("Name", "নাম"), required=True, placeholder="Maya"),
    FieldSpec("days", L("Working days", "কাজের দিন"), "days", required=True),
    FieldSpec("start_time", L("Starts at", "শুরু"), "time", required=True, default="10:00"),
    FieldSpec("end_time", L("Ends at", "শেষ"), "time", required=True, default="18:00"),
    FieldSpec("services", L("Services", "সার্ভিস"), "list", help=L("Service names, one per line; empty = everything.", "সার্ভিসের নাম, প্রতি লাইনে একটি; খালি = সব।")),
    FieldSpec("notes", L("Notes for the agent", "এজেন্টের জন্য নোট"), "textarea", placeholder="Colour specialist."),
    FieldSpec(
        "calendar_ics",
        L("Busy calendar (iCal link)", "ব্যস্ত সময়ের ক্যালেন্ডার (iCal লিংক)"),
        placeholder="https://calendar.google.com/calendar/ical/…/basic.ics",
        help=L("Optional. Busy times are never offered.", "ঐচ্ছিক। ব্যস্ত সময়ে বুকিং দেওয়া হবে না।"),
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
    label=L("Salon & spa", "সেলুন ও স্পা"),
    description=L(
        "Answers the salon's phone: books services with the right stylist or therapist (or anyone free), fits each service into their hours, moves or cancels bookings, and can take a deposit.",
        "সেলুনের ফোন ধরে: পছন্দের স্টাইলিস্ট বা থেরাপিস্টের কাছে (বা যে কেউ খালি) সার্ভিস বুক করে, সময় মিলিয়ে দেয়, বুকিং বদলায় বা বাতিল করে, অগ্রিমও নিতে পারে।",
    ),
    record_kind=KIND_BOOKING,
    record_label=L("Booking", "বুকিং"),
    record_label_plural=L("Bookings", "বুকিং"),
    record_fields=(
        FieldSpec("customer_name", L("Client name", "ক্লায়েন্টের নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("service", L("Service", "সার্ভিস"), required=True, list_column=True),
        # The booked person is the record's catalog item: capacity is per person.
        FieldSpec("catalog_item_id", L("With", "কার কাছে"), "catalog", list_column=True, catalog_kind=KIND_STAFF),
        FieldSpec("scheduled_at", L("Date & time", "দিন ও সময়"), "datetime", required=True, list_column=True),
        FieldSpec("duration_minutes", L("Duration (minutes)", "সময় (মিনিট)"), "number"),
        FieldSpec("total_amount", L("Price", "দাম"), "money"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_SERVICE,
    catalog_label=L("Service", "সার্ভিস"),
    catalog_label_plural=L("Services", "সার্ভিস"),
    catalog_fields=SERVICE_FIELDS,
    catalog_kinds=(
        CatalogKind(KIND_SERVICE, L("Service", "সার্ভিস"), L("Services", "সার্ভিস"), SERVICE_FIELDS, ref_prefix="S"),
        CatalogKind(KIND_STAFF, L("Staff member", "কর্মী"), L("Staff", "কর্মী"), STAFF_FIELDS, ref_prefix="T"),
    ),
    config_fields=(
        FieldSpec("booking_horizon_days", L("Book how many days ahead", "কত দিন আগে পর্যন্ত বুকিং"), "number", default=30),
        FieldSpec("lead_minutes", L("Earliest booking (minutes from now)", "এখন থেকে অন্তত কত মিনিট পরে"), "number", default=60),
        FieldSpec("slot_minutes", L("Start times every (minutes)", "শুরুর সময়ের ব্যবধান (মিনিট)"), "number", default=15),
        FieldSpec("open_days", L("Open days (no staff list)", "খোলার দিন (কর্মী তালিকা না থাকলে)"), "days", default=CONFIG_DEFAULTS["open_days"]),
        FieldSpec("open_time", L("Opens at", "খোলে"), "time", default="10:00"),
        FieldSpec("close_time", L("Closes at", "বন্ধ হয়"), "time", default="19:00"),
    ),
    config_defaults=dict(CONFIG_DEFAULTS),
    status_labels={
        "pending": L("Awaiting deposit", "অগ্রিমের অপেক্ষায়"),
        "confirmed": L("Booked", "বুকড"),
        "cancelled": L("Cancelled", "বাতিল"),
        "needs_review": L("Call back", "কলব্যাক"),
    },
    scheduled=True,
    summarize=summarize,
)

__all__ = ["SALON_SPEC", "SERVICE_FIELDS", "STAFF_FIELDS", "summarize"]
