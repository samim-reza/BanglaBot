import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


class OrderStatus(str, enum.Enum):
    pending = "pending"          # waiting for a confirmation call
    calling = "calling"          # confirmation call in progress
    confirmed = "confirmed"      # customer confirmed on the call
    cancelled = "cancelled"      # customer cancelled on the call
    no_answer = "no_answer"      # customer did not pick up
    needs_review = "needs_review"  # asked for a human / unclear outcome
    rescheduled = "rescheduled"  # courier: deliver another day — still callable


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    order_ref: Mapped[str] = mapped_column(String(60), default="")  # merchant's own order number
    customer_name: Mapped[str] = mapped_column(String(120))
    customer_phone: Mapped[str] = mapped_column(String(32))
    address: Mapped[str] = mapped_column(Text, default="")
    items_summary: Mapped[str] = mapped_column(Text, default="")  # e.g. "পাঞ্জাবি (L) x1, শাড়ি x2"
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="banglabot_order_status"), default=OrderStatus.pending, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    # Structured answers the flow agent collected on the last call
    # (delivery_time, new_address, note, ... — keys per service flow).
    flow_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    call_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
