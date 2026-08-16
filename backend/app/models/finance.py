from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


class CostRate(Base):
    """Date-versioned unit cost. Never edited in place — a rate change appends a
    new row; the effective rate is the newest row per cost_key."""

    __tablename__ = "cost_rates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    cost_key: Mapped[str] = mapped_column(String(40), index=True)
    label_bn: Mapped[str] = mapped_column(String(120), default="")
    unit: Mapped[str] = mapped_column(String(16), default="per_minute")  # per_minute|per_month
    rate_bdt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CallCost(Base):
    """Automatic cost attribution for one completed call, priced at the rates
    effective when the call finished."""

    __tablename__ = "call_costs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    call_log_id: Mapped[str] = mapped_column(ForeignKey("call_logs.id"), unique=True, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    duration_secs: Mapped[int] = mapped_column(Integer, default=0)
    billed_minutes: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    telephony_bdt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    stt_bdt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    tts_bdt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    llm_bdt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    total_bdt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
