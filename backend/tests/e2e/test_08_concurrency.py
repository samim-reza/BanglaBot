"""The last free slot under contention: two simultaneous commits (exactly one wins, under the
advisory lock in real Postgres), and two live phone calls that both heard the slot was free."""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from tests.e2e.api import admin_token, create_account, fetch, salon_catalog
from tests.e2e.fakes import tool_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import booking_day, dial, salon_booking


async def _salon(client):  # noqa: ANN001, ANN202
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth")
    account["catalog"] = await salon_catalog(client, account["headers"])
    return account


async def _call_log(merchant_id: str, caller: str) -> str:
    from app.db.session import AsyncSessionLocal
    from app.models import CallLog

    async with AsyncSessionLocal() as session:
        log = CallLog(merchant_id=merchant_id, direction="inbound", call_status="in-progress", caller_number=caller, flow="salon.inbound")
        session.add(log)
        await session.commit()
        return log.id


async def test_two_simultaneous_commits_for_the_last_slot_exactly_one_wins(client):
    from app.flows.base import CommitAction
    from app.models import CallLog, Order
    from app.services.call_service import DbCallStore

    account = await _salon(client)
    merchant_id, maya = account["merchant"]["id"], account["catalog"]["Maya"]["id"]
    start = datetime.fromisoformat(f"{booking_day(8)}T09:00").replace(tzinfo=ZoneInfo("America/New_York"))

    async def commit(caller: str, name: str):  # noqa: ANN202
        log_id = await _call_log(merchant_id, caller)
        store = DbCallStore(order_id="", call_log_id=log_id, merchant_id=merchant_id, currency="USD", source="inbound_call")
        action = CommitAction(
            outcome="booked", status="confirmed", capacity=(maya, start, 1),
            fields={"kind": "booking", "customer_name": name, "customer_phone": caller, "catalog_item_id": maya, "scheduled_at": start,
                    "details": {"service": "Haircut", "idem": f"idem-{caller}"}},
        )
        return log_id, await store.commit(action, final_node="wrap_up", flow_data={}, language="en")

    for round_no in range(3):  # the first race has one winner; later rounds find the slot taken
        results = await asyncio.gather(*(commit(f"+1212555{round_no}2{n:02d}", f"Caller {n}") for n in range(4)))
        wins = [result for _, result in results if result.ok]
        losses = [result for _, result in results if not result.ok]
        assert len(wins) == (1 if round_no == 0 else 0), results
        assert all(result.reason == "slot_taken" for result in losses)
    await settle_background()
    booked = [row for row in await fetch(Order, merchant_id=merchant_id) if row.scheduled_at == start]
    assert len(booked) == 1 and booked[0].status.value == "confirmed"
    outcomes = sorted(log.outcome for log in await fetch(CallLog, merchant_id=merchant_id))
    assert outcomes.count("booked") == 1

    # The same write retried (same idempotency key) finds the first record instead of colliding.
    [winner_log] = [log for log in await fetch(CallLog, merchant_id=merchant_id) if log.outcome == "booked"]
    store = DbCallStore(order_id="", call_log_id=winner_log.id, merchant_id=merchant_id, currency="USD", source="inbound_call")
    retry = CommitAction(
        outcome="booked", status="confirmed", capacity=(maya, start, 1),
        fields={"kind": "booking", "customer_name": booked[0].customer_name, "catalog_item_id": maya, "scheduled_at": start,
                "details": {"idem": booked[0].details["idem"]}},
    )
    again = await store.commit(retry, final_node="wrap_up", flow_data={}, language="en")
    assert again.ok and again.record_id == booked[0].id
    await settle_background()


async def test_two_live_calls_race_for_the_same_slot_and_only_one_books(app, client, providers):
    from app.models import CallLog, Order

    account = await _salon(client)
    merchant, number = account["merchant"], account["merchant"]["inbound_number"]
    day = booking_day(9)
    providers.script(tool_reply("save_details", salon_booking(day, "16:00", "Caller One")), tool_reply("end_call"))
    providers.script(tool_reply("save_details", salon_booking(day, "16:00", "Caller Two")))
    first = await dial(client, app, providers, to=number, caller="+12125550301", call_sid="v3:e2e-race-1")
    second = await dial(client, app, providers, to=number, caller="+12125550302", call_sid="v3:e2e-race-2")
    # Both callers were answered before either booked: both hear the 4 PM slot read back.
    await first.says("A haircut with Maya at 4pm, I'm Caller One")
    await second.says("A haircut with Maya at 4pm, I'm Caller Two")
    assert "4 PM" in first.agent_lines()[-1] and "4 PM" in second.agent_lines()[-1]

    await first.says("yes please")
    assert any(line.startswith("You're all set") for line in first.agent_lines())
    await second.says("yes please")
    late = second.agent_lines()[-1]
    assert not late.startswith("You're all set"), second.agent_lines()

    await first.wraps_up()
    await second.peer.stop()
    await second.peer.finished(timeout=10.0)
    await settle_background()
    start = datetime.fromisoformat(f"{day}T16:00").replace(tzinfo=ZoneInfo("America/New_York"))
    booked = [row for row in await fetch(Order, merchant_id=merchant["id"]) if row.scheduled_at == start]
    assert [row.customer_name for row in booked] == ["Caller One"]
    [log_two] = await fetch(CallLog, id=second.call_log_id)
    assert log_two.outcome != "booked" and log_two.order_id is None


async def test_simultaneous_call_limit_of_the_plan_is_enforced_and_freed(app, client, providers):
    from tests.e2e.phone import answer_inbound

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="starter")  # 2 calls at once
    await salon_catalog(client, account["headers"])
    number = account["merchant"]["inbound_number"]
    first = await dial(client, app, providers, to=number, caller="+12125550311", call_sid="v3:e2e-limit-1")
    second = await dial(client, app, providers, to=number, caller="+12125550312", call_sid="v3:e2e-limit-2")
    busy = await answer_inbound(client, to=number, caller="+12125550313", call_sid="v3:e2e-limit-3")
    assert "lines are busy" in busy.text and "<Stream" not in busy.text
    await first.peer.stop()
    await first.peer.finished(timeout=10.0)
    third = await dial(client, app, providers, to=number, caller="+12125550314", call_sid="v3:e2e-limit-4")
    assert third.agent_lines()
    for call in (second, third):
        await call.peer.stop()
        await call.peer.finished(timeout=10.0)
