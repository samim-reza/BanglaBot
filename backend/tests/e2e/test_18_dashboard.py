"""The owner dashboard's summary on real SQL: what the agent did this week, after-hours calls from
the doctors' own hours, test traffic and other accounts never counted, and the outbound section
only for accounts that place calls."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from tests.e2e.api import admin_token, create_account, ok

NY = ZoneInfo("America/New_York")
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]


def past_weekday(now: datetime) -> datetime:
    """A Monday–Friday 1–6 days ago, business-local (inside the 7-day range, never today)."""
    for back in range(1, 7):
        day = (now - timedelta(days=back)).date()
        if day.weekday() < 5:
            return datetime.combine(day, time(0, 0), tzinfo=NY)
    raise AssertionError("no weekday in the last six days")


async def _insert(*rows) -> None:  # noqa: ANN002
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        session.add_all(list(rows))
        await session.commit()


async def _clinic(client, admin: str) -> dict:  # noqa: ANN001
    account = await create_account(client, admin, vertical="clinic", plan="growth")
    await ok(await client.post("/api/catalog", headers=account["headers"], json={
        "name": "Dr. Lee", "specialty": "Family medicine", "days": WEEKDAYS, "start_time": "09:00", "end_time": "17:00",
    }), 201)
    return account


async def test_the_week_summary_counts_what_the_agent_did(client):
    from app.models import CallLog, Order, OrderStatus

    admin = await admin_token(client)
    account = await _clinic(client, admin)
    other = await _clinic(client, admin)
    mid, headers = account["merchant"]["id"], account["headers"]
    now = datetime.now(NY)
    day = past_weekday(now)
    recent = max(now - timedelta(minutes=5), datetime.combine(now.date(), time(0, 0), tzinfo=NY))  # earlier today
    # The doctor works Monday–Friday 9–5: whether "just now" is after hours depends on when this runs.
    now_after_hours = not (now.weekday() < 5 and time(9, 0) <= now.time() < time(17, 0))

    def call(direction: str, at: datetime, **extra) -> CallLog:  # noqa: ANN003
        return CallLog(merchant_id=mid, direction=direction, created_at=at, **{"call_status": "completed", **extra})

    def record(source: str, **extra) -> Order:  # noqa: ANN003
        values = {"kind": "appointment", "customer_name": "Pat", "customer_phone": "+12125550199", "status": OrderStatus.confirmed, **extra}
        return Order(merchant_id=mid, source=source, created_at=recent, **values)

    await _insert(
        call("inbound", day + timedelta(hours=10), duration_secs=120, outcome="booked"),          # in hours
        call("inbound", day + timedelta(hours=22), duration_secs=60, outcome="transfer"),         # after hours
        call("inbound", day + timedelta(hours=11), call_status="busy", outcome="busy"),           # never answered
        call("widget", day + timedelta(hours=12), transcript="Agent: Hi\nCustomer: are you open?"),
        call("whatsapp", day + timedelta(hours=13), transcript="Agent: Hi", outcome="emergency"),  # urgent, but nobody wrote
        call("web", day + timedelta(hours=14), duration_secs=500, outcome="transfer"),            # portal test call
        call("inbound", now - timedelta(days=20), duration_secs=30),                              # 30 days only
        call("inbound", now - timedelta(days=40), duration_secs=30),                              # out of every range
        record("inbound_call", total_amount=Decimal("80.00"), scheduled_at=now + timedelta(days=2)),
        record("whatsapp", kind="lead", status=OrderStatus.needs_review),
        record("inbound_call", status=OrderStatus.cancelled, total_amount=Decimal("99.00")),       # cancelled later
        record("manual", total_amount=Decimal("500.00")),                                          # the owner's own
        record("test", total_amount=Decimal("700.00")),                                            # a test call
    )
    await _insert(call("inbound", now, duration_secs=90))  # just now: today

    week = await ok(await client.get("/api/dashboard/summary?range=7d", headers=headers))
    assert week["inbound_first"] is True and week["timezone"] == "America/New_York" and week["currency"] == "USD"
    assert (week["calls_answered"], week["chats_handled"], week["transfers_urgent"]) == (3, 1, 2), week
    assert week["after_hours"] == 1 + int(now_after_hours), week
    assert (week["bookings"], week["bookings_value"], week["messages_leads"]) == (1, 80.0, 1), week
    assert week["minutes_used"] == round((120 + 60 + 90) / 60, 1) and week["avg_call_secs"] == 90 and week["hours_known"] is True
    assert week["outbound"] is None

    today = await ok(await client.get("/api/dashboard/summary?range=today", headers=headers))
    assert today["calls_answered"] == 1 and today["bookings"] == 1
    assert datetime.fromisoformat(today["start"]).astimezone(NY).time() == time(0, 0)
    month = await ok(await client.get("/api/dashboard/summary?range=30d", headers=headers))
    assert month["calls_answered"] == 4

    # Another account sees none of it; a bad range or no sign-in is refused.
    assert (await ok(await client.get("/api/dashboard/summary", headers=other["headers"])))["calls_answered"] == 0
    assert (await client.get("/api/dashboard/summary?range=year", headers=headers)).status_code == 422
    assert (await client.get("/api/dashboard/summary")).status_code == 401

    # Reminder calls placed → the secondary outbound section appears, with the status tiles.
    await _insert(
        call("outbound", now - timedelta(hours=1), duration_secs=40, outcome="confirmed"),
        call("outbound", now - timedelta(hours=1), call_status="no-answer", outcome="no_answer"),
    )
    week = await ok(await client.get("/api/dashboard/summary?range=7d", headers=headers))
    outbound = week["outbound"]
    assert outbound is not None and (outbound["calls"], outbound["confirmed"], outbound["no_answer"]) == (2, 1, 1), outbound
    assert outbound["statuses"]["total"] == 5 and outbound["statuses"]["confirmed"] == 3
    assert week["minutes_used"] == round((120 + 60 + 90 + 40) / 60, 1)


async def test_order_confirmation_accounts_are_outbound_first(client):
    from app.models import CallLog, Order, OrderStatus

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="ecommerce", plan="growth", inbound=False)
    mid = account["merchant"]["id"]
    order = await ok(await client.post("/api/orders", headers=account["headers"], json={
        "customer_name": "Cash Buyer", "customer_phone": "+14155550444", "items_summary": "Hoodie x1", "total_amount": 40,
    }), 201)
    await _insert(
        CallLog(merchant_id=mid, order_id=order["id"], direction="outbound", call_status="completed", outcome="confirmed", duration_secs=50),
        CallLog(merchant_id=mid, direction="outbound", call_status="completed", outcome="not_interested", duration_secs=20),
        Order(merchant_id=mid, source="manual", kind="order", customer_name="Later", customer_phone="+14155550445", status=OrderStatus.pending),
    )
    summary = await ok(await client.get("/api/dashboard/summary?range=today", headers=account["headers"]))
    assert summary["inbound_first"] is False and summary["hours_known"] is False
    outbound = summary["outbound"]
    assert (outbound["calls"], outbound["confirmed"], outbound["cancelled"]) == (2, 1, 1), outbound
    assert outbound["statuses"]["pending"] == 2 and outbound["statuses"]["total"] == 2
    assert summary["bookings"] == 0 and summary["minutes_used"] == round(70 / 60, 1)


async def test_finish_setup_requests_a_phone_number_the_admin_assigns(client):
    from tests.e2e.api import bearer, next_number

    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth", inbound=False)
    headers, mid = account["headers"], account["merchant"]["id"]
    assert await ok(await client.get("/api/phone-line", headers=headers)) == {"number": "", "request": None}

    first = await ok(await client.post("/api/phone-line/request", json={"note": "212 area code"}, headers=headers), 201)
    again = await ok(await client.post("/api/phone-line/request", json={}, headers=headers), 201)
    assert first["request"]["status"] == "pending" and again["request"]["id"] == first["request"]["id"]
    assert again["request"]["note"] == "212 area code"

    # It sits in the admin's queue; approving it needs the number assigned first, and switches no add-on on.
    queue = await ok(await client.get("/api/admin/addon-requests", headers=bearer(admin)))
    [row] = [item for item in queue["items"] if item["merchant_id"] == mid]
    assert row["addon"] == "phone_line" and row["addon_name"] == "Phone number (included)"
    early = await client.post(f"/api/admin/addon-requests/{row['id']}/approve", json={}, headers=bearer(admin))
    assert early.status_code == 409
    number = next_number()
    await ok(await client.patch(f"/api/admin/merchants/{mid}", json={"inbound_number": number}, headers=bearer(admin)))
    decided = await ok(await client.post(f"/api/admin/addon-requests/{row['id']}/approve", json={"admin_note": "done"}, headers=bearer(admin)))
    assert decided["status"] == "approved"
    view = await ok(await client.get("/api/phone-line", headers=headers))
    assert view["number"] == number and view["request"]["status"] == "approved"
    assert "phone_line" not in (await ok(await client.get("/api/auth/me", headers=headers)))["addons"]
    assert (await client.post("/api/phone-line/request", json={}, headers=headers)).status_code == 409
