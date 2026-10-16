"""Tenant isolation (IDOR): another account's records, calls, catalog items, add-on
requests and messages answer 404 — never data — and cross-account links are refused.
Routes run on ``FakeDB`` holding rows of two accounts (m1 signed in, m2 the victim)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.ratelimit import backends
from app.core.security import issue_merchant_token
from app.db.session import get_db
from app.main import app
from app.models import AddonRequest, CallLog, CatalogItem, Merchant, Order, OrderStatus
from app.services import audit_service
from app.services.calendar import ics_feed
from tests.security_fakes import FakeDB, FakeSessionFactory, db_override, make_merchant

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def _theirs() -> list:
    """Rows owned by the other account (m2)."""
    return [
        Order(id="o2", merchant_id="m2", kind="appointment", customer_name="Victim", customer_phone="+14155550199",
              status=OrderStatus.pending, details={}, flow_data={}, created_at=NOW),
        CallLog(id="c2", merchant_id="m2", recording_sid="rec_victim", call_status="completed"),
        CatalogItem(id="i2", merchant_id="m2", kind="doctor", name="Their doctor", data={}, active=True, sort_order=0),
        AddonRequest(id="r2", merchant_id="m2", addon="web_chat", quantity=1, status="pending"),
    ]


@pytest.fixture
def tenant(monkeypatch):
    backends.memory.reset()
    monkeypatch.setattr(audit_service, "session_factory", FakeSessionFactory())
    me = make_merchant(id="m1", vertical="clinic")
    mine = Order(id="o1", merchant_id="m1", kind="appointment", customer_name="Mine", customer_phone="+14155550111",
                 status=OrderStatus.pending, details={}, flow_data={}, created_at=NOW)
    db = FakeDB(me, make_merchant(id="m2", username="victim"), mine, *_theirs())
    app.dependency_overrides[get_db] = db_override(db)
    yield TestClient(app), {"Authorization": f"Bearer {issue_merchant_token(me)}"}, db
    app.dependency_overrides.pop(get_db, None)
    backends.memory.reset()


FOREIGN = [
    ("GET", "/api/orders/o2", None, "Record not found"),
    ("PATCH", "/api/orders/o2", {"customer_name": "Hijacked"}, "Record not found"),
    ("DELETE", "/api/orders/o2", None, "Record not found"),
    ("POST", "/api/orders/o2/call", None, "Record not found"),
    ("POST", "/api/orders/o2/mark-paid", None, "Record not found"),
    ("GET", "/api/orders/recordings/c2", None, "Call log not found"),
    ("GET", "/api/calls/c2/recording", None, "Call not found"),
    ("PATCH", "/api/catalog/i2", {"name": "Hijacked"}, "Catalog item not found"),
    ("DELETE", "/api/catalog/i2", None, "Catalog item not found"),
    ("DELETE", "/api/addons/requests/r2", None, "Request not found"),
    ("POST", "/api/integrations/messages/order/o2", {}, "Record not found"),
    ("PUT", "/api/integrations/calendar/items/i2", {"calendar_ics": "https://cal.example.com/a.ics"}, "Catalog item not found"),
]


@pytest.mark.parametrize(("method", "url", "body", "detail"), FOREIGN, ids=[f"{m} {u}" for m, u, *_ in FOREIGN])
def test_other_accounts_objects_are_404(tenant, method, url, body, detail):
    client, headers, db = tenant
    response = client.request(method, url, json=body, headers=headers)
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": detail}
    # Nothing of theirs changed, was deleted or committed.
    assert db.deleted == [] and db.commits == 0
    victim = db.rows[(Order, "o2")]
    assert victim.customer_name == "Victim" and victim.status == OrderStatus.pending


def test_unknown_ids_look_exactly_like_foreign_ones(tenant):
    client, headers, _ = tenant
    foreign = client.get("/api/orders/o2", headers=headers)
    missing = client.get("/api/orders/does-not-exist", headers=headers)
    assert foreign.status_code == missing.status_code == 404 and foreign.json() == missing.json()


def test_own_record_cannot_be_linked_to_another_accounts_catalog_item(tenant):
    client, headers, db = tenant
    response = client.patch("/api/orders/o1", json={"catalog_item_id": "i2"}, headers=headers)
    assert response.status_code == 422 and "does not belong to this account" in response.json()["detail"]
    assert db.rows[(Order, "o1")].catalog_item_id is None and db.commits == 0


def test_list_queries_are_scoped_to_the_signed_in_account(tenant):
    client, headers, db = tenant
    for url in ("/api/catalog", "/api/addons", "/api/integrations/messages?order_id=o2"):
        db.statements.clear()
        assert client.get(url, headers=headers).status_code == 200, url
        compiled = [stmt.compile(dialect=postgresql.dialect()) for stmt in db.statements]
        assert compiled, url
        for statement in compiled:
            assert "merchant_id" in str(statement) and "m1" in statement.params.values(), (url, str(statement))
            assert "m2" not in statement.params.values()


def test_a_facebook_page_connected_elsewhere_is_refused(tenant, monkeypatch):
    from app.core.addons import entitlements

    client, headers, db = tenant
    monkeypatch.setattr(entitlements(db.rows[(Merchant, "m1")]).__class__, "has_channel", lambda self, channel: True)
    db.scalar_queue.append("m2")  # meta_channels.taken(): another account has this page
    response = client.put("/api/channels/messenger", json={"page_id": "1234567", "page_token": "t" * 30}, headers=headers)
    assert response.status_code == 409 and db.commits == 0


class _FeedSession:
    def __init__(self) -> None:
        self.statements: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalars(self, stmt):
        self.statements.append(stmt)
        return []


async def test_calendar_feed_only_names_its_own_catalog_items(monkeypatch):
    session = _FeedSession()
    monkeypatch.setattr(ics_feed, "AsyncSessionLocal", lambda: session)

    async def by_token(db, token):
        return make_merchant(id="m1")

    monkeypatch.setattr(ics_feed, "merchant_for_feed_token", by_token)
    result = await ics_feed.feed("feed-token-123", "i2")  # someone else's item id
    assert result is not None and "Their doctor" not in result[1]
    for stmt in session.statements:
        compiled = stmt.compile(dialect=postgresql.dialect())
        assert "merchant_id" in str(compiled) and "m1" in compiled.params.values()
