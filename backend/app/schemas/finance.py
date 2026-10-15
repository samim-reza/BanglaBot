from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class MonthOut(BaseModel):
    month: str
    period_start: str
    period_end: str


class CategoryCost(BaseModel):
    category: str
    cost_usd: float
    list_cost_usd: float


class FinanceOverview(MonthOut):
    fraction_elapsed: float
    cost_usd: float
    list_cost_usd: float
    revenue_usd: float
    margin_usd: float
    margin_pct: float | None
    minutes: float
    calls: int
    chats: int
    #: Telephony + STT + TTS + LLM cost per phone minute (chats' LLM cost included).
    cost_per_minute_usd: float | None
    cache_savings_usd: float
    free_tier_savings_usd: float
    accounts: int
    paying_accounts: int
    by_category: list[CategoryCost]


class BreakdownItem(BaseModel):
    key: str
    label: str
    cost_usd: float
    list_cost_usd: float
    cache_savings_usd: float
    free_tier_savings_usd: float
    share_pct: float
    events: int
    category: str | None = None
    provider: str | None = None


class FinanceBreakdown(MonthOut):
    by: str
    total_cost_usd: float
    items: list[BreakdownItem]


class AccountFinance(BaseModel):
    merchant_id: str
    business_name: str
    vertical: str
    plan: str
    active: bool
    minutes: float
    calls: int
    chats: int
    cost_usd: float
    list_cost_usd: float
    revenue_usd: float
    margin_usd: float
    margin_pct: float | None
    cost_per_minute_usd: float | None
    cache_savings_usd: float
    free_tier_savings_usd: float
    revenue: dict[str, Any] | None = None


class AccountFinancePage(MonthOut):
    items: list[AccountFinance]
    next_cursor: str | None = None


class CostLine(BaseModel):
    category: str
    provider: str
    sku: str
    unit: str
    quantity: str
    unit_cost: str
    cost_usd: float
    list_cost_usd: float
    free_tier: bool
    cache_hit: bool
    meta: dict[str, Any] = Field(default_factory=dict)


class CallCosts(BaseModel):
    call_log_id: str
    merchant_id: str
    direction: str
    flow: str
    duration_secs: int
    created_at: datetime | None = None
    metered: bool
    lines: list[CostLine]
    cost_usd: float
    list_cost_usd: float
    cache_savings_usd: float
    free_tier_savings_usd: float
    by_category: dict[str, float]


class CategoryForecast(BaseModel):
    category: str
    cost_mtd_usd: float
    cost_forecast_usd: float


class FinanceForecast(MonthOut):
    fraction_elapsed: float
    cost_mtd_usd: float
    cost_forecast_usd: float
    revenue_mtd_usd: float
    revenue_forecast_usd: float
    margin_forecast_usd: float
    margin_forecast_pct: float | None
    minutes_mtd: float
    minutes_forecast: float
    by_category: list[CategoryForecast]


class PriceOut(BaseModel):
    key: str
    provider: str
    sku: str
    category: str
    unit: str
    per: int
    unit_cost: str
    list_price: str
    free_tier: bool
    increment_secs: int
    note: str


class PricebookVersion(BaseModel):
    effective_from: str
    prices: dict[str, dict[str, Any]]
    note: str = ""
    created_by: str = ""
    created_at: str = ""


class PricebookOut(BaseModel):
    #: The book in force on ``at``.
    at: str
    effective_from: str
    version: int
    prices: list[PriceOut]
    versions: list[PricebookVersion]


class PriceOverrideIn(BaseModel):
    provider: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_\-]+$")
    sku: str = Field(min_length=1, max_length=120)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    list_price: Decimal | None = Field(default=None, ge=0)
    free_tier: bool | None = None
    increment_secs: int | None = Field(default=None, ge=0, le=3600)
    note: str | None = Field(default=None, max_length=200)
    #: Required only for a SKU the defaults don't know.
    category: str | None = Field(default=None, max_length=16)
    unit: str | None = Field(default=None, max_length=16)
    per: int | None = Field(default=None, ge=1, le=1_000_000_000)


class PricebookPut(BaseModel):
    #: First day the new prices apply (default: today, UTC). Past dates re-price nothing already written.
    effective_from: date | None = None
    note: str = Field(default="", max_length=300)
    prices: list[PriceOverrideIn] = Field(min_length=1, max_length=200)


class ProviderCap(BaseModel):
    provider: str
    cap_usd: str | None
    spent_today_usd: str
    over_cap: bool


class CapsOut(BaseModel):
    items: list[ProviderCap]


class CapsPut(BaseModel):
    #: provider → daily USD cap; null removes the provider's cap (0 blocks it).
    caps: dict[str, Decimal | None] = Field(min_length=1, max_length=50)
