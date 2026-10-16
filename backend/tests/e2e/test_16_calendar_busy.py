"""Calendar integration (in): a stylist's busy iCal link, fetched through the outbound guard,
keeps the agent from offering a time that is taken in the owner's own calendar."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from tests.e2e.api import fetch, ok, salon_with_widget
from tests.e2e.fakes import tool_reply
from tests.e2e.fixtures import settle_background
from tests.e2e.phone import booking_day, salon_booking

ICS_URL = "https://cal.example.test/maya.ics"


def _ics(start: datetime) -> str:
    stamp = start.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    end = start.replace(hour=start.hour + 2).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//e2e//EN", "BEGIN:VEVENT", "UID:busy-1@e2e", f"DTSTAMP:{stamp}",
        f"DTSTART:{stamp}", f"DTEND:{end}", "SUMMARY:Dentist", "END:VEVENT", "END:VCALENDAR", "",
    ])


@pytest.fixture
def calendar_server(monkeypatch):  # noqa: ANN001, ANN201
    from app.core.security import outbound

    served: dict[str, str] = {}
    hits: list[httpx.Request] = []

    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request)
        body = served.get(request.headers.get("host", "") + request.url.path)
        return httpx.Response(200, text=body, headers={"Content-Type": "text/calendar"}) if body else httpx.Response(404)

    monkeypatch.setattr(outbound, "resolver", resolve)
    monkeypatch.setattr(outbound, "transport", httpx.MockTransport(handler))
    return served, hits


async def test_a_busy_ical_event_blocks_that_time(client, providers, calendar_server):
    from app.models import Order

    served, hits = calendar_server
    account = await salon_with_widget(client)
    headers, key = account["headers"], account["merchant"]["widget_key"]
    day = booking_day(5)
    busy_start = datetime.fromisoformat(f"{day}T11:00").replace(tzinfo=ZoneInfo("America/New_York"))
    served["cal.example.test/maya.ics"] = _ics(busy_start)
    summary = await ok(await client.get("/api/integrations", headers=headers))
    [maya] = summary["calendar"]["items"]
    assert maya["name"] == "Maya"
    saved = await ok(await client.put(f"/api/integrations/calendar/items/{maya['id']}", json={"calendar_ics": ICS_URL}, headers=headers))
    assert saved["calendar"]["items"][0]["calendar_ics"] == ICS_URL

    providers.script(tool_reply("save_details", salon_booking(day, "11:00", "Busy Caller")), tool_reply("save_details", {"phone": "4155550199"}), tool_reply("end_call"))
    session_id = (await ok(await client.post(f"/api/public/widget/{key}/start")))["session_id"]
    assert hits and hits[0].headers["host"] == "cal.example.test"  # fetched while the chat opened
    replies = []
    for text in ("A haircut with Maya at 11, I'm Busy Caller", "415 555 0199"):
        replies = (await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": session_id, "text": text})))["messages"]
    readback = replies[-1]
    # Maya is at the dentist 11–1: the agent says so and proposes the nearest free time instead.
    assert "11 AM isn't free" in readback and "Shall I book it?" in readback and " at 11 AM" not in readback, readback
    await ok(await client.post(f"/api/public/widget/{key}/say", json={"session_id": session_id, "text": "yes please"}))
    await settle_background()
    [record] = await fetch(Order, merchant_id=account["merchant"]["id"])
    local = record.scheduled_at.astimezone(ZoneInfo("America/New_York"))
    assert not (busy_start <= local < busy_start.replace(hour=13)), local
