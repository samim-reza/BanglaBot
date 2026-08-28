from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.voice.languages import LANGUAGE_NAMES, normalize_language

VOICE_PERSONAS = ("female", "male")


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
    language: str
    supported_languages: list[str]
    voice_persona: str
    verify_address: bool
    max_call_seconds: int
    silence_hangup_secs: int
    active: bool
    created_at: datetime | None = None


class MerchantSettingsUpdate(BaseModel):
    """Fields a merchant may change about themselves (PATCH /api/auth/me)."""

    business_name: str | None = Field(default=None, min_length=1, max_length=160)
    owner_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=160)
    support_phone: str | None = Field(default=None, max_length=32)
    custom_greeting: str | None = Field(default=None, max_length=300)
    language: str | None = None
    supported_languages: list[str] | None = None
    voice_persona: str | None = None
    verify_address: bool | None = None
    max_call_seconds: int | None = Field(default=None, ge=0, le=900)
    silence_hangup_secs: int | None = Field(default=None, ge=5, le=60)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = normalize_language(value, fallback="")
        if not code:
            raise ValueError(f"language must be one of {', '.join(LANGUAGE_NAMES)}")
        return code

    @field_validator("supported_languages")
    @classmethod
    def _supported(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        codes: list[str] = []
        for item in value:
            code = normalize_language(item, fallback="")
            if not code:
                raise ValueError(f"unsupported language code: {item}")
            if code not in codes:
                codes.append(code)
        if not codes:
            raise ValueError("at least one supported language is required")
        return codes

    @field_validator("voice_persona")
    @classmethod
    def _persona(cls, value: str | None) -> str | None:
        if value is None:
            return None
        persona = str(value).strip().lower()
        if persona not in VOICE_PERSONAS:
            raise ValueError("voice_persona must be 'female' or 'male'")
        return persona

    @field_validator("max_call_seconds")
    @classmethod
    def _max_call(cls, value: int | None) -> int | None:
        if value is None or value == 0:
            return value
        if value < 60:
            raise ValueError("max_call_seconds must be 0 (platform default) or at least 60")
        return value
