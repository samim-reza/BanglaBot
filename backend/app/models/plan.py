from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


class Plan(Base):
    """A subscription plan merchants can be on (trial/starter/growth/...)."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)  # e.g. "trial","starter"
    name_bn: Mapped[str] = mapped_column(String(80))
    price_monthly: Mapped[float] = mapped_column(Numeric(10, 2), default=0)  # BDT
    max_calls_per_month: Mapped[int] = mapped_column(Integer)
    max_minutes_per_month: Mapped[int] = mapped_column(Integer)
    features: Mapped[list] = mapped_column(JSON, default=list)  # list[str], Bengali bullets
    trial_days: Mapped[int] = mapped_column(Integer, default=0)  # >0 => it's the trial plan
    is_default_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
