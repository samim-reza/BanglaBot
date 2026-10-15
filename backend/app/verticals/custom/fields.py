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
    label=L("Custom business", "নিজস্ব ব্যবসা"),
    description=L(
        "Your own setup: books what you offer, asks the questions you choose, and takes messages for your team.",
        "আপনার নিজের মতো: আপনার সেবা বুক করে, আপনার প্রশ্নগুলো করে, আর টিমের জন্য বার্তা নেয়।",
    ),
    record_kind=KIND_BOOKING,
    record_label=L("Booking", "বুকিং"),
    record_label_plural=L("Bookings", "বুকিং"),
    record_fields=(
        FieldSpec("customer_name", L("Name", "নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("catalog_item_id", L("Service", "সেবা"), "catalog", list_column=True),
        FieldSpec("scheduled_at", L("Date & time", "দিন ও সময়"), "datetime", list_column=True),
        FieldSpec("items_summary", L("Summary", "সারসংক্ষেপ"), "textarea"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_RESOURCE,
    catalog_label=L("Service", "সেবা"),
    catalog_label_plural=L("Services", "সেবা"),
    catalog_fields=(
        FieldSpec("name", L("Name", "নাম"), required=True, placeholder="Meeting room / Yoga class / Consultation"),
        FieldSpec("description", L("Description", "বিবরণ"), "textarea"),
        FieldSpec("days", L("Days", "দিন"), "days", required=True),
        FieldSpec("start_time", L("From", "শুরু"), "time", required=True, default="09:00"),
        FieldSpec("end_time", L("To", "শেষ"), "time", required=True, default="17:00"),
        FieldSpec("slot_minutes", L("Minutes per booking", "প্রতি বুকিং (মিনিট)"), "number", default=30),
        FieldSpec("capacity", L("Bookings per time", "একই সময়ে বুকিং"), "number", default=1),
        FieldSpec("price", L("Price", "দাম"), "money"),
    ),
    config_fields=(
        FieldSpec("booking_horizon_days", L("Book how many days ahead", "কত দিন আগে পর্যন্ত বুকিং"), "number", default=14),
        FieldSpec("lead_minutes", L("Earliest booking (minutes from now)", "এখন থেকে অন্তত কত মিনিট পরে"), "number", default=60),
    ),
    config_defaults={"booking_horizon_days": 14, "lead_minutes": 60},
    status_labels={
        "pending": L("New", "নতুন"),
        "confirmed": L("Confirmed", "কনফার্মড"),
        "cancelled": L("Cancelled", "বাতিল"),
        "needs_review": L("Follow up", "ফলো আপ"),
    },
    scheduled=True,
    summarize=summarize,
)

__all__ = ["CUSTOM_SPEC", "summarize"]
