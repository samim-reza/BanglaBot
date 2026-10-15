from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class Payment(Base):
    """One payment link and what became of it: a booking's online payment, a
    subscription / add-on charge, or an owner's "mark as paid".

    The row's ``id`` is the reference handed to the provider (dummy token,
    Stripe ``client_reference_id``, owner link ``{ref}``). Written by
    ``app.services.payments``.
    """

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_merchant_created", "merchant_id", "created_at"),
        Index("ix_payments_status_hold", "status", "hold_until"),
        Index("ix_payments_status_expires", "status", "expires_at"),
        Index("ix_payments_provider_ref", "provider", "provider_ref"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    # The booking / order it pays for (detached, not deleted, with the record).
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    # A subscription / add-on charge (no FK: the subscriptions table belongs to billing).
    subscription_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # order | subscription | addon | other — picks the "paid" handlers.
    kind: Mapped[str] = mapped_column(String(16), default="order")
    # dummy | stripe | link (owner's own link) | manual (marked paid by the owner)
    provider: Mapped[str] = mapped_column(String(16), default="dummy")
    # Stripe Checkout Session id, ``dummy_<id>``, ...
    provider_ref: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    # pending | paid | failed | refunded | expired
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(String(200), default="")
    # An online-required booking is released when it is still unpaid at this time.
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The link stops working at this time (dummy / Stripe: 24 h).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # Small JSON context: payment_intent, paid_via, amount mismatches, ...
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
