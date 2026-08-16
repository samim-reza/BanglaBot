from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)  # "BB-{YYYYMM}-{4-digit seq}"
    amount_due: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(8), default="due")  # due|paid|void
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    line_items: Mapped[list] = mapped_column(JSON, default=list)  # list[{"label", "amount"}]
    payment_method: Mapped[str] = mapped_column(String(16), default="")  # bkash|manual|""
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
