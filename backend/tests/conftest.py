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
    phone: str = "+8801700000000"
    email: str = ""
    support_phone: str = ""
    custom_greeting: str = ""
    language: str = "bn"
    supported_languages: list[str] = field(default_factory=lambda: ["bn", "en"])
    voice_persona: str = "female"
    verify_address: bool = False
    max_call_seconds: int = 0
    silence_hangup_secs: int = 10
    active: bool = True
    vertical: str = "ecommerce"
    vertical_config: dict = field(default_factory=dict)
    knowledge: str = ""
    inbound_number: str = ""
    region: str = "BD"
    timezone: str = "Asia/Dhaka"
    currency: str = "BDT"
    emergency_number: str = "999"


@dataclass
class FakeOrder:
    id: str = "o1"
    merchant_id: str = "m1"
    order_ref: str = "A-1"
    customer_name: str = "রাহিম উদ্দিন"
    customer_phone: str = "01711111111"
    address: str = "বাড়ি ১২, রোড ৫, ধানমন্ডি, ঢাকা"
    items_summary: str = "পাঞ্জাবি (L) x1"
    total_amount: Decimal = Decimal("1850.00")
    currency: str = "BDT"
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
