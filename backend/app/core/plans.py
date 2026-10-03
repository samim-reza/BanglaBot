"""Subscription plans shown on the website and metered in the portal.

Prices are list prices in USD; ``usage_service`` meters voice minutes and
website-chat conversations against ``included_minutes`` / ``included_chats``.
The rationale behind the numbers (cost per minute, margins, competitors) is in
docs/pricing.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_month: float
    included_minutes: int
    overage_per_minute: float
    included_chats: int
    phone_numbers: int
    tagline: str
    features: tuple[str, ...] = field(default_factory=tuple)
    #: Shown on the website (trial / enterprise are assigned by the admin).
    public: bool = True
    highlight: bool = False
    #: SMS confirmations + reminders included per month.
    included_sms: int = 0

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["features"] = list(self.features)
        return data


PLANS: dict[str, Plan] = {
    plan.key: plan
    for plan in (
        Plan(
            "trial", "Free trial", 0, 50, 0.0, 100, 1,
            "14 days · 50 call minutes · every agent unlocked.",
            ("All four business agents", "Browser test console", "Website chat widget"),
            public=False,
            included_sms=50,
        ),
        Plan(
            "starter", "Starter", 49, 150, 0.30, 100, 1,
            "Never miss a call again — for a single practice, shop or crew.",
            (
                "1 phone number",
                "150 call minutes / month (inbound + outbound)",
                "100 website chats / month",
                "Booking, leads and call recordings",
                "Doctor / listing / service catalog",
                "100 SMS confirmations & reminders",
                "Calendar feed (Google, Outlook, Apple)",
                "Email support",
            ),
            included_sms=100,
        ),
        Plan(
            "growth", "Growth", 149, 600, 0.22, 500, 2,
            "For busy front desks: answers, books and calls back.",
            (
                "Everything in Starter",
                "2 phone numbers",
                "600 call minutes / month",
                "500 website chats / month",
                "Reminder & confirmation calls",
                "500 SMS confirmations & reminders",
                "Two-way Google Calendar sync",
                "Webhooks into your systems",
                "Live transfer to your team",
            ),
            highlight=True,
            included_sms=500,
        ),
        Plan(
            "pro", "Pro", 349, 1800, 0.16, 2000, 3,
            "For multi-location clinics, agencies and service fleets.",
            (
                "Everything in Growth",
                "3 phone numbers",
                "1,800 call minutes / month",
                "2,000 website chats / month",
                "Bulk & scheduled outbound campaigns",
                "2,000 SMS confirmations & reminders",
                "Priority support and onboarding",
            ),
            included_sms=2000,
        ),
        Plan(
            "enterprise", "Enterprise", 999, 0, 0.10, 0, 0,
            "Custom volume, locations, SLAs and integrations.",
            ("Volume minutes from $0.10", "Unlimited locations", "Custom integrations & SSO", "Dedicated success manager"),
            public=True,
        ),
    )
}

#: Add-ons sold on top of any plan (USD / month unless stated).
ADDONS: tuple[dict[str, Any], ...] = (
    {"key": "number", "name": "Extra phone number", "price": "$5 / mo", "note": "US & Canada; $10 UK / Australia"},
    {"key": "location", "name": "Extra location or agent", "price": "$49 / mo", "note": "A second clinic, office or brand"},
    {"key": "language", "name": "Extra language", "price": "$19 / mo", "note": "Bangla today; more coming"},
    {"key": "chat", "name": "Chat-only plan", "price": "$29 / mo", "note": "Website chat widget, 500 conversations"},
    {"key": "recording", "name": "Extended recording retention", "price": "$10 / mo", "note": "Keep call recordings for 12 months"},
    {"key": "sms", "name": "Extra texts", "price": "$10 / 500", "note": "SMS beyond your plan's included texts (US & Canada)"},
    {"key": "setup", "name": "Done-for-you setup", "price": "$299 once", "note": "We load your catalog, script and number"},
    {"key": "cod", "name": "COD order confirmation", "price": "$0.20 / answered call", "note": "E-commerce, US / UK / Canada"},
)
DEFAULT_PLAN = "trial"


def get_plan(key: Any) -> Plan:
    return PLANS.get(str(key or "").strip().lower(), PLANS[DEFAULT_PLAN])


__all__ = ["ADDONS", "DEFAULT_PLAN", "PLANS", "Plan", "get_plan"]
