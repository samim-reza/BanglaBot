from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class Signup(Base):
    """A self-serve signup: the account (created inactive) waiting for payment, email
    verification and — unless ``signup.auto_activate`` is on — the admin's approval.

    The email-verification token is stored as a peppered hash (lookup) plus an
    encrypted copy so the admin can pass the link on while no mail provider is set.
    """

    __tablename__ = "signups"
    __table_args__ = (Index("ix_signups_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), unique=True, index=True)
    subscription_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(160), index=True)
    # pending_payment | awaiting_approval | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending_payment")
    vertical: Mapped[str] = mapped_column(String(32), default="")
    tier: Mapped[str] = mapped_column(String(24), default="")
    email_token_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    email_token_enc: Mapped[str] = mapped_column(String(255), default="")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    admin_note: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(80), default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
