from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformSetting(Base):
    """Platform-wide settings the admin console edits, one JSON value per key.

    Generic on purpose: ``finance.pricebook`` (price overrides by effective date),
    ``finance.caps`` (daily provider spend caps), ``plans.catalog`` (tiers), ...
    Read and written through ``app.finance.settings_store``.
    """

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # Admin user id (or ``env:<name>`` / ``system``) of the last change.
    updated_by: Mapped[str] = mapped_column(String(80), default="")
