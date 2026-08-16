from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    actor_role: Mapped[str] = mapped_column(String(10))  # admin|merchant|system
    actor_id: Mapped[str] = mapped_column(String, default="")
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    # Machine key, e.g. "signup", "login", "plan_changed", "entitlement_denied".
    action: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")  # Bengali human sentence
    merchant_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
