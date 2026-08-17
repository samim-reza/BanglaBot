from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MerchantCreate(BaseModel):
    business_name: str
    owner_name: str = ""
    username: str
    password: str
    phone: str = ""
    email: str = ""
    support_phone: str = ""


class MerchantUpdate(BaseModel):
    """Admin-side merchant edit — covers profile and agent settings alike."""

    business_name: str | None = None
    owner_name: str | None = None
    password: str | None = None
    phone: str | None = None
    email: str | None = None
    support_phone: str | None = None
    custom_greeting: str | None = Field(default=None, max_length=200)
    max_call_seconds: int | None = None  # 0 = platform default
    voice_tier: str | None = None
    noise_mode: str | None = None
    barge_in_mode: str | None = None
    silence_hangup_secs: int | None = None
    active: bool | None = None

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


class MerchantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    business_name: str
    owner_name: str
    username: str
    phone: str
    email: str
    support_phone: str
    custom_greeting: str
    max_call_seconds: int
    voice_tier: str
    noise_mode: str
    barge_in_mode: str
    silence_hangup_secs: int
    active: bool
    created_at: datetime
