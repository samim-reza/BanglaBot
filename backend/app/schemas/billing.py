from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ChangePlanRequest(BaseModel):
    plan_key: str


class AdminSubscriptionUpdate(BaseModel):
    plan_key: str | None = None
    status: str | None = None
    extend_days: int | None = None  # adds to current_period_end
    bonus_calls: int | None = None
    bonus_minutes: int | None = None
    note: str | None = None


class PlanCreate(BaseModel):
    key: str
    name_bn: str
    price_monthly: Decimal
    max_calls_per_month: int
    max_minutes_per_month: int
    features: list[str]
    trial_days: int = 0
    active: bool = True
    sort_order: int = 0


class PlanUpdate(BaseModel):
    name_bn: str | None = None
    price_monthly: Decimal | None = None
    max_calls_per_month: int | None = None
    max_minutes_per_month: int | None = None
    features: list[str] | None = None
    trial_days: int | None = None
    active: bool | None = None
    sort_order: int | None = None


class InvoiceGenerate(BaseModel):
    merchant_id: str


class InvoicePatch(BaseModel):
    status: str | None = None
    payment_method: str | None = None


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    name_bn: str
    price_monthly: Decimal
    max_calls_per_month: int
    max_minutes_per_month: int
    features: list[str]
    trial_days: int
    is_default_trial: bool
    active: bool
    sort_order: int
    created_at: datetime


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    merchant_id: str
    plan_key: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    bonus_calls: int
    bonus_minutes: int
    note: str
    canceled_at: datetime | None
    created_at: datetime


class UsageOut(BaseModel):
    calls_used: int
    minutes_used: int
    call_limit: int
    minute_limit: int


class BillingSummary(BaseModel):
    plan: PlanOut | None
    subscription: SubscriptionOut | None
    usage: UsageOut
    invoices_due: int
    bkash_number: str
    support_phone: str
    support_email: str


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    merchant_id: str
    number: str
    amount_due: Decimal
    status: str
    period_start: datetime
    period_end: datetime
    line_items: list[dict]
    payment_method: str
    paid_at: datetime | None
    created_at: datetime


class AdminInvoiceOut(InvoiceOut):
    merchant_name: str
