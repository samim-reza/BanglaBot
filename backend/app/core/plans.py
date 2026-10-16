"""Tiers: the one base product an account buys. Extras come from add-ons (``app.core.addons``).

A tier is one product with limits: the **voice agent** (Starter / Growth / Pro /
Enterprise) or the **chat agent** (website chat only), plus the free trial.
Everything else — more minutes, a website chatbot next to the voice agent,
WhatsApp, Messenger, Instagram, more texts — is an add-on on top. Prices are
list prices in USD; the rationale is in docs/pricing.md.

The catalog is data-driven: the admin edits tiers in the console (stored in
``platform_settings["plans.catalog"]`` by ``app.services.catalog_plans``) and
the values below are the defaults until then. ``PLANS`` / ``get_plan`` always
read the installed catalog, so callers never notice where it came from.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any

#: Channels an account can talk to customers on.
CHANNEL_VOICE = "voice"
CHANNEL_WEB_CHAT = "web_chat"
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_MESSENGER = "messenger"
CHANNEL_INSTAGRAM = "instagram"
ALL_CHANNELS = (CHANNEL_VOICE, CHANNEL_WEB_CHAT, CHANNEL_WHATSAPP, CHANNEL_MESSENGER, CHANNEL_INSTAGRAM)
CHANNEL_LABELS = {
    CHANNEL_VOICE: "Phone calls",
    CHANNEL_WEB_CHAT: "Website chat",
    CHANNEL_WHATSAPP: "WhatsApp",
    CHANNEL_MESSENGER: "Messenger",
    CHANNEL_INSTAGRAM: "Instagram DM",
}

#: Features a tier can include (or an add-on can unlock).
FEATURE_GOOGLE_CALENDAR = "google_calendar"
FEATURE_RECORDING_RETENTION = "recording_retention"
ALL_FEATURES = (FEATURE_GOOGLE_CALENDAR, FEATURE_RECORDING_RETENTION)

#: Capabilities a tier's limits switch on; an add-on can switch them on too (as a feature key).
FEATURE_PAYMENTS = "payments"
FEATURE_CUSTOM_FIELDS = "custom_fields"
FEATURE_API_WEBHOOKS = "api_webhooks"
FEATURE_FULL_FLOW_EDITING = "flow_editing_full"
CAPABILITY_FEATURES = (FEATURE_PAYMENTS, FEATURE_CUSTOM_FIELDS, FEATURE_API_WEBHOOKS, FEATURE_FULL_FLOW_EDITING)

#: How much of the call flow the owner may edit: the lines the agent says, or the whole flow.
FLOW_LINES = "lines"
FLOW_FULL = "full"
FLOW_EDITING_LEVELS = (FLOW_LINES, FLOW_FULL)

PRODUCT_VOICE = "voice"
PRODUCT_CHAT = "chat"
PRODUCTS = (PRODUCT_VOICE, PRODUCT_CHAT)

#: Yearly price when a tier sets none: "2 months free".
ANNUAL_MONTHS = 10


@dataclass(frozen=True)
class TierLimits:
    #: Calls (in + out) live at once; 0 = no phone calls.
    max_concurrent_calls: int = 1
    flow_editing: str = FLOW_LINES
    #: Collect payments on calls / chats (payment links).
    payments: bool = False
    #: Extra fields on bookings / records.
    custom_fields: bool = False
    #: Signed webhooks + API access.
    api_webhooks: bool = False

    @classmethod
    def from_json(cls, data: Any, base: TierLimits | None = None) -> TierLimits:
        start = base or cls()
        if not isinstance(data, dict):
            return start
        known = {item.name for item in fields(cls)}
        return replace(start, **{key: value for key, value in data.items() if key in known})


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
    #: Marketing bullets for the pricing page.
    features: tuple[str, ...] = field(default_factory=tuple)
    #: Shown on the website and offered at signup ("visible" in the admin editor).
    public: bool = True
    highlight: bool = False
    #: SMS confirmations + reminders included per month.
    included_sms: int = 0
    #: Channels the tier itself includes; the others are add-ons.
    channels: tuple[str, ...] = (CHANNEL_VOICE,)
    #: Feature keys the tier includes (see ``ALL_FEATURES``).
    includes: tuple[str, ...] = ()
    #: "voice" or "chat": which product this tier is.
    product: str = PRODUCT_VOICE
    #: Yearly price; 0 = ``ANNUAL_MONTHS`` × the monthly price.
    price_year: float = 0.0
    limits: TierLimits = field(default_factory=TierLimits)
    #: Verticals this tier is offered for; empty = all.
    verticals: tuple[str, ...] = ()
    sort: int = 0
    #: Can be bought online (Enterprise is "talk to sales").
    checkout: bool = True
    #: Free tier with a fixed length (the trial); 0 = a normal billing period.
    trial_days: int = 0

    @property
    def visible(self) -> bool:
        return self.public

    def yearly_price(self) -> float:
        return float(self.price_year) if self.price_year else float(self.price_month) * ANNUAL_MONTHS

    def offered_for(self, vertical: str | None) -> bool:
        return not vertical or not self.verticals or vertical in self.verticals

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("features", "channels", "includes", "verticals"):
            data[key] = list(getattr(self, key))
        data["visible"] = self.public
        data["price_year"] = self.yearly_price()
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any], base: Plan | None = None) -> Plan:
        """A tier from stored / edited JSON; missing fields come from ``base`` (or the field defaults)."""
        values: dict[str, Any] = asdict(base) if base else {}
        values.pop("limits", None)
        known = {item.name for item in fields(cls)}
        for key, value in data.items():
            if key in known and key != "limits":
                values[key] = value
        if "visible" in data and "public" not in data:
            values["public"] = bool(data["visible"])
        for key in ("features", "channels", "includes", "verticals"):
            if key in values:
                values[key] = tuple(values[key] or ())
        # A stored tier may still list a retired feature (the old extra-language one).
        values["includes"] = tuple(key for key in values.get("includes", ()) if key in ALL_FEATURES)
        limits = TierLimits.from_json(data.get("limits"), base.limits if base else None)
        return cls(**values, limits=limits)


def _limits(calls: int, flow: str = FLOW_LINES, *, payments: bool = False, custom: bool = False, webhooks: bool = False) -> TierLimits:
    return TierLimits(max_concurrent_calls=calls, flow_editing=flow, payments=payments, custom_fields=custom, api_webhooks=webhooks)


#: The catalog until the admin edits it (and the base for fields a stored tier lacks).
DEFAULT_PLANS: dict[str, Plan] = {
    plan.key: plan
    for plan in (
        Plan(
            "trial", "Free trial", 0, 50, 0.0, 100, 1, "14 days to try everything.",
            ("Voice + every chat channel", "50 call minutes", "50 texts"),
            public=False, included_sms=50,
            channels=(CHANNEL_VOICE, CHANNEL_WEB_CHAT, CHANNEL_WHATSAPP, CHANNEL_MESSENGER),
            includes=ALL_FEATURES, limits=_limits(1, custom=True), sort=0, trial_days=14,
        ),
        Plan(
            "chat", "Chat agent", 29, 0, 0.0, 1000, 0, "A chatbot for your website.",
            ("Website chatbot", "1,000 chats / month", "100 texts / month", "Calendar feed"),
            included_sms=100, channels=(CHANNEL_WEB_CHAT,), product=PRODUCT_CHAT, limits=_limits(0), sort=10,
        ),
        Plan(
            "starter", "Starter", 49, 150, 0.30, 0, 1, "One number, never miss a call.",
            ("1 phone number", "150 call minutes / month", "100 texts / month", "Booking + recordings", "Calendar feed"),
            included_sms=100, limits=_limits(2), sort=20,
        ),
        Plan(
            "growth", "Growth", 149, 600, 0.22, 0, 2, "For busy front desks.",
            ("2 phone numbers", "600 call minutes / month", "500 texts / month", "Reminder calls",
             "Two-way Google Calendar", "Webhooks + live transfer"),
            highlight=True, included_sms=500, includes=(FEATURE_GOOGLE_CALENDAR,),
            limits=_limits(4, FLOW_FULL, payments=True, custom=True, webhooks=True), sort=30,
        ),
        Plan(
            "pro", "Pro", 349, 1800, 0.16, 0, 3, "For multi-location teams.",
            ("3 phone numbers", "1,800 call minutes / month", "2,000 texts / month", "Bulk + scheduled campaigns",
             "12-month recordings", "Priority support"),
            included_sms=2000, includes=(FEATURE_GOOGLE_CALENDAR, FEATURE_RECORDING_RETENTION),
            limits=_limits(8, FLOW_FULL, payments=True, custom=True, webhooks=True), sort=40,
        ),
        Plan(
            "enterprise", "Enterprise", 999, 0, 0.10, 0, 0, "Custom volume and integrations.",
            ("Every channel", "Volume minutes from $0.10", "Custom integrations & SSO", "Dedicated success manager"),
            channels=ALL_CHANNELS, includes=ALL_FEATURES,
            limits=_limits(20, FLOW_FULL, payments=True, custom=True, webhooks=True), sort=50, checkout=False,
        ),
    )
}

DEFAULT_PLAN = "trial"
#: Tiers with no monthly limits.
UNLIMITED_PLANS = frozenset({"enterprise"})

_installed: dict[str, Plan] = dict(DEFAULT_PLANS)


class _LivePlans(Mapping[str, Plan]):
    """``PLANS``: a read-only view of the installed catalog (``key in PLANS``, ``PLANS.values()``)."""

    def __getitem__(self, key: str) -> Plan:
        return _installed[key]

    def __iter__(self) -> Iterator[str]:
        return iter(_installed)

    def __len__(self) -> int:
        return len(_installed)

    def __repr__(self) -> str:
        return f"PLANS({list(_installed)!r})"


PLANS: Mapping[str, Plan] = _LivePlans()


def install_plans(plans: Iterable[Plan]) -> None:
    """Make ``plans`` the live catalog (ordered by ``sort``). The trial always exists."""
    global _installed
    ordered = sorted(plans, key=lambda plan: (plan.sort, plan.key))
    catalog = {plan.key: plan for plan in ordered}
    catalog.setdefault(DEFAULT_PLAN, DEFAULT_PLANS[DEFAULT_PLAN])
    _installed = catalog


def reset_plans() -> None:
    install_plans(DEFAULT_PLANS.values())


def get_plan(key: Any) -> Plan:
    return _installed.get(str(key or "").strip().lower()) or _installed.get(DEFAULT_PLAN) or DEFAULT_PLANS[DEFAULT_PLAN]


def is_unlimited(plan: Plan) -> bool:
    return plan.key in UNLIMITED_PLANS


__all__ = [
    "ALL_CHANNELS",
    "ALL_FEATURES",
    "ANNUAL_MONTHS",
    "CAPABILITY_FEATURES",
    "CHANNEL_INSTAGRAM",
    "CHANNEL_LABELS",
    "CHANNEL_MESSENGER",
    "CHANNEL_VOICE",
    "CHANNEL_WEB_CHAT",
    "CHANNEL_WHATSAPP",
    "DEFAULT_PLAN",
    "DEFAULT_PLANS",
    "FEATURE_API_WEBHOOKS",
    "FEATURE_CUSTOM_FIELDS",
    "FEATURE_FULL_FLOW_EDITING",
    "FEATURE_GOOGLE_CALENDAR",
    "FEATURE_PAYMENTS",
    "FEATURE_RECORDING_RETENTION",
    "FLOW_EDITING_LEVELS",
    "FLOW_FULL",
    "FLOW_LINES",
    "PLANS",
    "PRODUCTS",
    "Plan",
    "TierLimits",
    "get_plan",
    "install_plans",
    "is_unlimited",
    "reset_plans",
]
