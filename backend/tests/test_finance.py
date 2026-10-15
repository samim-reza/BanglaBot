"""Finance engine: meter math, free tiers + shadow cost, cache savings, rollups, revenue / margin,
price book versions, the cost guard, the failure-proof recorder and the admin API's role gate."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import memo
from app.db.session import get_db
from app.finance import accounts, export, guard, pricebook, recorder, revenue, rollup, sms_meter
from app.finance.meter import CallMeter, meter_call
from app.finance.periods import parse_month
from app.finance.reports import margin, project
from app.models import AdminUser
from tests.finance_fakes import FakeSession, db_dependency

D = Decimal
AT = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolated():
    memo.clear()
    guard.reset()
    yield
    guard.reset()
    revenue.use_subscription_source(None)


def book() -> pricebook.PriceBook:
    return pricebook.defaults_book()


def by_sku(lines):
    return {(line.provider, line.sku, line.cache_hit): line for line in lines}


# ------------------------------------------------------------------ meter → ledger lines
def test_llm_lines_split_input_cached_output_at_paid_prices():
    meter = CallMeter(book())
    meter.add_llm({"by_model": {"openai:gpt-5.4-mini": {"prompt_tokens": 10_000, "cached_tokens": 4_000, "completion_tokens": 500}}})
    lines = by_sku(meter.lines)
    assert lines[("openai", "gpt-5.4-mini:input", False)].quantity == 6_000
    assert lines[("openai", "gpt-5.4-mini:input", False)].cost_usd == D("0.0015")
    cached = lines[("openai", "gpt-5.4-mini:cached", True)]
    assert cached.cost_usd == D("0.0001") and cached.list_cost_usd == D("0.001") and cached.cache_savings == D("0.0009")
    assert lines[("openai", "gpt-5.4-mini:output", False)].cost_usd == D("0.001")
    totals = meter.totals()
    assert totals["cost_usd"] == D("0.0026") and totals["cache_savings_usd"] == D("0.0009") and totals["free_tier_savings_usd"] == 0


def test_free_tier_costs_nothing_but_keeps_the_shadow_list_cost():
    meter = CallMeter(book())
    meter.add_llm({"provider": "groq", "model": "openai/gpt-oss-120b", "prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
    assert all(line.free_tier and line.cost_usd == 0 for line in meter.lines)
    totals = meter.totals()
    assert totals["cost_usd"] == 0 and totals["list_cost_usd"] == D("0.75") and totals["free_tier_savings_usd"] == D("0.75")


def test_tts_cache_hits_are_free_and_counted_as_savings():
    meter = CallMeter(book())
    meter.add_tts({"providers": {"azure": {"chars": 1_000, "cached_chars": 3_000}}})
    lines = by_sku(meter.lines)
    assert lines[("azure", "neural-tts", False)].cost_usd == D("0.015")
    hit = lines[("azure", "neural-tts", True)]
    assert hit.cost_usd == 0 and hit.unit_cost == 0 and hit.list_cost_usd == D("0.045")
    assert meter.totals()["cache_savings_usd"] == D("0.045")


def test_phone_call_meter_telephony_stt_and_estimated_fallbacks():
    meter = meter_call(
        book(), direction="inbound", seconds=61, language="en",
        counters={"tts_chars": 2_000, "tts_cache_hits": 3, "llm_prompt_tokens": 1_000, "llm_completion_tokens": 100},
        stt_usage=[{"provider": "deepgram", "model": "nova-3", "audio_seconds": 50, "billed_seconds": 90}],
    )
    meter_lines = meter.lines
    lines = by_sku(meter_lines)
    voice = lines[("telnyx", "voice_inbound", False)]
    assert voice.quantity == 2 and voice.cost_usd == D("0.0110")  # billed per started minute
    assert lines[("telnyx", "media_streaming", False)].cost_usd == D("0.0070")
    stt = lines[("deepgram", "nova-3", False)]
    assert stt.quantity == D("1.5") and stt.cost_usd == D("0.01155")
    estimated = [line for line in meter_lines if line.meta.get("estimated")]
    assert {line.category for line in estimated} == {"tts", "llm"}
    cached_tts = next(line for line in estimated if line.category == "tts" and line.cache_hit)
    assert cached_tts.quantity == 3 * 48 and cached_tts.cost_usd == 0


def test_chat_has_no_telephony_or_speech_and_unknown_skus_are_flagged():
    meter = meter_call(book(), direction="widget", seconds=300, llm_stats={"by_model": {"groq:openai/gpt-oss-20b": {"prompt_tokens": 800, "completion_tokens": 50}}})
    assert {line.category for line in meter.lines} == {"llm"}
    odd = CallMeter(book())
    odd.add("stt", "acme", "turbo-9", 2)
    assert odd.unpriced == ["acme|turbo-9"] and odd.lines[0].meta["unpriced"] and odd.lines[0].cost_usd == 0
    dated = CallMeter(book())
    dated.add_llm({"by_model": {"openai:gpt-5.4-mini-2026-09-01": {"prompt_tokens": 1_000_000}}})
    assert dated.lines[0].cost_usd == D("0.25")  # versioned model ids price as their base model


def test_payment_fee_lines_use_fx():
    meter = CallMeter(book())
    meter.add_payment_fee(D("100"), "USD")
    assert meter.totals()["cost_usd"] == D("3.20")
    other = CallMeter(book())
    other.add_payment_fee(D("100"), "XYZ")
    assert other.totals()["cost_usd"] == D("0.30") and other.lines[0].meta["fx_unknown"]


# ------------------------------------------------------------------ rollups
def test_rollup_aggregates_lines_per_sku_and_day():
    first = CallMeter(book())
    first.add_tts({"provider": "azure", "chars": 1_000, "cached_chars": 1_000})
    second = CallMeter(book())
    second.add_tts({"provider": "azure", "chars": 3_000})
    second.add_llm({"provider": "groq", "model": "openai/gpt-oss-120b", "prompt_tokens": 1_000_000})
    rows = {(r["sku"]): r for r in rollup.aggregate(first.lines + second.lines, merchant_id="m1", occurred_at=AT)}
    tts = rows["neural-tts"]
    assert tts["day"] == date(2026, 10, 16) and tts["events"] == 3 and tts["quantity"] == D("5000.0000")
    assert tts["cost_usd"] == D("0.060000") and tts["cache_savings_usd"] == D("0.015000")
    llm = rows["openai/gpt-oss-120b:input"]
    assert llm["cost_usd"] == 0 and llm["free_tier_savings_usd"] == D("0.150000")


# ------------------------------------------------------------------ revenue + margin
def test_revenue_from_plan_addons_and_overage():
    from app.core.addons import CATALOG
    from app.core.plans import get_plan

    plan, minutes_addon = get_plan("starter"), CATALOG["minutes"]
    merchant = SimpleNamespace(id="m1", plan="starter", addons={"_v": 1, "minutes": 1}, active=True, created_at=AT)
    included = plan.included_minutes + minutes_addon.grants["minutes"]
    row = revenue.account_revenue(merchant, D(included + 50))
    assert row.overage_minutes == 50
    assert row.total_usd == (D(str(plan.price_month)) + D(str(minutes_addon.price)) + 50 * D(str(plan.overage_per_minute))).quantize(D("0.01"))
    assert revenue.account_revenue(SimpleNamespace(**{**merchant.__dict__, "active": False}), D(999)).total_usd == 0
    assert margin(D("100"), D("25")) == (75.0, 75.0) and margin(D("0"), D("5")) == (-5.0, None)


async def test_subscription_source_overrides_plan_revenue():
    async def source(db, ids, month):
        return {"m1": {"plan": "pro", "plan_usd": "300", "addons_usd": "0"}}

    revenue.use_subscription_source(source)
    merchant = SimpleNamespace(id="m1", plan="trial", addons={}, active=True, created_at=AT)
    later = SimpleNamespace(id="m2", plan="pro", addons={}, active=True, created_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
    rows = await revenue.revenue_for(None, [merchant, later], parse_month("2026-10"), {})
    assert list(rows) == ["m1"] and rows["m1"].plan == "pro" and rows["m1"].total_usd == D("300.00")


def test_subscription_rows_set_monthly_plan_revenue():
    from app.finance import subscriptions

    yearly = SimpleNamespace(merchant_id="m1", tier="pro", recurring_amount=D("1200"), interval="year", currency="USD")
    older = SimpleNamespace(merchant_id="m1", tier="starter", recurring_amount=D("49"), interval="month", currency="USD")
    monthly = SimpleNamespace(merchant_id="m2", tier="growth", recurring_amount=D("149"), interval="month", currency="USD")
    picked = subscriptions.pick([yearly, older, monthly])  # newest-activated first per account
    assert picked["m1"]["plan"] == "pro" and picked["m1"]["plan_usd"] == D("100") and picked["m2"]["plan_usd"] == D("149")
    merchant = SimpleNamespace(id="m1", plan="trial", addons={}, active=True, created_at=AT)
    assert revenue.account_revenue(merchant, D(0), picked["m1"]).total_usd == D("100.00")


def test_account_row_and_forecast_math():
    costs = [{"category": "telephony", "cost_usd": D("2"), "list_cost_usd": D("2"), "cache_savings_usd": D(0), "free_tier_savings_usd": D(0)},
             {"category": "sms", "cost_usd": D("1"), "list_cost_usd": D("1"), "cache_savings_usd": D(0), "free_tier_savings_usd": D(0)}]
    rev = revenue.AccountRevenue("m1", "starter", D("49"), D("0"), D("100"), D("0"), D("0"))
    row = accounts.account_row(SimpleNamespace(id="m1", business_name="A", vertical="clinic", active=True), {"seconds": 6000, "calls": 4}, costs, rev)
    assert row["cost_usd"] == 3.0 and row["revenue_usd"] == 49.0 and row["margin_usd"] == 46.0 and row["cost_per_minute_usd"] == 0.02
    month = parse_month("2026-10")
    assert month.days == 31 and parse_month("2026-12").end == date(2027, 1, 1)
    with pytest.raises(ValueError):
        parse_month("2026-13")
    assert project(D("10"), 0.5) == D("20") and project(D("10"), 1.0) == D("10") and project(D("10"), 0) == 0


# ------------------------------------------------------------------ price book versions
def test_pricebook_version_selection_by_date():
    versions = pricebook.parse_versions({"versions": [
        {"effective_from": "2026-11-01", "prices": {"openai|gpt-5.4-mini:input": {"unit_cost": "0.40"}, "groq|openai/gpt-oss-120b:input": {"free_tier": False}}},
        {"effective_from": "2026-10-01", "prices": {"openai|gpt-5.4-mini:input": {"unit_cost": "0.30"}}},
        {"effective_from": "junk", "prices": {}},
    ]})
    assert [v["effective_from"] for v in versions] == ["2026-10-01", "2026-11-01"]
    before = pricebook.build(versions, date(2026, 9, 30))
    assert before.get("openai", "gpt-5.4-mini:input").unit_cost == D("0.25") and before.version == 0
    october = pricebook.build(versions, date(2026, 10, 15))
    assert october.get("openai", "gpt-5.4-mini:input").unit_cost == D("0.30") and october.get("groq", "openai/gpt-oss-120b:input").free_tier
    november = pricebook.build(versions, date(2026, 11, 2))
    groq = november.get("groq", "openai/gpt-oss-120b:input")
    assert november.get("openai", "gpt-5.4-mini:input").unit_cost == D("0.40") and not groq.free_tier and november.version == 2
    assert november.effective_from == date(2026, 11, 1)


def test_pricebook_entries_are_validated():
    with pytest.raises(ValueError):
        pricebook.validate_entries([{"provider": "acme", "sku": "new-model", "unit_cost": "1"}])
    with pytest.raises(ValueError):
        pricebook.validate_entries([{"provider": "openai", "sku": "gpt-5.4-mini:input", "unit_cost": "-1"}])
    ok = pricebook.validate_entries([{"provider": "acme", "sku": "s1", "unit_cost": "2", "category": "stt", "unit": "minute"}])
    assert ok == {"acme|s1": {"unit_cost": "2", "category": "stt", "unit": "minute"}}


async def test_add_version_merges_same_day_and_drops_cache():
    session = FakeSession()
    await pricebook.add_version(session, effective_from=date(2026, 10, 20), entries=[{"provider": "azure", "sku": "neural-tts", "unit_cost": "16"}], updated_by="a1")
    await pricebook.add_version(session, effective_from=date(2026, 10, 20), entries=[{"provider": "deepgram", "sku": "aura-2", "unit_cost": "0.027"}], updated_by="a1")
    versions = await pricebook.load_versions(session)
    assert len(versions) == 1 and set(versions[0]["prices"]) == {"azure|neural-tts", "deepgram|aura-2"}
    current = await pricebook.current(session, date(2026, 10, 21))
    assert current.get("azure", "neural-tts").unit_cost == D("16")


# ------------------------------------------------------------------ cost guard
def test_cost_guard_caps(monkeypatch):
    monkeypatch.setattr(guard, "get_finance_settings", lambda: SimpleNamespace(provider_daily_caps_usd="openai=0.01, deepgram=bad"))
    assert guard.caps() == {"openai": D("0.01")}
    assert not guard.over_cap("openai") and not guard.over_cap("groq")
    guard.record_spend([SimpleNamespace(provider="openai", cost_usd=D("0.006"))] * 2)
    assert guard.over_cap("OpenAI")
    guard._admin_caps = guard.parse_admin_caps({"caps": {"openai": None, "groq": "0"}})
    assert not guard.over_cap("openai") and guard.over_cap("groq")  # null removes a cap, 0 blocks


# ------------------------------------------------------------------ recorder (failure-proof flush)
async def test_record_call_writes_lines_and_rollup_once():
    session = FakeSession()
    log = SimpleNamespace(id="c1", merchant_id="m1", direction="inbound", language="en", duration_secs=0)
    stats = {"by_model": {"openai:gpt-5.4-mini": {"prompt_tokens": 1000, "completion_tokens": 100}}}
    count = await recorder.record_call(session, log, {"duration_secs": 30, "tts_chars": 100}, llm_stats=stats, stt_usage=[{"provider": "deepgram", "audio_seconds": 30}], tts_usage={"provider": "azure", "chars": 100})
    assert count == 6 and session.commits == 1 and len(session.executed) == 2  # one INSERT + one upsert
    inserted = session.executed[0][1]
    assert {row["call_log_id"] for row in inserted} == {"c1"} and {row["category"] for row in inserted} == {"telephony", "stt", "tts", "llm"}
    assert guard.spent_today("openai") > 0
    again = FakeSession(scalar=["e1"])  # already metered
    assert await recorder.record_call(again, log, {"duration_secs": 30}) == 0 and not again.executed


async def test_scheduled_metering_runs_detached_on_its_own_session(monkeypatch):
    import asyncio

    from app.models import CallLog
    from tests.finance_fakes import Factory

    log = CallLog(id="c7", merchant_id="m1", direction="widget", language="en", duration_secs=0)
    session = FakeSession(log)
    monkeypatch.setattr(recorder, "session_factory", Factory(session))
    recorder.schedule_call("c7", {"duration_secs": 40}, llm_stats={"provider": "groq", "model": "openai/gpt-oss-20b", "prompt_tokens": 500, "completion_tokens": 40})
    assert recorder._pending
    await asyncio.gather(*list(recorder._pending))
    assert session.commits == 1 and {row["category"] for row in session.executed[0][1]} == {"llm"}
    assert await recorder.record_call_log("missing", {}) == 0
    recorder.schedule_call("c7", {})  # outside a loop it would be skipped, inside it never raises
    await asyncio.gather(*list(recorder._pending))


async def test_record_call_never_raises():
    session = FakeSession(fail_execute=True)
    log = SimpleNamespace(id="c1", merchant_id="m1", direction="outbound", language="en", duration_secs=60)
    assert await recorder.record_call(session, log, {"llm_prompt_tokens": 10}, llm_stats={"provider": "groq", "model": "openai/gpt-oss-20b", "prompt_tokens": 10}) == 0
    assert session.rollbacks == 1


def test_sms_lines_only_for_billable_messages():
    messages = [SimpleNamespace(id="s1", status="delivered", segments=2, kind="confirmation"),
                SimpleNamespace(id="s2", status="failed", segments=1, kind="reminder"),
                SimpleNamespace(id="s3", status="skipped", segments=1, kind="test")]
    priced = sms_meter.message_lines(messages, book())
    assert [m.id for m, _ in priced] == ["s1"] and priced[0][1][0].quantity == 2 and priced[0][1][0].cost_usd == D("0.0110")


def test_csv_cells_are_formula_safe():
    assert export.safe_cell("=HYPERLINK()") == "'=HYPERLINK()" and export.safe_cell("Clinic") == "Clinic" and export.safe_cell(5) == 5


# ------------------------------------------------------------------ admin API role gate
def test_finance_api_admits_finance_role_only():
    from app.core.security import issue_admin_token
    from app.main import app

    finance = AdminUser(id="f1", username="money", password_hash="", role="finance", totp_secret=None, totp_enabled=False, totp_last_step=0, token_version=0, active=True)
    support = AdminUser(id="s1", username="help", password_hash="", role="support", totp_secret=None, totp_enabled=False, totp_last_step=0, token_version=0, active=True)
    app.dependency_overrides[get_db] = db_dependency(FakeSession(finance, support))
    try:
        client = TestClient(app)

        def bearer(user):
            return {"Authorization": f"Bearer {issue_admin_token(sub=user.id, username=user.username, role=user.role)}"}

        assert client.get("/api/admin/finance/pricebook", headers=bearer(support)).status_code == 403
        response = client.get("/api/admin/finance/pricebook?at=2026-10-16", headers=bearer(finance))
        assert response.status_code == 200 and response.json()["version"] == 0
        assert any(p["key"] == "telnyx|voice_inbound" for p in response.json()["prices"])
        assert client.get("/api/admin/finance/overview?month=2026-13", headers=bearer(finance)).status_code == 422
        assert client.get("/api/admin/finance/overview").status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)
