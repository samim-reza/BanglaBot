from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id

DEFAULT_SUPPORTED_LANGUAGES = ["bn", "en"]


class Merchant(Base):
    """An e-commerce business whose orders the agent confirms by phone."""

    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    business_name: Mapped[str] = mapped_column(String(160))
    owner_name: Mapped[str] = mapped_column(String(120), default="")
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    # Number a customer is transferred to when they ask for a real person.
    support_phone: Mapped[str] = mapped_column(String(32), default="")
    # Opening sentence spoken verbatim; empty = the default greeting.
    custom_greeting: Mapped[str] = mapped_column(Text, default="")
    # Primary call language ("bn" | "en") and the languages the agent may switch to.
    language: Mapped[str] = mapped_column(String(8), default="bn")
    supported_languages: Mapped[list] = mapped_column(JSONB, default=lambda: list(DEFAULT_SUPPORTED_LANGUAGES))
    voice_persona: Mapped[str] = mapped_column(String(12), default="female")
    # Ask the customer to confirm the delivery address before the order itself.
    verify_address: Mapped[bool] = mapped_column(Boolean, default=False)
    # Hard cap on one call; 0 = platform default (settings.voice_max_call_seconds).
    max_call_seconds: Mapped[int] = mapped_column(Integer, default=0)
    # Seconds of caller silence before the agent re-asks (then hangs up).
    silence_hangup_secs: Mapped[int] = mapped_column(Integer, default=10)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
