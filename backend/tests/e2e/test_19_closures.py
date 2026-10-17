"""Closure dates on real SQL: the owner saves holidays and one stylist's day off, the list survives
other settings saves, bad input and other accounts are refused, and a website visitor asking
for a closed day is told why — nothing is booked."""

from __future__ import annotations

from datetime import date, timedelta

from tests.e2e.api import admin_token, create_account, fetch, ok, salon_with_widget
from tests.e2e.fakes import tool_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import booking_day, salon_booking


async def test_owner_saves_closures_and_the_agent_refuses_the_day(client, providers):
    from app.models import Merchant, Order

    account = await salon_with_widget(client)
    headers, key, mid = account["headers"], account["merchant"]["widget_key"], account["merchant"]["id"]
    listed = await ok(await client.get("/api/closures", headers=headers))
    assert listed["closures"] == [] and [item["name"] for item in listed["items"]] == ["Maya"]
    maya = listed["items"][0]["id"]

    closed, off = booking_day(4), booking_day(6)
    later = (date.fromisoformat(off) + timedelta(days=2)).isoformat()
    body = {"closures": [
        {"start": off, "item_id": maya},
        {"start": closed, "label": "Staff training"},
        {"start": off, "end": later, "label": "Holidays"},
        {"start": "2020-01-01", "label": "long gone"},
    ]}
    saved = await ok(await client.put("/api/closures", json=body, headers=headers))
    assert [(row["start"], row["label"], row["item_id"]) for row in saved["closures"]] == [
        (closed, "Staff training", ""), (off, "", maya), (off, "Holidays", ""),
    ]
    assert saved["closures"][2]["end"] == later

    # Another settings save keeps the list; bad input, other accounts and anonymous callers are refused.
    await ok(await client.patch("/api/auth/me", json={"vertical_config": {"slot_minutes": 30}}, headers=headers))
    [row] = await fetch(Merchant, id=mid)
    assert len(row.vertical_config["closures"]) == 3 and row.vertical_config["slot_minutes"] == 30
    bad = await client.put("/api/closures", json={"closures": [{"start": closed, "end": "2020-01-01"}]}, headers=headers)
    assert bad.status_code == 422 and "before the start" in bad.json()["detail"]
    stranger = await client.put("/api/closures", json={"closures": [{"start": closed, "item_id": "not-mine"}]}, headers=headers)
    assert stranger.status_code == 422
    other = await create_account(client, await admin_token(client), vertical="clinic", plan="growth")
    assert (await ok(await client.get("/api/closures", headers=other["headers"])))["closures"] == []
    assert (await client.get("/api/closures")).status_code == 401

    # A visitor asks for a haircut on the closed day: the agent says why and books nothing.
    providers.script(tool_reply("save_details", salon_booking(closed, "14:00", "Lee Park")), tool_reply("end_call"))
    start = await ok(await client.post(f"/api/public/widget/{key}/start", headers={"Origin": "https://customer-site.example"}))
    said = await ok(await client.post(
        f"/api/public/widget/{key}/say", json={"session_id": start["session_id"], "text": "A haircut with Maya at 2pm, I'm Lee Park"}
    ))
    line = said["messages"][-1]
    assert line.startswith("We're closed on ") and "for Staff training — the next open day is" in line, line
    assert "Closed — no bookings on these dates:" in "\n".join(str(m.get("content")) for m in providers.llms[-1].requests[-1]["messages"])
    await client.post(f"/api/public/widget/{key}/say", json={"session_id": start["session_id"], "text": "ok bye"})
    assert not await fetch(Order, merchant_id=mid)
    assert not await settle_background()
