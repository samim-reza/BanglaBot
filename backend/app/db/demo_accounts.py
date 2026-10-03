"""Demo accounts — one per business engine — for testing (``AUTO_SEED_DEMO_DATA=true``).

Idempotent by username: an account that already exists is left untouched, so
edits made in the portal survive restarts. All demo accounts are English, US
region (America/New_York, USD, 911) with the website chat widget enabled.

    shop / shop123                 e-commerce order confirmation   (Urban Threads)
    clinic / clinic123             doctor appointments              (CityCare Family Clinic)
    realestate / realestate123     real estate agency               (Keystone Realty)
    homeservice / homeservice123   home services                    (FixRight Home Services)
"""

from __future__ import annotations

import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.regions import region_defaults
from app.core.security import hash_password
from app.flows.timefmt import business_tz
from app.models import CatalogItem, Merchant, Order, OrderStatus

US = region_defaults("US")

#: Catalogs of the demo accounts (also used by scripts/simulate.py).
CLINIC_DOCTORS: list[tuple[str, dict[str, Any]]] = [
    ("Dr. Sarah Mitchell", {"specialty": "Family Medicine", "degrees": "MD", "days": ["mon", "tue", "wed", "thu", "fri"],
                            "start_time": "09:00", "end_time": "17:00", "slot_minutes": 20, "fee": 150,
                            "notes": "Sees adults and children for check-ups, colds, flu and chronic conditions."}),
    ("Dr. James Carter", {"specialty": "Pediatrics", "degrees": "MD, FAAP", "days": ["mon", "wed", "fri"],
                          "start_time": "10:00", "end_time": "16:00", "slot_minutes": 20, "fee": 140,
                          "notes": "Children from newborns to 17. Vaccinations and school physicals."}),
    ("Dr. Priya Nair", {"specialty": "Dermatology", "degrees": "MD", "days": ["tue", "thu", "sat"],
                        "start_time": "09:00", "end_time": "13:00", "slot_minutes": 15, "fee": 180,
                        "notes": "Skin, hair and nail conditions; acne; mole checks."}),
    ("Dr. Michael Chen", {"specialty": "Cardiology", "degrees": "MD, FACC", "days": ["mon", "thu"],
                          "start_time": "13:00", "end_time": "17:00", "slot_minutes": 30, "fee": 220,
                          "notes": "Referral preferred. ECG available on site."}),
]

REALTY_LISTINGS: list[tuple[str, dict[str, Any]]] = [
    ("3-bed family home, Maple Grove", {"listing_type": "sale", "property_type": "house", "location": "Maple Grove",
                                        "size": "2,100 sq ft", "price": 485000, "bedrooms": 3,
                                        "features": "Renovated kitchen, fenced backyard, two-car garage, near schools"}),
    ("2-bed apartment, Riverside Towers", {"listing_type": "sale", "property_type": "flat", "location": "Riverside",
                                           "size": "1,150 sq ft", "price": 329000, "bedrooms": 2,
                                           "features": "River view, gym and pool, 24-hour concierge"}),
    ("Modern 1-bed condo, Downtown", {"listing_type": "rent", "property_type": "flat", "location": "Downtown",
                                      "size": "720 sq ft", "price": 2100, "bedrooms": 1,
                                      "features": "Walk to the metro, in-unit laundry, pets allowed"}),
    ("Half-acre building lot, Oak Hills", {"listing_type": "sale", "property_type": "land", "location": "Oak Hills",
                                           "size": "0.5 acre", "price": 145000,
                                           "features": "Zoned residential, utilities at the street, quiet cul-de-sac"}),
    ("Retail unit, Main Street", {"listing_type": "rent", "property_type": "commercial", "location": "Main Street",
                                  "size": "1,400 sq ft", "price": 3800, "price_note": "per month, plus utilities",
                                  "features": "Corner unit, high foot traffic, storefront glass"}),
]

