"""Dashboard summary: business-local ranges, working hours per vertical, the after-hours SQL,
row → schema mapping and tenant scoping — all against a fake session (no database)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.flows.context import CatalogEntry
from app.flows.timefmt import business_tz
from app.services.dashboard import DEFAULT_HOURS, range_bounds, summary, working_hours
from app.services.dashboard.queries import call_stats, in_hours, local_time, ran_outbound, record_stats
from app.verticals import get_vertical

NY = business_tz("America/New_York")
NOW = datetime(2026, 10, 18, 3, 30, tzinfo=timezone.utc)  # Saturday 23:30 in New York


@dataclass
class Account:
    id: str = "m-dash"
    vertical: str = "clinic"
    timezone: str = "America/New_York"
    region: str = "US"
    currency: str = "usd"
    vertical_config: dict = field(default_factory=dict)
    auto_call_at: datetime | None = None


class Result:
    def __init__(self, row: Any = None, rows: list[Any] | None = None) -> None:
        self.row, self.rows = row, list(rows or [])

    def one(self) -> Any:
        return self.row

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    """Queued answers for ``execute`` / ``scalar`` / ``scalars``; every statement is kept."""

    def __init__(self, results: list[Result], *, scalar: Any = None, catalog: list[Any] | None = None) -> None:
        self.results = deque(results)
        self.scalar_value = scalar
        self.catalog = list(catalog or [])
        self.statements: list[Any] = []

    async def execute(self, stmt: Any, params: Any = None) -> Result:
        self.statements.append(stmt)
        return self.results.popleft()

    async def scalar(self, stmt: Any) -> Any:
        self.statements.append(stmt)
        return self.scalar_value

    async def scalars(self, stmt: Any) -> list[Any]:
        self.statements.append(stmt)
        return list(self.catalog)


def calls_row(**values: Any) -> SimpleNamespace:
    row = dict(calls_answered=0, chats_handled=0, after_hours=0, transfers_urgent=0, voice_secs=0, avg_secs=None)
    row.update(values)
    return SimpleNamespace(**row)


def records_row(**values: Any) -> SimpleNamespace:
    row = dict(bookings=0, bookings_value=0, messages_leads=0)
    row.update(values)
    return SimpleNamespace(**row)


def compiled(stmt: Any):
    return stmt.compile(dialect=postgresql.dialect())


def doctor(ref: str, days: list[str], start: str, end: str) -> CatalogEntry:
    return CatalogEntry(f"id-{ref}", ref, "doctor", f"Dr. {ref}", {"days": days, "start_time": start, "end_time": end})


@pytest.fixture(autouse=True)
def _fresh_catalog_cache():
    from app.services.context_service import invalidate_catalog

    invalidate_catalog("m-dash")
    yield
    invalidate_catalog("m-dash")


# ---------------------------------------------------------------------------- ranges
def test_today_starts_at_the_business_local_midnight():
    start, end = range_bounds("today", NY, NOW)
    assert end == NOW and start == datetime(2026, 10, 17, 0, 0, tzinfo=NY)
    assert start.utcoffset() == timedelta(hours=-4)


def test_rolling_ranges_and_unknown_keys():
    assert range_bounds("7d", NY, NOW) == (NOW - timedelta(days=7), NOW)
    assert range_bounds("30d", NY, NOW)[0] == NOW - timedelta(days=30)
    with pytest.raises(ValueError):
        range_bounds("year", NY, NOW)


# ---------------------------------------------------------------------------- working hours
def test_doctors_hours_merge_into_one_envelope_per_weekday():
    catalog = [doctor("D1", ["mon", "wed", "sat"], "17:00", "21:00"), doctor("D2", ["mon"], "09:00", "13:00")]
    hours, known = working_hours("clinic", {}, catalog)
    assert known and hours == {1: (time(9), time(21)), 3: (time(17), time(21)), 6: (time(17), time(21))}
    # A schedule without days is every day; dental and vet use their doctors too.
    hours, _ = working_hours("vet", {}, [doctor("V1", [], "08:00", "18:00")])
    assert sorted(hours) == [1, 2, 3, 4, 5, 6, 7]


def test_salon_staff_hours_else_the_salons_opening_hours():
    staff = [CatalogEntry("t1", "T1", "staff", "Maya", {"days": ["tue"], "start_time": "10:00", "end_time": "18:00"})]
    assert working_hours("salon", {"open_days": ["mon"], "open_time": "08:00", "close_time": "20:00"}, staff)[0] == {2: (time(10), time(18))}
    service_only = [CatalogEntry("s1", "S1", "service", "Haircut", {"days": ["sun"], "start_time": "06:00", "end_time": "07:00"})]
    assert working_hours("salon", {"open_days": ["mon"], "open_time": "08:00", "close_time": "20:00"}, service_only)[0] == {1: (time(8), time(20))}


def test_restaurant_home_service_real_estate_and_custom_hours():
    restaurant = get_vertical("restaurant").config(Account(vertical="restaurant"))
    assert working_hours("restaurant", restaurant)[0] == {day: (time(11), time(22)) for day in range(1, 8)}
    home = {"working_days": ["mon", "fri"], "time_windows": [{"key": "a", "start": "08:00", "end": "12:00"}, {"key": "b", "start": "13:00", "end": "17:30"}]}
    assert working_hours("home_service", home)[0] == {1: (time(8), time(17, 30)), 5: (time(8), time(17, 30))}
    realty = {"visit_days": ["sat"], "visit_start": "10:00", "visit_end": "16:00"}
    assert working_hours("real_estate", realty)[0] == {6: (time(10), time(16))}
    rooms = [CatalogEntry("r1", "R1", "resource", "Room", {"days": ["thu"], "start_time": "07:00", "end_time": "09:00"})]
    assert working_hours("custom", {}, rooms)[0] == {4: (time(7), time(9))}


def test_nothing_derivable_falls_back_to_weekdays_nine_to_five():
    assert working_hours("ecommerce", {}) == (DEFAULT_HOURS, False)
    assert working_hours("clinic", {}, [doctor("D1", ["mon"], "21:00", "09:00")]) == (DEFAULT_HOURS, False)  # overnight: skipped
    assert DEFAULT_HOURS == {day: (time(9), time(17)) for day in range(1, 6)}


# ---------------------------------------------------------------------------- SQL
def test_after_hours_is_one_weekday_or_expression_on_the_local_clock():
    sql = str(compiled(in_hours(local_time("America/New_York"), {1: (time(9), time(17)), 6: (time(10), time(14))})))
    assert sql.count("EXTRACT(isodow FROM timezone(") == 2 and " OR " in sql and "AS TIME" in sql
    assert str(compiled(in_hours(local_time("UTC"), {}))) == "false"


def test_every_statement_is_scoped_to_the_account():
    start, end = NOW - timedelta(days=7), NOW
    for stmt in (
        call_stats("m-dash", start, end, tz="UTC", hours=DEFAULT_HOURS, outbound=True),
        record_stats("m-dash", start, end),
        ran_outbound("m-dash", start),
    ):
        sql = compiled(stmt)
        assert "merchant_id = %(merchant_id_1)s" in str(sql) and sql.params["merchant_id_1"] == "m-dash"
    # Test traffic never counts: real directions only, agent-written records only.
    call_sql = compiled(call_stats("m-dash", start, end, tz="UTC", hours=DEFAULT_HOURS, outbound=False))
    assert "'web'" not in str(call_sql.params) and "out_calls" not in str(call_sql)
    assert "test" not in compiled(record_stats("m-dash", start, end)).params["source_1"]


# ---------------------------------------------------------------------------- the summary
@pytest.mark.asyncio
async def test_clinic_summary_maps_the_aggregate_rows():
    catalog = [SimpleNamespace(id="d1", kind="doctor", name="Dr. Lee", data={"days": ["mon"], "start_time": "09:00", "end_time": "17:00"}, sort_order=0)]
    db = FakeSession(
        [
            Result(calls_row(calls_answered=12, chats_handled=3, after_hours=5, transfers_urgent=2, voice_secs=1530, avg_secs=Decimal("127.6"))),
            Result(records_row(bookings=7, bookings_value=Decimal("840.5"), messages_leads=4)),
        ],
        scalar=False,
        catalog=catalog,
    )
    out = await summary(db, Account(), "7d", now=NOW)
    assert (out.calls_answered, out.chats_handled, out.after_hours, out.transfers_urgent) == (12, 3, 5, 2)
    assert (out.bookings, out.bookings_value, out.messages_leads) == (7, 840.5, 4)
    assert out.avg_call_secs == 128 and out.minutes_used == 25.5 and out.hours_known is True
    assert out.inbound_first is True and out.outbound is None and out.currency == "USD" and out.timezone == "America/New_York"
    assert out.start == NOW - timedelta(days=7) and out.range == "7d"
    # Catalog (doctors' hours), the outbound check, calls, records — each scoped to the account.
    assert len(db.statements) == 4
    for stmt in db.statements:
        assert compiled(stmt).params.get("merchant_id_1") == "m-dash"


@pytest.mark.asyncio
async def test_a_clinic_that_ran_reminder_calls_gets_the_outbound_section():
    out_row = calls_row(out_calls=9, out_confirmed=5, out_cancelled=1, out_no_answer=2, out_rescheduled=1, out_needs_review=0)
    db = FakeSession([Result(out_row), Result(records_row()), Result(rows=[("confirmed", 6), ("pending", 2)])], scalar=True)
    out = await summary(db, Account(), "today", now=NOW)
    assert out.outbound is not None and out.outbound.calls == 9 and out.outbound.no_answer == 2
    assert out.outbound.statuses["confirmed"] == 6 and out.outbound.statuses["total"] == 8
    assert out.avg_call_secs == 0 and out.minutes_used == 0.0


@pytest.mark.asyncio
async def test_ecommerce_is_outbound_first_without_looking_back():
    out_row = calls_row(out_calls=3, out_confirmed=2, out_cancelled=1, out_no_answer=0, out_rescheduled=0, out_needs_review=0)
    db = FakeSession([Result(out_row), Result(records_row()), Result(rows=[])])
    out = await summary(db, Account(vertical="ecommerce"), "30d", now=NOW)
    assert out.inbound_first is False and out.outbound is not None and out.outbound.confirmed == 2
    assert out.hours_known is False
    assert not any("EXISTS" in str(compiled(stmt)) for stmt in db.statements)


@pytest.mark.asyncio
async def test_salon_has_no_outbound_calls_and_never_asks():
    db = FakeSession([Result(calls_row()), Result(records_row())])
    out = await summary(db, Account(vertical="salon", vertical_config={"open_days": ["mon"]}), "7d", now=NOW)
    assert out.outbound is None and not any("EXISTS" in str(compiled(stmt)) for stmt in db.statements)


def test_the_route_validates_the_range(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_merchant
    from app.db.session import get_db
    from app.main import app
    from app.services import dashboard

    async def fake_summary(db, merchant, range_key, now=None):  # noqa: ANN001, ANN202
        return {"range": range_key, "start": NOW, "end": NOW, "timezone": "UTC", "currency": "USD", "inbound_first": True}

    async def no_db():  # noqa: ANN202
        yield None

    monkeypatch.setattr(dashboard, "summary", fake_summary)
    app.dependency_overrides[get_current_merchant] = lambda: Account()
    app.dependency_overrides[get_db] = no_db
    try:
        client = TestClient(app)
        assert client.get("/api/dashboard/summary?range=year").status_code == 422
        body = client.get("/api/dashboard/summary?range=today").json()
        assert body["range"] == "today" and body["calls_answered"] == 0 and body["outbound"] is None
        assert client.get("/api/dashboard/summary").json()["range"] == "7d"
    finally:
        app.dependency_overrides.pop(get_current_merchant, None)
        app.dependency_overrides.pop(get_db, None)
