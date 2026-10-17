"""A booked website chat gets its AI summary, the owner gets one text alert carrying it, the
customer's first text carries the STOP notice; STOP / HELP / START replies on the Telnyx
profile webhook switch texts off, answer, and back on (real SQL, fake Telnyx)."""

from __future__ import annotations

from typing import Any

from tests.e2e.api import fetch, ok, salon_with_widget
from tests.e2e.fakes import text_reply, tool_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import booking_day, salon_booking

OWNER = "+16175550199"
CUSTOMER = "+14155550123"
SUMMARY = "Lee Park booked a haircut with Maya; no follow-up needed."


class SummaryLLM:
    """The account's chain as the summary sees it (one short answer)."""

    def __init__(self) -> None:
        self.requests: list[list[dict[str, Any]]] = []

    async def complete(self, messages, **_: Any):  # noqa: ANN001, ANN201
        self.requests.append(messages)
        return text_reply(f"Summary: {SUMMARY}")

    def stats(self) -> dict[str, Any]:
        return {"provider": "openai", "model": "gpt-5.4-mini", "prompt_tokens": 600, "completion_tokens": 25,
                "by_model": {"openai:gpt-5.4-mini": {"prompt_tokens": 600, "completion_tokens": 25}}}


def inbound_text(text: str) -> dict[str, Any]:
    payload = {"id": "in-1", "direction": "inbound", "text": text, "from": {"phone_number": CUSTOMER},
               "to": [{"phone_number": "+18723428160", "status": "webhook_delivered"}]}
    return {"data": {"event_type": "message.received", "payload": payload}}


