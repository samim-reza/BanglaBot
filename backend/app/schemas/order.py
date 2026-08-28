from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.order import OrderStatus


def _clean_phone(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("customer_phone is required")
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 7:
        raise ValueError("customer_phone does not look like a phone number")
    return text


class OrderCreate(BaseModel):
    order_ref: str = Field(default="", max_length=60)
    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str = Field(min_length=1, max_length=32)
    address: str = Field(default="", max_length=2000)
    items_summary: str = Field(default="", max_length=2000)
    total_amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str = Field(default="", max_length=2000)

    @field_validator("customer_phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return _clean_phone(value)

    @field_validator("customer_name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("customer_name is required")
        return cleaned


class OrderUpdate(BaseModel):
    order_ref: str | None = Field(default=None, max_length=60)
    customer_name: str | None = Field(default=None, min_length=1, max_length=120)
    customer_phone: str | None = Field(default=None, min_length=1, max_length=32)
    address: str | None = Field(default=None, max_length=2000)
    items_summary: str | None = Field(default=None, max_length=2000)
    total_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    status: OrderStatus | None = None

    @field_validator("customer_phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return None if value is None else _clean_phone(value)

    @field_validator("status")
    @classmethod
    def _status(cls, value: OrderStatus | None) -> OrderStatus | None:
        if value == OrderStatus.calling:
            raise ValueError("status 'calling' is set by starting a call")
        return value


class CallLogOut(BaseModel):
    id: str
    order_id: str | None
    twilio_call_sid: str
    recording_sid: str
    call_status: str
    outcome: str
    transcript: str
    language: str
    duration_secs: int
    final_node: str
    created_at: datetime | None


class OrderOut(BaseModel):
    id: str
    merchant_id: str
    order_ref: str
    customer_name: str
    customer_phone: str
    address: str
    items_summary: str
    total_amount: str
    currency: str
    status: str
    notes: str
    flow_data: dict[str, Any]
    call_attempts: int
    last_call_at: datetime | None
    created_at: datetime | None


class OrderDetailOut(OrderOut):
    call_logs: list[CallLogOut]


class OrderPage(BaseModel):
    items: list[OrderOut]
    total: int
    page: int
    page_size: int


class OrderStats(BaseModel):
    pending: int = 0
    calling: int = 0
    confirmed: int = 0
    cancelled: int = 0
    no_answer: int = 0
    needs_review: int = 0
    total: int = 0
