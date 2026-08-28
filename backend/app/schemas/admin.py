from pydantic import BaseModel, Field, field_validator

from app.schemas.merchant import MerchantOut, MerchantSettingsUpdate
from app.schemas.order import CallLogOut, OrderOut
from app.voice.languages import normalize_language


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class AdminTokenResponse(BaseModel):
    token: str


class MerchantCreate(BaseModel):
    business_name: str = Field(min_length=1, max_length=160)
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=200)
    owner_name: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=160)
    support_phone: str = Field(default="", max_length=32)
    language: str = "bn"

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        code = normalize_language(value, fallback="")
        if not code:
            raise ValueError("language must be 'bn' or 'en'")
        return code


class MerchantAdminUpdate(MerchantSettingsUpdate):
    password: str | None = Field(default=None, min_length=6, max_length=200)
    active: bool | None = None


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
