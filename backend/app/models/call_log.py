from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id

#: Values ``CallLog.outcome`` may hold ("" while the call is still running).
OUTCOMES = ("confirmed", "cancelled", "transfer", "wrong_number", "relay", "unclear", "auto_dropped")


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    # Nullable: logs are detached (not deleted) when their order is deleted.
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    twilio_call_sid: Mapped[str] = mapped_column(String(64), index=True, default="")
    recording_sid: Mapped[str] = mapped_column(String(64), default="")
    call_status: Mapped[str] = mapped_column(String(32), default="initiated")
    outcome: Mapped[str] = mapped_column(String(32), default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(8), default="")
    duration_secs: Mapped[int] = mapped_column(Integer, default=0)
    final_node: Mapped[str] = mapped_column(String(32), default="")
    llm_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tts_chars: Mapped[int] = mapped_column(Integer, default=0)
    tts_cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
