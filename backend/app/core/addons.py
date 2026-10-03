"""Add-ons: extras an account buys on top of its plan, and what the account may use.

An account's add-ons are stored on ``merchants.addons`` as ``{key: quantity}``
(plus the marker ``"_v": 1``). :func:`entitlements` merges them with the plan:
which channels are on (voice, website chat, WhatsApp, Messenger), which
features (two-way Google Calendar, ...) and the monthly limits (minutes, chats,
texts, numbers). Until online payment exists, the owner *requests* an add-on in
the portal and the platform admin turns it on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.plans import (
    CHANNEL_MESSENGER,
    CHANNEL_WEB_CHAT,
    CHANNEL_WHATSAPP,
    FEATURE_EXTRA_LANGUAGE,
    FEATURE_GOOGLE_CALENDAR,
    FEATURE_RECORDING_RETENTION,
    Plan,
    get_plan,
)

#: Marker stored with the quantities (see db/bootstrap.py, which grandfathers
#: accounts that had the website widget before add-ons existed).
VERSION_KEY = "_v"

CATEGORY_CHANNEL = "channel"
CATEGORY_CAPACITY = "capacity"
CATEGORY_FEATURE = "feature"
CATEGORY_SERVICE = "service"


@dataclass(frozen=True)
class Addon:
    key: str
    name: str
    category: str
    price: float
    #: "month" (recurring), "once" (one-off service)
    period: str
    summary: str
    #: Several can be bought (minute packs, numbers).
    stackable: bool = False
    #: The channel this add-on switches on.
    channel: str = ""
    #: The feature this add-on switches on.
    feature: str = ""
    #: Per unit: extra monthly allowance, e.g. {"minutes": 100}.
    grants: dict[str, int] = field(default_factory=dict)
    #: Only for these products ("voice" / "chat"); empty = any.
    products: tuple[str, ...] = ()

    def price_label(self) -> str:
        amount = f"${self.price:,.0f}" if float(self.price).is_integer() else f"${self.price:,.2f}"
        return f"{amount} once" if self.period == "once" else f"{amount} / mo"

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "period": self.period,
            "price_label": self.price_label(),
            "summary": self.summary,
            "stackable": self.stackable,
            "channel": self.channel,
            "feature": self.feature,
            "grants": dict(self.grants),
            "products": list(self.products),
        }


CATALOG: dict[str, Addon] = {
    addon.key: addon
    for addon in (
        Addon("web_chat", "Website chatbot", CATEGORY_CHANNEL, 29, "month", "Your agent as a chat bubble on your site.",
              channel=CHANNEL_WEB_CHAT, grants={"chats": 1000}),
        # 300 chats, not 1,000: Twilio bills ≈ $0.005 per WhatsApp message in and out (≈ $0.09 a chat).
        Addon("whatsapp", "WhatsApp bot", CATEGORY_CHANNEL, 49, "month", "Customers chat and book on WhatsApp.",
              channel=CHANNEL_WHATSAPP, grants={"chats": 300}),
        Addon("messenger", "Messenger bot", CATEGORY_CHANNEL, 29, "month", "Answers your Facebook Page messages.",
              channel=CHANNEL_MESSENGER, grants={"chats": 1000}),
        Addon("minutes", "Extra 100 minutes", CATEGORY_CAPACITY, 25, "month", "More call minutes every month.",
              stackable=True, grants={"minutes": 100}, products=("voice",)),
        Addon("sms", "Extra 500 texts", CATEGORY_CAPACITY, 10, "month", "More SMS confirmations and reminders.",
              stackable=True, grants={"sms": 500}),
        Addon("number", "Extra phone number", CATEGORY_CAPACITY, 5, "month", "Another line for a branch or campaign.",
              stackable=True, grants={"numbers": 1}, products=("voice",)),
        Addon("google_calendar", "Two-way Google Calendar", CATEGORY_FEATURE, 9, "month", "Bookings sync both ways with Google.",
              feature=FEATURE_GOOGLE_CALENDAR),
        Addon("extra_language", "Extra language", CATEGORY_FEATURE, 19, "month", "Serve callers in a second language.",
              feature=FEATURE_EXTRA_LANGUAGE),
        Addon("recording_retention", "12-month recordings", CATEGORY_FEATURE, 10, "month", "Keep call recordings for a year.",
              feature=FEATURE_RECORDING_RETENTION, products=("voice",)),
        Addon("setup", "Done-for-you setup", CATEGORY_SERVICE, 299, "once", "We load your catalog, script and number."),
    )
}

#: Most of any stackable add-on one account can hold.
MAX_QUANTITY = 50


def public_catalog() -> list[dict[str, Any]]:
    return [addon.as_json() for addon in CATALOG.values()]


def quantities(raw: Any) -> dict[str, int]:
    """Clean ``merchants.addons`` into ``{key: quantity}`` for known add-ons only."""
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        addon = CATALOG.get(str(key))
        if addon is None:
            continue
        try:
            qty = int(value.get("qty", 1) if isinstance(value, dict) else value)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        out[addon.key] = min(qty, MAX_QUANTITY) if addon.stackable else 1
    return out


def stored(quantities_: dict[str, int]) -> dict[str, Any]:
    """The value to write to ``merchants.addons``."""
    return {VERSION_KEY: 1, **quantities(quantities_)}


@dataclass(frozen=True)
class Entitlements:
    plan: Plan
    channels: frozenset[str]
    features: frozenset[str]
    addons: dict[str, int]
    #: Monthly allowances; ``None`` = no limit (enterprise).
    minutes: int | None
    chats: int | None
    sms: int | None
    numbers: int | None

    def has_channel(self, channel: str) -> bool:
        return channel in self.channels

    def has_feature(self, feature: str) -> bool:
        return feature in self.features

    def as_json(self) -> dict[str, Any]:
        return {
            "plan": self.plan.key,
            "product": self.plan.product,
            "channels": sorted(self.channels),
            "features": sorted(self.features),
            "addons": dict(self.addons),
            "limits": {"minutes": self.minutes, "chats": self.chats, "sms": self.sms, "numbers": self.numbers},
        }


def entitlements(merchant: Any) -> Entitlements:
    plan = get_plan(getattr(merchant, "plan", None))
    owned = quantities(getattr(merchant, "addons", None) or {})
    channels = set(plan.channels)
    features = set(plan.includes)
    extra: dict[str, int] = {"minutes": 0, "chats": 0, "sms": 0, "numbers": 0}
    for key, qty in owned.items():
        addon = CATALOG[key]
        if addon.channel:
            channels.add(addon.channel)
        if addon.feature:
            features.add(addon.feature)
        for name, amount in addon.grants.items():
            extra[name] = extra.get(name, 0) + amount * qty
    unlimited = plan.key == "enterprise"

    def limit(base: int, name: str) -> int | None:
        return None if unlimited else base + extra.get(name, 0)

    return Entitlements(
        plan=plan,
        channels=frozenset(channels),
        features=frozenset(features),
        addons=owned,
        minutes=limit(plan.included_minutes, "minutes"),
        chats=limit(plan.included_chats, "chats"),
        sms=limit(plan.included_sms, "sms"),
        numbers=limit(plan.phone_numbers, "numbers"),
    )


def available_for(merchant: Any) -> list[str]:
    """Add-on keys this account could still request (not already covered by its plan)."""
    ent = entitlements(merchant)
    out: list[str] = []
    for addon in CATALOG.values():
        if addon.products and ent.plan.product not in addon.products:
            continue
        if addon.channel and addon.channel in ent.plan.channels:
            continue
        if addon.feature and addon.feature in ent.plan.includes:
            continue
        out.append(addon.key)
    return out


__all__ = [
    "CATALOG",
    "Addon",
    "Entitlements",
    "available_for",
    "entitlements",
    "public_catalog",
    "quantities",
    "stored",
]
