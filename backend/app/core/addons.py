"""Add-ons: extras an account buys on top of its tier, and the catalog they come from.

An account's add-ons are stored on ``merchants.addons`` as ``{key: quantity}``
(plus the marker ``"_v": 1``). What an add-on raises is declared on it: a
channel it switches on, a feature (or capability) it unlocks, and per-unit
``grants`` to the monthly allowances. :func:`entitlements` (``app.core.entitlements``,
re-exported here) merges them with the tier — the single gate everything uses.

Like tiers, the catalog is data-driven (``platform_settings["addons.catalog"]``,
see ``app.services.catalog_plans``); the values below are the defaults.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from app.core.plans import (
    CHANNEL_INSTAGRAM,
    CHANNEL_MESSENGER,
    CHANNEL_WEB_CHAT,
    CHANNEL_WHATSAPP,
    FEATURE_EXTRA_LANGUAGE,
    FEATURE_GOOGLE_CALENDAR,
    FEATURE_RECORDING_RETENTION,
    PRODUCT_VOICE,
)

#: Marker stored with the quantities (see db/bootstrap.py, which grandfathers
#: accounts that had the website widget before add-ons existed).
VERSION_KEY = "_v"

CATEGORY_CHANNEL = "channel"
CATEGORY_CAPACITY = "capacity"
CATEGORY_FEATURE = "feature"
CATEGORY_SERVICE = "service"
CATEGORIES = (CATEGORY_CHANNEL, CATEGORY_CAPACITY, CATEGORY_FEATURE, CATEGORY_SERVICE)

PERIOD_MONTH = "month"
PERIOD_ONCE = "once"
PERIODS = (PERIOD_MONTH, PERIOD_ONCE)

#: Allowances an add-on can raise, per unit.
GRANT_KEYS = ("minutes", "chats", "sms", "numbers", "languages", "concurrent_calls")

#: Most of any stackable add-on one account can hold.
MAX_QUANTITY = 50


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
    #: The feature (or capability, e.g. "payments") this add-on switches on.
    feature: str = ""
    #: Per unit: extra monthly allowance, e.g. {"minutes": 100}.
    grants: dict[str, int] = field(default_factory=dict)
    #: Only for these products ("voice" / "chat"); empty = any.
    products: tuple[str, ...] = ()
    #: Only for these verticals; empty = any.
    verticals: tuple[str, ...] = ()
    #: Offered in the shop and at signup.
    visible: bool = True
    sort: int = 0
    #: Most one account can hold (stackable add-ons only; others are 0 or 1).
    max_quantity: int = MAX_QUANTITY

    @property
    def limit(self) -> int:
        return max(1, min(int(self.max_quantity or 1), MAX_QUANTITY)) if self.stackable else 1

    def offered_for(self, product: str | None = None, vertical: str | None = None) -> bool:
        if product and self.products and product not in self.products:
            return False
        return not vertical or not self.verticals or vertical in self.verticals

    def price_label(self) -> str:
        amount = f"${self.price:,.0f}" if float(self.price).is_integer() else f"${self.price:,.2f}"
        return f"{amount} once" if self.period == PERIOD_ONCE else f"{amount} / mo"

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["products"] = list(self.products)
        data["verticals"] = list(self.verticals)
        data["grants"] = dict(self.grants)
        data["max_quantity"] = self.limit
        data["price_label"] = self.price_label()
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any], base: Addon | None = None) -> Addon:
        values: dict[str, Any] = asdict(base) if base else {}
        known = {item.name for item in fields(cls)}
        values.update({key: value for key, value in data.items() if key in known})
        for key in ("products", "verticals"):
            if key in values:
                values[key] = tuple(values[key] or ())
        values["grants"] = {str(k): int(v) for k, v in dict(values.get("grants") or {}).items()}
        return cls(**values)


#: The catalog until the admin edits it (and the base for fields a stored add-on lacks).
DEFAULT_CATALOG: dict[str, Addon] = {
    addon.key: addon
    for addon in (
        Addon("web_chat", "Website chatbot", CATEGORY_CHANNEL, 29, PERIOD_MONTH, "Your agent as a chat bubble on your site.",
              channel=CHANNEL_WEB_CHAT, grants={"chats": 1000}, sort=10),
        # 300 chats, not 1,000: Twilio bills ≈ $0.005 per WhatsApp message in and out (≈ $0.09 a chat).
        Addon("whatsapp", "WhatsApp bot", CATEGORY_CHANNEL, 49, PERIOD_MONTH, "Customers chat and book on WhatsApp.",
              channel=CHANNEL_WHATSAPP, grants={"chats": 300}, sort=20),
        Addon("messenger", "Messenger bot", CATEGORY_CHANNEL, 29, PERIOD_MONTH, "Answers your Facebook Page messages.",
              channel=CHANNEL_MESSENGER, grants={"chats": 1000}, sort=30),
        # Meta charges nothing per Instagram message: priced like Messenger.
        Addon("instagram", "Instagram DM bot", CATEGORY_CHANNEL, 29, PERIOD_MONTH, "Answers your Instagram direct messages.",
              channel=CHANNEL_INSTAGRAM, grants={"chats": 1000}, sort=35),
        Addon("minutes", "Extra 100 minutes", CATEGORY_CAPACITY, 25, PERIOD_MONTH, "More call minutes every month.",
              stackable=True, grants={"minutes": 100}, products=(PRODUCT_VOICE,), sort=40),
        Addon("sms", "Extra 500 texts", CATEGORY_CAPACITY, 10, PERIOD_MONTH, "More SMS confirmations and reminders.",
              stackable=True, grants={"sms": 500}, sort=50),
        Addon("number", "Extra phone number", CATEGORY_CAPACITY, 5, PERIOD_MONTH, "Another line for a branch or campaign.",
              stackable=True, grants={"numbers": 1}, products=(PRODUCT_VOICE,), sort=60),
        # Hidden until the admin prices it: one more call at the same time.
        Addon("concurrent_call", "Extra simultaneous call", CATEGORY_CAPACITY, 15, PERIOD_MONTH, "One more call at the same time.",
              stackable=True, grants={"concurrent_calls": 1}, products=(PRODUCT_VOICE,), visible=False, max_quantity=10, sort=65),
        Addon("google_calendar", "Two-way Google Calendar", CATEGORY_FEATURE, 9, PERIOD_MONTH, "Bookings sync both ways with Google.",
              feature=FEATURE_GOOGLE_CALENDAR, sort=70),
        Addon("extra_language", "Extra language", CATEGORY_FEATURE, 19, PERIOD_MONTH, "Serve callers in a second language.",
              feature=FEATURE_EXTRA_LANGUAGE, grants={"languages": 1}, sort=80),
        Addon("recording_retention", "12-month recordings", CATEGORY_FEATURE, 10, PERIOD_MONTH, "Keep call recordings for a year.",
              feature=FEATURE_RECORDING_RETENTION, products=(PRODUCT_VOICE,), sort=90),
        Addon("setup", "Done-for-you setup", CATEGORY_SERVICE, 299, PERIOD_ONCE, "We load your catalog, script and number.", sort=100),
    )
}

_installed: dict[str, Addon] = dict(DEFAULT_CATALOG)


class _LiveCatalog(Mapping[str, Addon]):
    """``CATALOG``: a read-only view of the installed add-on catalog."""

    def __getitem__(self, key: str) -> Addon:
        return _installed[key]

    def __iter__(self) -> Iterator[str]:
        return iter(_installed)

    def __len__(self) -> int:
        return len(_installed)

    def __repr__(self) -> str:
        return f"CATALOG({list(_installed)!r})"


CATALOG: Mapping[str, Addon] = _LiveCatalog()


def install_addons(addons: Iterable[Addon]) -> None:
    global _installed
    _installed = {addon.key: addon for addon in sorted(addons, key=lambda addon: (addon.sort, addon.key))}


def reset_addons() -> None:
    install_addons(DEFAULT_CATALOG.values())


def public_catalog(*, vertical: str | None = None, include_hidden: bool = False) -> list[dict[str, Any]]:
    return [
        addon.as_json()
        for addon in _installed.values()
        if (include_hidden or addon.visible) and addon.offered_for(vertical=vertical)
    ]


def quantities(raw: Any) -> dict[str, int]:
    """Clean ``merchants.addons`` into ``{key: quantity}`` for known add-ons only."""
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        addon = _installed.get(str(key))
        if addon is None:
            continue
        try:
            qty = int(value.get("qty", 1) if isinstance(value, dict) else value)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        out[addon.key] = min(qty, addon.limit)
    return out


def stored(quantities_: dict[str, int]) -> dict[str, Any]:
    """The value to write to ``merchants.addons``."""
    return {VERSION_KEY: 1, **quantities(quantities_)}


def available_for(merchant: Any) -> list[str]:
    """Add-on keys this account could still request (offered, not already covered by its tier)."""
    from app.core.entitlements import entitlements as _entitlements

    ent = _entitlements(merchant)
    vertical = str(getattr(merchant, "vertical", "") or "") or None
    out: list[str] = []
    for addon in _installed.values():
        if not addon.visible and addon.key not in ent.addons:
            continue
        if not addon.offered_for(ent.plan.product, vertical):
            continue
        if addon.channel and addon.channel in ent.plan.channels:
            continue
        if addon.feature and addon.feature in ent.plan.includes:
            continue
        out.append(addon.key)
    return out


def entitlements(merchant: Any):
    """What the account may use: tier + add-ons (see ``app.core.entitlements``)."""
    from app.core.entitlements import entitlements as _entitlements

    return _entitlements(merchant)


def __getattr__(name: str) -> Any:
    if name == "Entitlements":
        from app.core.entitlements import Entitlements

        return Entitlements
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CATALOG",
    "CATEGORIES",
    "DEFAULT_CATALOG",
    "GRANT_KEYS",
    "MAX_QUANTITY",
    "PERIODS",
    "Addon",
    "available_for",
    "entitlements",
    "install_addons",
    "public_catalog",
    "quantities",
    "reset_addons",
    "stored",
]
