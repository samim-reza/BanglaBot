"""Base plans: what an account buys first. Extras come from add-ons (``app.core.addons``).

A plan is one product with limits: the **voice agent** (Starter / Growth / Pro)
or the **chat agent** (website chat only). Everything else — more minutes, a
website chatbot next to the voice agent, WhatsApp, Messenger, more texts — is an
add-on on top. Prices are list prices in USD; the rationale (cost per minute,
margins, competitors) is in docs/pricing.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

#: Channels an account can talk to customers on.
CHANNEL_VOICE = "voice"
CHANNEL_WEB_CHAT = "web_chat"
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_MESSENGER = "messenger"
ALL_CHANNELS = (CHANNEL_VOICE, CHANNEL_WEB_CHAT, CHANNEL_WHATSAPP, CHANNEL_MESSENGER)

#: Features a plan can include (or an add-on can unlock).
FEATURE_GOOGLE_CALENDAR = "google_calendar"
FEATURE_RECORDING_RETENTION = "recording_retention"
FEATURE_EXTRA_LANGUAGE = "extra_language"
ALL_FEATURES = (FEATURE_GOOGLE_CALENDAR, FEATURE_RECORDING_RETENTION, FEATURE_EXTRA_LANGUAGE)


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
    #: Channels the plan itself includes; the others are add-ons.
    channels: tuple[str, ...] = (CHANNEL_VOICE,)
    #: Feature keys the plan includes (see ``ALL_FEATURES``).
    includes: tuple[str, ...] = ()
    #: "voice" or "chat": which product this plan is.
    product: str = "voice"

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["features"] = list(self.features)
        data["channels"] = list(self.channels)
        data["includes"] = list(self.includes)
        return data


PLANS: dict[str, Plan] = {
    plan.key: plan
    for plan in (
        Plan(
            "trial", "Free trial", 0, 50, 0.0, 100, 1,
            "14 days to try everything.",
            ("Voice + every chat channel", "50 call minutes", "50 texts"),
            public=False,
            included_sms=50,
            channels=ALL_CHANNELS,
            includes=ALL_FEATURES,
        ),
        Plan(
            "chat", "Chat agent", 29, 0, 0.0, 1000, 0,
            "A chatbot for your website.",
            ("Website chatbot", "1,000 chats / month", "100 texts / month", "Calendar feed"),
            included_sms=100,
            channels=(CHANNEL_WEB_CHAT,),
            product="chat",
        ),
        Plan(
            "starter", "Starter", 49, 150, 0.30, 0, 1,
            "One number, never miss a call.",
            ("1 phone number", "150 call minutes / month", "100 texts / month", "Booking + recordings", "Calendar feed"),
            included_sms=100,
        ),
        Plan(
            "growth", "Growth", 149, 600, 0.22, 0, 2,
            "For busy front desks.",
            (
                "2 phone numbers",
                "600 call minutes / month",
                "500 texts / month",
                "Reminder calls",
                "Two-way Google Calendar",
                "Webhooks + live transfer",
            ),
            highlight=True,
            included_sms=500,
            includes=(FEATURE_GOOGLE_CALENDAR,),
        ),
        Plan(
            "pro", "Pro", 349, 1800, 0.16, 0, 3,
            "For multi-location teams.",
            (
                "3 phone numbers",
                "1,800 call minutes / month",
                "2,000 texts / month",
                "Bulk + scheduled campaigns",
                "12-month recordings",
                "Priority support",
            ),
            included_sms=2000,
            includes=(FEATURE_GOOGLE_CALENDAR, FEATURE_RECORDING_RETENTION),
        ),
        Plan(
            "enterprise", "Enterprise", 999, 0, 0.10, 0, 0,
            "Custom volume and integrations.",
            ("Every channel", "Volume minutes from $0.10", "Custom integrations & SSO", "Dedicated success manager"),
            channels=ALL_CHANNELS,
            includes=ALL_FEATURES,
        ),
    )
}

DEFAULT_PLAN = "trial"


def get_plan(key: Any) -> Plan:
    return PLANS.get(str(key or "").strip().lower(), PLANS[DEFAULT_PLAN])


__all__ = [
    "ALL_CHANNELS",
    "ALL_FEATURES",
    "CHANNEL_MESSENGER",
    "CHANNEL_VOICE",
    "CHANNEL_WEB_CHAT",
    "CHANNEL_WHATSAPP",
    "DEFAULT_PLAN",
    "FEATURE_EXTRA_LANGUAGE",
    "FEATURE_GOOGLE_CALENDAR",
    "FEATURE_RECORDING_RETENTION",
    "PLANS",
    "Plan",
    "get_plan",
]
