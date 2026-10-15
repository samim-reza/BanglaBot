"""Audit log: cursors, metadata hygiene, best-effort writes and the admin listing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.cursor import decode_cursor, encode_cursor, page_size
from app.core.security import issue_admin_token
from app.db.session import get_db
from app.main import app
from app.models import AdminUser, AuditEvent
from app.services import admin_user_service as admins
from app.services import audit_service
from tests.security_fakes import FakeDB, FakeSessionFactory, db_override

T0 = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app.dependency_overrides.pop(get_db, None)


def test_cursor_round_trip_and_rejects_garbage():
    cursor = encode_cursor(T0, "e1")
    assert "=" not in cursor and decode_cursor(cursor) == (T0, "e1")
    assert decode_cursor(encode_cursor(T0.replace(tzinfo=None), "e2"))[0].tzinfo is not None
    for bad in ("", "!!!", "W10", "x" * 300, encode_cursor(T0, "e1")[:-3]):
        with pytest.raises(ValueError):
            decode_cursor(bad)
    assert (page_size(0), page_size(500), page_size(None), page_size("7")) == (50, 100, 50, 7)


def test_meta_is_masked_and_capped():
    meta = audit_service.clean_meta({"password": "hunter2", "code": "123456", "status_code": 200, "nested": {"api_key": "k"}, "note": "ok"})
    assert meta == {"password": "***", "code": "***", "status_code": 200, "nested": {"api_key": "***"}, "note": "ok"}
    big = audit_service.clean_meta({"blob": "x" * 5000})
    assert big["truncated"] is True and len(str(big).encode()) <= audit_service.MAX_META_BYTES
    assert audit_service.clean_meta(None) == {}


async def test_record_writes_its_own_row_and_never_raises(monkeypatch):
    factory = FakeSessionFactory()
    monkeypatch.setattr(audit_service, "session_factory", factory)
    await audit_service.record(action="admin.login", actor_type="admin", actor_id="a1", ip="1.2.3.4", meta={"via": "user"})
    event = factory.added[0]
    assert (event.action, event.actor_type, event.actor_id, event.ip, event.meta) == ("admin.login", "admin", "a1", "1.2.3.4", {"via": "user"})
    assert factory.commits == 1
    monkeypatch.setattr(audit_service, "session_factory", FakeSessionFactory(fail=True))
    await audit_service.record(action="admin.login")  # swallowed and logged
    db = FakeDB()
    audit_service.stage(db, action="flow.saved", actor_type="bogus", merchant_id="m1")
    assert db.added[0].actor_type == "system" and db.added[0].merchant_id == "m1" and db.commits == 0


def _events(n: int) -> list[AuditEvent]:
    return [AuditEvent(id=f"e{i}", at=T0 - timedelta(minutes=i), action="admin.login", actor_type="admin", actor_id="a1", meta={}) for i in range(n)]


async def test_list_events_keyset_pagination():
    db = FakeDB(scalar_rows=[_events(3)])
    page = await audit_service.list_events(db, limit=2, action="admin.*", merchant_id="m1")
    assert [item["id"] for item in page["items"]] == ["e0", "e1"]
    assert decode_cursor(page["next_cursor"]) == (T0 - timedelta(minutes=1), "e1")
    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "LIMIT" in sql and "ORDER BY audit_events.at DESC, audit_events.id DESC" in sql
    assert "audit_events.action LIKE" in sql and "audit_events.merchant_id =" in sql
    db = FakeDB(scalar_rows=[_events(1)])
    last = await audit_service.list_events(db, limit=2, cursor=page["next_cursor"])
    assert last["next_cursor"] is None
    assert "(audit_events.at, audit_events.id) < (" in str(db.statements[0].compile(dialect=postgresql.dialect()))


def test_admin_audit_endpoint_roles_and_cursor(monkeypatch):
    async def users_exist(db):
        return True

    monkeypatch.setattr(admins, "has_admin_users", users_exist)
    support = AdminUser(id="s1", username="help", role="support", password_hash="", token_version=0, active=True)
    finance = AdminUser(id="f1", username="money", role="finance", password_hash="", token_version=0, active=True)
    db = FakeDB(support, finance, scalar_rows=[_events(2)])
    app.dependency_overrides[get_db] = db_override(db)
    client = TestClient(app)

    def bearer(user):
        return {"Authorization": f"Bearer {issue_admin_token(sub=user.id, username=user.username, role=user.role)}"}

    ok = client.get("/api/admin/audit?limit=5&actor_type=admin", headers=bearer(support))
    assert ok.status_code == 200 and [item["id"] for item in ok.json()["items"]] == ["e0", "e1"] and ok.json()["next_cursor"] is None
    assert client.get("/api/admin/audit", headers=bearer(finance)).status_code == 403
    assert client.get("/api/admin/audit?cursor=garbage", headers=bearer(support)).status_code == 422
    assert client.get("/api/admin/audit?limit=500", headers=bearer(support)).status_code == 422
