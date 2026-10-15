"""Admin editor payloads: the tier + add-on catalog, offered verticals, signup settings."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.addons import CATEGORIES, GRANT_KEYS, MAX_QUANTITY, PERIOD_ONCE, PERIODS
from app.core.plans import ALL_CHANNELS, ALL_FEATURES, CAPABILITY_FEATURES, DEFAULT_PLAN, FLOW_EDITING_LEVELS, PRODUCTS

MONEY_MAX = 100_000


def _subset(values: list[str], allowed: tuple[str, ...] | list[str], what: str) -> list[str]:
    cleaned = list(dict.fromkeys(str(value).strip().lower() for value in values if str(value).strip()))
    unknown = [value for value in cleaned if value not in allowed]
    if unknown:
        raise ValueError(f"unknown {what}: {', '.join(unknown)}")
    return cleaned


def _verticals(values: list[str]) -> list[str]:
    from app.verticals import VERTICALS

    return _subset(values, list(VERTICALS), "vertical")


class TierLimitsIn(BaseModel):
    max_concurrent_calls: int = Field(default=1, ge=0, le=1000)
    flow_editing: str = "lines"
    payments: bool = False
    custom_fields: bool = False
    api_webhooks: bool = False

    @field_validator("flow_editing")
    @classmethod
    def _flow(cls, value: str) -> str:
        level = str(value or "").strip().lower()
        if level not in FLOW_EDITING_LEVELS:
            raise ValueError(f"flow_editing must be one of {', '.join(FLOW_EDITING_LEVELS)}")
        return level


class TierIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,23}$")
    name: str = Field(min_length=1, max_length=60)
    tagline: str = Field(default="", max_length=120)
    product: Literal["voice", "chat"] = "voice"
    price_month: float = Field(ge=0, le=MONEY_MAX)
    #: 0 = 10 × the monthly price ("2 months free").
    price_year: float = Field(default=0, ge=0, le=MONEY_MAX * 12)
    overage_per_minute: float = Field(default=0, ge=0, le=100)
    included_minutes: int = Field(default=0, ge=0, le=1_000_000)
    included_chats: int = Field(default=0, ge=0, le=1_000_000)
    included_sms: int = Field(default=0, ge=0, le=1_000_000)
    phone_numbers: int = Field(default=0, ge=0, le=1000)
    included_languages: int = Field(default=1, ge=1, le=20)
    channels: list[str] = Field(default_factory=list, max_length=len(ALL_CHANNELS))
    includes: list[str] = Field(default_factory=list, max_length=len(ALL_FEATURES))
    #: Marketing bullets.
    features: list[str] = Field(default_factory=list, max_length=12)
    limits: TierLimitsIn = Field(default_factory=TierLimitsIn)
    verticals: list[str] = Field(default_factory=list, max_length=50)
    visible: bool = True
    highlight: bool = False
    checkout: bool = True
    trial_days: int = Field(default=0, ge=0, le=365)
    sort: int = Field(default=0, ge=-1000, le=1000)

    @field_validator("channels")
    @classmethod
    def _channels(cls, value: list[str]) -> list[str]:
        return _subset(value, ALL_CHANNELS, "channel")

    @field_validator("includes")
    @classmethod
    def _includes(cls, value: list[str]) -> list[str]:
        return _subset(value, ALL_FEATURES, "feature")

    @field_validator("features")
    @classmethod
    def _bullets(cls, value: list[str]) -> list[str]:
        bullets = [str(item).strip() for item in value if str(item).strip()]
        if any(len(item) > 80 for item in bullets):
            raise ValueError("feature bullets are at most 80 characters")
        return bullets

    @field_validator("verticals")
    @classmethod
    def _tier_verticals(cls, value: list[str]) -> list[str]:
        return _verticals(value)

    @model_validator(mode="after")
    def _consistent(self) -> TierIn:
        if not self.channels:
            raise ValueError(f"tier {self.key}: pick at least one channel")
        if self.product == "voice" and "voice" not in self.channels:
            raise ValueError(f"tier {self.key}: a voice tier includes the voice channel")
        if self.product == "chat" and self.limits.max_concurrent_calls:
            raise ValueError(f"tier {self.key}: a chat tier has no concurrent calls")
        return self


class AddonIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    name: str = Field(min_length=1, max_length=60)
    summary: str = Field(default="", max_length=160)
    category: str
    price: float = Field(ge=0, le=MONEY_MAX)
    period: str = "month"
    stackable: bool = False
    max_quantity: int = Field(default=1, ge=1, le=MAX_QUANTITY)
    channel: str = ""
    feature: str = ""
    grants: dict[str, int] = Field(default_factory=dict)
    products: list[str] = Field(default_factory=list, max_length=len(PRODUCTS))
    verticals: list[str] = Field(default_factory=list, max_length=50)
    visible: bool = True
    sort: int = Field(default=0, ge=-1000, le=1000)

    @field_validator("category")
    @classmethod
    def _category(cls, value: str) -> str:
        return _subset([value], CATEGORIES, "category")[0]

    @field_validator("period")
    @classmethod
    def _period(cls, value: str) -> str:
        return _subset([value], PERIODS, "period")[0]

    @field_validator("channel")
    @classmethod
    def _channel(cls, value: str) -> str:
        return _subset([value], ALL_CHANNELS, "channel")[0] if str(value or "").strip() else ""

    @field_validator("feature")
    @classmethod
    def _feature(cls, value: str) -> str:
        return _subset([value], ALL_FEATURES + CAPABILITY_FEATURES, "feature")[0] if str(value or "").strip() else ""

    @field_validator("grants")
    @classmethod
    def _grants(cls, value: dict[str, int]) -> dict[str, int]:
        _subset(list(value), GRANT_KEYS, "grant")
        if any(int(amount) < 1 or int(amount) > 1_000_000 for amount in value.values()):
            raise ValueError("grants are between 1 and 1,000,000 per unit")
        return {str(key).strip().lower(): int(amount) for key, amount in value.items()}

    @field_validator("products")
    @classmethod
    def _products(cls, value: list[str]) -> list[str]:
        return _subset(value, PRODUCTS, "product")

    @field_validator("verticals")
    @classmethod
    def _addon_verticals(cls, value: list[str]) -> list[str]:
        return _verticals(value)

    @model_validator(mode="after")
    def _consistent(self) -> AddonIn:
        if self.period == PERIOD_ONCE and (self.channel or self.feature or self.grants or self.stackable):
            raise ValueError(f"add-on {self.key}: a one-off service can't switch on channels, features or allowances")
        if not self.stackable:
            self.max_quantity = 1
        if not (self.channel or self.feature or self.grants or self.period == PERIOD_ONCE):
            raise ValueError(f"add-on {self.key}: say what it raises (a channel, a feature or an allowance)")
        return self


class CatalogIn(BaseModel):
    tiers: list[TierIn] = Field(min_length=1, max_length=30)
    addons: list[AddonIn] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def _catalog(self) -> CatalogIn:
        tier_keys = [tier.key for tier in self.tiers]
        addon_keys = [addon.key for addon in self.addons]
        for what, keys in (("tier", tier_keys), ("add-on", addon_keys)):
            twice = sorted({key for key in keys if keys.count(key) > 1})
            if twice:
                raise ValueError(f"duplicate {what} key: {', '.join(twice)}")
        if DEFAULT_PLAN not in tier_keys:
            raise ValueError(f"the '{DEFAULT_PLAN}' tier must stay (new and unpaid accounts fall back to it)")
        if not any(tier.visible and tier.checkout for tier in self.tiers):
            raise ValueError("at least one tier must be visible and buyable online")
        channels = [addon.channel for addon in self.addons if addon.channel]
        twice = sorted({channel for channel in channels if channels.count(channel) > 1})
        if twice:
            raise ValueError(f"one add-on per channel: {', '.join(twice)}")
        return self


class VerticalsIn(BaseModel):
    offered: list[str] = Field(min_length=1, max_length=50)

    @field_validator("offered")
    @classmethod
    def _offered(cls, value: list[str]) -> list[str]:
        cleaned = _verticals(value)
        if not cleaned:
            raise ValueError("offer at least one vertical")
        return cleaned


class SignupSettingsIn(BaseModel):
    #: Paid signups go live without an admin approving them.
    auto_activate: bool = False
    #: Auto-activation also waits for the owner's email to be verified.
    require_verified_email: bool = False


__all__ = ["AddonIn", "CatalogIn", "SignupSettingsIn", "TierIn", "TierLimitsIn", "VerticalsIn"]
