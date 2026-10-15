"""The home-service vertical's portal vocabulary and forms: bookings, services (catalog), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.home_service.catalog import CONFIG_DEFAULTS, KIND_BOOKING, KIND_SERVICE


def summarize(record: Any, names: dict[str, str]) -> str:
    details = getattr(record, "details", None) or {}
    service = names.get(str(getattr(record, "catalog_item_id", "") or ""), "") or str(getattr(record, "items_summary", "") or "")
    problem = details.get("problem", "") if isinstance(details, dict) else ""
    window = details.get("time_window", "") if isinstance(details, dict) else ""
    return " · ".join(part for part in (service, str(problem or ""), str(window or "")) if part)


#: Keyword arguments of the home-service :class:`~app.verticals.base.Vertical` (everything but its flows).
HOME_SERVICE_SPEC: dict[str, Any] = dict(
    key="home_service",
    label=L("Home services", "হোম সার্ভিস"),
    description=L(
        "Answers the service line: takes the job (service, problem, address), checks the service area, books an arrival window with the visit charge, and confirms visits by phone.",
        "সার্ভিস লাইনের ফোন ধরে: সার্ভিস, সমস্যা ও ঠিকানা নেয়, এলাকা যাচাই করে, ভিজিটিং চার্জসহ টাইম-উইন্ডো বুক করে, আর ভিজিটের আগে কনফার্মেশন কল করে।",
    ),
    record_kind=KIND_BOOKING,
    record_label=L("Booking", "বুকিং"),
    record_label_plural=L("Bookings", "বুকিং"),
    record_fields=(
        FieldSpec("customer_name", L("Customer name", "কাস্টমারের নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("catalog_item_id", L("Service", "সার্ভিস"), "catalog", required=True, list_column=True),
        FieldSpec("problem", L("Problem", "সমস্যা"), "textarea"),
        FieldSpec("address", L("Address", "ঠিকানা"), "textarea", required=True),
        FieldSpec("scheduled_at", L("Visit (window start)", "ভিজিট (শুরুর সময়)"), "datetime", required=True, list_column=True),
        FieldSpec(
            "time_window",
            L("Arrival window", "টাইম-উইন্ডো"),
            "select",
            options=(("morning", L("Morning", "সকাল")), ("afternoon", L("Afternoon", "দুপুর")), ("evening", L("Evening", "বিকেল"))),
        ),
        FieldSpec("total_amount", L("Visit charge", "ভিজিটিং চার্জ"), "money"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_SERVICE,
    catalog_label=L("Service", "সার্ভিস"),
    catalog_label_plural=L("Services", "সার্ভিস"),
    catalog_fields=(
        FieldSpec("name", L("Service name", "সার্ভিসের নাম"), required=True, placeholder="AC servicing"),
        FieldSpec("category", L("Category", "ক্যাটাগরি"), placeholder="AC / Plumbing / Electrical"),
        FieldSpec("visit_charge", L("Visit / call-out charge", "ভিজিটিং চার্জ"), "money", required=True),
        FieldSpec("price_from", L("Usual price from", "সাধারণ খরচ শুরু"), "money"),
        FieldSpec("price_to", L("Usual price up to", "সাধারণ খরচ সর্বোচ্চ"), "money"),
        FieldSpec("duration", L("Typical duration", "সাধারণ সময়"), placeholder="1–2 hours"),
        FieldSpec("notes", L("Notes for the agent", "এজেন্টের জন্য নোট"), "textarea", placeholder="Gas refill priced separately."),
    ),
    config_fields=(
        FieldSpec("service_areas", L("Service areas", "সার্ভিস এলাকা"), "list", help=L("One area per line; empty = anywhere", "প্রতি লাইনে একটি এলাকা; খালি = সব জায়গা")),
        FieldSpec("working_days", L("Working days", "কাজের দিন"), "days", default=["mon", "tue", "wed", "thu", "fri", "sat"]),
        FieldSpec("teams", L("Teams per time window", "প্রতি উইন্ডোতে টিম"), "number", default=3),
        FieldSpec("booking_horizon_days", L("Book how many days ahead", "কত দিন আগে পর্যন্ত বুকিং"), "number", default=7),
    ),
    config_defaults=dict(CONFIG_DEFAULTS),
    status_labels={
        "pending": L("Requested", "অনুরোধ"),
        "confirmed": L("Booked", "বুকড"),
        "cancelled": L("Cancelled", "বাতিল"),
        "needs_review": L("Call back", "কলব্যাক"),
    },
    outbound_label=L("Confirmation call", "কনফার্মেশন কল"),
    scheduled=True,
    summarize=summarize,
)

__all__ = ["HOME_SERVICE_SPEC", "summarize"]
