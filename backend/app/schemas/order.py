from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    """A record (order / appointment / lead / booking). Columns are top-level;
    vertical-specific fields may be top-level too or under ``details`` — both are
    validated against the account's vertical field specs."""

    model_config = ConfigDict(extra="allow")

    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str = Field(min_length=1, max_length=32)
    order_ref: str = Field(default="", max_length=60)
    address: str = Field(default="", max_length=2000)
    items_summary: str = Field(default="", max_length=2000)
    total_amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str = Field(default="", max_length=2000)
    scheduled_at: datetime | None = None
    catalog_item_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

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
    model_config = ConfigDict(extra="allow")

    order_ref: str | None = Field(default=None, max_length=60)
    customer_name: str | None = Field(default=None, min_length=1, max_length=120)
    customer_phone: str | None = Field(default=None, min_length=1, max_length=32)
    address: str | None = Field(default=None, max_length=2000)
    items_summary: str | None = Field(default=None, max_length=2000)
    total_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    scheduled_at: datetime | None = None
    catalog_item_id: str | None = None
    details: dict[str, Any] | None = None
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
    direction: str = "outbound"
    flow: str = ""
    caller_number: str = ""
    twilio_call_sid: str
    recording_sid: str
    call_status: str
    outcome: str
    transcript: str
    language: str
    duration_secs: int
    final_node: str
    llm_prompt_tokens: int = 0
    llm_cached_tokens: int = 0
    llm_completion_tokens: int = 0
    tts_chars: int = 0
    tts_cache_hits: int = 0
    created_at: datetime | None


class CallLogPage(BaseModel):
    items: list[CallLogOut]
    total: int
    page: int
    page_size: int


class OrderOut(BaseModel):
    id: str
    merchant_id: str
    kind: str = "order"
    source: str = "manual"
    order_ref: str
    customer_name: str
    customer_phone: str
    address: str
    items_summary: str
    total_amount: str
    currency: str
    status: str
    notes: str
    catalog_item_id: str | None = None
    catalog_item_name: str = ""
    scheduled_at: datetime | None = None
    details: dict[str, Any] = {}
    summary: str = ""
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


class BulkCallStart(BaseModel):
    """Which orders a "Call all" batch should dial (default: every callable one)."""

    statuses: list[OrderStatus] | None = None

    @field_validator("statuses")
    @classmethod
    def _statuses(cls, value: list[OrderStatus] | None) -> list[OrderStatus] | None:
        if value is None:
            return None
        from app.models.order import CALLABLE_STATUSES

        bad = [item.value for item in value if item not in CALLABLE_STATUSES]
        if bad:
            raise ValueError(f"cannot batch-call orders in status: {', '.join(bad)}")
        return list(dict.fromkeys(value))


class BulkCallRun(BaseModel):
    id: str
    state: str  # queued | running | done | cancelled | failed
    source: str  # manual | scheduled
    total: int
    started: int
    failed: int
    skipped: int
    error: str = ""
    created_at: datetime | None
    finished_at: datetime | None


class AutoCallSchedule(BaseModel):
    at: datetime | None = None
    repeat_daily: bool = False


class AutoCallScheduleUpdate(BaseModel):
    at: datetime
    repeat_daily: bool = False

    @field_validator("at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("at must include a timezone offset (send an ISO-8601 UTC timestamp)")
        return value


class BulkCallStatus(BaseModel):
    """Everything the Orders page needs to render the bulk-call controls."""

    eligible: int
    max_concurrent: int
    max_attempts: int
    run: BulkCallRun | None = None
    schedule: AutoCallSchedule


class OrderStats(BaseModel):
    pending: int = 0
    calling: int = 0
    confirmed: int = 0
    cancelled: int = 0
    no_answer: int = 0
    needs_review: int = 0
    total: int = 0
