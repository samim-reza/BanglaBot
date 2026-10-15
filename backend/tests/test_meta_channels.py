"""Instagram DM and WhatsApp (Meta Cloud API): webhook signatures, routing to the agent,
replies through the Graph API, connecting accounts. HTTP is mocked, no database."""

from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.services import channel_service, meta_channels
from tests.billing_fakes import reset_catalog


@pytest.fixture(autouse=True)
def _meta(monkeypatch):
    reset_catalog()
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_secret", "app-secret")
    monkeypatch.setattr(settings, "meta_verify_token", "verify-me")
    spawned: list = []
    monkeypatch.setattr(meta_channels, "_spawn", spawned.append)
    yield spawned
    for coro in spawned:
        coro.close()


def shop(**kw):
    base = dict(id="m1", vertical="clinic", business_name="Bright Smiles", plan="starter", active=True,
                addons={"_v": 1, "instagram": 1, "whatsapp": 1}, channel_settings={})
    base.update(kw)
    return SimpleNamespace(**base)


def graph(sent: list, reply: dict | None = None, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status, json=reply or {"ok": True})

    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def instagram_event(account="1784", sender="igsid-7", text="Do you have Saturday slots?", **message):
    return {"object": "instagram", "entry": [{"id": account, "messaging": [
        {"sender": {"id": sender}, "recipient": {"id": account}, "message": {"mid": "m", "text": text, **message}}]}]}


def whatsapp_event(number_id="1099", sender="14155550123", text="Book me in"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": number_id, "display_phone_number": "+1 555"},
        "messages": [{"from": sender, "id": "wamid", "type": "text", "text": {"body": text}}]}}]}]}


