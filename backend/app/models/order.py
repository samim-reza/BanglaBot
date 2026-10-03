import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class OrderStatus(str, enum.Enum):
    pending = "pending"  # waiting for a call (new order / scheduled appointment / new lead)
    calling = "calling"  # a call about it is in progress
    confirmed = "confirmed"  # confirmed / booked on a call
    cancelled = "cancelled"  # cancelled / not interested
    no_answer = "no_answer"  # nobody picked up / silent line
    needs_review = "needs_review"  # unclear, wrong number, relay, transfer, lead to follow up


#: Statuses a merchant may (re)start a confirmation call from.
CALLABLE_STATUSES = frozenset({OrderStatus.pending, OrderStatus.no_answer, OrderStatus.needs_review})


class Order(Base):
    """A record the agent calls about or that a call produced — an e-commerce
    order, a clinic appointment, a real-estate lead, a home-service booking, a
    message. ``kind`` says which; vertical-specific fields live in ``details``.
    (The table keeps its original name so existing databases keep working.)"""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    # order | appointment | lead | booking | message
    kind: Mapped[str] = mapped_column(String(24), default="order")
    # manual | inbound_call | outbound_call | test | import
    source: Mapped[str] = mapped_column(String(16), default="manual")
    # The doctor / listing / service it is about.
    catalog_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Appointment / viewing / visit time (UTC).
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    order_ref: Mapped[str] = mapped_column(String(60), default="")
    customer_name: Mapped[str] = mapped_column(String(120))
    customer_phone: Mapped[str] = mapped_column(String(32))
    address: Mapped[str] = mapped_column(Text, default="")
    items_summary: Mapped[str] = mapped_column(Text, default="")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="")
    # Same Postgres enum type name as the previous deployment so an existing
    # database keeps working; values are a strict subset.
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="banglabot_order_status"), default=OrderStatus.pending, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    # Slots the agent collected on the last call (identity, address, note, ...).
    flow_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    call_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
