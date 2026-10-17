"""Payments: dummy tokens + pay page, Stripe (signatures, Checkout via MockTransport), owner links,
booking links after a commit, the hold sweeper and the owner's mark-paid. Never a database."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import memo
from app.core.ratelimit import backends
from app.core.security import issue_merchant_token
from app.db.session import get_db
from app.models import Order, OrderStatus, Payment
from app.services import audit_service, notification_service, sms_service
from app.services.payments import holds, link, pay_page, records, service
from app.services.payments.base import PaymentError, PaymentEvent, WebhookSignatureError
from app.services.payments.dummy import DummyProvider, read_pay_token, sign_pay_token
from app.services.payments.stripe import StripeProvider, minor_units, parse_event, verify_signature
from tests.finance_fakes import Factory, FakeSession, db_dependency
from tests.security_fakes import FakeSessionFactory, make_merchant

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
SECRET = "whsec_test_secret"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    backends.memory.reset()
    memo.clear()
    monkeypatch.setattr(audit_service, "session_factory", FakeSessionFactory())
    yield
    monkeypatch.setattr(service, "session_factory", None)
    backends.memory.reset()


def booking(**overrides) -> Order:
    payment = {"mode": "online_required", "method": "online", "amount": 50.0, "currency": "USD", "status": "link_pending", "hold_minutes": 30}
    values = dict(
        id="o1", merchant_id="m1", kind="appointment", source="inbound_call", customer_name="Ana", customer_phone="+15550001111",
        order_ref="A-7", items_summary="Dr. Lee", total_amount=Decimal("50.00"), currency="USD", status=OrderStatus.pending,
        notes="", details={"payment": payment}, flow_data={}, payment_status="not_required", payment_ref="", payment_url="",
    )
    values.update(overrides)
    return Order(**values)


async def linked_booking(session: FakeSession, **overrides) -> tuple[Order, Payment]:
    record = booking(**overrides)
    session.put(record)
    payment = await service.create_payment(
        session, merchant_id="m1", amount=Decimal("50"), currency="USD", description="Clinic - Dr. Lee", order_id=record.id,
        hold_minutes=30, provider=DummyProvider(base_url="https://portal.test"), now=NOW,
    )
    records.apply_link(record, payment)
    return record, payment


# ------------------------------------------------------------------ dummy tokens
def test_pay_token_round_trip_and_tamper():
    token = sign_pay_token(reference="p1", amount=Decimal("12.5"), currency="usd")
    claims = read_pay_token(token)
    assert claims["reference"] == "p1" and claims["amount"] == Decimal("12.50") and claims["currency"] == "USD"
    body, sig = token.split(".", 1)
    with pytest.raises(PaymentError):
        read_pay_token(body + "." + ("0" if sig[0] != "0" else "1") + sig[1:])
    with pytest.raises(PaymentError):
        read_pay_token(sign_pay_token(reference="p1", amount=Decimal("1"), currency="USD", ttl_seconds=-10))


async def test_dummy_link_points_at_our_pay_page():
    link_ = await DummyProvider(base_url="https://portal.test/").create_link(reference="p9", amount=Decimal("5"), currency="USD", description="x", metadata={})
    assert link_.url.startswith("https://portal.test/pay/") and link_.provider == "dummy" and link_.provider_ref == "dummy_p9"
    assert read_pay_token(link_.url.rsplit("/", 1)[1])["reference"] == "p9"
    assert link_.expires_at and timedelta(hours=23) < link_.expires_at - datetime.now(timezone.utc) <= timedelta(hours=24)


async def test_dummy_complete_marks_paid_and_confirms_booking(monkeypatch):
    session = FakeSession(make_merchant(id="m1", business_name="Clinic"))
    record, payment = await linked_booking(session)
    paid: list[str] = []

    async def fake_after_paid(p):
        paid.append(p.id)

    monkeypatch.setattr(service, "after_paid", fake_after_paid)
    token = payment.url.rsplit("/", 1)[1]
    view = await pay_page.pay_view(session, token)
    assert view["amount"] == "50.00" and view["business"] == "Clinic" and view["reference"] == "A-7" and view["can_complete"]
    done = await pay_page.complete_dummy(session, token, now=NOW + timedelta(minutes=5))
    assert done["status"] == "paid" and payment.status == "paid" and paid == [payment.id]
    assert record.status == OrderStatus.confirmed and record.payment_status == "paid" and record.details["payment"]["status"] == "paid"
    again = await pay_page.complete_dummy(session, token, now=NOW + timedelta(minutes=6))
    assert again["status"] == "paid" and paid == [payment.id]  # idempotent


async def test_dummy_complete_refuses_expired_and_tampered(monkeypatch):
    session = FakeSession(make_merchant(id="m1"))
    _, payment = await linked_booking(session)
    token = payment.url.rsplit("/", 1)[1]
    with pytest.raises(PaymentError):
        # The link's expiry comes from the real clock: step past it, whatever today is.
        await pay_page.complete_dummy(session, token, now=payment.expires_at + timedelta(minutes=1))
    payment.amount = Decimal("1.00")  # the row no longer matches the signed amount
    with pytest.raises(PaymentError):
        await pay_page.pay_view(session, token)


def test_pay_routes_404_for_bad_token_and_rate_limit(monkeypatch):
    from app.main import app

    app.dependency_overrides[get_db] = db_dependency(FakeSession())
    try:
        client = TestClient(app)
        bad = "x" * 40
        assert client.get(f"/api/public/pay/{bad}").status_code == 404
        codes = [client.post(f"/api/public/pay/{bad}/complete").status_code for _ in range(11)]
        assert codes[:10] == [404] * 10 and codes[10] == 429
    finally:
        app.dependency_overrides.pop(get_db, None)


# ------------------------------------------------------------------ Stripe
def _stripe_header(payload: bytes, *, secret: str = SECRET, at: int | None = None) -> str:
    stamp = int(time.time()) if at is None else at
    sig = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={sig}"


def test_stripe_signature_valid_invalid_expired():
    payload = b'{"id": "evt_1"}'
    assert verify_signature(payload, _stripe_header(payload), SECRET) > 0
    with pytest.raises(WebhookSignatureError):
        verify_signature(payload, _stripe_header(payload, secret="whsec_other"), SECRET)
    with pytest.raises(WebhookSignatureError):
        verify_signature(payload, _stripe_header(payload, at=int(time.time()) - 3600), SECRET, tolerance=300)
    with pytest.raises(WebhookSignatureError):
        verify_signature(payload, "", SECRET)
    with pytest.raises(WebhookSignatureError):
        verify_signature(b'{"id": "evt_2"}', _stripe_header(payload), SECRET)


async def test_stripe_checkout_session_via_mock_transport():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(200, json={"id": "cs_test_1", "url": "https://checkout.stripe.test/c/cs_test_1", "expires_at": 1_800_000_000})

    provider = StripeProvider(secret_key="sk_test_x", webhook_secret=SECRET, return_base="https://portal.test", transport=httpx.MockTransport(handler))
    result = await provider.create_link(reference="p1", amount=Decimal("50"), currency="usd", description="Clinic", metadata={"order_id": "o1"})
    assert result.url.endswith("cs_test_1") and result.provider_ref == "cs_test_1" and result.expires_at is not None
    form = seen["form"]
    assert seen["path"] == "/v1/checkout/sessions" and seen["auth"] == "Bearer sk_test_x"
    assert form["client_reference_id"] == "p1" and form["line_items[0][price_data][unit_amount]"] == "5000"
    assert form["line_items[0][price_data][currency]"] == "usd" and form["metadata[order_id]"] == "o1"
    assert minor_units(Decimal("500"), "JPY") == 500


async def test_stripe_errors_never_leak_the_key():
    provider = StripeProvider(secret_key="sk_test_secret_value", webhook_secret=SECRET, return_base="https://p.test",
                              transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "Invalid API Key"}})))
    with pytest.raises(PaymentError) as caught:
        await provider.create_link(reference="p1", amount=Decimal("5"), currency="USD", description="x", metadata={})
    assert "sk_test_secret_value" not in str(caught.value)


async def test_stripe_webhook_parses_completed_session():
    event = {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {
        "id": "cs_1", "client_reference_id": "p1", "payment_status": "paid", "amount_total": 5000, "currency": "usd", "payment_intent": "pi_1"}}}
    body = json.dumps(event).encode()
    provider = StripeProvider(secret_key="sk_test_x", webhook_secret=SECRET)
    parsed = await provider.handle_webhook(body, {"Stripe-Signature": _stripe_header(body)})
    assert parsed.status == "paid" and parsed.reference == "p1" and parsed.amount == Decimal("50.00") and parsed.meta["payment_intent"] == "pi_1"
    assert parse_event({"type": "checkout.session.completed", "data": {"object": {"payment_status": "unpaid"}}}) is None
    with pytest.raises(WebhookSignatureError):
        await provider.handle_webhook(body, {"stripe-signature": "t=1,v1=bad"})


async def test_events_mismatch_refund_and_failure():
    session = FakeSession()
    record, payment = await linked_booking(session)
    payment.provider = "stripe"
    wrong, changed = await service.apply_event(session, PaymentEvent("stripe", "paid", reference=payment.id, amount=Decimal("5"), currency="USD"))
    assert not changed and payment.status == "pending" and "amount_mismatch" in payment.meta
    _, changed = await service.apply_event(session, PaymentEvent("stripe", "paid", reference=payment.id, amount=Decimal("50"), currency="USD", meta={"payment_intent": "pi_9"}))
    assert changed and payment.status == "paid" and payment.meta["payment_intent"] == "pi_9"
    _, changed = await service.apply_event(session, PaymentEvent("stripe", "refunded", reference=payment.id))
    assert changed and payment.status == "refunded" and record.payment_status == "refunded"
    _, changed = await service.apply_event(session, PaymentEvent("dummy", "paid", reference=payment.id))
    assert not changed  # another provider can't touch a Stripe payment


# ------------------------------------------------------------------ owner link + settings
def test_owner_link_template_rules_and_fill():
    assert link.validate_template("https://pay.example.com/x?amt={amount}&r={ref}") .startswith("https://")
    for bad in ("http://pay.example.com/{amount}", "https://pay.example.com/{price}", "pay.example.com", "https://a.com/ {ref}"):
        with pytest.raises(ValueError):
            link.validate_template(bad)
    url = link.fill("https://pay.example.com/{ref}?a={amount}&c={currency}", amount=Decimal("9.5"), currency="usd", reference="A 7/x")
    assert url == "https://pay.example.com/A%207%2Fx?a=9.50&c=USD"
    merchant = SimpleNamespace(payment_settings={})
    with pytest.raises(ValueError):
        link.updated_settings(merchant, {"provider": "link"})
    updated = link.updated_settings(merchant, {"provider": "link", "link_template": "https://p.example.com/{ref}", "methods": ["online"]})
    assert updated == {"provider": "link", "link_template": "https://p.example.com/{ref}", "methods": ["online"]}


async def test_registry_prefers_owner_link():
    from app.services.payments.registry import get_provider

    merchant = SimpleNamespace(payment_settings={"provider": "link", "link_template": "https://p.example.com/{ref}"})
    provider = get_provider(merchant)
    made = await provider.create_link(reference="p1", amount=Decimal("3"), currency="USD", description="", metadata={})
    assert provider.name == "link" and made.url == "https://p.example.com/p1"
    assert get_provider(None).name in ("dummy", "stripe")


# ------------------------------------------------------------------ after an agent commit
async def test_after_commit_creates_link_and_sms_carries_it(monkeypatch):
    merchant = make_merchant(id="m1", business_name="Clinic", language="en", region="US", timezone="UTC", currency="USD")
    record = booking()
    session = FakeSession(merchant, record)
    monkeypatch.setattr(service, "session_factory", Factory(session))
    monkeypatch.setattr(service, "get_provider", lambda merchant=None: DummyProvider(base_url="https://portal.test"))
    payment = await service.after_commit("m1", "o1", "booked")
    assert payment is not None and payment.hold_until is not None and session.commits == 1
    assert record.payment_status == "pending" and record.payment_ref == payment.id and record.payment_url == payment.url
    assert record.details["payment"]["url"] == payment.url and record.status == OrderStatus.pending
    assert await service.after_commit("m1", "o1", "booked") is None  # idempotent: one link per booking
    text = sms_service.compose("confirmation", record, merchant, item_name="Dr. Lee")
    assert text.endswith(f"Pay here: {payment.url}")


async def test_after_commit_pay_at_venue_and_failures_never_raise(monkeypatch):
    record = booking(details={"payment": {"mode": "at_venue", "method": "at_venue", "amount": 50, "status": "pay_at_venue"}})
    session = FakeSession(make_merchant(id="m1"), record)
    monkeypatch.setattr(service, "session_factory", Factory(session))
    assert await service.after_commit("m1", "o1", "booked") is None and record.payment_status == "at_venue"
    monkeypatch.setattr(service, "session_factory", FakeSessionFactory(fail=True))
    assert await service.after_commit("m1", "o1", "booked") is None


# ------------------------------------------------------------------ hold sweeper
async def test_hold_sweeper_releases_unpaid_pending_bookings(monkeypatch):
    session = FakeSession()
    record, payment = await linked_booking(session)
    paid_record, paid_payment = await linked_booking(session, id="o2")
    paid_record.payment_status = "paid"  # paid through another path: keep the booking
    session.scalars_queue.append([payment, paid_payment])
    monkeypatch.setattr(service, "session_factory", Factory(session))
    notified: list[tuple] = []
    monkeypatch.setattr(notification_service, "after_outcome", lambda *args: notified.append(args))
    released = await holds.release_expired_holds(now=NOW + timedelta(minutes=31))
    assert released == [("m1", "o1")] and notified == [("m1", "o1", "cancelled")]
    assert record.status == OrderStatus.cancelled and record.payment_status == "expired" and payment.status == "expired"
    assert paid_record.status == OrderStatus.pending and paid_record.payment_status == "paid"
    assert "booking released" in record.notes
    # Paid after the release: the booking goes to review instead of silently confirming.
    payment.status = "pending"
    await service.mark_paid(session, payment, source="dummy", now=NOW + timedelta(minutes=40))
    assert record.status == OrderStatus.needs_review and record.payment_status == "paid"


def test_should_release_only_waiting_bookings():
    payment = SimpleNamespace(id="p1")
    assert holds.should_release(booking(payment_ref="p1", payment_status="pending"), payment)
    assert not holds.should_release(booking(payment_ref="p2", payment_status="pending"), payment)
    assert not holds.should_release(booking(payment_ref="p1", payment_status="pending", status=OrderStatus.confirmed), payment)


# ------------------------------------------------------------------ owner: mark paid
def test_mark_paid_is_tenant_checked(monkeypatch):
    from app.main import app

    owner = make_merchant(id="m1")
    other_record = booking(id="o9", merchant_id="m2")
    own_record = booking(id="o1", merchant_id="m1", details={"payment": {"method": "at_venue", "amount": 50, "currency": "USD"}})
    session = FakeSession(owner, other_record, own_record)

    async def no_after_paid(payment):
        return None

    monkeypatch.setattr(service, "after_paid", no_after_paid)
    app.dependency_overrides[get_db] = db_dependency(session)
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {issue_merchant_token(owner)}"}
        assert client.post("/api/orders/o9/mark-paid", headers=headers).status_code == 404
        assert other_record.payment_status == "not_required"
        response = client.post("/api/orders/o1/mark-paid", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["payment_status"] == "paid" and body["payment"]["provider"] == "manual" and body["payment"]["amount"] == "50.00"
        assert own_record.payment_status == "paid"
        assert client.post("/api/orders/o1/mark-paid").status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)
