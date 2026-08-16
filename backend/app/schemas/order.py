from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus


class OrderCreate(BaseModel):
    order_ref: str = ""
    customer_name: str = Field(min_length=1)
    customer_phone: str = Field(min_length=6)
    address: str = ""
    items_summary: str = ""
    total_amount: Decimal = Decimal("0")
    notes: str = ""


class OrderUpdate(BaseModel):
    order_ref: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    address: str | None = None
    items_summary: str | None = None
    total_amount: Decimal | None = None
    notes: str | None = None
    status: OrderStatus | None = None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    merchant_id: str
    order_ref: str
    customer_name: str
    customer_phone: str
    address: str
    items_summary: str
    total_amount: Decimal
    status: OrderStatus
    notes: str
    call_attempts: int
    last_call_at: datetime | None
    created_at: datetime


class CallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str | None
    twilio_call_sid: str
    recording_sid: str
    call_status: str
    outcome: str
    transcript: str
    duration_secs: int
    created_at: datetime


class OrderDetail(OrderOut):
    call_logs: list[CallLogOut] = []
