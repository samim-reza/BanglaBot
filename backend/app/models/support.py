from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


def _make_reference(context) -> str:
    """Human-friendly ticket reference derived from the ticket's own id.

    9 hex chars keep the unique-collision odds negligible (6 would reach ~50%
    around 4,800 tickets).
    """
    return "BB-" + context.get_current_parameters()["id"][:9].upper()


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(12), unique=True, default=_make_reference)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|answered|closed
    priority: Mapped[str] = mapped_column(String(8), default="normal")  # normal|urgent
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("support_tickets.id"), index=True)
    author_role: Mapped[str] = mapped_column(String(10))  # merchant|admin
    author_name: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
