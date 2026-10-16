"""Entitlements: what one account may use — its tier merged with its add-ons.

The single gate every channel, feature and limit check goes through
(``app.core.addons.entitlements`` re-exports it). Channels and features are the
tier's plus the add-ons'; monthly allowances are the tier's plus each add-on's
per-unit ``grants`` × quantity; capabilities (payments, custom fields, API +
webhooks, full flow editing) are on when the tier's limits say so or an add-on
unlocks them; concurrent calls are the tier's limit plus add-on grants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.addons import CATALOG, quantities
from app.core.plans import (
    ALL_CHANNELS,
    CHANNEL_LABELS,
    FEATURE_API_WEBHOOKS,
    FEATURE_CUSTOM_FIELDS,
    FEATURE_FULL_FLOW_EDITING,
    FEATURE_PAYMENTS,
    FLOW_FULL,
    FLOW_LINES,
    Plan,
    get_plan,
    is_unlimited,
)


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
    #: Calls live at once (tier limit + add-ons); 0 = no phone calls.
    max_concurrent_calls: int = 1
    flow_editing: str = FLOW_LINES
    payments: bool = False
    custom_fields: bool = False
    api_webhooks: bool = False

    def has_channel(self, channel: str) -> bool:
        return channel in self.channels

    def has_feature(self, feature: str) -> bool:
        return feature in self.features

    @property
    def capabilities(self) -> dict[str, Any]:
        return {
            "flow_editing": self.flow_editing,
            "payments": self.payments,
            "custom_fields": self.custom_fields,
            "api_webhooks": self.api_webhooks,
        }

    def as_json(self) -> dict[str, Any]:
        return {
            "plan": self.plan.key,
            "product": self.plan.product,
            "channels": sorted(self.channels),
            "features": sorted(self.features),
            "addons": dict(self.addons),
            "limits": {
                "minutes": self.minutes,
                "chats": self.chats,
                "sms": self.sms,
                "numbers": self.numbers,
                "max_concurrent_calls": self.max_concurrent_calls,
            },
            "capabilities": self.capabilities,
        }


def entitlements(merchant: Any) -> Entitlements:
    plan = get_plan(getattr(merchant, "plan", None))
    owned = quantities(getattr(merchant, "addons", None) or {})
    channels = set(plan.channels)
    features = set(plan.includes)
    extra: dict[str, int] = {}
    for key, qty in owned.items():
        addon = CATALOG[key]
        if addon.channel:
            channels.add(addon.channel)
        if addon.feature:
            features.add(addon.feature)
        for name, amount in addon.grants.items():
            extra[name] = extra.get(name, 0) + int(amount) * qty
    limits = plan.limits
    payments = limits.payments or FEATURE_PAYMENTS in features
    custom_fields = limits.custom_fields or FEATURE_CUSTOM_FIELDS in features
    api_webhooks = limits.api_webhooks or FEATURE_API_WEBHOOKS in features
    full_flow = limits.flow_editing == FLOW_FULL or FEATURE_FULL_FLOW_EDITING in features
    for flag, key in ((payments, FEATURE_PAYMENTS), (custom_fields, FEATURE_CUSTOM_FIELDS),
                      (api_webhooks, FEATURE_API_WEBHOOKS), (full_flow, FEATURE_FULL_FLOW_EDITING)):
        if flag:
            features.add(key)
    unlimited = is_unlimited(plan)

    def allowance(base: int, name: str) -> int | None:
        return None if unlimited else int(base) + extra.get(name, 0)

    return Entitlements(
        plan=plan,
        channels=frozenset(channels),
        features=frozenset(features),
        addons=owned,
        minutes=allowance(plan.included_minutes, "minutes"),
        chats=allowance(plan.included_chats, "chats"),
        sms=allowance(plan.included_sms, "sms"),
        numbers=allowance(plan.phone_numbers, "numbers"),
        max_concurrent_calls=max(0, int(limits.max_concurrent_calls) + extra.get("concurrent_calls", 0)),
        flow_editing=FLOW_FULL if full_flow else FLOW_LINES,
        payments=payments,
        custom_fields=custom_fields,
        api_webhooks=api_webhooks,
    )


def channel_states(merchant: Any) -> list[dict[str, Any]]:
    """Each channel for the Channels page: ``included`` (in the tier), ``addon`` (bought),
    ``available`` (can be bought), or ``unavailable`` (not offered for this account)."""
    ent = entitlements(merchant)
    vertical = str(getattr(merchant, "vertical", "") or "") or None
    by_channel = {addon.channel: addon for addon in CATALOG.values() if addon.channel}
    out: list[dict[str, Any]] = []
    for channel in ALL_CHANNELS:
        addon = by_channel.get(channel)
        if channel in ent.plan.channels:
            state = "included"
        elif addon is not None and addon.key in ent.addons:
            state = "addon"
        elif addon is not None and addon.visible and addon.offered_for(ent.plan.product, vertical):
            state = "available"
        else:
            state = "unavailable"
        out.append(
            {
                "channel": channel,
                "label": CHANNEL_LABELS.get(channel, channel),
                "state": state,
                "active": channel in ent.channels,
                "addon": addon.key if addon else "",
                "price_label": addon.price_label() if addon and state == "available" else "",
            }
        )
    return out


__all__ = ["Entitlements", "channel_states", "entitlements"]
