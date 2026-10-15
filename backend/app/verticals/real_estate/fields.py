"""The real-estate vertical's portal vocabulary and forms: leads, listings (catalog), settings."""

from __future__ import annotations

from typing import Any

from app.verticals.base import FieldSpec, L
from app.verticals.real_estate.catalog import CONFIG_DEFAULTS, KIND_LEAD, KIND_PROPERTY, TYPE_WORDS

_TYPES = tuple((key, L(words["en"].capitalize(), words["bn"])) for key, words in TYPE_WORDS.items())


def summarize(record: Any, names: dict[str, str]) -> str:
    details = getattr(record, "details", None) or {}
    score = details.get("lead_score") if isinstance(details, dict) else ""
    base = str(getattr(record, "items_summary", "") or "")
    listing = names.get(str(getattr(record, "catalog_item_id", "") or ""), "")
    return " · ".join(part for part in (base, listing, str(score or "").upper()) if part)


#: Keyword arguments of the real-estate :class:`~app.verticals.base.Vertical` (everything but its flows).
REAL_ESTATE_SPEC: dict[str, Any] = dict(
    key="real_estate",
    label=L("Real estate / land broker", "রিয়েল এস্টেট / জমির ব্রোকার"),
    description=L(
        "Answers buyers, renters and sellers: qualifies them, presents matching listings, books site visits and scores every lead; follows up leads by phone.",
        "ক্রেতা, ভাড়াটিয়া ও বিক্রেতার ফোন ধরে: চাহিদা জেনে মিলে যাওয়া প্রপার্টি বলে, সাইট ভিজিট বুক করে, প্রতিটি লিড স্কোর করে; লিড ফলো-আপ কলও করে।",
    ),
    record_kind=KIND_LEAD,
    record_label=L("Lead", "লিড"),
    record_label_plural=L("Leads", "লিড"),
    record_fields=(
        FieldSpec("customer_name", L("Name", "নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec(
            "intent",
            L("Looking to", "উদ্দেশ্য"),
            "select",
            options=(("buy", L("Buy", "কেনা")), ("rent", L("Rent", "ভাড়া")), ("sell", L("Sell", "বিক্রি"))),
            default="buy",
        ),
        FieldSpec("property_type", L("Property type", "ধরন"), "select", options=_TYPES),
        FieldSpec("location", L("Area", "এলাকা"), placeholder="Riverside / Downtown"),
        FieldSpec("budget", L("Budget", "বাজেট"), placeholder="400k–450k"),
        FieldSpec("catalog_item_id", L("Listing of interest", "আগ্রহের প্রপার্টি"), "catalog"),
        FieldSpec("scheduled_at", L("Site visit", "সাইট ভিজিট"), "datetime", list_column=True),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    catalog_kind=KIND_PROPERTY,
    catalog_label=L("Listing", "প্রপার্টি"),
    catalog_label_plural=L("Listings", "প্রপার্টি তালিকা"),
    catalog_fields=(
        FieldSpec("name", L("Title", "শিরোনাম"), required=True, placeholder="3-bed apartment, Riverside Towers"),
        FieldSpec("listing_type", L("For", "উদ্দেশ্য"), "select", required=True, options=(("sale", L("Sale", "বিক্রি")), ("rent", L("Rent", "ভাড়া"))), default="sale"),
        FieldSpec("property_type", L("Type", "ধরন"), "select", required=True, options=_TYPES, default="land"),
        FieldSpec("location", L("Area", "এলাকা"), required=True, placeholder="Riverside"),
        FieldSpec("size", L("Size", "আকার"), placeholder="1,450 sq ft / 0.5 acre / 5 katha"),
        FieldSpec("price", L("Price (monthly for rent)", "দাম (ভাড়া হলে মাসিক)"), "money"),
        FieldSpec("price_note", L("Price note", "দামের নোট"), placeholder="negotiable / per katha"),
        FieldSpec("bedrooms", L("Bedrooms", "বেডরুম"), "number"),
        FieldSpec("features", L("Highlights", "বৈশিষ্ট্য"), "textarea", placeholder="South facing, parking, ready to move in"),
    ),
    config_fields=(
        FieldSpec("visit_days", L("Viewing days", "সাইট ভিজিটের দিন"), "days", default=["mon", "tue", "wed", "thu", "fri", "sat"]),
        FieldSpec("visit_start", L("Visits from", "ভিজিট শুরু"), "time", default="10:00"),
        FieldSpec("visit_end", L("Visits until", "ভিজিট শেষ"), "time", default="18:00"),
        FieldSpec("visit_slot_minutes", L("Minutes per visit", "প্রতি ভিজিট (মিনিট)"), "number", default=60),
        FieldSpec("visit_capacity", L("Visits at the same time", "একসাথে কয়টি ভিজিট"), "number", default=1),
        FieldSpec("booking_horizon_days", L("Book how many days ahead", "কত দিন আগে পর্যন্ত বুকিং"), "number", default=14),
    ),
    config_defaults=dict(CONFIG_DEFAULTS),
    status_labels={
        "pending": L("New", "নতুন"),
        "confirmed": L("Visit booked", "ভিজিট বুকড"),
        "cancelled": L("Not interested", "আগ্রহী নন"),
        "needs_review": L("Follow up", "ফলো-আপ"),
    },
    outbound_label=L("Follow-up call", "ফলো-আপ কল"),
    scheduled=True,
    summarize=summarize,
)

__all__ = ["REAL_ESTATE_SPEC", "summarize"]
