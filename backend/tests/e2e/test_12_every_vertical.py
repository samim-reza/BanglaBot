"""Every business engine on real SQL: its downloadable catalog template imports, an inbound
call is answered and greeted (context built from Postgres: catalog, bookings, caller history),
and a caller's question is answered before they hang up."""

from __future__ import annotations

import pytest

from tests.e2e.api import admin_token, create_account, fetch, ok
from tests.e2e.fakes import text_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import dial

VERTICALS = ("clinic", "dental", "vet", "salon", "home_service", "real_estate", "restaurant", "ecommerce", "custom")


@pytest.mark.parametrize("vertical", VERTICALS)
async def test_vertical_template_imports_and_an_inbound_call_is_answered(app, client, providers, vertical):
    from app.models import CallLog, CatalogItem
    from app.verticals import VERTICALS as ENGINES

    if vertical not in ENGINES:
        pytest.skip(f"{vertical} is not an engine any more")
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical=vertical, plan="growth")
    headers, merchant = account["headers"], account["merchant"]
    engine = ENGINES[vertical]
    for kind in engine.kinds:
        template = await client.get(f"/api/catalog/template.csv?kind={kind.kind}", headers=headers)
        assert template.status_code == 200, template.text
        result = await ok(await client.post(f"/api/catalog/import?kind={kind.kind}", headers=headers, json={"csv": template.text}))
        assert result["created"] == 1 and not result["errors"], f"{vertical}/{kind.kind}: the template's own example row does not import: {result}"
    assert len(await fetch(CatalogItem, merchant_id=merchant["id"])) == len(engine.kinds)

    if "inbound" not in engine.flows:
        return
    providers.script(text_reply("We're open nine to five, Monday to Friday. Would you like to book?"))
    call = await dial(client, app, providers, to=merchant["inbound_number"], caller="+12125551001", call_sid=f"v3:e2e-{vertical}")
    assert merchant["business_name"] in call.agent_lines()[0], call.agent_lines()
    await call.says("What are your opening hours?")
    await call.peer.stop()
    await call.peer.finished(timeout=10.0)
    await settle_background()
    [log] = await fetch(CallLog, id=call.call_log_id)
    assert log.call_status == "completed" and log.flow and log.direction == "inbound", (log.call_status, log.flow)
    assert "Customer: What are your opening hours?" in log.transcript, log.transcript


async def test_clinic_patient_books_then_calls_back_to_cancel(app, client, providers):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.models import CallLog, Order
    from tests.e2e.fakes import tool_reply
    from tests.e2e.phone import booking_day

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="clinic", plan="growth")
    headers, number = account["headers"], account["merchant"]["inbound_number"]
    await ok(await client.post("/api/catalog", headers=headers, json={
        "name": "Dr. Nair", "specialty": "Pediatrics", "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "start_time": "09:00", "end_time": "17:00", "fee": 50,
    }), 201)
    day, caller = booking_day(4), "+12125551101"
    providers.script(tool_reply("save_details", {"intent": "book", "doctor": "D1", "date": day, "time_pref": "10:00", "patient_name": "Emma Stone"}), tool_reply("end_call"))
    call = await dial(client, app, providers, to=number, caller=caller, call_sid="v3:e2e-clinic-book")
    await call.says("I'd like to see Dr Nair at 10, for Emma Stone")
    assert "Dr. Nair for Emma Stone" in call.agent_lines()[-1], call.agent_lines()
    await call.says("yes")
    await call.wraps_up()
    await settle_background()
    [record] = await fetch(Order, merchant_id=account["merchant"]["id"])
    assert record.kind == "appointment" and record.status.value == "confirmed" and record.customer_phone == caller
    assert record.scheduled_at == datetime.fromisoformat(f"{day}T10:00").replace(tzinfo=ZoneInfo("America/New_York"))

    # The same number calls back: the agent finds the appointment in Postgres and cancels it.
    providers.script(tool_reply("save_details", {"intent": "cancel", "appointment": "A1"}), tool_reply("end_call"))
    call = await dial(client, app, providers, to=number, caller=caller, call_sid="v3:e2e-clinic-cancel")
    await call.says("I need to cancel my appointment")
    assert "cancel" in call.agent_lines()[-1].lower(), call.agent_lines()
    await call.says("yes")
    await call.wraps_up()
    await settle_background()
    [record] = await fetch(Order, id=record.id)
    assert record.status.value == "cancelled", record.status
    [log] = await fetch(CallLog, id=call.call_log_id)
    assert log.outcome == "cancelled" and log.order_id == record.id
