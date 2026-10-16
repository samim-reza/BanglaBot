from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import decrypt_secret, encrypt_secret, is_encrypted, lookup_hash
from app.db.base import Base, new_id

DEFAULT_SUPPORTED_LANGUAGES = ["en"]
#: ``lookup_hash`` purpose of calendar feed tokens.
CALENDAR_TOKEN_PURPOSE = "calendar-feed"


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
    # Telnyx number (E.164) whose inbound calls this account answers; "" = none.
    inbound_number: Mapped[str] = mapped_column(String(32), default="", index=True)
    region: Mapped[str] = mapped_column(String(8), default="INTL")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    emergency_number: Mapped[str] = mapped_column(String(16), default="112")
    # Number a caller is transferred to when they ask for a real person.
    support_phone: Mapped[str] = mapped_column(String(32), default="")
    # Opening sentence spoken verbatim; empty = the default greeting.
    custom_greeting: Mapped[str] = mapped_column(Text, default="")
    # Call language ("en"; English is the only one).
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
    # Stored as ``enc:<fernet>`` (rows from before: plaintext until the next write);
    # read and set through the ``webhook_secret`` property.
    webhook_secret_stored: Mapped[str] = mapped_column("webhook_secret", String(255), default="")
    # SMS confirmations / reminders: {"enabled", "on_booking", "on_change", "reminder_hours"}.
    sms_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Secret in the account's calendar feed URL (iCal subscription), read and set through the
    # ``calendar_token`` property: found by its peppered hash, an encrypted copy rebuilds the
    # URL for the owner. ``calendar_token_legacy`` is plaintext from before (cleared on upgrade).
    calendar_token_legacy: Mapped[str] = mapped_column("calendar_token", String(48), default="", index=True)
    calendar_token_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    calendar_token_enc: Mapped[str] = mapped_column(String(255), default="")
    # {"busy_ics_urls": [...], "google": {"email", "calendar_id", "refresh_token_enc", ...}}
    calendar_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Add-ons on top of the plan: {"_v": 1, "<addon key>": quantity} (see app.core.addons).
    addons: Mapped[dict] = mapped_column(JSONB, default=lambda: {"_v": 1})
    # Booking payments: {"provider": "platform" | "link", "link_template", "methods"} (app.services.payments.link).
    payment_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Chat channels: {"whatsapp": {"number"}, "messenger": {"page_id", "page_name", "token_enc"}}.
    channel_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # The owner's call-flow settings, sparse (see app.pipeline.config): {"_v", "steps", "branches", "order"}.
    agent_flow: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Platform-admin locks on call-flow settings: {"_v": 1, "locks": {path: value}}.
    agent_flow_locks: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Admin-only provider overrides: {"llm_chain": "...", "stt_chain": "...", "tts_chain": "..."}.
    provider_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Scheduled "call everyone who needs a call" run (UTC); NULL = nothing scheduled.
    auto_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Re-arm the schedule for the same time the next day after it fires.
    auto_call_repeat_daily: Mapped[bool] = mapped_column(Boolean, default=False)
    # Bumped on a password change / "sign out everywhere": older session tokens stop working.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # --- secrets at rest -----------------------------------------------------------
    @property
    def webhook_secret(self) -> str:
        return decrypt_secret(self.webhook_secret_stored or "")

    @webhook_secret.setter
    def webhook_secret(self, value: str) -> None:
        self.webhook_secret_stored = encrypt_secret(value or "")

    @property
    def calendar_token(self) -> str:
        if self.calendar_token_enc:
            return decrypt_secret(self.calendar_token_enc)
        return self.calendar_token_legacy or ""

    @calendar_token.setter
    def calendar_token(self, value: str) -> None:
        token = value or ""
        self.calendar_token_hash = lookup_hash(token, purpose=CALENDAR_TOKEN_PURPOSE) if token else ""
        self.calendar_token_enc = encrypt_secret(token)
        self.calendar_token_legacy = ""

    def upgrade_stored_secrets(self) -> bool:
        """Encrypt / hash secrets still stored in plaintext; True when anything changed."""
        changed = False
        if self.webhook_secret_stored and not is_encrypted(self.webhook_secret_stored):
            self.webhook_secret = self.webhook_secret_stored
            changed = True
        if self.calendar_token_legacy and not self.calendar_token_hash:
            self.calendar_token = self.calendar_token_legacy
            changed = True
        return changed