HOME_SERVICES: list[tuple[str, dict[str, Any]]] = [
    ("AC repair & servicing", {"category": "HVAC", "visit_charge": 89, "price_from": 120, "price_to": 450,
                               "duration": "1-2 hours", "notes": "Refrigerant recharge priced separately."}),
    ("Plumbing", {"category": "Plumbing", "visit_charge": 79, "price_from": 100, "price_to": 600,
                  "duration": "1-3 hours", "notes": "Leaks, clogs, water heaters, fixtures."}),
    ("Electrical", {"category": "Electrical", "visit_charge": 85, "price_from": 90, "price_to": 500,
                    "duration": "1-2 hours", "notes": "Outlets, breakers, lighting, ceiling fans."}),
    ("Deep cleaning", {"category": "Cleaning", "visit_charge": 49, "price_from": 150, "price_to": 350,
                       "duration": "3-5 hours", "notes": "Priced by home size; supplies included."}),
    ("Appliance repair", {"category": "Appliances", "visit_charge": 75, "price_from": 90, "price_to": 300,
                          "duration": "1-2 hours", "notes": "Washers, dryers, fridges, ovens."}),
]



def _next_weekday(start: datetime, weekdays: set[int]) -> datetime:
    day = start + timedelta(days=1)
    while day.weekday() not in weekdays:
        day += timedelta(days=1)
    return day


async def _account(session: AsyncSession, *, username: str, password: str, **fields: Any) -> Merchant | None:
    """Create the account unless it exists; returns the new account or None."""
    existing = await session.scalar(select(Merchant).where(Merchant.username == username))
    if existing is not None:
        return None
    merchant = Merchant(
        username=username,
        password_hash=hash_password(password),
        language="en",
        supported_languages=["en", "bn"],
        voice_persona="female",
        widget_enabled=True,
        widget_key=secrets.token_urlsafe(18),
        sms_settings={"enabled": True, "on_booking": True, "on_change": True, "reminder_hours": 24},
        calendar_token=secrets.token_urlsafe(24),
        calendar_settings={},
        plan="growth",
        **US,
        **fields,
    )
    session.add(merchant)
    await session.flush()
    return merchant


def _items(merchant: Merchant, kind: str, rows: list[tuple[str, dict[str, Any]]]) -> list[CatalogItem]:
    return [
        CatalogItem(merchant_id=merchant.id, kind=kind, name=name, data=data, active=True, sort_order=index)
        for index, (name, data) in enumerate(rows)
    ]


async def seed_shop(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="shop",
        password="shop123",
        business_name="Urban Threads",
        owner_name="Alex Morgan",
        email="shop@example.com",
        phone="+12125550100",
        vertical="ecommerce",
        verify_address=True,
        knowledge=(
            "Urban Threads is an online clothing store. Delivery takes 2-4 business days in the US. "
            "Cash on delivery is available for orders under $300. Returns are free within 30 days. "
            "Support hours: Monday to Saturday, 9am to 7pm Eastern."
        ),
        widget_settings={"title": "Urban Threads", "subtitle": "Questions about your order?", "color": "#111827"},
    )
    if merchant is None:
        return None
    session.add_all(
        [
            Order(
                merchant_id=merchant.id, kind="order", order_ref="UT-1001", customer_name="Emily Johnson",
                customer_phone="+14155550123", address="221 Pine Street, Apt 4B, San Francisco, CA 94104",
                items_summary="Denim jacket (M) x1, White tee x2", total_amount=Decimal("128.00"), currency="USD",
                status=OrderStatus.pending,
            ),
            Order(
                merchant_id=merchant.id, kind="order", order_ref="UT-1002", customer_name="Daniel Smith",
                customer_phone="+12125550187", address="48 W 21st Street, New York, NY 10010",
                items_summary="Running shoes size 10 x1", total_amount=Decimal("89.99"), currency="USD",
                status=OrderStatus.pending, notes="Leave with the doorman",
            ),
        ]
    )
    return merchant.username


