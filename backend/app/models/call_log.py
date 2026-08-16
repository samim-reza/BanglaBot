from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    # Nullable: logs are detached (not deleted) when their order is deleted, so
    # usage metering keeps counting them against the merchant's quota.
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    twilio_call_sid: Mapped[str] = mapped_column(String(64), index=True, default="")
    # Twilio recording SID; empty until the recording-status webhook fires.
    recording_sid: Mapped[str] = mapped_column(String(64), default="")
    call_status: Mapped[str] = mapped_column(String(32), default="initiated")  # twilio call status
    outcome: Mapped[str] = mapped_column(String(32), default="")  # confirmed/cancelled/transfer/...
    transcript: Mapped[str] = mapped_column(Text, default="")
    duration_secs: Mapped[int] = mapped_column(Integer, default=0)
    # Voice tier snapshotted at call start — mid-month tier changes don't reprice old calls.
    voice_tier: Mapped[str] = mapped_column(String(20), default="")
    # Plan-quota seconds this call consumed (duration × tier multiplier).
    billed_secs: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
