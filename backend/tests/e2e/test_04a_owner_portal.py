"""Owner portal: settings, catalog CRUD + CSV import, records (pagination, filters, cancel,
reschedule, delete), channels and the integrations summary."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tests.e2e.api import admin_token, create_account, ok
from tests.e2e.phone import booking_day

STAFF_CSV = "name,days,start_time,end_time\nLeo,\"mon,tue,wed\",09:00,17:00\nNia,\"thu,fri\",10:00,18:00\n,mon,09:00,17:00\nLate,mon,25:00,17:00\n"
EVERY_DAY = {"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "start_time": "09:00", "end_time": "18:00"}


async def _salon(client, plan: str = "growth"):  # noqa: ANN001, ANN202
    admin = await admin_token(client)
    return await create_account(client, admin, vertical="salon", plan=plan)


async def test_settings_update_and_validation(client):
    account = await _salon(client)
    headers = account["headers"]
    me = await ok(await client.patch(
        "/api/auth/me", headers=headers,
        json={"business_name": "  Glow Studio  ", "custom_greeting": "Hi, Glow here!", "knowledge": "Parking behind the shop.",
              "support_phone": "+1 415 555 0177", "vertical_config": {"booking_horizon_days": 21}, "silence_hangup_secs": 12},
    ))
    assert me["business_name"] == "Glow Studio" and me["custom_greeting"] == "Hi, Glow here!" and me["silence_hangup_secs"] == 12
    assert me["vertical_config"]["booking_horizon_days"] == 21
    workspace = await ok(await client.get("/api/auth/workspace", headers=headers))
    assert workspace["merchant"]["knowledge"] == "Parking behind the shop." and workspace["config"]["booking_horizon_days"] == 21
    assert workspace["entitlements"]["plan"] == "growth" and workspace["entitlements"]["limits"]["max_concurrent_calls"] == 4
    for bad in ({"timezone": "Mars/Base"}, {"silence_hangup_secs": 2}, {"voice_persona": "robot"}, {"max_call_seconds": 30}):
        assert (await client.patch("/api/auth/me", json=bad, headers=headers)).status_code == 422, bad
    # The admin-only fields are not the owner's to change.
    await ok(await client.patch("/api/auth/me", json={"inbound_number": "+19998887777", "plan": "pro"}, headers=headers))
    me = await ok(await client.get("/api/auth/me", headers=headers))
    assert me["inbound_number"] == account["merchant"]["inbound_number"] and me["plan"] == "growth"


async def test_catalog_crud_and_csv_import(client):
    account = await _salon(client)
    headers = account["headers"]
    service = await ok(await client.post("/api/catalog?kind=service", headers=headers, json={"name": "Balayage", "duration_minutes": 120, "price": 180}), 201)
    assert service["kind"] == "service" and service["data"]["duration_minutes"] == 120
    assert (await client.post("/api/catalog?kind=service", headers=headers, json={"duration_minutes": 30})).status_code == 422
    assert (await client.post("/api/catalog?kind=spaceship", headers=headers, json={"name": "X"})).status_code == 422
    patched = await ok(await client.patch(f"/api/catalog/{service['id']}", headers=headers, json={"data": {"price": 200}}))
    assert patched["data"]["price"] == 200 and patched["data"]["duration_minutes"] == 120

    template = await client.get("/api/catalog/template.csv?kind=staff", headers=headers)
    assert template.status_code == 200 and template.text.splitlines()[0].startswith("name,")
    result = await ok(await client.post("/api/catalog/import?kind=staff", headers=headers, json={"csv": STAFF_CSV}))
    assert result["created"] == 2 and result["skipped"] == 2 and len(result["errors"]) == 2, result
    staff = await ok(await client.get("/api/catalog?kind=staff", headers=headers))
    assert [row["name"] for row in staff] == ["Leo", "Nia"] and staff[0]["data"]["days"] == ["mon", "tue", "wed"]
    replaced = await ok(await client.post("/api/catalog/import?kind=staff", headers=headers, json={"csv": "name,days,start_time,end_time\nOmar,sat,10:00,16:00\n", "replace": True}))
    assert replaced["created"] == 1
    assert [row["name"] for row in await ok(await client.get("/api/catalog?kind=staff", headers=headers))] == ["Omar"]

    assert (await client.delete(f"/api/catalog/{service['id']}", headers=headers)).status_code == 204
    assert await ok(await client.get("/api/catalog?kind=service", headers=headers)) == []
    # Another account's item is invisible.
    other = await _salon(client)
    foreign = await ok(await client.post("/api/catalog?kind=service", headers=other["headers"], json={"name": "Theirs", "duration_minutes": 30}), 201)
    assert (await client.patch(f"/api/catalog/{foreign['id']}", headers=headers, json={"name": "Mine"})).status_code == 404


async def test_records_pagination_filters_cancel_reschedule_delete(client):
    account = await _salon(client)
    headers = account["headers"]
    staff = await ok(await client.post("/api/catalog?kind=staff", headers=headers, json={"name": "Maya", **EVERY_DAY}), 201)
    ids = []
    for index in range(5):
        record = await ok(await client.post("/api/orders", headers=headers, json={
            "customer_name": f"Client {index}", "customer_phone": f"+1415555{index:04d}", "service": "Haircut",
            "catalog_item_id": staff["id"], "scheduled_at": f"{booking_day(10 + index)}T10:00",
        }), 201)
        ids.append(record["id"])
    page1 = await ok(await client.get("/api/orders?page=1&page_size=2", headers=headers))
    page3 = await ok(await client.get("/api/orders?page=3&page_size=2", headers=headers))
    assert page1["total"] == 5 and len(page1["items"]) == 2 and len(page3["items"]) == 1
    assert page1["items"][0]["id"] == ids[-1]  # newest first
    by_time = await ok(await client.get("/api/orders?sort=scheduled&page_size=10", headers=headers))
    assert [row["id"] for row in by_time["items"]] == ids
    assert [row["customer_name"] for row in (await ok(await client.get("/api/orders?search=Client%203", headers=headers)))["items"]] == ["Client 3"]
    assert (await ok(await client.get("/api/orders?upcoming=true", headers=headers)))["total"] == 5
    assert (await client.get("/api/orders?status=bogus", headers=headers)).status_code == 422

    cancelled = await ok(await client.patch(f"/api/orders/{ids[0]}", headers=headers, json={"status": "cancelled"}))
    assert cancelled["status"] == "cancelled"
    moved = await ok(await client.patch(f"/api/orders/{ids[1]}", headers=headers, json={"scheduled_at": f"{booking_day(20)}T15:30"}))
    local = datetime.fromisoformat(moved["scheduled_at"]).astimezone(ZoneInfo("America/New_York"))
    assert local.strftime("%Y-%m-%d %H:%M") == f"{booking_day(20)} 15:30"  # a naive time is the business's local time
    assert (await ok(await client.get("/api/orders?status=cancelled", headers=headers)))["total"] == 1
    stats = await ok(await client.get("/api/orders/stats", headers=headers))
    assert stats["total"] == 5 and stats["cancelled"] == 1 and stats["pending"] == 4
    assert (await client.delete(f"/api/orders/{ids[2]}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/orders/{ids[2]}", headers=headers)).status_code == 404
    assert (await client.patch(f"/api/orders/{ids[3]}", headers=headers, json={"status": "calling"})).status_code == 422


async def test_channels_and_integrations_summary(client):
    account = await _salon(client)
    headers = account["headers"]
    channels = await ok(await client.get("/api/channels", headers=headers))
    assert "whatsapp" in str(channels) and "messenger" in str(channels)
    staff = await ok(await client.post("/api/catalog?kind=staff", headers=headers, json={"name": "Maya", **EVERY_DAY}), 201)
    await ok(await client.post("/api/catalog?kind=service", headers=headers, json={"name": "Haircut", "duration_minutes": 45}), 201)
    summary = await ok(await client.post("/api/integrations/calendar/feed-token", headers=headers))
    calendar = summary["calendar"]
    assert calendar["feed_url"].startswith("http://testserver/api/public/calendar/") and calendar["public"] is True
    # Salon bookings are per stylist: the per-calendar feeds must be the staff's, not the services'.
    assert [item["name"] for item in calendar["items"]] == ["Maya"] and calendar["items"][0]["id"] == staff["id"]
    assert summary["sms"]["platform_ready"] is False
    bad = await client.patch("/api/integrations/calendar", headers=headers, json={"busy_ics_urls": ["http://127.0.0.1/cal.ics"]})
    assert bad.status_code == 422


async def test_staff_without_any_valid_working_day_is_refused(client):
    account = await _salon(client)
    result = await ok(await client.post("/api/catalog/import?kind=staff", headers=account["headers"], json={"csv": "name,days,start_time,end_time\nNobody,funday,09:00,17:00\n"}))
    assert result["created"] == 0
