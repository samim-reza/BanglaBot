"""Data-driven tiers + add-ons: defaults, stored overrides, admin validation, entitlements
(incl. the new limits), channel states and quote math. No database: settings are in memory."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import addons
from app.core.entitlements import channel_states, entitlements
from app.core.plans import CHANNEL_INSTAGRAM, FLOW_FULL, FLOW_LINES, PLANS, get_plan
from app.schemas.plans import CatalogIn
from app.services import catalog_plans
from app.services.pricing import QuoteError, build_quote
from tests.billing_fakes import account, editor_payload, isolate_catalog, reset_catalog
from tests.security_fakes import FakeDB


@pytest.fixture(autouse=True)
def memory(monkeypatch):
    store = isolate_catalog(monkeypatch)
    yield store
    reset_catalog()


# ------------------------------------------------------------------ catalog defaults + overrides
def test_defaults_are_installed_and_pass_the_admin_validator():
    assert list(PLANS) == ["trial", "chat", "starter", "growth", "pro", "enterprise"]
    assert get_plan("nope").key == "trial" and get_plan("growth").price_month == 149
    assert get_plan("growth").yearly_price() == 1490  # 2 months free
    assert "instagram" in addons.CATALOG and not addons.CATALOG["concurrent_call"].visible
    checked = CatalogIn.model_validate(editor_payload())
    assert len(checked.tiers) == 6 and len(checked.addons) == len(addons.DEFAULT_CATALOG)


async def test_stored_catalog_overrides_defaults_and_fills_missing_fields(memory):
    memory.values[catalog_plans.PLANS_KEY] = {
        "tiers": [
            {"key": "trial", "name": "Trial", "price_month": 0, "included_minutes": 20, "overage_per_minute": 0,
             "included_chats": 10, "phone_numbers": 1, "tagline": ""},
            {"key": "starter", "price_month": 59, "limits": {"max_concurrent_calls": 3}},  # partial: rest from defaults
            {"key": "solo", "name": "Solo", "price_month": 19, "included_minutes": 30, "overage_per_minute": 0.4,
             "included_chats": 0, "phone_numbers": 1, "tagline": "Just you", "verticals": ["clinic"], "sort": 5},
        ]
    }
    memory.values[catalog_plans.ADDONS_KEY] = {"addons": [{"key": "sms", "price": 12}]}
    memory.values[catalog_plans.VERTICALS_KEY] = {"keys": ["clinic", "gone"]}
    memory.values[catalog_plans.AUTO_ACTIVATE_KEY] = {"enabled": True}
    await catalog_plans.load()
    assert list(PLANS) == ["trial", "solo", "starter"]
    starter = get_plan("starter")
    assert starter.price_month == 59 and starter.included_minutes == 150 and starter.limits.max_concurrent_calls == 3
    assert get_plan("growth").key == "trial"  # removed tiers fall back to the trial
    assert list(addons.CATALOG) == ["sms"] and addons.CATALOG["sms"].grants == {"sms": 500}
    assert catalog_plans.offered_verticals() == ["clinic"]
    assert catalog_plans.signup_settings()["auto_activate"] is True


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d["tiers"].pop(0), "trial"),
        (lambda d: d["tiers"].append(dict(d["tiers"][1])), "duplicate tier"),
        (lambda d: d["tiers"][2].update(channels=["voice", "fax"]), "unknown channel"),
        (lambda d: d["tiers"][1].update(limits={"max_concurrent_calls": 2}), "chat tier"),
        (lambda d: d["tiers"][2].update(verticals=["spaceships"]), "unknown vertical"),
        (lambda d: d["tiers"][2]["limits"].update(flow_editing="everything"), "flow_editing"),
        (lambda d: d["addons"][-1].update(grants={"minutes": 10}), "one-off"),
        (lambda d: d["addons"][0].update(grants={"gold": 1}), "unknown grant"),
        (lambda d: d["addons"].append({**d["addons"][0], "key": "web_chat_two"}), "one add-on per channel"),
        (lambda d: [t.update(visible=False) for t in d["tiers"]], "visible"),
    ],
)
def test_admin_catalog_validation(mutate, message):
    data = editor_payload()
    mutate(data)
    with pytest.raises(ValidationError) as info:
        CatalogIn.model_validate(data)
    assert message in str(info.value)


async def test_saving_refuses_to_delete_keys_in_use_and_installs_otherwise(memory):
    data = editor_payload()
    data["tiers"] = [tier for tier in data["tiers"] if tier["key"] != "pro"]
    in_use = FakeDB(scalars=["m7"])  # an account is still on Pro
    with pytest.raises(HTTPException) as info:
        await catalog_plans.save_catalog(in_use, CatalogIn.model_validate(data), by="a1")
    assert info.value.status_code == 422 and "tier pro" in info.value.detail
    data["tiers"][2]["price_month"] = 55  # starter
    result = await catalog_plans.save_catalog(FakeDB(), CatalogIn.model_validate(data), by="a1")
    assert result["removed"] == {"tiers": ["pro"], "addons": []}
    assert get_plan("starter").price_month == 55 and "pro" not in PLANS
    assert [key for key, _, by in memory.puts] == [catalog_plans.PLANS_KEY, catalog_plans.ADDONS_KEY] and memory.puts[0][2] == "a1"


def test_catalog_editor_needs_a_superadmin():
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/admin/plans/catalog").status_code == 401
    assert client.put("/api/admin/plans/catalog", json=editor_payload()).status_code == 401
    assert client.get("/api/admin/subscriptions").status_code == 401
    assert client.post("/api/admin/signups/m1/approve", json={}).status_code == 401
    assert client.put("/api/admin/verticals", json={"offered": ["clinic"]}).status_code == 401
    assert client.get("/api/plan").status_code == 401


def test_admin_puts_the_catalog_with_roles(monkeypatch):
    from app.core.security import issue_admin_token
    from app.db.session import get_db
    from app.main import app
    from app.models import AdminUser
    from app.services import audit_service
    from tests.security_fakes import FakeSessionFactory, db_override

    monkeypatch.setattr(audit_service, "session_factory", FakeSessionFactory())
    boss = AdminUser(id="a1", username="boss", password_hash="", role="superadmin", totp_enabled=False, token_version=0, active=True)
    helper = AdminUser(id="a2", username="help", password_hash="", role="support", totp_enabled=False, token_version=0, active=True)
    db = FakeDB(boss, helper)
    app.dependency_overrides[get_db] = db_override(db)
    try:
        client = TestClient(app)

        def bearer(user):
            return {"Authorization": f"Bearer {issue_admin_token(sub=user.id, username=user.username, role=user.role)}"}

        data = editor_payload()
        data["addons"][0]["price"] = 39
        assert client.put("/api/admin/plans/catalog", json=data, headers=bearer(helper)).status_code == 403
        saved = client.put("/api/admin/plans/catalog", json=data, headers=bearer(boss))
        assert saved.status_code == 200
        assert next(a for a in saved.json()["addons"] if a["key"] == "web_chat")["price"] == 39
        assert "options" in saved.json() and "defaults" in saved.json()
        assert any(getattr(row, "action", "") == "catalog.updated" for row in db.added)
        verticals = client.put("/api/admin/verticals", json={"offered": ["clinic", "home_service"]}, headers=bearer(boss)).json()
        assert {v["key"]: v["offered"] for v in verticals["items"]}["ecommerce"] is False
        assert client.get("/api/public/catalog").json()["verticals"][0]["key"] == "clinic"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_public_catalog_shows_visible_tiers_for_a_vertical(memory):
    from app.main import app

    client = TestClient(app)
    body = client.get("/api/public/catalog").json()
    keys = [plan["key"] for plan in body["plans"]]
    assert "trial" not in keys and keys[0] == "chat"
    assert next(p for p in body["plans"] if p["key"] == "enterprise")["checkout"] is False
    assert "concurrent_call" not in [a["key"] for a in body["addons"]]
    assert body["billing"] == {"currency": "USD", "intervals": ["month", "year"], "annual_months": 10}
    assert client.get("/api/public/catalog", params={"vertical": "spaceships"}).status_code == 422


# ------------------------------------------------------------------ entitlements
def test_entitlements_carry_the_new_limits():
    starter = entitlements(account("starter"))
    assert (starter.max_concurrent_calls, starter.flow_editing, starter.payments, starter.api_webhooks) == (2, FLOW_LINES, False, False)
    growth = entitlements(account("growth", {"concurrent_call": 2, "extra_language": 1}))
    assert growth.max_concurrent_calls == 6 and growth.flow_editing == FLOW_FULL and growth.payments and growth.custom_fields
    assert growth.languages == 2 and growth.has_feature("payments")
    assert entitlements(account("chat")).max_concurrent_calls == 0
    shape = entitlements(account("enterprise")).as_json()
    assert shape["limits"]["minutes"] is None and shape["limits"]["max_concurrent_calls"] == 20
    assert set(shape) >= {"plan", "product", "channels", "features", "addons", "limits", "capabilities"}


def test_an_add_on_can_unlock_a_capability():
    addons.install_addons([*addons.DEFAULT_CATALOG.values(), addons.Addon("pay", "Payments", "feature", 15, "month", "", feature="payments")])
    assert entitlements(account("starter", {"pay": 1})).payments is True
    assert entitlements(account("starter")).payments is False


def test_channel_states_for_the_channels_page():
    states = {row["channel"]: row for row in channel_states(account("starter", {"whatsapp": 1}))}
    assert states["voice"]["state"] == "included" and states["whatsapp"]["state"] == "addon"
    assert states[CHANNEL_INSTAGRAM]["state"] == "available" and states[CHANNEL_INSTAGRAM]["price_label"] == "$29 / mo"
    assert {row["channel"]: row["state"] for row in channel_states(account("chat"))}["voice"] == "unavailable"


# ------------------------------------------------------------------ quotes
def test_quote_math_monthly_yearly_and_quantities():
    monthly = build_quote("growth", "month", {"minutes": 2, "whatsapp": 1, "setup": 1})
    assert (monthly.recurring, monthly.one_time, monthly.total) == (Decimal("248.00"), Decimal("299.00"), Decimal("547.00"))
    assert monthly.addons == {"whatsapp": 1, "minutes": 2} and monthly.once == {"setup": 1}
    yearly = build_quote("growth", "year", {"minutes": 2, "setup": 1})
    assert (yearly.recurring, yearly.one_time) == (Decimal("1990.00"), Decimal("299.00"))  # 1490 + 2 × 250
    assert [item["period"] for item in yearly.as_json()["items"]] == ["year", "year", "once"]
    assert build_quote("starter", "month", {"setup": 1}, owned_once={"setup"}).total == Decimal("49.00")
    assert build_quote("starter", "month", {"minutes": 0}).addons == {}


@pytest.mark.parametrize(
    "tier, extras, message",
    [
        ("trial", {}, "isn't available"),
        ("enterprise", {}, "isn't available"),
        ("growth", {"google_calendar": 1}, "already included"),
        ("chat", {"minutes": 1}, "isn't available with"),
        ("starter", {"minutes": 51}, "at most 50"),
        ("starter", {"whatsapp": 2}, "at most 1"),
        ("starter", {"concurrent_call": 1}, "Unknown add-on"),
        ("starter", {"nope": 1}, "Unknown add-on"),
    ],
)
def test_quote_rejects_what_cant_be_bought(tier, extras, message):
    with pytest.raises(QuoteError) as info:
        build_quote(tier, "month", extras)
    assert message in str(info.value)


def test_quote_respects_verticals_and_interval():
    from dataclasses import replace

    from app.core.plans import install_plans

    install_plans([replace(p, verticals=("clinic",)) if p.key == "starter" else p for p in PLANS.values()])
    assert build_quote("starter", "month", vertical="clinic").total == Decimal("49.00")
    with pytest.raises(QuoteError):
        build_quote("starter", "month", vertical="ecommerce")
    with pytest.raises(QuoteError):
        build_quote("growth", "weekly")
    assert "starter" not in [t["key"] for t in catalog_plans.tiers_json(include_hidden=False, vertical="ecommerce")]
