from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class AuditEvent(Base):
    """Who did what, append-only: admin sign-ins, impersonation, admin user changes,
    password changes, settings that matter. Written by ``services.audit_service``."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_at_id", "at", "id"),
        Index("ix_audit_events_merchant_at", "merchant_id", "at"),
        Index("ix_audit_events_action_at", "action", "at"),
        Index("ix_audit_events_actor_at", "actor_id", "at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # admin | merchant | system
    actor_type: Mapped[str] = mapped_column(String(16), default="system")
    actor_id: Mapped[str] = mapped_column(String(80), default="")
    # Dotted verb, e.g. "admin.login", "merchant.password_changed".
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(80), default="")
    # The account the event concerns (filters the log per account); NULL = platform-level.
    merchant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    # Small JSON context (≤ 2 KB, secrets masked).
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
