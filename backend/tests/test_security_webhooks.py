"""Inbound webhooks: Telnyx (signed paths, production default, body hygiene, media socket),
Twilio WhatsApp (X-Twilio-Signature), Meta (X-Hub-Signature-256 + verify handshake) and
Stripe (Stripe-Signature). Fakes only — no database, no network."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from twilio.request_validator import RequestValidator

from app.api.routes import telnyx as telnyx_routes
from app.core.config import get_settings
from app.core.security import boot_guard, sign_media_stream_token, sign_token
from app.main import app
from app.services import call_service, channel_service, meta_channels, telnyx, telnyx_urls
from app.services.calls import callbacks
from app.services.payments.base import WebhookSignatureError
from app.services.payments.stripe import verify_signature
from tests.security_fakes import FakeDB, FakeSessionFactory

BASE = "https://api.example.com"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    settings = get_settings()
    for key, value in (("public_base_url", BASE), ("telnyx_webhook_secret", "w" * 40), ("telnyx_public_key", None),
                       ("enforce_webhook_signatures", None), ("environment", "development"), ("twilio_auth_token", None),
                       ("meta_app_secret", "app-secret"), ("meta_verify_token", "verify-me")):
        monkeypatch.setattr(settings, key, value)
    factory = FakeSessionFactory()
    monkeypatch.setattr(telnyx_routes, "AsyncSessionLocal", factory)
    seen: list[tuple] = []

    async def status(session, order_id, call_sid, call_status, duration):
        seen.append(("status", order_id, call_sid, duration))

    async def recording(session, order_id, call_sid, recording_sid):
        seen.append(("recording", order_id, recording_sid))

    monkeypatch.setattr(call_service, "apply_status_callback", status)
    monkeypatch.setattr(call_service, "apply_recording_callback", recording)
    monkeypatch.setattr(telnyx, "remember_account_sid", lambda sid: seen.append(("sid", sid)))
    return SimpleNamespace(seen=seen, factory=factory)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _signed(url: str) -> str:
    return url.removeprefix(BASE)


# ------------------------------------------------------------------ Telnyx
def test_production_refuses_unsigned_telnyx_paths_by_default(client, monkeypatch, _settings):
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert boot_guard.webhook_signatures_enforced(get_settings())
    for path in ("/telnyx/inbound", "/telnyx/status/o1", "/telnyx/amd/o1", "/telnyx/recording/o1", "/telnyx/sms-events", "/telnyx/sms-status/m1"):
        assert client.post(path, data={"To": "+15550001"}).status_code == 403, path
    ok = client.post(_signed(telnyx_urls.status_callback_url("o1")), data={"CallSid": "v3:1", "CallStatus": "completed", "CallDuration": "42"})
    assert ok.status_code == 204 and ("status", "o1", "v3:1", 42) in _settings.seen
    # The operator can still opt out explicitly (logged as a weakened control at boot).
    monkeypatch.setattr(get_settings(), "enforce_webhook_signatures", False)
    assert "unsigned Telnyx / Twilio webhooks are accepted" in " ".join(boot_guard.advisories(get_settings()))


def test_unsigned_texml_route_is_gone_and_the_signed_one_checks_its_order(client):
    assert client.post("/telnyx/texml/o1", data={}).status_code in (404, 405)
    assert client.post("/telnyx/texml/o1/" + "0" * 32, data={}).status_code == 403


def test_only_authenticated_callbacks_teach_the_account_sid(client, _settings):
    client.post("/telnyx/status/o1", data={"AccountSid": "evil", "CallStatus": "ringing"})  # unsigned (development)
    assert ("sid", "evil") not in _settings.seen
    client.post(_signed(telnyx_urls.status_callback_url("o1")), data={"AccountSid": "real", "CallStatus": "ringing"})
    assert ("sid", "real") in _settings.seen


@pytest.mark.parametrize(("raw", "seconds"), [("42", 42), ("12.9", 12), ("-999999", 0), ("inf", 0), ("nan", 0), ("1e12", 0), ("x", 0), ("", 0)])
def test_call_duration_is_range_checked(raw, seconds):
    assert telnyx_routes._duration(raw) == seconds


def test_recording_ids_are_plain_tokens(client, _settings):
    url = _signed(telnyx_urls.recording_callback_url("o1"))
    client.post(url, data={"RecordingSid": "../../v2/numbers?x=1"})
    client.post(url, data={"RecordingSid": "rec_9f2-AB"})
    assert [item for item in _settings.seen if item[0] == "recording"] == [("recording", "o1", "rec_9f2-AB")]


async def test_callback_call_sid_is_bound_to_the_signed_order(monkeypatch):
    db = FakeDB()
    hung_up: list[str] = []

    async def complete(sid):
        hung_up.append(sid)

    monkeypatch.setattr(callbacks, "complete_call", complete)
    await callbacks.apply_status_callback(db, "o1", "v3:other-tenants-call", "completed", 30)
    first = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "call_logs.twilio_call_sid" in first and "call_logs.order_id" in first
    # No log of this order matched: a forged CallSid is never hung up.
    assert await callbacks.apply_amd_callback(FakeDB(), "o1", "v3:victim", "machine_start") is True
    assert hung_up == []


def test_media_socket_closes_before_any_lookup_on_a_bad_token(client, _settings):
    session = sign_token({"sub": "m1", "role": "merchant"}, typ="session")
    for token in (session, sign_media_stream_token(order_id="o1", call_log_id="c2"), sign_media_stream_token(order_id="o1", call_log_id="c1", ttl_seconds=-5)):
        with client.websocket_connect("/telnyx/media") as ws:
            ws.send_json({"event": "connected"})
            ws.send_json({"event": "start", "start": {"custom_parameters": {"order_id": "o1", "call_log_id": "c1", "media_token": token}}})
            assert ws.receive()["code"] == 1008
    assert _settings.factory.added == [] and _settings.factory.commits == 0


def test_media_socket_drops_silent_or_malformed_clients(client, monkeypatch):
    monkeypatch.setattr(telnyx_routes, "MEDIA_HANDSHAKE_SECONDS", 0.05)
    with client.websocket_connect("/telnyx/media") as ws:
        assert ws.receive()["code"] == 1008  # nothing sent within the handshake window
    with client.websocket_connect("/telnyx/media") as ws:
        ws.send_json(["not", "an", "object"])
        assert ws.receive()["code"] == 1002


# ------------------------------------------------------------------ Twilio WhatsApp
def _twilio(client, params: dict[str, str], signature: str | None):
    headers = {"X-Twilio-Signature": signature} if signature is not None else {}
    return client.post("/twilio/whatsapp", data=params, headers=headers)


def test_twilio_signature_is_checked_whenever_a_token_is_set(client, monkeypatch):
    async def reply(values):
        return "<Response/>"

    monkeypatch.setattr(channel_service, "handle_whatsapp", reply)
    monkeypatch.setattr(get_settings(), "twilio_auth_token", "tw-token")
    params = {"From": "whatsapp:+14155550123", "To": "whatsapp:+14155238886", "Body": "cancel my booking"}
    good = RequestValidator("tw-token").compute_signature(f"{BASE}/twilio/whatsapp", params)
    assert _twilio(client, params, good).status_code == 200
    assert _twilio(client, params, "forged").status_code == 401
    assert _twilio(client, {**params, "From": "whatsapp:+19998887777"}, good).status_code == 401  # body is signed
    assert _twilio(client, params, None).status_code == 401
    # No token: refused in production, allowed (with a warning) in development.
    monkeypatch.setattr(get_settings(), "twilio_auth_token", None)
    assert _twilio(client, params, None).status_code == 200
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert _twilio(client, params, None).status_code == 503


# ------------------------------------------------------------------ Meta
def _meta_sig(body: bytes, secret: bytes = b"app-secret") -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_meta_webhook_signature(client, monkeypatch):
    async def none(payload):
        return 0

    monkeypatch.setattr(channel_service, "handle_messenger", none)
    monkeypatch.setattr(meta_channels, "handle", none)
    body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
    assert client.post("/api/meta/webhook", content=body, headers={"X-Hub-Signature-256": _meta_sig(body)}).status_code == 200
    for header in ("", "sha256=" + "0" * 64, _meta_sig(body, b"other"), _meta_sig(body + b" "), "sha256=ü".encode("latin-1")):
        assert client.post("/api/meta/webhook", content=body, headers={"X-Hub-Signature-256": header}).status_code == 401, header
    monkeypatch.setattr(get_settings(), "meta_app_secret", None)  # unset secret fails closed
    assert client.post("/api/meta/webhook", content=body, headers={"X-Hub-Signature-256": _meta_sig(body)}).status_code == 401


def test_meta_verify_handshake(client, monkeypatch):
    params = {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "<script>alert(1)</script>"}
    ok = client.get("/api/meta/webhook", params=params)
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/plain")
    assert ok.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/meta/webhook", params={**params, "hub.verify_token": "verify-mf"}).status_code == 403
    assert client.get("/api/meta/webhook", params={**params, "hub.mode": "unsubscribe"}).status_code == 403
    monkeypatch.setattr(get_settings(), "meta_verify_token", None)
    assert client.get("/api/meta/webhook", params={**params, "hub.verify_token": ""}).status_code == 403


# ------------------------------------------------------------------ Stripe
SECRET = "whsec_test"


def _stripe(payload: bytes, *, at: int | str | None = None, secret: str = SECRET, scheme: str = "v1") -> str:
    stamp = str(int(time.time()) if at is None else at)
    digest = hmac.new(secret.encode(), stamp.encode("utf-8") + b"." + payload, hashlib.sha256).hexdigest()
    return f"t={stamp},{scheme}={digest}"


def test_stripe_signature_rules():
    payload = b'{"id": "evt_1"}'
    good = _stripe(payload)
    assert verify_signature(payload, f"{good},v1={'0' * 64}", SECRET) > 0  # any one of several v1 values
    bad = [
        _stripe(payload, scheme="v0"),  # only v1 counts
        _stripe(payload, at=int(time.time()) - 301),  # replay window
        _stripe(payload, at=int(time.time()) + 301),
        _stripe(payload, at="１２３"),  # non-ASCII digits: refused, not a crash
        "t=,v1=" + "0" * 64,
        good.replace("v1=", "v1=ü"),
    ]
    for header in bad:
        with pytest.raises(WebhookSignatureError):
            verify_signature(payload, header, SECRET)
    # A zero tolerance keeps the default window instead of switching it off.
    with pytest.raises(WebhookSignatureError):
        verify_signature(payload, _stripe(payload, at=int(time.time()) - 3600), SECRET, tolerance=0)
    with pytest.raises(WebhookSignatureError):
        verify_signature(payload, good, "")


def test_stripe_webhook_route_fails_closed_without_keys(client):
    assert client.post("/api/payments/stripe/webhook", content=b"{}", headers={"Stripe-Signature": _stripe(b"{}")}).status_code == 503

