"""The bulk dialer ("Call all" + the scheduled auto-call) with a fake Telnyx API: every eligible
record gets dialed, never more at once than the plan's lines, and a cancel stops new dials."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.e2e.api import admin_token, create_account, ok
from tests.e2e.telnyx_peer import wait_until
from tests.e2e.test_13_outbound_calls import FakeTelnyx


@pytest.fixture
def dialer_telnyx(monkeypatch) -> FakeTelnyx:  # noqa: ANN001
    from app.core.config import get_settings
    from app.services import telnyx
    from app.services.dialer import batch

    fake = FakeTelnyx()
    settings = get_settings()
    for name, value in (("telnyx_api_key", "KEY-e2e"), ("telnyx_texml_app_id", "app-e2e"), ("telnyx_from_number", "+18725550000"),
                        ("bulk_call_gap_seconds", 0.0)):
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(batch, "SLOT_POLL_SECONDS", 0.2)
    monkeypatch.setattr(telnyx, "create_call", fake.create_call)
    monkeypatch.setattr(telnyx, "hangup_call", fake.hangup_call)
    return fake


async def _orders(client, headers, count: int) -> list[str]:  # noqa: ANN001
    ids = []
    for index in range(count):
        row = await ok(await client.post("/api/orders", headers=headers, json={
            "customer_name": f"Buyer {index}", "customer_phone": f"+1415555{3000 + index}", "items_summary": "Kurta x1",
            "total_amount": "20", "address": f"{index} Main St, Springfield",
        }), 201)
        ids.append(row["id"])
    return ids


async def _settle_calls(client, fake: FakeTelnyx, order_ids: list[str], already: int = 0) -> None:  # noqa: ANN001
    """The carrier reports every placed call finished (nobody answered)."""
    from urllib.parse import urlsplit

    for created in fake.calls[already:]:
        path = urlsplit(created["status_callback"]).path
        await client.post(path, data={"CallSid": "x", "CallStatus": "no-answer", "CallDuration": "0"})


async def test_call_all_dials_every_record_within_the_plans_line_limit(client, dialer_telnyx):
    from app.services.dialer.batch import current_run

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="ecommerce", plan="starter", inbound=False)  # 2 lines
    headers, merchant_id = account["headers"], account["merchant"]["id"]
    order_ids = await _orders(client, headers, 3)
    started = await ok(await client.post("/api/orders/call-all", headers=headers, json={}), 202)
    assert started["run"]["total"] == 3
    await wait_until(lambda: len(dialer_telnyx.calls) >= 2, what="the first two dials")
    # Two lines busy: the third record waits for a line instead of being skipped.
    await _settle_calls(client, dialer_telnyx, order_ids)
    await wait_until(lambda: not current_run(merchant_id).active, timeout=10.0, what="the batch to finish")
    run = current_run(merchant_id)
    assert (run.state, run.started, run.skipped, run.failed) == ("done", 3, 0, 0), run
    assert sorted(call["to"] for call in dialer_telnyx.calls) == ["+14155553000", "+14155553001", "+14155553002"]
    await _settle_calls(client, dialer_telnyx, order_ids, already=2)


async def test_scheduled_auto_call_fires_once_and_cancel_stops_new_dials(client, dialer_telnyx):
    from app.core.datetime_utils import utcnow
    from app.models import Merchant
    from app.services.dialer.batch import current_run
    from app.services.dialer.schedule import fire_due_schedules
    from tests.e2e.api import fetch

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="ecommerce", plan="growth", inbound=False)
    headers, merchant_id = account["headers"], account["merchant"]["id"]
    order_ids = await _orders(client, headers, 5)
    at = (utcnow() + timedelta(minutes=5)).isoformat()
    scheduled = await ok(await client.put("/api/orders/call-all/schedule", headers=headers, json={"at": at, "repeat_daily": False}))
    assert scheduled["schedule"]["at"] is not None
    assert await fire_due_schedules(now=utcnow()) == 0  # not yet
    assert await fire_due_schedules(now=utcnow() + timedelta(minutes=6)) >= 1
    assert (await fetch(Merchant, id=merchant_id))[0].auto_call_at is None  # one-off: cleared
    await wait_until(lambda: len(dialer_telnyx.calls) >= 3, what="the first dials")
    cancelled = await ok(await client.post("/api/orders/call-all/cancel", headers=headers))
    assert cancelled["run"]["source"] == "scheduled"
    await _settle_calls(client, dialer_telnyx, order_ids)
    await wait_until(lambda: not current_run(merchant_id).active, timeout=10.0, what="the batch to stop")
    assert current_run(merchant_id).state == "cancelled" and len(dialer_telnyx.calls) < 5


async def test_unanswered_outbound_calls_give_their_lines_back(client, dialer_telnyx):
    from urllib.parse import urlsplit

    from tests.e2e.phone import answer_inbound

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="ecommerce", plan="starter")  # 2 lines
    headers = account["headers"]
    order_ids = await _orders(client, headers, 2)
    for order_id in order_ids:
        await ok(await client.post(f"/api/orders/{order_id}/call", headers=headers))
    number = account["merchant"]["inbound_number"]
    busy = await answer_inbound(client, to=number, caller="+12125550411", call_sid="v3:e2e-lines-1")
    assert "lines are busy" in busy.text  # both lines ring out to customers
    for created in dialer_telnyx.calls:
        await client.post(urlsplit(created["status_callback"]).path, data={"CallSid": "x", "CallStatus": "no-answer"})
    # Nobody answered: both lines are free again at once (not after the 2-hour stale timeout).
    answered = await answer_inbound(client, to=number, caller="+12125550412", call_sid="v3:e2e-lines-2")
    assert "<Stream" in answered.text, answered.text
