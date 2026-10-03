import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.merchant import (
    MerchantOut,
    MerchantSettingsUpdate,
    validate_currency,
    validate_emergency,
    validate_timezone,
)
from app.schemas.order import CallLogOut, OrderOut
from app.voice.languages import normalize_language


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class AdminTokenResponse(BaseModel):
    token: str


def _vertical(value: str) -> str:
    from app.verticals import VERTICALS

    key = str(value or "").strip().lower()
    if key not in VERTICALS:
        raise ValueError(f"vertical must be one of {', '.join(VERTICALS)}")
    return key


def _region(value: str) -> str:
    from app.core.regions import REGIONS

    code = str(value or "").strip().upper()
    if code not in REGIONS:
        raise ValueError(f"region must be one of {', '.join(REGIONS)}")
    return code


def _phone(value: str) -> str:
    text = str(value or "").strip()
    if text and len(re.sub(r"\D", "", text)) < 7:
        raise ValueError("does not look like a phone number")
    return text


class MerchantCreate(BaseModel):
    business_name: str = Field(min_length=1, max_length=160)
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=200)
    #: Business engine — fixed for the life of the account.
    vertical: str = "ecommerce"
    region: str = "INTL"
    language: str = "en"
    owner_name: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=160)
    support_phone: str = Field(default="", max_length=32)
    inbound_number: str = Field(default="", max_length=32)
    voice_persona: str = "female"
    plan: str = "trial"
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, max_length=8)
    emergency_number: str | None = Field(default=None, max_length=16)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        code = normalize_language(value, fallback="")
        if not code:
            raise ValueError("language must be 'en' or 'bn'")
        return code

    @field_validator("vertical")
    @classmethod
    def _vertical(cls, value: str) -> str:
        return _vertical(value)

    @field_validator("region")
    @classmethod
    def _region(cls, value: str) -> str:
        return _region(value)

    @field_validator("inbound_number")
    @classmethod
    def _inbound(cls, value: str) -> str:
        return _phone(value)

    @field_validator("voice_persona")
    @classmethod
    def _persona(cls, value: str) -> str:
        persona = str(value or "female").strip().lower()
        if persona not in ("female", "male"):
            raise ValueError("voice_persona must be 'female' or 'male'")
        return persona

    # Same rules as an owner's settings update.
    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return validate_timezone(value)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return validate_currency(value)

    @field_validator("emergency_number")
    @classmethod
    def _emergency(cls, value: str | None) -> str | None:
        return validate_emergency(value)


class MerchantAdminUpdate(MerchantSettingsUpdate):
    password: str | None = Field(default=None, min_length=6, max_length=200)
    active: bool | None = None
    plan: str | None = None

    @field_validator("plan")
    @classmethod
    def _plan(cls, value: str | None) -> str | None:
        from app.core.plans import PLANS

        if value is None:
            return None
        key = str(value).strip().lower()
        if key not in PLANS:
            raise ValueError(f"plan must be one of {', '.join(PLANS)}")
        return key
    region: str | None = None
    inbound_number: str | None = Field(default=None, max_length=32)
    #: The account's Twilio WhatsApp sender ("" = none).
    whatsapp_number: str | None = Field(default=None, max_length=32)

    @field_validator("region")
    @classmethod
    def _region(cls, value: str | None) -> str | None:
        return None if value is None else _region(value)

    @field_validator("inbound_number", "whatsapp_number")
    @classmethod
    def _inbound(cls, value: str | None) -> str | None:
        return None if value is None else _phone(value)


class AdminOverview(BaseModel):
    merchants: int
    active_merchants: int
    orders: int
    calls_today: int
    confirmed_today: int
    cancelled_today: int
    orders_today: int
    pending_orders: int
    calling_orders: int
    needs_review_orders: int
    inbound_today: int = 0
    booked_today: int = 0
    by_vertical: dict[str, int] = {}
    pending_addon_requests: int = 0


class AdminOrderOut(OrderOut):
    merchant_name: str


class AdminOrderPage(BaseModel):
    items: list[AdminOrderOut]
    total: int
    page: int
    page_size: int


class AdminCallLogOut(CallLogOut):
    merchant_id: str
    merchant_name: str
    customer_name: str
    order_ref: str


class AdminCallPage(BaseModel):
    items: list[AdminCallLogOut]
    total: int
    page: int
    page_size: int


class MerchantListOut(BaseModel):
    items: list[MerchantOut]
    total: int
