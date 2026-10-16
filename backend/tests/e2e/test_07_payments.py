"""Online payment (dummy provider): an online-required booking is held pending, its pay link
goes out in the confirmation text, the signed pay page marks it paid and confirms the
booking; tampered tokens are refused; an unpaid hold is released by the sweeper."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit

from tests.e2e.api import fetch, ok, salon_with_widget
from tests.e2e.fakes import tool_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import booking_day, salon_booking

ONLINE_DEPOSIT = {"steps": {"payment": {"enabled": True, "options": {"mode": "online_required", "amount_source": "deposit", "deposit_amount": 20, "hold_minutes": 30}}}}


async def _book_by_chat(client, providers, key: str, day: str, time_pref: str, name: str, phone: str) -> list[str]:  # noqa: ANN001
    providers.script(tool_reply("save_details", salon_booking(day, time_pref, name)), tool_reply("save_details", {"phone": phone}), tool_reply("end_call"))
    session_id = (await ok(await client.post(f"/api/public/widget/{key}/start")))["session_id"]
    said = []
    for text in (f"A haircut with Maya at {time_pref}, I'm {name}", phone, "yes please"):
        said = (await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": session_id, "text": text})))["messages"]
    return said


async def test_online_required_booking_is_paid_on_the_signed_page(client, providers, sms_outbox):
    from app.models import Order, Payment
    from app.services.payments.dummy import sign_pay_token

    account = await salon_with_widget(client)
    headers, key = account["headers"], account["merchant"]["widget_key"]
    flow = await ok(await client.get("/api/agent/flow", headers=headers))
    await ok(await client.put("/api/agent/flow", json={"config": ONLINE_DEPOSIT, "base_hash": flow["hash"]}, headers=headers))
    sms = await ok(await client.patch("/api/integrations/sms", json={"enabled": True}, headers=headers))
    assert sms["sms"]["settings"]["enabled"] is True and sms["sms"]["platform_ready"] is True

    closing = await _book_by_chat(client, providers, key, booking_day(5), "15:00", "Kim Ray", "4155550144")
    assert closing and "link" in " ".join(closing).lower(), closing
    assert not await settle_background()

    [record] = await fetch(Order, merchant_id=account["merchant"]["id"])
    assert record.status.value == "pending" and record.payment_status == "pending"
    assert record.payment_url.startswith("http://portal.test/pay/")
    [payment] = await fetch(Payment, order_id=record.id)
    assert payment.status == "pending" and payment.amount == Decimal("20.00") and payment.hold_until is not None

    # The confirmation text carries the link (SMS on, Telnyx faked).
    [text] = sms_outbox
    assert text["to"] == "+14155550144" and f"Pay here: {record.payment_url}" in text["text"], text
    messages = await ok(await client.get("/api/integrations/messages", headers=headers))
    assert messages["items"][0]["status"] == "sent" and messages["items"][0]["kind"] == "confirmation"

    token = urlsplit(record.payment_url).path.removeprefix("/pay/")
    page = await ok(await client.get(f"/api/public/pay/{token}"))
    assert page["amount"] == "20.00" and page["status"] == "pending" and page["can_complete"] and page["business"] == account["merchant"]["business_name"]
    # Tampered: a broken signature, and a validly signed token for another amount.
    assert (await client.get(f"/api/public/pay/{token[:-2]}xx")).status_code == 404
    cheaper = sign_pay_token(reference=payment.id, amount=Decimal("1.00"), currency=payment.currency)
    assert (await client.post(f"/api/public/pay/{cheaper}/complete")).status_code == 404

    paid = await ok(await client.post(f"/api/public/pay/{token}/complete"))
    assert paid["status"] == "paid"
    await settle_background()
    [record] = await fetch(Order, id=record.id)
    assert record.status.value == "confirmed" and record.payment_status == "paid"
    listed = await ok(await client.get("/api/orders", headers=headers))
    assert listed["items"][0]["payment_status"] == "paid"


async def test_an_unpaid_hold_is_released_by_the_sweeper(client, providers, sms_outbox):
    from app.core.datetime_utils import utcnow
    from app.models import Order, Payment
    from app.services.payments import holds

    account = await salon_with_widget(client)
    headers, key = account["headers"], account["merchant"]["widget_key"]
    flow = await ok(await client.get("/api/agent/flow", headers=headers))
    await ok(await client.put("/api/agent/flow", json={"config": ONLINE_DEPOSIT, "base_hash": flow["hash"]}, headers=headers))
    await ok(await client.patch("/api/integrations/sms", json={"enabled": True}, headers=headers))  # the link goes out by text
    await _book_by_chat(client, providers, key, booking_day(6), "10:00", "Jo Unpaid", "4155550155")
    await settle_background()
    [record] = await fetch(Order, merchant_id=account["merchant"]["id"])
    assert record.status.value == "pending"

    released = await holds.release_expired_holds(now=utcnow() + timedelta(minutes=31))
    assert (record.merchant_id, record.id) in released
    await settle_background()
    [record] = await fetch(Order, id=record.id)
    assert record.status.value == "cancelled" and record.payment_status == "expired"
    [payment] = await fetch(Payment, order_id=record.id)
    assert payment.status == "expired" and payment.meta.get("expired_by") == "hold"
    # The released link can't be paid any more; the page says so.
    token = urlsplit(record.payment_url).path.removeprefix("/pay/")
    late = await client.post(f"/api/public/pay/{token}/complete")
    assert late.status_code == 409 and "expired" in late.json()["detail"]
    assert (await ok(await client.get(f"/api/public/pay/{token}")))["can_complete"] is False


async def test_owner_marks_a_venue_payment_as_paid(client, providers):
    from app.models import Payment

    account = await salon_with_widget(client)
    headers = account["headers"]
    staff = (await ok(await client.get("/api/catalog?kind=staff", headers=headers)))[0]
    record = await ok(
        await client.post(
            "/api/orders", headers=headers,
            json={"customer_name": "Walk In", "customer_phone": "+14155550166", "service": "Haircut", "catalog_item_id": staff["id"],
                  "scheduled_at": f"{booking_day(7)}T12:00", "total_amount": "45"},
        ),
        201,
    )
    marked = await ok(await client.post(f"/api/orders/{record['id']}/mark-paid", headers=headers))
    assert marked["payment_status"] == "paid" and marked["payment"]["provider"] == "manual" and marked["payment"]["amount"] == "45.00"
    assert [p.status for p in await fetch(Payment, order_id=record["id"])] == ["paid"]


async def test_owner_payment_link_template_and_mark_paid(client, providers, sms_outbox):
    from app.models import Order, Payment

    account = await salon_with_widget(client)
    headers, key = account["headers"], account["merchant"]["widget_key"]
    bad = await client.put("/api/payments/settings", headers=headers, json={"provider": "link", "link_template": "http://pay.example.test/{amount}"})
    assert bad.status_code == 422
    settings = await ok(await client.put("/api/payments/settings", headers=headers, json={"provider": "link", "link_template": "https://pay.example.test/glow?amount={amount}&ref={ref}"}))
    assert settings["provider"] == "link" and settings["platform_provider"] == "dummy"
    flow = await ok(await client.get("/api/agent/flow", headers=headers))
    await ok(await client.put("/api/agent/flow", json={"config": ONLINE_DEPOSIT, "base_hash": flow["hash"]}, headers=headers))
    await ok(await client.patch("/api/integrations/sms", json={"enabled": True}, headers=headers))  # the link goes out by text
    await _book_by_chat(client, providers, key, booking_day(8), "11:00", "Lin Kowner", "4155550177")
    assert not await settle_background()
    [record] = await fetch(Order, merchant_id=account["merchant"]["id"])
    [payment] = await fetch(Payment, order_id=record.id)
    assert payment.provider == "link" and record.payment_url == f"https://pay.example.test/glow?amount=20.00&ref={payment.id}"
    assert record.status.value == "pending"
    # Nothing reports back from the owner's link: the owner marks it paid, the booking is confirmed.
    marked = await ok(await client.post(f"/api/orders/{record.id}/mark-paid", headers=headers))
    assert marked["payment_status"] == "paid" and marked["status"] == "confirmed" and marked["payment"]["id"] == payment.id
