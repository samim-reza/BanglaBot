"""Rate limiting, owner sign-in, tenant isolation, HTTP hardening and log redaction.

No database: routes run against ``FakeDB`` through the ``get_db`` override, the
limiter uses its in-memory store, and the audit log writes into a fake session.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.http_security import BodySizeLimitMiddleware, cors_origins
from app.core.log_redaction import AccessLogFilter, redact_event, scrub
from app.core.ratelimit import backends, lockout, parse_client_ip
from app.core.security import hash_password, issue_merchant_token, sign_media_stream_token, verify_token
from app.core.security.passwords import legacy_pbkdf2_hash
from app.db.session import get_db
from app.main import app
from app.models import CallLog, Order
from app.services import audit_service
from app.services.tenancy import owned, scoped
from tests.security_fakes import FakeDB, FakeSessionFactory, db_override, make_merchant

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    backends.memory.reset()
    monkeypatch.setattr(audit_service, "session_factory", FakeSessionFactory())
    yield
    backends.memory.reset()
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)  # no `with`: the lifespan (database bootstrap) never runs


# ------------------------------------------------------------------ client IP + limiter
def test_client_ip_honours_trusted_hops():
    assert parse_client_ip("6.6.6.6, 1.2.3.4", "10.0.0.1", 1) == "1.2.3.4"  # spoofed left entry ignored
    assert parse_client_ip("6.6.6.6, 1.2.3.4, 10.0.0.2", "10.0.0.1", 2) == "1.2.3.4"
    assert parse_client_ip("1.2.3.4", "10.0.0.1", 3) == "1.2.3.4"  # fewer entries than hops
    assert parse_client_ip("6.6.6.6", "10.0.0.1", 0) == "10.0.0.1"  # header ignored
    assert parse_client_ip(None, None, 1) == "unknown"


def test_memory_backend_sliding_window():
    store = backends.MemoryBackend()
    assert [store.hit_sync("k", 2, 60, now=t) for t in (0, 1)] == [0.0, 0.0]
    assert store.hit_sync("k", 2, 60, now=2) == pytest.approx(58)
    assert store.hit_sync("k", 2, 60, now=60.5) == 0.0  # the first hit left the window


async def test_lockout_grows_and_resets(monkeypatch):
    policy = lockout.LoginPolicy("t", per_ip=(100, 60), per_user=(100, 60), steps=((2, 60), (4, 300)))
    assert [lockout.lock_seconds(policy, n) for n in (1, 2, 3, 4, 9)] == [0, 60, 60, 300, 300]
    request = Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1)})
    await lockout.record_failure(policy, "Bob")
    await lockout.before_attempt(request, policy, "bob")
    assert await lockout.record_failure(policy, "bob") == 60
    with pytest.raises(HTTPException) as info:
        await lockout.before_attempt(request, policy, "BOB ")
    assert info.value.status_code == 429 and int(info.value.headers["Retry-After"]) >= 59
    await lockout.record_success(policy, "bob")
    await lockout.before_attempt(request, policy, "bob")


# ------------------------------------------------------------------ owner sign-in
def test_merchant_login_rehashes_legacy_passwords_and_encrypts_secrets(client):
    merchant = make_merchant(password_hash=legacy_pbkdf2_hash(PASSWORD, iterations=1000), token_version=2)
    merchant.webhook_secret_stored = "plaintext-secret"
    db = FakeDB(scalars=[merchant])
    app.dependency_overrides[get_db] = db_override(db)
    response = client.post("/api/auth/login", json={"username": "demo", "password": PASSWORD})
    assert response.status_code == 200, response.text
    claims = verify_token(response.json()["token"])
    assert claims["typ"] == "session" and claims["ver"] == 2 and claims["sub"] == "m1"
    assert merchant.password_hash.startswith("$argon2id$") and db.commits == 1
    assert merchant.webhook_secret_stored.startswith("enc:") and response.json()["merchant"]["webhook_secret"] == "plaintext-secret"
    assert response.headers["cache-control"] == "no-store"


def test_merchant_login_locks_out_after_repeated_failures(client):
    merchant = make_merchant(password_hash=hash_password(PASSWORD))
    db = FakeDB(scalars=[merchant] * 10)
    app.dependency_overrides[get_db] = db_override(db)
    codes = [client.post("/api/auth/login", json={"username": "demo", "password": "wrong-one"}).status_code for _ in range(5)]
    assert codes == [401] * 5
    blocked = client.post("/api/auth/login", json={"username": "demo", "password": PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1


def test_password_change_revokes_older_sessions(client):
    merchant = make_merchant(password_hash=hash_password(PASSWORD), token_version=0)
    old_token = issue_merchant_token(merchant)
    db = FakeDB(merchant)
    app.dependency_overrides[get_db] = db_override(db)
    headers = {"Authorization": f"Bearer {old_token}"}
    weak = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "password123"}, headers=headers)
    assert weak.status_code == 422
    ok = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "a-much-better-passphrase"}, headers=headers)
    assert ok.status_code == 200 and merchant.token_version == 1
    assert [event.action for event in db.added] == ["merchant.password_changed"]
    assert client.get("/api/auth/me", headers=headers).status_code == 401  # the old session is gone
    fresh = {"Authorization": f"Bearer {ok.json()['token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200


def test_portal_rejects_non_session_tokens(client):
    merchant = make_merchant()
    app.dependency_overrides[get_db] = db_override(FakeDB(merchant))
    media = sign_media_stream_token(order_id="o1", call_log_id="c1")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {media}"}).status_code == 401


# ------------------------------------------------------------------ tenant isolation
async def test_owned_hides_other_accounts_rows():
    mine, theirs = Order(id="o1", merchant_id="m1"), Order(id="o2", merchant_id="m2")
    db = FakeDB(mine, theirs)
    assert await owned(db, Order, "o1", make_merchant()) is mine
    for obj_id, owner in (("o2", "m1"), ("missing", "m1"), ("", "m1"), ("o1", "")):
        with pytest.raises(HTTPException) as info:
            await owned(db, Order, obj_id, owner, detail="Record not found")
        assert info.value.status_code == 404 and info.value.detail == "Record not found"
    from sqlalchemy import select

    assert "call_logs.merchant_id = :merchant_id_1" in str(scoped(select(CallLog), CallLog, "m1"))


def test_cross_tenant_recording_is_404(client):
    db = FakeDB(make_merchant(), CallLog(id="c9", merchant_id="m2"))
    app.dependency_overrides[get_db] = db_override(db)
    headers = {"Authorization": f"Bearer {issue_merchant_token(make_merchant())}"}
    assert client.get("/api/calls/c9/recording", headers=headers).status_code == 404


# ------------------------------------------------------------------ HTTP hardening
def test_security_headers(client):
    health = client.get("/health")
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in health.headers["content-security-policy"]
    assert health.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "strict-transport-security" not in health.headers  # development
    widget = client.get("/api/public/widget.js")
    assert "x-frame-options" not in widget.headers and widget.headers["access-control-allow-origin"] == "*"


def test_cors_split_between_widget_and_portal(client):
    preflight = {"Origin": "https://any-shop.example", "Access-Control-Request-Method": "POST"}
    widget = client.options("/api/public/widget/k/say", headers=preflight)
    assert widget.status_code == 204 and widget.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in widget.headers
    assert client.options("/api/auth/login", headers=preflight).status_code == 400
    portal = client.options("/api/auth/login", headers={**preflight, "Origin": "http://localhost:3000"})
    assert portal.status_code == 200 and portal.headers["access-control-allow-origin"] == "http://localhost:3000"
    exposed = client.get("/health", headers={"Origin": "http://localhost:3000"}).headers["access-control-expose-headers"]
    assert "X-2FA-Required" in exposed and "Retry-After" in exposed


def test_cors_origins_in_production_add_www_twins_and_drop_dev_hosts():
    origins, regex = cors_origins("https://www.banglabot.xyz, https://app.example.com/", production=True)
    assert origins == ["https://www.banglabot.xyz", "https://banglabot.xyz", "https://app.example.com", "https://www.app.example.com"]
    assert regex is None
    dev, dev_regex = cors_origins("http://localhost:3000", production=False)
    assert "http://localhost:5173" in dev and dev_regex


def test_public_bodies_are_capped(client):
    big = "x" * 70_000
    response = client.post("/api/public/contact", content=big, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_streamed_bodies_over_the_limit_get_413():
    async def echo(request):
        return JSONResponse({"size": len(await request.body())})

    inner = Starlette(routes=[Route("/api/public/x", echo, methods=["POST"]), Route("/big", echo, methods=["POST"])])
    limited = BodySizeLimitMiddleware(inner, max_bytes=100, max_small_bytes=10)
    small = TestClient(limited)

    def chunks(n):
        yield b"a" * n

    assert small.post("/api/public/x", content=chunks(5)).json() == {"size": 5}
    assert small.post("/api/public/x", content=chunks(50)).status_code == 413
    assert small.post("/big", content=chunks(50)).json() == {"size": 50}


# ------------------------------------------------------------------ log redaction
def test_log_redaction_masks_people_and_credentials():
    event = redact_event(None, "info", {
        "event": "call from +14155550111 (rahim@example.com)",
        "authorization": "Bearer abcdefghijklmnop",
        "media_token": "eyJhbGciOiJIUzI1NiJ9.e30.sig",
        "llm_prompt_tokens": 120,
        "nested": {"to": "4155550111", "password": "p"},
        "timestamp": "2026-10-16T10:00:00Z",
    })
    assert event["event"] == "call from ***111 (***@example.com)"
    assert event["authorization"] == "***" and event["media_token"] == "***" and event["llm_prompt_tokens"] == 120
    assert event["nested"] == {"to": "***111", "password": "***"} and event["timestamp"] == "2026-10-16T10:00:00Z"
    assert scrub("id 3f2a1234567890ab9c at 2026-10-16 10:00") == "id 3f2a1234567890ab9c at 2026-10-16 10:00"
    assert scrub("key sk-proj-abcdefghijklmnop123") == "key ***"


def test_access_log_paths_hide_feed_tokens_and_signatures():
    import logging

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', None, None)
    record.args = ("1.2.3.4:5", "GET", "/api/public/calendar/AbC_123.ics?item=9", "1.1", 200)
    AccessLogFilter().filter(record)
    assert record.args[2] == "/api/public/calendar/***.ics?item=9"
    record.args = ("1.2.3.4:5", "POST", "/telnyx/inbound/" + "a" * 32, "1.1", 204)
    AccessLogFilter().filter(record)
    assert record.args[2] == "/telnyx/inbound/***"
