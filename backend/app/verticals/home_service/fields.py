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
    label=L("Home services"),
    description=L(
        "Answers the service line: takes the job (service, problem, address), checks the service area, books an arrival window with the visit charge, and confirms visits by phone.",
    ),
    record_kind=KIND_BOOKING,
    record_label=L("Booking"),
    record_label_plural=L("Bookings"),
    record_fields=(
        FieldSpec("customer_name", L("Customer name"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("catalog_item_id", L("Service"), "catalog", required=True, list_column=True),
        FieldSpec("problem", L("Problem"), "textarea"),
        FieldSpec("address", L("Address"), "textarea", required=True),
        FieldSpec("scheduled_at", L("Visit (window start)"), "datetime", required=True, list_column=True),
        FieldSpec(
            "time_window",
            L("Arrival window"),
            "select",
            options=(("morning", L("Morning")), ("afternoon", L("Afternoon")), ("evening", L("Evening"))),
        ),
        FieldSpec("total_amount", L("Visit charge"), "money"),
        FieldSpec("notes", L("Notes"), "textarea"),
    ),
    catalog_kind=KIND_SERVICE,
    catalog_label=L("Service"),
    catalog_label_plural=L("Services"),
    catalog_fields=(
        FieldSpec("name", L("Service name"), required=True, placeholder="AC servicing"),
        FieldSpec("category", L("Category"), placeholder="AC / Plumbing / Electrical"),
        FieldSpec("visit_charge", L("Visit / call-out charge"), "money", required=True),
        FieldSpec("price_from", L("Usual price from"), "money"),
        FieldSpec("price_to", L("Usual price up to"), "money"),
        FieldSpec("duration", L("Typical duration"), placeholder="1–2 hours"),
        FieldSpec("notes", L("Notes for the agent"), "textarea", placeholder="Gas refill priced separately."),
    ),
    config_fields=(
        FieldSpec("service_areas", L("Service areas"), "list", help=L("One area per line; empty = anywhere")),
        FieldSpec("working_days", L("Working days"), "days", default=["mon", "tue", "wed", "thu", "fri", "sat"]),
        FieldSpec("teams", L("Teams per time window"), "number", default=3),
        FieldSpec("booking_horizon_days", L("Book how many days ahead"), "number", default=7),
    ),
    config_defaults=dict(CONFIG_DEFAULTS),
    status_labels={
        "pending": L("Requested"),
        "confirmed": L("Booked"),
        "cancelled": L("Cancelled"),
        "needs_review": L("Call back"),
    },
    outbound_label=L("Confirmation call"),
    scheduled=True,
    summarize=summarize,
)

__all__ = ["HOME_SERVICE_SPEC", "summarize"]
