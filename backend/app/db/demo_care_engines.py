"""Demo accounts for the dental, vet and salon engines (same rules as :mod:`app.db.demo_accounts`).

    dental / dental123             dental practice                  (BrightSmile Dental)
    vet / vet123                   veterinary clinic                (Pawsitive Vet Clinic)
    salon / salon123               salon & spa: services + staff    (Glow Studio)
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.demo_accounts import US, _account, _items, _next_weekday
from app.flows.timefmt import business_tz
from app.models import Order, OrderStatus

#: Catalogs of the demo accounts (also used by scripts/simulate.py).
DENTISTS: list[tuple[str, dict[str, Any]]] = [
    ("Dr. Emily Park", {"specialty": "General Dentistry", "degrees": "DDS", "days": ["mon", "tue", "wed", "thu", "fri"],
                        "start_time": "08:00", "end_time": "16:00", "slot_minutes": 30, "fee": 95,
                        "notes": "Check-ups, cleanings, fillings, crowns. Sees children from age 3."}),
    ("Dr. Raj Patel", {"specialty": "Orthodontics", "degrees": "DMD, MS", "days": ["tue", "thu"],
                       "start_time": "10:00", "end_time": "18:00", "slot_minutes": 30, "fee": 150,
                       "notes": "Braces and clear aligners; free first consultation for teens."}),
    ("Dr. Lisa Gomez", {"specialty": "Pediatric Dentistry", "degrees": "DDS", "days": ["mon", "wed", "sat"],
                        "start_time": "09:00", "end_time": "14:00", "slot_minutes": 30, "fee": 90}),
]

VETS: list[tuple[str, dict[str, Any]]] = [
    ("Dr. Hannah Lee", {"specialty": "General Practice", "degrees": "DVM", "days": ["mon", "tue", "wed", "thu", "fri"],
                        "start_time": "09:00", "end_time": "17:00", "slot_minutes": 20, "fee": 80,
                        "notes": "Dogs and cats: check-ups, vaccinations, illness."}),
    ("Dr. Marcus Webb", {"specialty": "Exotics (birds, rabbits, reptiles)", "degrees": "DVM", "days": ["tue", "thu", "sat"],
                         "start_time": "10:00", "end_time": "15:00", "slot_minutes": 30, "fee": 95}),
]

SALON_SERVICES: list[tuple[str, dict[str, Any]]] = [
    ("Women's haircut", {"category": "Hair", "duration_minutes": 60, "price": 65, "staff": ["Maya", "Leo"], "notes": "Includes wash and blow-dry."}),
    ("Men's haircut", {"category": "Hair", "duration_minutes": 30, "price": 35, "staff": ["Leo", "Maya"]}),
    ("Balayage", {"category": "Color", "duration_minutes": 150, "price": 220, "staff": ["Maya"], "notes": "Patch test 48 hours before for new clients."}),
    ("Gel manicure", {"category": "Nails", "duration_minutes": 45, "price": 40, "staff": ["Ivy"]}),
    ("Deep tissue massage", {"category": "Spa", "duration_minutes": 60, "price": 95, "staff": ["Ivy"]}),
]
SALON_STAFF: list[tuple[str, dict[str, Any]]] = [
    ("Maya", {"days": ["tue", "wed", "thu", "fri", "sat"], "start_time": "10:00", "end_time": "19:00", "notes": "Colour specialist."}),
    ("Leo", {"days": ["mon", "tue", "wed", "thu", "fri"], "start_time": "09:00", "end_time": "17:00", "services": ["Women's haircut", "Men's haircut"]}),
    ("Ivy", {"days": ["wed", "thu", "fri", "sat", "sun"], "start_time": "11:00", "end_time": "19:00", "notes": "Nails and spa."}),
]


async def seed_dental(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="dental",
        password="dental123",
        business_name="BrightSmile Dental",
        owner_name="Dr. Emily Park",
        email="dental@example.com",
        phone="+16175550200",
        vertical="dental",
        vertical_config={"booking_horizon_days": 30, "lead_minutes": 60},
        knowledge=(
            "BrightSmile Dental, 88 Newbury Street, Boston, MA 02116. Open Monday to Friday 8am-6pm, Saturday 9am-2pm. "
            "We accept Delta Dental, Cigna, MetLife, Aetna and Guardian; we file claims for you. New patients get a full exam and "
            "cleaning in their first visit (about 60 minutes). Please give 24 hours notice to cancel. Same-day visits for toothache when available."
        ),
        widget_settings={"title": "BrightSmile Dental", "subtitle": "Book a check-up or cleaning", "color": "#0e7490"},
    )
    if merchant is None:
        return None
    dentists = _items(merchant, "doctor", DENTISTS)
    session.add_all(dentists)
    await session.flush()
    tz = business_tz(US["timezone"])
    day = _next_weekday(datetime.now(tz), {0, 1, 2, 3, 4})
    session.add(
        Order(
            merchant_id=merchant.id, kind="appointment", customer_name="Grace Kim", customer_phone="+16175550241",
            catalog_item_id=dentists[0].id, scheduled_at=datetime.combine(day.date(), time(9, 30), tzinfo=tz),
            items_summary="Dr. Emily Park — General Dentistry", total_amount=Decimal("95"), currency="USD",
            details={"serial": 4, "doctor": "Dr. Emily Park", "specialty": "General Dentistry", "reason": "Cleaning", "insurance": "Delta Dental"},
            status=OrderStatus.pending,
        )
    )
    return merchant.username


async def seed_vet(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="vet",
        password="vet123",
        business_name="Pawsitive Vet Clinic",
        owner_name="Dr. Hannah Lee",
        email="vet@example.com",
        phone="+17185550300",
        vertical="vet",
        vertical_config={"booking_horizon_days": 21, "lead_minutes": 60, "emergency_vet": "BluePearl Animal ER on 4th Avenue, open 24 hours"},
        knowledge=(
            "Pawsitive Vet Clinic, 410 Atlantic Avenue, Brooklyn, NY 11217. Open Monday to Friday 9am-6pm, Saturday 10am-3pm. "
            "Dogs and cats seen every day; birds, rabbits and reptiles with Dr. Webb. Vaccination packages from $65. "
            "Please bring dogs on a leash and cats in a carrier, and any previous vaccination records."
        ),
        widget_settings={"title": "Pawsitive Vet Clinic", "subtitle": "Book a visit for your pet", "color": "#15803d"},
    )
    if merchant is None:
        return None
    vets = _items(merchant, "doctor", VETS)
    session.add_all(vets)
    await session.flush()
    tz = business_tz(US["timezone"])
    day = _next_weekday(datetime.now(tz), {0, 1, 2, 3, 4})
    session.add(
        Order(
            merchant_id=merchant.id, kind="appointment", customer_name="Sam Rivera", customer_phone="+17185550341",
            catalog_item_id=vets[0].id, scheduled_at=datetime.combine(day.date(), time(10, 20), tzinfo=tz),
            items_summary="Dr. Hannah Lee — Bella (dog)", total_amount=Decimal("80"), currency="USD",
            details={"serial": 5, "doctor": "Dr. Hannah Lee", "specialty": "General Practice", "pet_name": "Bella", "species": "dog", "reason": "Vaccination"},
            status=OrderStatus.pending,
        )
    )
    return merchant.username


async def seed_salon(session: AsyncSession) -> str | None:
    merchant = await _account(
        session,
        username="salon",
        password="salon123",
        business_name="Glow Studio",
        owner_name="Maya Chen",
        email="salon@example.com",
        phone="+12125550400",
        vertical="salon",
        vertical_config={"booking_horizon_days": 30, "lead_minutes": 60, "slot_minutes": 15},
        knowledge=(
            "Glow Studio, 212 Bleecker Street, New York, NY 10012. Open Tuesday to Sunday; closed Mondays except for Leo's haircuts. "
            "Free consultation for colour clients. Street parking and a lot behind the building. "
            "Please give 24 hours notice to cancel or move a booking."
        ),
        widget_settings={"title": "Glow Studio", "subtitle": "Book hair, nails and spa", "color": "#be185d"},
    )
    if merchant is None:
        return None
    services = _items(merchant, "service", SALON_SERVICES)
    staff = _items(merchant, "staff", SALON_STAFF)
    session.add_all([*services, *staff])
    await session.flush()
    tz = business_tz(US["timezone"])
    day = _next_weekday(datetime.now(tz), {1, 2, 3, 4, 5})
    session.add(
        Order(
            merchant_id=merchant.id, kind="booking", customer_name="Olivia Hart", customer_phone="+12125550451",
            catalog_item_id=staff[0].id, scheduled_at=datetime.combine(day.date(), time(13, 0), tzinfo=tz),
            items_summary="Women's haircut — Maya", total_amount=Decimal("65"), currency="USD",
            details={"service": "Women's haircut", "service_id": services[0].id, "staff": "Maya", "duration_minutes": 60},
            status=OrderStatus.confirmed,
        )
    )
    return merchant.username


#: Seed per vertical key (scripts/simulate.py and the demo seeder).
CARE_SEEDS = {"dental": seed_dental, "vet": seed_vet, "salon": seed_salon}

__all__ = ["CARE_SEEDS", "DENTISTS", "SALON_SERVICES", "SALON_STAFF", "VETS", "seed_dental", "seed_salon", "seed_vet"]