async def test_summary_owner_alert_and_stop_start_help(client, providers, sms_outbox, monkeypatch):
    from app.models import CallLog, Order, SmsOptOut, UsageEvent
    from app.services.sms import optout
    from app.services.summaries import runner

    summarizer = SummaryLLM()
    monkeypatch.setattr(runner, "llm_factory", lambda merchant: summarizer)
    account = await salon_with_widget(client)
    headers, key, merchant_id = account["headers"], account["merchant"]["widget_key"], account["merchant"]["id"]

    # Owner alerts by text for bookings; customer texts on.
    summary = await ok(await client.get("/api/integrations", headers=headers))
    assert summary["alerts"]["settings"] == {"email_events": ["booking", "message", "urgent"], "sms_events": [], "sms_to": ""}
    refused = await client.patch("/api/integrations/alerts", json={"sms_events": ["booking"]}, headers=headers)
    assert refused.status_code == 422  # no number to text yet
    saved = await ok(await client.patch("/api/integrations/alerts", json={"sms_events": ["booking", "urgent"], "sms_to": "+1 617 555 0199"}, headers=headers))
    assert saved["alerts"]["settings"]["sms_to"] == OWNER and saved["alerts"]["sms_ready"] is True
    await ok(await client.patch("/api/integrations/sms", json={"enabled": True}, headers=headers))

    # A visitor books through the widget, then says goodbye.
    providers.script(
        tool_reply("save_details", salon_booking(booking_day(4), "14:00", "Lee Park")), tool_reply("save_details", {"phone": "4155550123"}), tool_reply("end_call"),
    )
    start = await ok(await client.post(f"/api/public/widget/{key}/start"))
    sid = start["session_id"]
    for text in ("A haircut with Maya at 2pm, I'm Lee Park", "415 555 0123", "yes please"):
        await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": sid, "text": text}))
    bye = await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": sid, "text": "No, that's all, thanks. Bye!"}))
    assert bye["ended"] is True
    assert not await settle_background()

    [record] = await fetch(Order, merchant_id=merchant_id)
    [log] = await fetch(CallLog, merchant_id=merchant_id)
    assert log.summary == SUMMARY and len(summarizer.requests) == 1
    assert "Customer name: Lee Park" in summarizer.requests[0][1]["content"]
    listed = await ok(await client.get("/api/calls", headers=headers))
    assert listed["items"][0]["summary"] == SUMMARY
    detail = await ok(await client.get(f"/api/orders/{record.id}", headers=headers))
    assert detail["call_logs"][0]["summary"] == SUMMARY
    metered = [row for row in await fetch(UsageEvent, merchant_id=merchant_id) if (row.meta or {}).get("purpose") == "summary"]
    assert metered and {row.category for row in metered} == {"llm"}

    # One owner alert, with the summary and a link to the booking; the customer's first text has the notice.
    owner = [sms for sms in sms_outbox if sms["to"] == OWNER]
    assert len(owner) == 1, owner
    alert = owner[0]["text"]
    assert alert.startswith(f"Callisa: New booking - Lee Park {CUSTOMER}.") and SUMMARY.split(";")[0] in alert
    # The owner's number was never texted before: the alert carries the notice too.
    assert alert.endswith(f"http://portal.test/orders/{record.id} Reply STOP to opt out.") and alert.isascii()
    [confirmation] = [sms for sms in sms_outbox if sms["to"] == CUSTOMER]
    assert confirmation["text"].endswith("Reply STOP to opt out.")

    # STOP: the opt-out lands in Postgres and the next text is skipped (with the reason shown).
    assert (await client.post("/telnyx/sms-events", json=inbound_text("Stop"))).status_code == 204
    [row] = await fetch(SmsOptOut, phone=CUSTOMER)
    assert row.merchant_id == merchant_id and row.keyword == "STOP"
    assert (await client.post("/telnyx/sms-events", json=inbound_text("STOP"))).status_code == 204  # a repeat upserts
    assert len(await fetch(SmsOptOut, phone=CUSTOMER)) == 1
    before = len(sms_outbox)
    skipped = await ok(await client.post(f"/api/integrations/messages/order/{record.id}", json={"body": ""}, headers=headers))
    assert skipped["status"] == "skipped" and skipped["error"] == optout.OPTED_OUT and len(sms_outbox) == before
    recent = await ok(await client.get("/api/integrations/messages", headers=headers))
    assert recent["items"][0]["error"] == optout.OPTED_OUT

    # HELP is answered once; START switches texts back on.
    assert (await client.post("/telnyx/sms-events", json=inbound_text("HELP"))).status_code == 204
    assert not await settle_background()
    [helped] = [sms for sms in sms_outbox[before:] if sms["to"] == CUSTOMER]
    assert helped["text"].startswith(account["merchant"]["business_name"]) and helped["text"].endswith("Reply STOP to opt out.")
    assert (await client.post("/telnyx/sms-events", json=inbound_text("start"))).status_code == 204
    assert await fetch(SmsOptOut, phone=CUSTOMER) == []
    sent = await ok(await client.post(f"/api/integrations/messages/order/{record.id}", json={"body": "See you soon!"}, headers=headers))
    assert sent["status"] == "sent" and sms_outbox[-1]["text"] == "See you soon!"  # texted before: no second notice


async def test_test_alert_is_rate_limited(client, sms_outbox):
    account = await salon_with_widget(client)
    headers = account["headers"]
    await ok(await client.patch("/api/integrations/alerts", json={"sms_to": OWNER, "email_events": []}, headers=headers))
    for _ in range(3):
        results = (await ok(await client.post("/api/integrations/alerts/test", headers=headers)))["results"]
        assert results["sms"]["status"] == "sent" and results["email"]["status"] == "skipped"  # no SMTP on this server
    assert (await client.post("/api/integrations/alerts/test", headers=headers)).status_code == 429
    assert [sms["to"] for sms in sms_outbox] == [OWNER] * 3 and "Test alert" in sms_outbox[0]["text"]
    assert sms_outbox[0]["text"].endswith("Reply STOP to opt out.") and not sms_outbox[1]["text"].endswith("Reply STOP to opt out.")