async def seed_clinic(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="clinic",
        password="clinic123",
        business_name="CityCare Family Clinic",
        owner_name="Dr. Laura Bennett",
        email="clinic@example.com",
        phone="+16175550100",
        vertical="clinic",
        vertical_config={"booking_horizon_days": 21, "lead_minutes": 60},
        knowledge=(
            "Address: 450 Commonwealth Avenue, Suite 200, Boston, MA 02215, across from Kenmore station; free patient "
            "parking behind the building. Opening hours: Monday to Friday 8am-6pm, Saturday 9am-1pm, closed Sunday. "
            "We accept Aetna, Blue Cross Blue Shield, Cigna, UnitedHealthcare and Medicare; self-pay patients are welcome. "
            "New patients: please arrive 15 minutes early with a photo ID and insurance card. "
            "Cancellations: please give at least 24 hours notice. Lab results are discussed at a follow-up visit. "
            "Walk-ins are seen only for urgent issues, subject to availability."
        ),
        widget_settings={"title": "CityCare Family Clinic", "subtitle": "Book an appointment in a minute", "color": "#0f766e"},
    )
    if merchant is None:
        return None
    doctors = _items(merchant, "doctor", CLINIC_DOCTORS)
    session.add_all(doctors)
    await session.flush()
    tz = business_tz(US["timezone"])
    now = datetime.now(tz)
    first = _next_weekday(now, {0, 2, 4})  # Dr. Carter's days
    second = _next_weekday(now, {0, 1, 2, 3, 4})
    session.add_all(
        [
            Order(
                merchant_id=merchant.id, kind="appointment", customer_name="Olivia Brown", customer_phone="+16175550142",
                catalog_item_id=doctors[1].id, scheduled_at=datetime.combine(first.date(), time(10, 40), tzinfo=tz),
                items_summary="Dr. James Carter — Pediatrics", total_amount=Decimal("140"), currency="USD",
                details={"serial": 3, "doctor": "Dr. James Carter", "specialty": "Pediatrics", "reason": "School physical"},
                status=OrderStatus.pending,
            ),
            Order(
                merchant_id=merchant.id, kind="appointment", customer_name="Robert Wilson", customer_phone="+16175550199",
                catalog_item_id=doctors[0].id, scheduled_at=datetime.combine(second.date(), time(14, 20), tzinfo=tz),
                items_summary="Dr. Sarah Mitchell — Family Medicine", total_amount=Decimal("150"), currency="USD",
                details={"serial": 17, "doctor": "Dr. Sarah Mitchell", "specialty": "Family Medicine", "reason": "Follow-up"},
                status=OrderStatus.pending,
            ),
        ]
    )
    return merchant.username


async def seed_real_estate(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="realestate",
        password="realestate123",
        business_name="Keystone Realty",
        owner_name="Mark Davis",
        email="realestate@example.com",
        phone="+13055550100",
        vertical="real_estate",
        vertical_config={
            "visit_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
            "visit_start": "10:00",
            "visit_end": "18:00",
            "visit_slot_minutes": 60,
            "visit_capacity": 2,
            "booking_horizon_days": 14,
        },
        knowledge=(
            "Keystone Realty, 120 Harbor Drive, Miami, FL 33131. Office hours Monday to Saturday 9am-6pm. "
            "Buyers pay no agency fee; sellers pay a 5 percent commission, negotiable for listings above one million. "
            "We work with Sunrise Mortgage for pre-approvals. Viewings are with a licensed agent; please bring a photo ID. "
            "HOA fees and property taxes are shared by the agent at the viewing."
        ),
        widget_settings={"title": "Keystone Realty", "subtitle": "Find your next home", "color": "#1d4ed8"},
    )
    if merchant is None:
        return None
    listings = _items(merchant, "property", REALTY_LISTINGS)
    session.add_all(listings)
    await session.flush()
    session.add_all(
        [
            Order(
                merchant_id=merchant.id, kind="lead", customer_name="Jessica Martinez", customer_phone="+13055550161",
                catalog_item_id=listings[0].id, items_summary="Buy · house · Maple Grove · around 500k", currency="USD",
                details={"intent": "buy", "property_type": "house", "location": "Maple Grove", "budget": "around 500k",
                         "budget_max": 500000, "lead_score": "warm"},
                status=OrderStatus.pending, source="manual",
            ),
            Order(
                merchant_id=merchant.id, kind="lead", customer_name="Kevin Lee", customer_phone="+13055550177",
                items_summary="Rent · apartment · Downtown · up to 2,300 a month", currency="USD",
                details={"intent": "rent", "property_type": "flat", "location": "Downtown", "budget": "up to 2,300 a month",
                         "budget_max": 2300, "lead_score": "cold"},
                status=OrderStatus.pending, source="manual",
            ),
        ]
    )
    return merchant.username