def test_webhook_checks_the_signature_and_routes_by_object(monkeypatch, _meta):
    from app.main import app

    found: list[tuple[str, str]] = []

    async def find(kind, value):
        found.append((kind, value))
        return shop()

    monkeypatch.setattr(meta_channels, "find_merchant", find)
    client = TestClient(app)
    for payload in (instagram_event(), whatsapp_event()):
        body = json.dumps(payload).encode()
        assert client.post("/api/meta/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
        signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        answer = client.post("/api/meta/webhook", content=body, headers={"X-Hub-Signature-256": signature})
        assert answer.json() == {"ok": True, "accepted": 1}
    assert found == [("instagram", "1784"), ("whatsapp_cloud", "1099")] and len(_meta) == 2
    ok = client.get("/api/meta/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "7"})
    assert ok.text == "7"


async def test_instagram_message_runs_the_agent_and_replies_through_the_send_api(monkeypatch, _meta):
    merchant = shop(channel_settings={"instagram": {"account_id": "1784", "token_enc": encrypt_secret("ig-page-token")}})

    async def find(kind, value):
        return merchant

    async def converse(m, channel, customer, text, caller_number=""):
        assert (channel, customer, text) == ("instagram", "igsid-7", "Do you have Saturday slots?")
        return ["Yes, 10am or 2pm.", "x" * 1500]

    sent: list[httpx.Request] = []
    monkeypatch.setattr(meta_channels, "find_merchant", find)
    monkeypatch.setattr(channel_service, "converse", converse)
    monkeypatch.setattr(channel_service, "http", graph(sent))
    assert await meta_channels.handle(instagram_event()) == 1
    await _meta.pop()
    assert sent[0].url.path == "/v21.0/me/messages" and sent[0].url.params["access_token"] == "ig-page-token"
    assert json.loads(sent[0].content) == {"recipient": {"id": "igsid-7"}, "messaging_type": "RESPONSE", "message": {"text": "Yes, 10am or 2pm."}}
    assert len(json.loads(sent[1].content)["message"]["text"]) == 1000


async def test_instagram_ignores_echoes_and_accounts_without_the_add_on(monkeypatch, _meta):
    async def find(kind, value):
        return shop(addons={"_v": 1})

    monkeypatch.setattr(meta_channels, "find_merchant", find)
    assert await meta_channels.handle(instagram_event()) == 0

    async def entitled(kind, value):
        return shop()

    monkeypatch.setattr(meta_channels, "find_merchant", entitled)
    assert await meta_channels.handle(instagram_event(is_echo=True)) == 0
    assert await meta_channels.handle(instagram_event(sender="1784")) == 0  # our own account
    assert _meta == []


async def test_whatsapp_cloud_message_replies_through_the_phone_number(monkeypatch, _meta):
    merchant = shop(channel_settings={"whatsapp_cloud": {"phone_number_id": "1099", "token_enc": encrypt_secret("wa-token")}})

    async def find(kind, value):
        assert (kind, value) == ("whatsapp_cloud", "1099")
        return merchant

    async def converse(m, channel, customer, text, caller_number=""):
        assert (channel, customer, caller_number, text) == ("whatsapp", "+14155550123", "+14155550123", "Book me in")
        return ["Sure — which day?"]

    sent: list[httpx.Request] = []
    monkeypatch.setattr(meta_channels, "find_merchant", find)
    monkeypatch.setattr(channel_service, "converse", converse)
    monkeypatch.setattr(channel_service, "http", graph(sent))
    assert await meta_channels.handle(whatsapp_event()) == 1
    await _meta.pop()
    assert sent[0].url.path == "/v21.0/1099/messages" and sent[0].headers["authorization"] == "Bearer wa-token"
    assert json.loads(sent[0].content) == {"messaging_product": "whatsapp", "recipient_type": "individual", "to": "14155550123",
                                           "type": "text", "text": {"preview_url": False, "body": "Sure — which day?"}}


async def test_whatsapp_cloud_skips_statuses_and_unentitled_accounts(monkeypatch, _meta):
    statuses = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "1099"}, "statuses": [{"status": "delivered"}]}}]}]}
    assert await meta_channels.handle(statuses) == 0

    async def find(kind, value):
        return shop(plan="chat", addons={"_v": 1})

    monkeypatch.setattr(meta_channels, "find_merchant", find)
    assert await meta_channels.handle(whatsapp_event()) == 0
    assert await meta_channels.handle({"object": "page", "entry": []}) == 0  # Messenger is channel_service's


async def test_connecting_checks_the_tokens_and_stores_them_encrypted(monkeypatch):
    sent: list[httpx.Request] = []
    monkeypatch.setattr(channel_service, "http", graph(sent, {"username": "brightsmiles", "display_phone_number": "+1 555-0100",
                                                               "verified_name": "Bright Smiles"}))
    stored = await meta_channels.connect_instagram("1784", "ig-page-token-abcdefghijkl")
    assert stored["username"] == "brightsmiles" and stored["token_enc"].startswith("enc:") and "ig-page" not in stored["token_enc"]
    cloud = await meta_channels.connect_whatsapp_cloud("1099", "wa-token-abcdefghijklmnop")
    assert cloud["display_number"] == "+1 555-0100" and sent[1].headers["authorization"] == "Bearer wa-token-abcdefghijklmnop"
    view = meta_channels.view(SimpleNamespace(channel_settings={"instagram": stored, "whatsapp_cloud": cloud}))
    assert view["instagram"] == {"account_id": "1784", "username": "brightsmiles", "connected": True}
    assert "token_enc" not in json.dumps(view)
    monkeypatch.setattr(channel_service, "http", graph([], status=400))
    with pytest.raises(ValueError):
        await meta_channels.connect_instagram("1784", "bad-token-abcdefghijklmn")


def test_channel_routes_need_a_login():
    from app.main import app

    client = TestClient(app)
    assert client.put("/api/channels/instagram", json={"account_id": "1", "page_token": "x"}).status_code == 401
    assert client.put("/api/channels/whatsapp-cloud", json={}).status_code == 401
