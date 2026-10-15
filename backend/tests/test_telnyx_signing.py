"""Signed Telnyx webhook paths: URL builders, verification, the legacy toggle, Ed25519."""

from __future__ import annotations

import base64
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from app.api.routes import telnyx as telnyx_routes
from app.core.config import get_settings
from app.core.security.signed_paths import path_signature, verify_path_signature
from app.main import app
from app.services import call_service, sms_service, telnyx, telnyx_urls
from tests.security_fakes import FakeSessionFactory

BASE = "https://api.example.com"


@pytest.fixture(autouse=True)
def _telnyx(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "public_base_url", BASE)
    monkeypatch.setattr(settings, "telnyx_webhook_secret", "w" * 40)
    monkeypatch.setattr(settings, "telnyx_public_key", None)
    monkeypatch.setattr(settings, "enforce_webhook_signatures", False)
    monkeypatch.setattr(telnyx_routes, "AsyncSessionLocal", FakeSessionFactory())
    calls: list[tuple] = []

    async def status(session, order_id, call_sid, call_status, duration):
        calls.append(("status", order_id, call_sid, call_status))

    async def inbound(session, *, to_number, from_number, call_sid):
        calls.append(("inbound", to_number, from_number))
        return "<Response/>"

    monkeypatch.setattr(call_service, "apply_status_callback", status)
    monkeypatch.setattr(call_service, "answer_inbound_call", inbound)
    return calls


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_signatures_are_scoped_constant_length_and_secret_bound(monkeypatch):
    sig = path_signature("telnyx:inbound")
    assert len(sig) == 32 and verify_path_signature("telnyx:inbound", sig)
    assert not verify_path_signature("telnyx:status:o1", sig)
    assert not verify_path_signature("telnyx:inbound", sig[:-1] + ("0" if sig[-1] != "0" else "1"))
    assert not verify_path_signature("telnyx:inbound", None)
    monkeypatch.setattr(get_settings(), "telnyx_webhook_secret", "z" * 40)
    assert not verify_path_signature("telnyx:inbound", sig)


def test_derived_key_follows_token_secret_rotation(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telnyx_webhook_secret", None)
    monkeypatch.setattr(settings, "admin_token_secret", "A" * 40)
    monkeypatch.setattr(settings, "admin_token_secret_previous", None)
    old = path_signature("telnyx:status:o1")
    monkeypatch.setattr(settings, "admin_token_secret", "B" * 40)
    monkeypatch.setattr(settings, "admin_token_secret_previous", "A" * 40)
    assert verify_path_signature("telnyx:status:o1", old)  # in-flight calls keep their callbacks
    assert path_signature("telnyx:status:o1") != old


def test_url_builders_sign_each_call_separately():
    inbound = telnyx_urls.inbound_url()
    assert inbound == f"{BASE}/telnyx/inbound/{telnyx_urls.sign('inbound')}"
    status = telnyx_urls.status_callback_url("o1")
    assert status.startswith(f"{BASE}/telnyx/status/o1/") and status != telnyx_urls.status_callback_url("o2").replace("o2", "o1")
    assert telnyx_urls.recording_callback_url("o1").rsplit("/", 1)[1] != status.rsplit("/", 1)[1]  # kind is signed too
    assert telnyx_urls.log_recording_callback_url("c1").startswith(f"{BASE}/telnyx/recording-log/c1/")
    assert sms_service._sms_status_url("msg1") == telnyx_urls.sms_status_url("msg1", BASE)
    assert telnyx_urls.mask(inbound).endswith("…") and telnyx_urls.sign("inbound") not in telnyx_urls.mask(inbound)


def test_signed_status_callback_is_accepted_and_forged_is_403(client, _telnyx):
    url = telnyx_urls.status_callback_url("o1").removeprefix(BASE)
    ok = client.post(url, data={"CallSid": "v3:1", "CallStatus": "completed"})
    assert ok.status_code == 204 and _telnyx == [("status", "o1", "v3:1", "completed")]
    other_order = url.replace("/o1/", "/o2/")
    assert client.post(other_order, data={"CallStatus": "completed"}).status_code == 403
    assert client.post("/telnyx/status/o1/" + "0" * 32, data={}).status_code == 403
    assert len(_telnyx) == 1


def test_legacy_unsigned_paths_work_only_until_enforced(client, monkeypatch, _telnyx):
    assert client.post("/telnyx/inbound", data={"To": "+1555", "From": "+1666"}).status_code == 200
    monkeypatch.setattr(get_settings(), "enforce_webhook_signatures", True)
    assert client.post("/telnyx/inbound", data={"To": "+1555"}).status_code == 403
    assert client.post("/telnyx/status/o1", data={}).status_code == 403
    assert client.post("/telnyx/sms-events", content=b"{}").status_code == 403
    signed = client.post(telnyx_urls.inbound_url().removeprefix(BASE), data={"To": "+1555", "From": "+1666"})
    assert signed.status_code == 200 and signed.text == "<Response/>"


def test_inbound_signature_check_endpoint(client):
    assert client.get(f"/telnyx/inbound/{telnyx_urls.sign('inbound')}").status_code == 204
    assert client.get("/telnyx/inbound/" + "a" * 32).status_code == 403


def test_ed25519_is_enforced_whenever_a_public_key_is_set(client, monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    monkeypatch.setattr(get_settings(), "telnyx_public_key", public)
    url = telnyx_urls.status_callback_url("o1").removeprefix(BASE)
    body = b"CallSid=v3%3A1&CallStatus=completed"
    assert client.post(url, content=body, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 401
    stamp = str(int(time.time()))
    signature = base64.b64encode(private.sign(stamp.encode() + b"|" + body)).decode()
    headers = {"Content-Type": "application/x-www-form-urlencoded", "telnyx-signature-ed25519": signature, "telnyx-timestamp": stamp}
    assert client.post(url, content=body, headers=headers).status_code == 204


async def test_auto_configure_points_the_app_at_the_signed_url(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telnyx_auto_configure_inbound", True)
    monkeypatch.setattr(settings, "telnyx_texml_app_id", "app-1")
    pointed: list[str] = []

    async def point(url):
        pointed.append(url)

    monkeypatch.setattr(telnyx, "point_app_at", point)
    await call_service.configure_inbound_webhook()
    assert pointed == [telnyx_urls.inbound_url()]


def test_route_script_refuses_without_server_confirmation(monkeypatch, capsys):
    from scripts import telnyx_route

    monkeypatch.setattr(telnyx_route, "server_accepts", lambda url: (False, "the server rejects this signature"))
    repointed: list[str] = []

    async def repoint(url):
        repointed.append(url)

    monkeypatch.setattr(telnyx_route, "repoint", repoint)
    assert telnyx_route.main(["local", "--url", "https://abc.ngrok-free.app"]) == 2 and repointed == []
    out = capsys.readouterr().out
    assert telnyx_urls.sign("inbound") not in out  # shortened unless --show-signature
    monkeypatch.setattr(telnyx_route, "server_accepts", lambda url: (True, "signature accepted"))
    assert telnyx_route.main(["local", "--url", "https://abc.ngrok-free.app", "--dry-run"]) == 0 and repointed == []
