from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class SalesInquiry(Base):
    """A "Talk to sales" / demo request from the public website."""

    __tablename__ = "sales_inquiries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    company: Mapped[str] = mapped_column(String(160), default="")
    business_type: Mapped[str] = mapped_column(String(40), default="")
    country: Mapped[str] = mapped_column(String(60), default="")
    monthly_calls: Mapped[str] = mapped_column(String(40), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    # new | contacted | demo | won | lost
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    admin_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
