import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.voice.languages import LANGUAGE_NAMES, normalize_language

VOICE_PERSONAS = ("female", "male")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class MerchantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    business_name: str
    owner_name: str
    username: str
    phone: str
    email: str
    vertical: str
    vertical_config: dict[str, Any]
    knowledge: str
    inbound_number: str
    region: str
    timezone: str
    currency: str
    emergency_number: str
    support_phone: str
    custom_greeting: str
    language: str
    supported_languages: list[str]
    voice_persona: str
    verify_address: bool
    max_call_seconds: int
    silence_hangup_secs: int
    active: bool
    plan: str = "trial"
    widget_enabled: bool = False
    widget_key: str = ""
    widget_settings: dict[str, Any] = {}
    webhook_url: str = ""
    webhook_secret: str = ""
    auto_call_at: datetime | None = None
    auto_call_repeat_daily: bool = False
    created_at: datetime | None = None


def validate_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    name = str(value).strip()
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001
        if name not in ("UTC", "Asia/Dhaka"):
            raise ValueError(f"unknown time zone: {name}") from exc
    return name


def validate_currency(value: str | None) -> str | None:
    if value is None:
        return None
    code = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError("currency must be a 3-letter code, e.g. USD")
    return code


def validate_emergency(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    if not 2 <= len(digits) <= 8:
        raise ValueError("emergency_number must be a short number such as 911, 999 or 112")
    return digits


class MerchantSettingsUpdate(BaseModel):
    """Fields an account owner may change (PATCH /api/auth/me).

    The business type (vertical), region and inbound number are the admin's."""

    business_name: str | None = Field(default=None, min_length=1, max_length=160)
    owner_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=160)
    support_phone: str | None = Field(default=None, max_length=32)
    custom_greeting: str | None = Field(default=None, max_length=300)
    knowledge: str | None = Field(default=None, max_length=8000)
    vertical_config: dict[str, Any] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, max_length=8)
    emergency_number: str | None = Field(default=None, max_length=16)
    language: str | None = None
    supported_languages: list[str] | None = None
    voice_persona: str | None = None
    verify_address: bool | None = None
    max_call_seconds: int | None = Field(default=None, ge=0, le=900)
    silence_hangup_secs: int | None = Field(default=None, ge=5, le=60)
    widget_enabled: bool | None = None
    widget_settings: dict[str, Any] | None = None
    webhook_url: str | None = Field(default=None, max_length=500)

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

    @field_validator("widget_settings")
    @classmethod
    def _widget(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        out: dict[str, Any] = {}
        title = " ".join(str(value.get("title") or "").split())[:60]
        if title:
            out["title"] = title
        color = str(value.get("color") or "").strip()
        if color:
            if not _HEX_COLOR.match(color):
                raise ValueError("widget color must be a hex color like #0f766e")
            out["color"] = color
        position = str(value.get("position") or "right").strip().lower()
        out["position"] = "left" if position == "left" else "right"
        subtitle = " ".join(str(value.get("subtitle") or "").split())[:80]
        if subtitle:
            out["subtitle"] = subtitle
        return out

    @field_validator("webhook_url")
    @classmethod
    def _webhook(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = str(value).strip()
        if url and not re.match(r"^https?://[^\s]+$", url):
            raise ValueError("webhook_url must start with http:// or https://")
        return url
