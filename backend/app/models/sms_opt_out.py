from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id


class SmsOptOut(Base):
    """A number that replied STOP to one of our sending numbers (US carrier / 10DLC rules).

    One row per (sending number, customer number): texts from that sender to that number
    are skipped until the customer replies START. ``merchant_id`` is the account the STOP
    was meant for (the number's owner, or the last account that texted them from a shared
    number); its texts are skipped from any sender.
    """

    __tablename__ = "sms_opt_outs"
    __table_args__ = (UniqueConstraint("sender_number", "phone", name="uq_sms_opt_outs_sender_phone"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    # Our number (E.164) the STOP was sent to.
    sender_number: Mapped[str] = mapped_column(String(32), default="")
    # The customer's number (E.164).
    phone: Mapped[str] = mapped_column(String(32), index=True)
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True, index=True)
    # The keyword they sent (STOP, UNSUBSCRIBE, ...).
    keyword: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
