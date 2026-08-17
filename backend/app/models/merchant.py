from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


class Merchant(Base):
    """An ecommerce business owner account (created by the platform admin)."""

    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    business_name: Mapped[str] = mapped_column(String(160))
    owner_name: Mapped[str] = mapped_column(String(120), default="")
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    # Number a customer is transferred to when they ask for a real person.
    support_phone: Mapped[str] = mapped_column(String(32), default="")
    # Opening sentence the agent must say verbatim; empty = default greeting.
    custom_greeting: Mapped[str] = mapped_column(String(200), default="")
    # Per-merchant hard cap on one call's length; 0 = platform default.
    max_call_seconds: Mapped[int] = mapped_column(Integer, default=0)
    # Voice quality tier key (see services/voice_tiers.py) — rank names only in UI.
    voice_tier: Mapped[str] = mapped_column(String(20), default="very_basic")
    # Call-behavior knobs (modes & defaults live in app/voice/behavior.py).
    noise_mode: Mapped[str] = mapped_column(String(10), default="normal")
    barge_in_mode: Mapped[str] = mapped_column(String(12), default="protected")
    # Hang up (outcome "auto_dropped", order callable again) after this many
    # seconds of caller silence following an agent utterance.
    silence_hangup_secs: Mapped[int] = mapped_column(Integer, default=10)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
