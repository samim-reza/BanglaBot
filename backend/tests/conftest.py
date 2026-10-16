"""Pure unit tests only: no database, no network. Everything external is a fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pytest


@dataclass
class FakeMerchant:
    id: str = "m1"
    business_name: str = "Demo Shop"
    owner_name: str = "Owner"
    username: str = "demo"
    phone: str = "+14155550100"
    email: str = ""
    support_phone: str = ""
    custom_greeting: str = ""
    language: str = "en"
    supported_languages: list[str] = field(default_factory=lambda: ["en"])
    voice_persona: str = "female"
    verify_address: bool = False
    max_call_seconds: int = 0
    silence_hangup_secs: int = 10
    active: bool = True
    vertical: str = "ecommerce"
    vertical_config: dict = field(default_factory=dict)
    knowledge: str = ""
    inbound_number: str = ""
    region: str = "US"
    timezone: str = "America/New_York"
    currency: str = "USD"
    emergency_number: str = "911"


@dataclass
class FakeOrder:
    id: str = "o1"
    merchant_id: str = "m1"
    order_ref: str = "A-1"
    customer_name: str = "Rahim Uddin"
    customer_phone: str = "4155550111"
    address: str = "12 Oak Street, Springfield"
    items_summary: str = "Cotton kurta (L) x1"
    total_amount: Decimal = Decimal("45.00")
    currency: str = "USD"
    status: str = "pending"
    notes: str = ""
    kind: str = "order"
    catalog_item_id: str | None = None
    scheduled_at: object = None
    details: dict = field(default_factory=dict)


@pytest.fixture
def merchant() -> FakeMerchant:
    return FakeMerchant()


@pytest.fixture
def order() -> FakeOrder:
    return FakeOrder()
