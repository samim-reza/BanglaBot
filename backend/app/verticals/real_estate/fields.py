"""The real-estate vertical's portal vocabulary and forms: leads, listings (catalog), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.real_estate.catalog import CONFIG_DEFAULTS, KIND_LEAD, KIND_PROPERTY, TYPE_WORDS

_TYPES = tuple((key, L(words["en"].capitalize())) for key, words in TYPE_WORDS.items())


def summarize(record: Any, names: dict[str, str]) -> str:
    details = getattr(record, "details", None) or {}
    score = details.get("lead_score") if isinstance(details, dict) else ""
    base = str(getattr(record, "items_summary", "") or "")
    listing = names.get(str(getattr(record, "catalog_item_id", "") or ""), "")
    return " · ".join(part for part in (base, listing, str(score or "").upper()) if part)


#: Keyword arguments of the real-estate :class:`~app.verticals.base.Vertical` (everything but its flows).
REAL_ESTATE_SPEC: dict[str, Any] = dict(
    key="real_estate",
    label=L("Real estate"),
    description=L(
        "Answers buyers, renters and sellers: qualifies them, presents matching listings, books site visits and scores every lead; follows up leads by phone.",
    ),
    record_kind=KIND_LEAD,
    record_label=L("Lead"),
    record_label_plural=L("Leads"),
    record_fields=(
        FieldSpec("customer_name", L("Name"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec(
            "intent",
            L("Looking to"),
            "select",
            options=(("buy", L("Buy")), ("rent", L("Rent")), ("sell", L("Sell"))),
            default="buy",
        ),
        FieldSpec("property_type", L("Property type"), "select", options=_TYPES),
        FieldSpec("location", L("Area"), placeholder="Riverside / Downtown"),
        FieldSpec("budget", L("Budget"), placeholder="400k–450k"),
        FieldSpec("catalog_item_id", L("Listing of interest"), "catalog"),
        FieldSpec("scheduled_at", L("Site visit"), "datetime", list_column=True),
        FieldSpec("notes", L("Notes"), "textarea"),
    ),
    catalog_kind=KIND_PROPERTY,
    catalog_label=L("Listing"),
    catalog_label_plural=L("Listings"),
    catalog_fields=(
        FieldSpec("name", L("Title"), required=True, placeholder="3-bed apartment, Riverside Towers"),
        FieldSpec("listing_type", L("For"), "select", required=True, options=(("sale", L("Sale")), ("rent", L("Rent"))), default="sale"),
        FieldSpec("property_type", L("Type"), "select", required=True, options=_TYPES, default="land"),
        FieldSpec("location", L("Area"), required=True, placeholder="Riverside"),
        FieldSpec("size", L("Size"), placeholder="1,450 sq ft / 0.5 acre"),
        FieldSpec("price", L("Price (monthly for rent)"), "money"),
        FieldSpec("price_note", L("Price note"), placeholder="negotiable / per sq ft"),
        FieldSpec("bedrooms", L("Bedrooms"), "number"),
        FieldSpec("features", L("Highlights"), "textarea", placeholder="South facing, parking, ready to move in"),
    ),
    config_fields=(
        FieldSpec("visit_days", L("Viewing days"), "days", default=["mon", "tue", "wed", "thu", "fri", "sat"]),
        FieldSpec("visit_start", L("Visits from"), "time", default="10:00"),
        FieldSpec("visit_end", L("Visits until"), "time", default="18:00"),
        FieldSpec("visit_slot_minutes", L("Minutes per visit"), "number", default=60),
        FieldSpec("visit_capacity", L("Visits at the same time"), "number", default=1),
        FieldSpec("booking_horizon_days", L("Book how many days ahead"), "number", default=14),
    ),
    config_defaults=dict(CONFIG_DEFAULTS),
    status_labels={
        "pending": L("New"),
        "confirmed": L("Visit booked"),
        "cancelled": L("Not interested"),
        "needs_review": L("Follow up"),
    },
    outbound_label=L("Follow-up call"),
    scheduled=True,
    summarize=summarize,
)

__all__ = ["REAL_ESTATE_SPEC", "summarize"]
