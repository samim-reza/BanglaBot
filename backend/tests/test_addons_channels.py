"""Add-ons (plan + extras → what an account may use), WhatsApp / Messenger channels and Jev —
no database, no network (HTTP is mocked)."""

from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import addons
from app.core.config import get_settings
from app.core.plans import CHANNEL_MESSENGER, CHANNEL_VOICE, CHANNEL_WEB_CHAT, CHANNEL_WHATSAPP, FEATURE_GOOGLE_CALENDAR
from app.flows import hearing
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.services import channel_service
from app.verticals import flow_for
from app.voice import jev
from app.voice.llm import LLMReply, LLMToolCall
from app.voice.text_session import TextSession
from app.voice.tools import NullCallStore


def account(plan: str, owned: dict | None = None, **kw):
    return SimpleNamespace(id="m1", plan=plan, addons={"_v": 1, **(owned or {})}, **kw)


# ------------------------------------------------------------------------------ add-ons
def test_a_voice_plan_is_voice_only_until_add_ons_are_bought():
    ent = addons.entitlements(account("starter"))
    assert ent.channels == {CHANNEL_VOICE} and not ent.has_feature(FEATURE_GOOGLE_CALENDAR)
    assert (ent.minutes, ent.chats, ent.sms, ent.numbers) == (150, 0, 100, 1)

    ent = addons.entitlements(account("starter", {"web_chat": 1, "whatsapp": 1, "minutes": 2, "sms": 3, "number": 1, "google_calendar": 1}))
    assert ent.channels == {CHANNEL_VOICE, CHANNEL_WEB_CHAT, CHANNEL_WHATSAPP}
    assert ent.has_feature(FEATURE_GOOGLE_CALENDAR)
    assert (ent.minutes, ent.chats, ent.sms, ent.numbers) == (350, 1300, 1600, 2)


def test_plans_include_some_extras_and_enterprise_has_no_limits():
    assert addons.entitlements(account("growth")).has_feature(FEATURE_GOOGLE_CALENDAR)
    assert addons.entitlements(account("trial")).channels == {CHANNEL_VOICE, CHANNEL_WEB_CHAT, CHANNEL_WHATSAPP, CHANNEL_MESSENGER}
    chat = addons.entitlements(account("chat"))
    assert chat.channels == {CHANNEL_WEB_CHAT} and chat.minutes == 0 and chat.chats == 1000
    big = addons.entitlements(account("enterprise", {"minutes": 5}))
    assert big.minutes is None and big.chats is None


def test_what_an_account_can_still_request():
    assert "google_calendar" not in addons.available_for(account("growth"))  # already in the plan
    assert "minutes" not in addons.available_for(account("chat"))  # no phone agent to add minutes to
    assert {"web_chat", "whatsapp", "messenger", "minutes"} <= set(addons.available_for(account("starter")))


def test_stored_add_ons_are_cleaned():
    assert addons.quantities({"_v": 1, "web_chat": 3, "minutes": "2", "nope": 1, "sms": 0, "number": 999}) == {
        "web_chat": 1,
        "minutes": 2,
        "number": addons.MAX_QUANTITY,
    }
    assert addons.stored({"web_chat": 1}) == {"_v": 1, "web_chat": 1}


def test_add_on_routes_need_a_login():
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/addons").status_code == 401
    assert client.post("/api/addons/requests", json={"addon": "web_chat"}).status_code == 401
    assert client.get("/api/channels").status_code == 401
    assert client.get("/api/admin/addon-requests").status_code == 401
    assert client.put("/api/admin/merchants/x/addons", json={"addons": {}}).status_code == 401


# ------------------------------------------------------------------------------ channels
class ScriptedLLM:
    def __init__(self, replies: list[LLMReply]) -> None:
        self.replies = list(replies)
        self.prompt_tokens = self.completion_tokens = self.cached_prompt_tokens = 0

    async def complete(self, messages, **kwargs):
        return self.replies.pop(0)


