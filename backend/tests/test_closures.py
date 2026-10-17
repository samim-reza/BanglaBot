"""Closure dates (holidays, a doctor's leave): validation, the engine's day questions, the phrases,
the agent's facts, the dashboard's after-hours rule and the Settings API — no database."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.flows import closures
from app.flows.closures import Closure, ClosureError, clean, closure_on, facts_line, parse, span_phrase
from app.flows.context import DIRECTION_INBOUND, CallContext, CatalogEntry
from app.flows.scheduling import Availability, Window, open_days
from app.flows.timefmt import business_tz
from app.verticals import flow_for

NY = business_tz("America/New_York")
TODAY = date(2026, 11, 20)  # a Friday
NOW = datetime(2026, 11, 20, 20, 0, tzinfo=NY)
THANKSGIVING = {"start": "2026-11-26", "end": "2026-11-26", "label": "Thanksgiving"}
HOLIDAYS = {"start": "2026-12-24", "end": "2026-12-26", "label": "Holidays"}


@dataclass
class Account:
    vertical: str = "clinic"
    business_name: str = "Bay Clinic"
    language: str = "en"
    region: str = "US"
    timezone: str = "America/New_York"
    currency: str = "USD"
    emergency_number: str = "911"
    custom_greeting: str = ""
    support_phone: str = ""
    knowledge: str = ""
    vertical_config: dict = field(default_factory=dict)
    id: str = "m-close"


# ---------------------------------------------------------------------------- validation
def test_clean_keeps_ranges_sorted_drops_ended_and_duplicates():
    stored = clean(
        [HOLIDAYS, {"start": "2026-11-26", "label": "  Thanksgiving  "}, THANKSGIVING, {"start": "2026-11-01", "end": "2026-11-19"}],
        today=TODAY,
    )
    assert stored == [
        {"start": "2026-11-26", "end": "2026-11-26", "label": "Thanksgiving", "item_id": ""},
        {"start": "2026-12-24", "end": "2026-12-26", "label": "Holidays", "item_id": ""},
    ]
    # A range that is still running is kept.
    assert clean([{"start": "2026-11-18", "end": "2026-11-21"}], today=TODAY)[0]["start"] == "2026-11-18"


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"start": "11/26/2026"}, "YYYY-MM-DD"),
        ({"start": "2026-02-30"}, "YYYY-MM-DD"),
        ({"start": "2026-12-26", "end": "2026-12-24"}, "before the start"),
        ({"start": "2029-01-01"}, "two years"),
        ({"start": "2026-12-01", "label": "x" * 61}, "60 characters"),
        ({"start": "2026-12-01", "item_id": "doc-gone"}, "no longer exists"),
        ("2026-12-01", "expected a start date"),
    ],
)
def test_clean_refuses_bad_entries(entry: Any, message: str):
    with pytest.raises(ClosureError, match=message):
        clean([entry], today=TODAY, item_ids=["doc-lee"])


def test_clean_caps_the_list_and_accepts_known_items():
    many = [{"start": (TODAY + timedelta(days=offset)).isoformat()} for offset in range(101)]
    with pytest.raises(ClosureError, match="Up to 100"):
        clean(many, today=TODAY)
    assert len(clean(many[:100], today=TODAY)) == 100
    assert clean([{"start": "2026-12-01", "item_id": "doc-lee"}], today=TODAY, item_ids=["doc-lee"])[0]["item_id"] == "doc-lee"
    with pytest.raises(ClosureError):
        clean({"start": "2026-12-01"}, today=TODAY)


def test_parse_skips_junk_and_ended_entries():
    raw = [THANKSGIVING, {"start": "nope"}, {"start": "2026-11-02"}, "x", {"start": "2026-12-05", "end": "2026-12-01"}]
    assert parse(raw, today=TODAY) == [Closure(date(2026, 11, 26), date(2026, 11, 26), "Thanksgiving")]
    assert len(parse(raw)) == 2  # without "today" an ended day is still a closure (the dashboard's history)
    assert parse(None) == [] and parse({"start": "2026-11-26"}) == []


# ---------------------------------------------------------------------------- questions
def test_the_whole_business_wins_over_one_persons_closure():
    mine = Closure(date(2026, 11, 26), date(2026, 11, 27), "Leave", "doc-lee")
    shop = Closure(date(2026, 11, 26), date(2026, 11, 26), "Thanksgiving")
    assert closure_on([mine, shop], date(2026, 11, 26), "doc-lee") == shop
    assert closure_on([mine, shop], date(2026, 11, 27), "doc-lee") == mine
    assert closure_on([mine, shop], date(2026, 11, 27), "doc-kim") is None
    assert closure_on([mine], date(2026, 11, 27)) is None  # a person's leave never closes the business


def test_free_slots_and_next_open_days_skip_closures():
    weekdays = Window(start=time(9), end=time(17), days=frozenset({"mon", "tue", "wed", "thu", "fri"}), step_minutes=60)
    shut = [Closure(date(2026, 11, 26), date(2026, 11, 26), "Thanksgiving"), Closure(date(2026, 11, 23), date(2026, 11, 24), "", "doc-lee")]
    availability = Availability(windows=[weekdays], item_id="doc-lee", horizon_days=14, closures=shut)
    assert availability.free(date(2026, 11, 26), now=NOW, booked={}) == []
    assert availability.free(date(2026, 11, 24), now=NOW, booked={}) == []
    assert availability.next_days(now=NOW, booked={}, limit=2) == [date(2026, 11, 25), date(2026, 11, 27)]
    # Another doctor is only shut by the business's closure.
    assert open_days([weekdays], now=NOW, horizon_days=14, item_id="doc-kim", closures=shut, limit=2) == [date(2026, 11, 23), date(2026, 11, 24)]


# ---------------------------------------------------------------------------- phrases
def test_span_phrases_say_the_day_or_the_range():
    assert span_phrase(date(2026, 11, 26), date(2026, 11, 26), TODAY) == "on Thursday, November 26"
    assert span_phrase(date(2026, 11, 26), date(2026, 11, 26), TODAY, month_first=False) == "on Thursday, 26 November"
    assert span_phrase(date(2026, 12, 24), date(2026, 12, 26), TODAY) == "from Thursday, December 24 to Saturday, December 26"
    assert span_phrase(TODAY, TODAY, TODAY) == "today" and span_phrase(date(2026, 11, 21), date(2026, 11, 21), TODAY) == "tomorrow"
    assert span_phrase(date(2026, 11, 18), date(2026, 11, 22), TODAY) == "from today to Sunday, November 22"


def test_facts_line_lists_business_closures_and_who_is_out():
    shut = parse([THANKSGIVING, HOLIDAYS, {"start": "2026-11-23", "item_id": "doc-lee"}, {"start": "2026-11-24", "item_id": "doc-gone"}])
    line = facts_line(shut, {"doc-lee": "Dr. Lee"})
    assert line == (
        "Closed — no bookings on these dates: Thu 2026-11-26 (Thanksgiving); Thu 2026-12-24 to Sat 2026-12-26 (Holidays). "
        "Dr. Lee not available: Mon 2026-11-23."
    )
    assert facts_line([]) == ""


def _ctx(config: dict, catalog: list[CatalogEntry] | None = None) -> CallContext:
    return CallContext(merchant=Account(vertical_config=config), catalog=list(catalog or []), direction=DIRECTION_INBOUND, now=NOW)


def test_both_prompt_profiles_carry_the_closures():
    from app.flows.runtime import FlowRuntime
    from app.pipeline.prompt import brief
    from app.voice.prompts import build_messages

    doctor = CatalogEntry("doc-lee", "D1", "doctor", "Dr. Lee", {"days": ["mon"], "start_time": "09:00", "end_time": "12:00"})
    ctx = _ctx({"closures": [THANKSGIVING, {"start": "2026-11-23", "item_id": "doc-lee"}]}, [doctor])
    flow = flow_for(ctx.merchant, DIRECTION_INBOUND)
    full = "\n".join(m["content"] for m in build_messages(flow, ctx, language="en", opening="Hello"))
    assert "Closed — no bookings on these dates: Thu 2026-11-26 (Thanksgiving)." in full and "Dr. Lee not available: Mon 2026-11-23." in full
    compact = brief(flow, FlowRuntime(flow, ctx, language="en"), ctx, "en", "are you open on thanksgiving?")
    assert "Thu 2026-11-26 (Thanksgiving)" in compact
    # Nothing coming up → no line at all; ended closures are gone.
    assert closures.call_facts(_ctx({"closures": [{"start": "2026-11-02"}]})) == []


def test_context_rereads_closures_when_the_settings_change():
    ctx = _ctx({"closures": [THANKSGIVING]})
    assert [c.label for c in ctx.closures] == ["Thanksgiving"]
    ctx.merchant.vertical_config = {"closures": [HOLIDAYS, {"start": "2026-11-23", "item_id": "doc-lee"}]}
    assert [c.label for c in ctx.closures] == ["", "Holidays"]
    assert [c.label for c in ctx.closures_for()] == ["Holidays"] and len(ctx.closures_for("doc-lee")) == 2


def test_dashboard_counts_closure_days_as_after_hours():
    from app.services.dashboard.queries import in_hours, local_time

    expr = in_hours(local_time("America/New_York"), {1: (time(9), time(17))}, [(date(2026, 11, 26), date(2026, 11, 26))])
    sql = str(expr.compile(dialect=postgresql.dialect()))
    assert "AS DATE) NOT BETWEEN" in sql
    assert str(in_hours(local_time("UTC"), {1: (time(9), time(17))}).compile(dialect=postgresql.dialect())).count("BETWEEN") == 0


# ---------------------------------------------------------------------------- the Settings API
class FakeDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def test_the_api_lists_and_replaces_closures(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_merchant
    from app.db.session import get_db
    from app.main import app
    from app.services import context_service

    merchant = SimpleNamespace(id="m-close", vertical="clinic", timezone="America/New_York", region="US", vertical_config={"slot_minutes": 20})
    db = FakeDB()

    async def catalog(_db, _merchant):  # noqa: ANN001, ANN202
        return [CatalogEntry("doc-lee", "D1", "doctor", "Dr. Lee"), CatalogEntry("svc-x", "S1", "service", "Not a person")]

    async def session():  # noqa: ANN202
        yield db

    monkeypatch.setattr(context_service, "load_catalog", catalog)
    monkeypatch.setattr(closures_route_module(), "_today", lambda m: TODAY)
    app.dependency_overrides[get_current_merchant] = lambda: merchant
    app.dependency_overrides[get_db] = session
    try:
        client = TestClient(app)
        body = client.get("/api/closures").json()
        assert body == {"closures": [], "items": [{"id": "doc-lee", "name": "Dr. Lee"}], "today": "2026-11-20"}
        saved = client.put("/api/closures", json={"closures": [HOLIDAYS, {"start": "2026-11-23", "item_id": "doc-lee"}]}).json()
        assert [row["start"] for row in saved["closures"]] == ["2026-11-23", "2026-12-24"] and db.commits == 1
        assert merchant.vertical_config["slot_minutes"] == 20 and len(merchant.vertical_config["closures"]) == 2
        bad = client.put("/api/closures", json={"closures": [{"start": "2026-12-26", "end": "2026-12-24"}]})
        assert bad.status_code == 422 and "before the start" in bad.json()["detail"]
        assert client.put("/api/closures", json={"closures": []}).json()["closures"] == []
        assert "closures" not in merchant.vertical_config
    finally:
        app.dependency_overrides.pop(get_current_merchant, None)
        app.dependency_overrides.pop(get_db, None)


def closures_route_module():  # noqa: ANN201
    from app.api.routes import closures as route

    return route