async def seed_home_service(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="homeservice",
        password="homeservice123",
        business_name="FixRight Home Services",
        owner_name="Tony Russo",
        email="homeservice@example.com",
        phone="+17185550100",
        vertical="home_service",
        vertical_config={
            "service_areas": ["Brooklyn", "Queens", "Manhattan", "Staten Island", "Jersey City"],
            "working_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
            "teams": 3,
            "booking_horizon_days": 7,
            "time_windows": [
                {"key": "morning", "start": "08:00", "end": "12:00"},
                {"key": "afternoon", "start": "12:00", "end": "16:00"},
                {"key": "evening", "start": "16:00", "end": "19:00"},
            ],
        },
        knowledge=(
            "FixRight is licensed and insured in New York and New Jersey. All repairs carry a 90-day workmanship warranty. "
            "We accept cards, Apple Pay and cash; payment after the job is done. The call-out charge is waived if you go ahead "
            "with the repair. Technicians call 30 minutes before arriving. Same-day visits depend on availability."
        ),
        widget_settings={"title": "FixRight Home Services", "subtitle": "Book a technician", "color": "#c2410c"},
    )
    if merchant is None:
        return None
    services = _items(merchant, "service", HOME_SERVICES)
    session.add_all(services)
    await session.flush()
    tz = business_tz(US["timezone"])
    now = datetime.now(tz)
    day = _next_weekday(now, {0, 1, 2, 3, 4, 5})
    session.add_all(
        [
            Order(
                merchant_id=merchant.id, kind="booking", customer_name="Maria Garcia", customer_phone="+17185550133",
                address="315 Atlantic Avenue, Apt 2, Brooklyn, NY 11201", catalog_item_id=services[0].id,
                scheduled_at=datetime.combine(day.date(), time(8, 0), tzinfo=tz), items_summary="AC repair & servicing",
                total_amount=Decimal("89"), currency="USD",
                details={"problem": "AC blowing warm air", "area": "Brooklyn", "time_window": "morning", "service": "AC repair & servicing"},
                status=OrderStatus.pending,
            ),
            Order(
                merchant_id=merchant.id, kind="booking", customer_name="David Thompson", customer_phone="+17185550148",
                address="88-12 35th Avenue, Jackson Heights, Queens, NY 11372", catalog_item_id=services[1].id,
                scheduled_at=datetime.combine(day.date(), time(12, 0), tzinfo=tz), items_summary="Plumbing",
                total_amount=Decimal("79"), currency="USD",
                details={"problem": "Kitchen sink blocked", "area": "Queens", "time_window": "afternoon", "service": "Plumbing"},
                status=OrderStatus.pending,
            ),
        ]
    )
    return merchant.username


async def seed_demo_accounts(session: AsyncSession) -> list[str]:
    created: list[str] = []
    for seed in (seed_shop, seed_clinic, seed_real_estate, seed_home_service):
        username = await seed(session)
        if username:
            created.append(username)
    await session.commit()
    return created


__all__ = ["seed_demo_accounts"]