def shop_merchant(**kw):
    base = dict(
        id="m1", vertical="ecommerce", business_name="Urban Threads", language="en", region="US", timezone="America/New_York",
        currency="USD", emergency_number="911", knowledge="", support_phone="+1999", custom_greeting="", vertical_config={},
        plan="starter", addons={"_v": 1, "whatsapp": 1}, active=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def session_for(merchant, llm, caller="+14155550123"):
    ctx = CallContext(merchant=merchant, direction=DIRECTION_INBOUND, caller_number=caller, channel="chat")
    return TextSession(merchant=merchant, ctx=ctx, flow=flow_for(merchant, DIRECTION_INBOUND), store=NullCallStore(), call_log_id="log", llm=llm)


@pytest.mark.asyncio
async def test_whatsapp_message_gets_the_agents_reply_as_twiml(monkeypatch):
    merchant = shop_merchant()
    llm = ScriptedLLM([LLMReply(content="Your order ships tomorrow.", tool_calls=[])])

    async def find(number):
        assert channel_service.bare_number(number) == "+14155238886"
        return merchant

    async def start(m, channel, customer, caller_number):
        assert (channel, customer, caller_number) == ("whatsapp", "+14155550123", "+14155550123")
        chat = session_for(m, llm, caller_number)
        channel_service._threads[(m.id, channel, customer)] = chat.id
        from app.voice import text_session

        text_session.register(chat)
        return chat

    monkeypatch.setattr(channel_service, "whatsapp_merchant", find)
    monkeypatch.setattr(channel_service, "_start", start)
    twiml = await channel_service.handle_whatsapp({"From": "whatsapp:+14155550123", "To": "whatsapp:+14155238886", "Body": "where is my order <3"})
    assert twiml == '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Your order ships tomorrow.</Message></Response>'
    # A bare greeting on a new conversation gets the opening line only (no model call).
    channel_service._threads.clear()
    twiml = await channel_service.handle_whatsapp({"From": "whatsapp:+14155550123", "To": "whatsapp:+14155238886", "Body": "Hi!"})
    assert "Hi, welcome to Urban Threads! How can I help you today?" in twiml


@pytest.mark.asyncio
async def test_whatsapp_is_silent_without_the_add_on(monkeypatch):
    async def find(number):
        return shop_merchant(addons={"_v": 1})

    monkeypatch.setattr(channel_service, "whatsapp_merchant", find)
    twiml = await channel_service.handle_whatsapp({"From": "whatsapp:+1", "To": "whatsapp:+2", "Body": "hello"})
    assert twiml.endswith("<Response></Response>")


def test_messenger_webhook_signature_and_verification(monkeypatch):
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_secret", "app-secret")
    monkeypatch.setattr(settings, "meta_verify_token", "verify-me")
    client = TestClient(app)
    ok = client.get("/api/meta/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert client.get("/api/meta/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"}).status_code == 403
    body = json.dumps({"object": "page", "entry": []}).encode()
    assert client.post("/api/meta/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    assert client.post("/api/meta/webhook", content=body, headers={"X-Hub-Signature-256": signature}).json() == {"ok": True, "accepted": 0}


@pytest.mark.asyncio
async def test_messenger_reply_goes_out_through_the_send_api(monkeypatch):
    from app.core.crypto import encrypt

    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["access_token"] == "page-token"
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message_id": "m"})

    monkeypatch.setattr(channel_service, "http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    merchant = shop_merchant(channel_settings={"messenger": {"page_id": "123", "token_enc": encrypt("page-token")}})
    await channel_service.send_messenger(merchant, "psid-9", ["Hello there", "x" * 2500])
    assert sent[0] == {"recipient": {"id": "psid-9"}, "messaging_type": "RESPONSE", "message": {"text": "Hello there"}}
    assert len(sent[1]["message"]["text"]) == 2000
    assert channel_service.channel_view(merchant)["messenger"] == {"page_id": "123", "page_name": "", "connected": True}


@pytest.mark.asyncio
async def test_connecting_a_facebook_page_checks_the_token_and_subscribes(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"name": "Urban Threads", "id": "123"})

    monkeypatch.setattr(channel_service, "http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    stored = await channel_service.connect_messenger("123", "page-token-abcdefghijklmnop")
    assert stored["page_name"] == "Urban Threads" and stored["token_enc"] and "page-token" not in stored["token_enc"]
    assert calls == ["GET /v21.0/123", "POST /v21.0/123/subscribed_apps"]


# ------------------------------------------------------------------------------ Jev
def jev_reply(choice: str, confidence: float):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer ts-key"
        assert body["questions"]["answer"]["type"] == "choice" and set(body["questions"]["answer"]["criteria"]) == {"yes", "no", "other"}
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"answer": {"type": "choice", "choice": choice, "confidence": confidence}}})

    return handler


@pytest.mark.asyncio
async def test_jev_only_answers_when_confident(monkeypatch):
    settings = get_settings()
    assert await jev.decide_yes_no("Is that right?", "yeah that works for me") is None  # no key = off
    monkeypatch.setattr(settings, "typesafe_api_key", "ts-key")
    monkeypatch.setattr(jev, "http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(jev_reply("yes", 0.96))))
    assert await jev.decide_yes_no("Is that right?", "yeah that works for me") == "yes"
    assert await jev.decide_yes_no("Is that right?", "yeah that works", language="bn") is None
    monkeypatch.setattr(jev, "http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(jev_reply("yes", 0.6))))
    assert await jev.decide_yes_no("Is that right?", "I guess, maybe") is None
    monkeypatch.setattr(jev, "http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(jev_reply("other", 0.99))))
    assert await jev.decide_yes_no("Is that right?", "yes but make it Friday") is None


@pytest.mark.asyncio
async def test_jev_settles_a_natural_read_back_answer_without_the_main_model(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "typesafe_api_key", "ts-key")
    monkeypatch.setattr(jev, "http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(jev_reply("yes", 0.95))))
    phrase = "you got it chief, ship it"
    assert "yes" not in hearing.classify(phrase)  # the keyword matcher alone can't settle it
    merchant = shop_merchant()
    llm = ScriptedLLM([LLMReply(content="", tool_calls=[LLMToolCall("c1", "save_details", '{"message": "Where is my order", "caller_name": "Emily"}')])])
    chat = session_for(merchant, llm)
    await chat.start()
    await chat.say("where is my order? I'm Emily")
    reply = await chat.say(phrase)  # no scripted LLM reply left: only the fast path can answer
    assert chat.ended and reply == ["Thank you. One of our team will get in touch with you shortly. Goodbye."]
