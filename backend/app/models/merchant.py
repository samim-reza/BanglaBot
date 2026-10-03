from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id

DEFAULT_SUPPORTED_LANGUAGES = ["en", "bn"]


class Merchant(Base):
    """An account: one business whose phone line the agent works.

    ``vertical`` (which business engine runs its calls) is chosen by the admin
    at creation and never changes. ``region`` fixes the phone format and voice
    accent; ``timezone`` / ``currency`` / ``emergency_number`` start from the
    region preset and stay editable.
    """

    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    business_name: Mapped[str] = mapped_column(String(160))
    owner_name: Mapped[str] = mapped_column(String(120), default="")
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    # Business engine: ecommerce | clinic | real_estate | home_service.
    vertical: Mapped[str] = mapped_column(String(32), default="ecommerce", index=True)
    # Engine-specific settings (validated against the vertical's config fields).
    vertical_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Facts the agent may answer from: address, hours, policies, FAQs.
    knowledge: Mapped[str] = mapped_column(Text, default="")
    # Twilio number (E.164) whose inbound calls this account answers; "" = none.
    inbound_number: Mapped[str] = mapped_column(String(32), default="", index=True)
    region: Mapped[str] = mapped_column(String(8), default="INTL")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    emergency_number: Mapped[str] = mapped_column(String(16), default="112")
    # Number a caller is transferred to when they ask for a real person.
    support_phone: Mapped[str] = mapped_column(String(32), default="")
    # Opening sentence spoken verbatim; empty = the default greeting.
    custom_greeting: Mapped[str] = mapped_column(Text, default="")
    # Call language ("en" | "bn").
    language: Mapped[str] = mapped_column(String(8), default="en")
    supported_languages: Mapped[list] = mapped_column(JSONB, default=lambda: list(DEFAULT_SUPPORTED_LANGUAGES))
    voice_persona: Mapped[str] = mapped_column(String(12), default="female")
    # E-commerce: ask the customer to confirm the delivery address after the yes.
    verify_address: Mapped[bool] = mapped_column(Boolean, default=False)
    # Hard cap on one call; 0 = platform default (outbound / inbound settings).
    max_call_seconds: Mapped[int] = mapped_column(Integer, default=0)
    # Seconds of caller silence before the agent re-asks (then hangs up).
    silence_hangup_secs: Mapped[int] = mapped_column(Integer, default=10)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Subscription plan key (app/core/plans.py); set by the admin.
    plan: Mapped[str] = mapped_column(String(24), default="trial")
    # --- add-ons ---------------------------------------------------------------
    # Website chat widget: the same agent, typed. The key is public (it is in the
    # embed snippet); disabling the widget makes it inert.
    widget_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    widget_key: Mapped[str] = mapped_column(String(40), default="", index=True)
    # {"title", "color", "position"} for the widget's look.
    widget_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # POSTed a signed JSON event when a call / chat ends (bookings into the business's own system).
    webhook_url: Mapped[str] = mapped_column(String(500), default="")
    webhook_secret: Mapped[str] = mapped_column(String(64), default="")
    # SMS confirmations / reminders: {"enabled", "on_booking", "on_change", "reminder_hours"}.
    sms_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Secret in the account's calendar feed URL (iCal subscription); "" = not issued yet.
    calendar_token: Mapped[str] = mapped_column(String(48), default="", index=True)
    # {"busy_ics_urls": [...], "google": {"email", "calendar_id", "refresh_token_enc", ...}}
    calendar_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Scheduled "call everyone who needs a call" run (UTC); NULL = nothing scheduled.
    auto_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Re-arm the schedule for the same time the next day after it fires.
    auto_call_repeat_daily: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
