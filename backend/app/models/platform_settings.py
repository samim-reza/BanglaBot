from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformSettings(Base):
    """Singleton row (id="default") with platform-wide knobs."""

    __tablename__ = "platform_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    platform_name: Mapped[str] = mapped_column(String(80), default="BanglaBot")
    support_email: Mapped[str] = mapped_column(String(160), default="")
    support_phone: Mapped[str] = mapped_column(String(32), default="")
    # Merchant-facing payment number.
    bkash_number: Mapped[str] = mapped_column(String(32), default="")
    signup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trial_plan_key: Mapped[str] = mapped_column(String(40), default="trial")
    entitlement_mode: Mapped[str] = mapped_column(String(10), default="enforce")  # enforce|observe
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
