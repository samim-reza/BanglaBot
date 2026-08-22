from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.merchant import MerchantOut


def _valid_service_type(v: str) -> str:
    from app.flows import is_valid_service

    if not is_valid_service(v):
        raise ValueError("অজানা সার্ভিস টাইপ")
    return v


class SignupRequest(BaseModel):
    business_name: str = Field(min_length=1)
    owner_name: str = ""
    username: str = Field(min_length=1)
    password: str = Field(min_length=6)
    phone: str = ""
    email: str = ""
    service_type: str = "ecommerce"

    _service = field_validator("service_type")(_valid_service_type)


class MerchantSelfUpdate(BaseModel):
    # service_type is deliberately absent: only the platform admin changes it.
    owner_name: str | None = None
    phone: str | None = None
    support_phone: str | None = None
    email: str | None = None
    flow_settings: dict[str, bool] | None = None
    custom_greeting: str | None = Field(default=None, max_length=200)
    max_call_seconds: int | None = None  # 0 = platform default
    voice_tier: str | None = None
    noise_mode: str | None = None
    barge_in_mode: str | None = None
    silence_hangup_secs: int | None = None
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

    @field_validator("noise_mode")
    @classmethod
    def _valid_noise_mode(cls, v: str | None) -> str | None:
        from app.voice.behavior import is_valid_noise_mode

        if v is not None and not is_valid_noise_mode(v):
            raise ValueError("অজানা নয়েজ ফিল্টার মোড")
        return v

    @field_validator("barge_in_mode")
    @classmethod
    def _valid_barge_in(cls, v: str | None) -> str | None:
        from app.voice.behavior import is_valid_barge_in_mode

        if v is not None and not is_valid_barge_in_mode(v):
            raise ValueError("অজানা বার্জ-ইন মোড")
        return v

    @field_validator("silence_hangup_secs")
    @classmethod
    def _valid_silence_secs(cls, v: int | None) -> int | None:
        from app.voice.behavior import SILENCE_HANGUP_MAX, SILENCE_HANGUP_MIN

        if v is not None and not (SILENCE_HANGUP_MIN <= v <= SILENCE_HANGUP_MAX):
            raise ValueError("নীরবতার সীমা ৫–৩০ সেকেন্ডের মধ্যে হতে হবে")
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


class MerchantOption(BaseModel):
    """Lightweight merchant row for filter dropdowns."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    business_name: str
    active: bool


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
