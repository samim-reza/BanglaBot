"""Self-serve signup, subscriptions and plan changes — routes and services on ``FakeDB``,
payments faked at the checkout port. Never a database, never a payment provider."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.crypto import lookup_hash
from app.core.ratelimit import backends
from app.db.session import get_db
from app.main import app
from app.models import Merchant, Signup, Subscription
from app.services import audit_service, catalog_plans, checkout_port, plan_service, signup_service, subscription_service
from app.services.pricing import build_quote
from tests.billing_fakes import isolate_catalog, reset_catalog
from tests.security_fakes import FakeDB, FakeSessionFactory, db_override, make_merchant

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
FORM = dict(
    business_name="Bright Smiles", owner_name="Dana Lee", email="Dana@Example.com", phone="+1 415 555 0100",
    password="sunny-molar-42-clinic", region="US", vertical="clinic", tier="growth", interval="month", addons={"whatsapp": 1},
)


@pytest.fixture(autouse=True)
def memory(monkeypatch):
    store = isolate_catalog(monkeypatch)
    backends.memory.reset()
    monkeypatch.setattr(audit_service, "session_factory", FakeSessionFactory())

    async def quiet(merchant, token):
        return None

    monkeypatch.setattr(signup_service, "_send_verification", quiet)
    yield store
    backends.memory.reset()
    reset_catalog()
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def checkouts(monkeypatch):
    made: list[dict] = []

    async def fake(db, **kw):
        made.append(kw)
        return checkout_port.Checkout(url="https://pay.example/p1", provider="dummy", provider_ref="dummy_p1", payment_id="p1")

    monkeypatch.setattr(checkout_port, "create_checkout", fake)
    return made


def client_with(db: FakeDB) -> TestClient:
    app.dependency_overrides[get_db] = db_override(db)
    return TestClient(app)


def of(db: FakeDB, model: type) -> list:
    return [row for row in db.added if isinstance(row, model)]


# ------------------------------------------------------------------ signup
def test_signup_creates_an_inactive_account_a_pending_subscription_and_a_checkout(checkouts):
    db = FakeDB()
    answer = client_with(db).post("/api/public/signup", json=FORM)
    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert body["checkout_url"] == "https://pay.example/p1" and body["status"] == "pending_payment"
    (merchant,), (sub,), (record,) = of(db, Merchant), of(db, Subscription), of(db, Signup)
    assert merchant.active is False and merchant.username == merchant.email == "dana@example.com"
    assert merchant.plan == "growth" and merchant.addons == {"_v": 1, "whatsapp": 1} and merchant.region == "US"
    assert merchant.password_hash.startswith("$argon2")
    assert (sub.status, sub.kind, sub.amount, sub.recurring_amount, body["reference"]) == ("pending", "signup", Decimal("198.00"), Decimal("198.00"), sub.id)
    assert sub.payment_ref == "p1" and checkouts[0]["amount"] == Decimal("198.00") and checkouts[0]["subscription_id"] == sub.id
    assert record.email_token_hash and record.email_token_enc.startswith("enc:") and record.subscription_id == sub.id
    assert any(getattr(row, "action", "") == "signup.created" for row in db.added) and db.commits == 1


def test_honeypot_gets_a_normal_answer_and_nothing_is_created(checkouts):
    db = FakeDB()
    answer = client_with(db).post("/api/public/signup", json={**FORM, "website": "http://spam.example"})
    assert answer.status_code == 201 and answer.json()["checkout_url"] == "" and answer.json()["reference"]
    assert db.added == [] and checkouts == []


@pytest.mark.parametrize("taken, detail", [(["m9"], "username is taken"), ([None, "m9"], "email already exists")])
def test_duplicate_username_or_email_is_refused(checkouts, taken, detail):
    answer = client_with(FakeDB(scalars=taken)).post("/api/public/signup", json=FORM)
    assert answer.status_code == 409 and detail in answer.json()["detail"]


@pytest.mark.parametrize(
    "change, status",
    [
        ({"password": "1234567890"}, 422),
        ({"password": "dana@example.com"}, 422),
        ({"email": "not-an-email"}, 422),
        ({"tier": "trial"}, 422),
        ({"tier": "enterprise"}, 422),
        ({"addons": {"google_calendar": 1}}, 422),  # already in Growth
        ({"region": "XX"}, 422),
        ({"vertical": "spaceships"}, 422),
    ],
)
def test_signup_validation(checkouts, change, status):
    answer = client_with(FakeDB()).post("/api/public/signup", json={**FORM, **change})
    assert answer.status_code == status, answer.text


def test_only_offered_verticals_can_sign_up_and_emails_are_rate_limited(checkouts, memory):
    memory.values[catalog_plans.VERTICALS_KEY] = {"keys": ["home_service"]}
    catalog_plans.install(memory.values)
    client = client_with(FakeDB())
    assert client.post("/api/public/signup", json=FORM).status_code == 422  # counts as an attempt for this email
    form = {**FORM, "vertical": "home_service"}
    assert [client.post("/api/public/signup", json=form).status_code for _ in range(3)] == [201, 201, 429]
    assert client.post("/api/public/signup", json={**form, "email": "other@example.com"}).status_code == 201


def test_quote_endpoint(checkouts):
    client = client_with(FakeDB())
    quote = client.post("/api/public/signup/quote", json={"tier": "starter", "interval": "year", "addons": {"minutes": 1}, "vertical": "clinic"})
    assert quote.status_code == 200 and quote.json()["total"] == 740.0  # 490 + 250
    assert client.post("/api/public/signup/quote", json={"tier": "starter", "addons": {"minutes": 99}}).status_code == 422


def test_payments_down_means_503_and_no_account(monkeypatch):
    async def down(db, **kw):
        raise checkout_port.PaymentsUnavailable("Online payment isn't available yet")

    monkeypatch.setattr(checkout_port, "create_checkout", down)
    db = FakeDB()
    assert client_with(db).post("/api/public/signup", json=FORM).status_code == 503
    assert db.rollbacks == 1 and db.commits == 0


# ------------------------------------------------------------------ payment → activation
def signup_rows(tier: str = "growth", extras: dict | None = None):
    merchant = make_merchant(id="m1", active=False, plan=tier, addons={"_v": 1, **(extras or {})}, vertical="clinic")
    sub = subscription_service.from_quote("m1", build_quote(tier, "month", extras or {}), kind="signup")
    record = Signup(id="s1", merchant_id="m1", subscription_id=sub.id, email="dana@example.com", status="pending_payment",
                    vertical="clinic", tier=tier, created_at=NOW)
    return merchant, sub, record


def paid(sub: Subscription, amount: str | None = None):
    return SimpleNamespace(id="p1", subscription_id=sub.id, amount=Decimal(amount or str(sub.amount)), currency="USD",
                           provider="dummy", status="paid", meta={})


async def test_payment_activates_the_subscription_and_the_signup_waits_for_the_admin():
    merchant, sub, record = signup_rows("growth", {"whatsapp": 1})
    db = FakeDB(merchant, sub, scalars=[record])
    assert await subscription_service.on_payment_paid(db, paid(sub), now=NOW) is sub
    assert sub.status == "active" and sub.payment_ref == "p1" and sub.payment_provider == "dummy"
    assert (sub.current_period_start, sub.current_period_end) == (NOW, datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc))
    assert record.status == "awaiting_approval" and record.paid_at == NOW and merchant.active is False
    assert await subscription_service.on_payment_paid(db, paid(sub), now=NOW) is sub  # a repeated event is harmless
    await signup_service.approve(db, record, by="a1")
    assert merchant.active is True and record.status == "approved" and record.decided_by == "a1"
    with pytest.raises(HTTPException):
        await signup_service.reject(db, record, by="a1")


async def test_auto_activation_and_verified_email_rule(memory):
    memory.values.update({catalog_plans.AUTO_ACTIVATE_KEY: {"enabled": True}, catalog_plans.VERIFIED_EMAIL_KEY: {"enabled": True}})
    catalog_plans.install(memory.values)
    merchant, sub, record = signup_rows()
    record.email_token_hash = lookup_hash("tok" * 8, purpose=signup_service.EMAIL_TOKEN_PURPOSE)
    db = FakeDB(merchant, sub, scalars=[record, record])
    await subscription_service.on_payment_paid(db, paid(sub), now=NOW)
    assert record.status == "awaiting_approval" and merchant.active is False  # email not verified yet
    answer = client_with(db).post("/api/public/signup/verify-email", json={"token": "tok" * 8})
    assert answer.status_code == 200 and answer.json() == {"verified": True, "status": "approved"}
    assert merchant.active is True and record.email_verified_at is not None and record.email_token_enc == ""


async def test_wrong_amount_does_not_activate_and_reject_cancels():
    merchant, sub, record = signup_rows()
    db = FakeDB(merchant, sub, scalars=[record])
    assert await subscription_service.on_payment_paid(db, paid(sub, "1.00"), now=NOW) is None
    assert sub.status == "pending"
    await signup_service.reject(db, record, by="a1", note="fraud")
    assert record.status == "rejected" and sub.status == "cancelled" and merchant.active is False


async def test_admin_can_approve_an_offline_payment():
    merchant, sub, record = signup_rows()
    db = FakeDB(merchant, sub)
    await signup_service.approve(db, record, by="a1", mark_paid=True, now=NOW)
    assert sub.status == "active" and sub.payment_provider == "manual" and merchant.active and record.paid_at == NOW


# ------------------------------------------------------------------ owner plan changes
def running(tier: str, extras: dict | None = None, interval: str = "month") -> Subscription:
    sub = subscription_service.from_quote("m1", build_quote(tier, interval, extras or {}), kind="signup")
    sub.status, sub.current_period_start, sub.current_period_end = "active", NOW - timedelta(days=10), NOW + timedelta(days=20)
    return sub


def test_change_rules_without_proration():
    starter, growth = running("starter"), running("growth")
    up = plan_service.decide(starter, build_quote("growth", "month"), NOW)
    assert (up.kind, up.due_now, up.effective) == ("upgrade", Decimal("100.00"), "on_payment")
    down = plan_service.decide(growth, build_quote("starter", "month"), NOW)
    assert (down.kind, down.due_now, down.effective_at) == ("downgrade", Decimal("0.00"), growth.current_period_end)
    assert plan_service.decide(None, build_quote("growth", "month"), NOW).due_now == Decimal("149.00")
    assert plan_service.decide(starter, build_quote("starter", "year"), NOW).kind == "new"  # interval change: new period
    assert plan_service.decide(starter, build_quote("starter", "month"), NOW).kind == "same"
    chat_web = running("starter", {"web_chat": 1})
    assert plan_service.decide(chat_web, build_quote("starter", "month", {"messenger": 1}), NOW).kind == "swap"
    with pytest.raises(HTTPException):
        plan_service.decide(growth, build_quote("starter", "month", {"setup": 1}), NOW)


def test_admin_set_up_account_is_not_charged_again_for_its_own_plan():
    # No subscription record: the admin created the account and bills it by hand.
    pro = make_merchant(id="m1", plan="pro", vertical="clinic", addons={"_v": 1, "minutes": 1, "setup": 1})
    assert plan_service.decide(None, build_quote("pro", "month", {"minutes": 1}), NOW, pro).kind == "same"
    assert plan_service.decide(None, build_quote("pro", "month"), NOW, pro).kind == "new"  # dropping an add-on is a change
    assert plan_service.decide(None, build_quote("growth", "month", {"minutes": 1}), NOW, pro).kind == "new"


async def test_upgrade_is_paid_then_applied_keeping_the_period(checkouts):
    merchant = make_merchant(id="m1", plan="starter", vertical="clinic")
    current = running("starter")
    db = FakeDB(merchant, current, scalars=[current])
    out = await plan_service.change(db, merchant, "growth", "month", {"sms": 1})
    assert out["checkout_url"] == "https://pay.example/p1" and out["change"]["kind"] == "upgrade" and out["change"]["due_now"] == 110.0
    (new,) = of(db, Subscription)
    assert new.amount == Decimal("110.00") and new.recurring_amount == Decimal("159.00") and new.replaces_id == current.id
    await subscription_service.on_payment_paid(db, paid(new), now=NOW)
    assert new.status == "active" and new.current_period_end == current.current_period_end
    assert current.status == "cancelled" and merchant.plan == "growth" and merchant.addons == {"_v": 1, "sms": 1}


async def test_downgrade_waits_for_the_period_end_and_cancel_ends_it():
    merchant = make_merchant(id="m1", plan="growth", addons={"_v": 1, "whatsapp": 1}, vertical="clinic")
    current = running("growth", {"whatsapp": 1})
    db = FakeDB(merchant, current, scalars=[current, current])
    out = await plan_service.change(db, merchant, "starter", "month", {})
    assert out["change"]["kind"] == "downgrade" and out["checkout_url"] is None and merchant.plan == "growth"
    assert current.scheduled_change["tier"] == "starter"
    await plan_service.set_cancel(db, merchant, True)
    db.scalars_queue.extend([[current], []])
    counts = await subscription_service.sweep(db, NOW + timedelta(days=21))
    assert counts == {"past_due": 0, "cancelled": 1, "downgraded": 1, "stale": 0}
    assert current.status == "cancelled" and merchant.plan == "starter" and merchant.addons == {"_v": 1}


async def test_plan_view_and_renewal(checkouts):
    merchant = make_merchant(id="m1", plan="starter", vertical="clinic")
    current = running("starter")
    current.status, current.current_period_end = "past_due", NOW - timedelta(days=1)
    db = FakeDB(merchant, current, scalars=[current])
    view = await plan_service.view(db, merchant)
    assert view["tier"]["key"] == "starter" and view["renewal"]["status"] == "past_due" and view["limits"]["max_concurrent_calls"] == 2
    db.scalar_queue.append(current)
    out = await plan_service.renew(db, merchant)
    (renewal,) = of(db, Subscription)
    assert out["checkout_url"] and renewal.kind == "renewal" and renewal.amount == Decimal("49.00")
    await subscription_service.on_payment_paid(db, paid(renewal), now=NOW)
    assert renewal.current_period_start == NOW and current.status == "cancelled"


def test_period_math():
    assert subscription_service.add_months(datetime(2026, 1, 31, tzinfo=timezone.utc), 1).day == 28
    assert subscription_service.period_end(NOW, "year") == datetime(2027, 10, 16, 12, 0, tzinfo=timezone.utc)
    assert subscription_service.period_end(NOW, "month", trial_days=14) == NOW + timedelta(days=14)


async def test_checkout_goes_through_the_payments_service_and_its_paid_hook(monkeypatch):
    from app.models import Payment
    from app.services.payments import service as payments

    made: dict = {}

    async def create_payment(db, **kw):
        made.update(kw)
        return Payment(id="pay9", merchant_id=kw["merchant_id"], subscription_id=kw["subscription_id"], kind=kw["kind"],
                       provider="dummy", provider_ref="dummy_pay9", amount=kw["amount"], currency="USD", status="pending",
                       url="https://app.example/pay/tok", meta={})

    monkeypatch.setattr(payments, "create_payment", create_payment)
    merchant, sub, record = signup_rows()
    db = FakeDB(merchant, sub, scalars=[record])
    checkout = await checkout_port.create_checkout(db, merchant_id="m1", subscription_id=sub.id, amount=sub.amount, currency="USD",
                                                   description="Growth plan", return_path=checkout_port.SIGNUP_RETURN_PATH)
    assert checkout.url == "https://app.example/pay/tok" and checkout.payment_id == "pay9"
    assert made["kind"] == "subscription" and made["success_url"].endswith(f"/signup/complete?reference={sub.id}")
    assert subscription_service.on_payment_paid in payments._paid_handlers["subscription"]
    payment = await create_payment(db, merchant_id="m1", subscription_id=sub.id, kind="subscription", amount=sub.amount)
    assert await payments.mark_paid(db, payment, source="dummy", now=NOW)  # the pay page's "paid"
    assert sub.status == "active" and sub.payment_ref == "pay9" and record.status == "awaiting_approval"
