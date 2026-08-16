from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.merchant import MerchantOut


class SignupRequest(BaseModel):
    business_name: str = Field(min_length=1)
    owner_name: str = ""
    username: str = Field(min_length=1)
    password: str = Field(min_length=6)
    phone: str = ""
    email: str = ""


class MerchantSelfUpdate(BaseModel):
    owner_name: str | None = None
    phone: str | None = None
    support_phone: str | None = None
    email: str | None = None
    custom_greeting: str | None = Field(default=None, max_length=200)
    max_call_seconds: int | None = None  # 0 = platform default
    voice_tier: str | None = None
    password: str | None = None
    current_password: str | None = None

    @field_validator("max_call_seconds")
    @classmethod
    def _valid_call_limit(cls, v: int | None) -> int | None:
        if v is not None and v != 0 and not (60 <= v <= 600):
            raise ValueError("কলের সর্বোচ্চ সময় ৬০–৬০০ সেকেন্ডের মধ্যে হতে হবে (০ = ডিফল্ট)")
        return v

    @field_validator("voice_tier")
    @classmethod
    def _valid_voice_tier(cls, v: str | None) -> str | None:
        from app.services.voice_tiers import is_valid_tier

        if v is not None and not is_valid_tier(v):
            raise ValueError("অজানা ভয়েস কোয়ালিটি")
        return v


class AdminUserCreate(BaseModel):
    username: str
    name: str
    password: str


class AdminUserPatch(BaseModel):
    name: str | None = None
    password: str | None = None


class SettingsUpdate(BaseModel):
    platform_name: str | None = None
    support_email: str | None = None
    support_phone: str | None = None
    bkash_number: str | None = None
    signup_enabled: bool | None = None
    trial_plan_key: str | None = None
    entitlement_mode: str | None = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_role: str
    actor_id: str
    actor_name: str
    action: str
    detail: str
    merchant_id: str | None
    created_at: datetime


class AdminMerchantOut(MerchantOut):
    plan_key: str | None
    plan_name_bn: str | None
    sub_status: str | None
    calls_used: int
    call_limit: int  # incl. bonus; 0 when no sub


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    name: str
    created_at: datetime


class AdminCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    merchant_id: str
    merchant_name: str
    # Null when the order was deleted — the log survives for usage metering.
    order_id: str | None
    order_ref: str | None
    call_status: str
    outcome: str
    duration_secs: int
    transcript: str
    recording_sid: str
    created_at: datetime


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform_name: str
    support_email: str
    support_phone: str
    bkash_number: str
    signup_enabled: bool
    trial_plan_key: str
    entitlement_mode: str
    updated_at: datetime
