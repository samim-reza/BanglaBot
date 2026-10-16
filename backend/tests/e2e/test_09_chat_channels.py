"""Chat channels on the same engine: WhatsApp through Twilio's signed webhook (TwiML replies)
and Messenger through Meta's signed webhook (replies posted to a mocked Graph API)."""

from __future__ import annotations

import hashlib
import hmac
import json
import xml.etree.ElementTree as ET

import httpx

from tests.e2e.api import admin_token, bearer, create_account, fetch, next_number, ok, salon_catalog
from tests.e2e.fakes import tool_reply
from tests.e2e.phone import booking_day, salon_booking
from tests.e2e.telnyx_peer import wait_until


def _replies(twiml: str) -> list[str]:
    return [node.text or "" for node in ET.fromstring(twiml).findall("Message")]


async def test_whatsapp_customer_books_through_the_twilio_webhook(client, providers, monkeypatch):
    from twilio.request_validator import RequestValidator

    from app.core.config import get_settings
    from app.models import Order

    monkeypatch.setattr(get_settings(), "twilio_auth_token", "e2e-twilio-token")
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="trial", inbound=False)
    await salon_catalog(client, account["headers"])
    number = next_number()
    merchant = await ok(await client.patch(f"/api/admin/merchants/{account['merchant']['id']}", json={"whatsapp_number": number}, headers=bearer(admin)))
    assert merchant["channels"]["whatsapp"]["number"] == number

    validator = RequestValidator("e2e-twilio-token")
    customer = "+12125550601"

    async def send(text: str, *, sign: bool = True) -> httpx.Response:
        form = {"From": f"whatsapp:{customer}", "To": f"whatsapp:{number}", "Body": text, "MessageSid": f"SM{len(text)}"}
        signature = validator.compute_signature("http://testserver/twilio/whatsapp", form) if sign else "forged"
        return await client.post("/twilio/whatsapp", data=form, headers={"X-Twilio-Signature": signature})

    assert (await send("Hi", sign=False)).status_code == 401
    providers.script(tool_reply("save_details", salon_booking(booking_day(11), "13:00", "Wa Customer")))
    opening = _replies((await send("Hi")).text)
    assert opening and opening[0].startswith("Hi, welcome to"), opening
    readback = _replies((await send("A haircut with Maya at 1pm, I'm Wa Customer")).text)
    assert "Shall I book it?" in readback[-1], readback  # the WhatsApp number is the phone: no question
    booked = _replies((await send("yes")).text)
    assert booked[-1].startswith("You're all set"), booked
    [record] = await fetch(Order, merchant_id=account["merchant"]["id"])
    assert record.source == "whatsapp" and record.customer_phone == customer and record.status.value == "confirmed"


async def test_messenger_page_is_connected_and_answers_through_the_graph_api(client, providers, monkeypatch):
    from app.core.config import get_settings
    from app.models import Order
    from app.services import channel_service

    monkeypatch.setattr(get_settings(), "meta_app_secret", "e2e-meta-secret")
    graph: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        graph.append(request)
        if request.url.path.endswith("/subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/me/messages"):
            return httpx.Response(200, json={"message_id": "m1"})
        return httpx.Response(200, json={"name": "Glow Page", "id": "1234567890"})

    monkeypatch.setattr(channel_service, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="trial", inbound=False)
    await salon_catalog(client, account["headers"])
    connected = await ok(await client.put("/api/channels/messenger", json={"page_id": "1234567890", "page_token": "EAAG" + "x" * 40}, headers=account["headers"]))
    assert "Glow Page" in json.dumps(connected) and "EAAG" not in json.dumps(connected)  # the token is never echoed

    async def deliver(text: str) -> None:
        body = json.dumps({"object": "page", "entry": [{"id": "1234567890", "messaging": [{"sender": {"id": "psid-77"}, "message": {"mid": text, "text": text}}]}]}).encode()
        signature = "sha256=" + hmac.new(b"e2e-meta-secret", body, hashlib.sha256).hexdigest()
        answer = await ok(await client.post("/api/meta/webhook", content=body, headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"}))
        assert answer["accepted"] == 1

    assert (await client.post("/api/meta/webhook", content=b"{}", headers={"X-Hub-Signature-256": "sha256=00"})).status_code == 401
    providers.script(tool_reply("save_details", salon_booking(booking_day(12), "12:00", "Mo Messenger")), tool_reply("save_details", {"phone": "4155550188"}))
    for text, expected in (("Hello", 1), ("A haircut with Maya at noon, I'm Mo Messenger", 2), ("415 555 0188", 3), ("yes please", 4)):
        await deliver(text)
        await wait_until(lambda: sum(1 for r in graph if r.url.path.endswith("/me/messages")) >= expected, what=f"the reply to {text!r}")
    sent = [json.loads(r.content)["message"]["text"] for r in graph if r.url.path.endswith("/me/messages")]
    assert sent[-1].startswith("You're all set"), sent
    [record] = await fetch(Order, merchant_id=account["merchant"]["id"])
    assert record.source == "messenger" and record.customer_name == "Mo Messenger" and record.customer_phone.endswith("4155550188")
