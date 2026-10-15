from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class UsageEvent(Base):
    """One priced line of provider usage, append-only (the cost ledger).

    A call writes its lines once, at the end (telephony minutes, STT minutes,
    TTS characters, LLM tokens); SMS segments and payment fees are written as
    they happen. ``cost_usd`` is what the platform pays (0 on a free tier),
    ``list_cost_usd`` the paid list price of the same usage (the shadow cost /
    what a cache hit saved). Written by ``app.finance.ledger``.
    """

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_occurred_id", "occurred_at", "id"),
        Index("ix_usage_events_merchant_occurred", "merchant_id", "occurred_at"),
        Index("ix_usage_events_provider_occurred", "provider", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    # No FKs: the ledger outlives deleted accounts / calls.
    merchant_id: Mapped[str] = mapped_column(String, default="")
    call_log_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # telephony | stt | tts | llm | sms | payment | storage
    category: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))
    # e.g. voice_inbound, nova-3, aura-2, openai/gpt-oss-120b:input, sms_segment
    sku: Mapped[str] = mapped_column(String(120))
    # minute | char | token | segment | usd | txn | message
    unit: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    # USD per one unit actually charged (0 on a free tier / cache hit).
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 12), default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0)
    list_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=0)
    free_tier: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class UsageDaily(Base):
    """Usage per account, UTC day and provider SKU: what the finance dashboards read.

    Upserted (added to) whenever ledger lines are written (``app.finance.rollup``).
    """

    __tablename__ = "usage_daily"
    __table_args__ = (
        UniqueConstraint("merchant_id", "day", "category", "provider", "sku", name="uq_usage_daily_key"),
        Index("ix_usage_daily_day", "day"),
        Index("ix_usage_daily_merchant_day", "merchant_id", "day"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    merchant_id: Mapped[str] = mapped_column(String, default="")
    day: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))
    sku: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(16), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(16, 6), default=0)
    list_cost_usd: Mapped[Decimal] = mapped_column(Numeric(16, 6), default=0)
    # list − cost on cache-hit lines / on free-tier lines.
    cache_savings_usd: Mapped[Decimal] = mapped_column(Numeric(16, 6), default=0)
    free_tier_savings_usd: Mapped[Decimal] = mapped_column(Numeric(16, 6), default=0)
    events: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
