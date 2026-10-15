from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class Subscription(Base):
    """One billing period bought for an account: a tier + add-ons for a month or a year.

    A new row is written for every purchase — the signup, an upgrade, a renewal —
    and the row it supersedes is cancelled when the new one activates.

    Finance: revenue = ``amount`` of rows with ``activated_at`` set (what was
    actually charged); MRR = ``recurring_amount`` of ``active`` rows (÷ 12 when
    ``interval`` is "year"). Written by ``app.services.subscription_service``.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_merchant_created", "merchant_id", "created_at"),
        Index("ix_subscriptions_status_created", "status", "created_at"),
        Index("ix_subscriptions_status_period_end", "status", "current_period_end"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    # Tier key (app/core/plans.py catalog) and the recurring add-ons {key: quantity} bought with it.
    tier: Mapped[str] = mapped_column(String(24))
    addons: Mapped[dict] = mapped_column(JSONB, default=dict)
    # month | year
    interval: Mapped[str] = mapped_column(String(8), default="month")
    # Charged when this row was paid (an upgrade charges the difference; one-off add-ons included).
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    # The price per interval going forward (what a renewal charges).
    recurring_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    # pending | active | past_due | cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # signup | change | renewal | manual
    kind: Mapped[str] = mapped_column(String(16), default="signup")
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The owner cancelled: the account keeps the tier until current_period_end, then it ends.
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    # A downgrade waiting for the period end: {"tier", "addons", "interval", "recurring_amount"}.
    scheduled_change: Mapped[dict] = mapped_column(JSONB, default=dict)
    # The quote this row was bought from (line items, one-off add-ons).
    line_items: Mapped[list] = mapped_column(JSONB, default=list)
    once_addons: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Payment: provider (dummy | stripe | manual | free) and its reference (payment id / session id).
    payment_provider: Mapped[str] = mapped_column(String(16), default="")
    payment_ref: Mapped[str] = mapped_column(String(255), default="", index=True)
    # The subscription this one supersedes when it activates.
    replaces_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
