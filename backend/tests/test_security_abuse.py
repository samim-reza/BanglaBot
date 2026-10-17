"""Abuse and injection controls: the public chat widget, signup email tokens, SMS caps,
CSV formulas / imports, iCal escaping, search wildcards, log redaction, error bodies and
the rate-limit store's memory bound. Fakes only."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from app.api.routes import public
from app.core.config import get_settings
from app.core.crypto import lookup_hash
from app.core.datetime_utils import utcnow
from app.core.log_redaction import RedactingFilter, install_stdlib_filter, scrub
from app.core.ratelimit import backends
from app.core.security import sign_token
from app.finance.export import safe_cell
from app.main import app, unhandled_exception_handler
from app.models import Order
from app.models.signup import Signup
from app.services import catalog_service, signup_service
from app.services.ics import _escape
from app.services.order_service import _apply_filters
from app.services.sms import sending
from app.voice import text_session
from tests.security_fakes import FakeDB, make_merchant

KEY = "k" * 24


@pytest.fixture(autouse=True)
def _fresh():
    backends.memory.reset()
    yield
    backends.memory.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _no_database(monkeypatch):
    def refuse():
        raise AssertionError("the database was queried")

    monkeypatch.setattr(public, "AsyncSessionLocal", refuse)


# ------------------------------------------------------------------ chat widget
def test_malformed_embed_keys_never_reach_the_database(client, monkeypatch):
    _no_database(monkeypatch)
    for key in ("short", "a" * 65, "bad key!", "dots.are.not.keys"):
        assert client.get(f"/api/public/widget/{key}/config").json() == {"enabled": False}
        assert client.post(f"/api/public/widget/{key}/start").status_code == 404
        assert client.post(f"/api/public/widget/{key}/say", json={"session_id": "x", "text": "hi"}).status_code == 404


def test_random_keys_cannot_dodge_the_per_visitor_start_limit(client, monkeypatch):
    async def nobody(key):
        return None

    monkeypatch.setattr(public, "_widget_merchant", nobody)
    codes = [client.post(f"/api/public/widget/{index:024d}/start").status_code for index in range(61)]
    assert codes[:60] == [404] * 60 and codes[60] == 429


def test_widget_config_only_serves_a_plain_hex_colour(client, monkeypatch):
    async def shop(key):
        return make_merchant(widget_enabled=True, widget_key=KEY, widget_settings={"color": "red}</style><img src=x onerror=alert(1)>", "position": "top"})

    monkeypatch.setattr(public, "_widget_merchant", shop)
    config = client.get(f"/api/public/widget/{KEY}/config").json()
    assert config["color"] == public.DEFAULT_WIDGET_COLOR and config["position"] == "right"
    script = (public._WIDGET_JS).read_text("utf-8")
    assert "/^#[0-9a-fA-F]{6}$/.test(" in script
    # Visitor / agent / owner text is only ever written with textContent.
    assert script.count(".innerHTML =") == 2 and 'msgs.innerHTML = ""' in script and "d.textContent = text" in script


def test_one_chat_is_capped_at_a_number_of_visitor_messages(client):
    async def say(text):
        return ["ok"]

    chat = SimpleNamespace(id="s" * 24, merchant=SimpleNamespace(widget_key=KEY), last_used=time.monotonic(), ended=False, say=say)
    text_session._sessions[chat.id] = chat
    try:
        codes = [client.post(f"/api/public/widget/{KEY}/say", json={"session_id": chat.id, "text": "hello"}).status_code
                 for _ in range(public.MAX_WIDGET_TURNS + 1)]
        assert codes[:-1] == [200] * public.MAX_WIDGET_TURNS and codes[-1] == 429
        other_site = client.post(f"/api/public/widget/{'z' * 24}/say", json={"session_id": chat.id, "text": "hi"})
        assert other_site.status_code == 404  # a session only answers on its own site's key
    finally:
        text_session._sessions.pop(chat.id, None)


# ------------------------------------------------------------------ signup email token
def _request() -> Request:
    return Request({"type": "http", "headers": [], "client": ("203.0.113.9", 1), "method": "POST", "path": "/"})


async def test_email_token_is_looked_up_by_hash_expires_and_is_single_use():
    token = "t" * 43
    old = Signup(id="s1", merchant_id="m1", subscription_id="sub1", email="a@example.com", status="pending_payment", vertical="clinic",
                 tier="starter", email_token_hash=lookup_hash(token, purpose=signup_service.EMAIL_TOKEN_PURPOSE), email_token_enc="enc",
                 created_at=utcnow() - timedelta(days=signup_service.EMAIL_TOKEN_DAYS + 1), email_verified_at=None)
    db = FakeDB(scalars=[old])
    with pytest.raises(HTTPException) as expired:
        await signup_service.verify_email(db, _request(), token)
    assert expired.value.status_code == 400 and old.email_verified_at is None
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    assert token not in str(compiled.params)  # only the peppered hash is queried
    # Already verified: answering again changes nothing (no commit, no audit row).
    old.email_verified_at = utcnow()
    again = FakeDB(scalars=[old])
    assert (await signup_service.verify_email(again, _request(), token))["verified"] is True
    assert again.commits == 0 and again.added == []


# ------------------------------------------------------------------ SMS caps
class _SmsSession:
    def __init__(self) -> None:
        self.rows: dict[str, object] = {}

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj) -> None:
        obj.id = obj.id or f"msg{len(self.rows) + 1}"
        self.rows[obj.id] = obj

    async def commit(self) -> None:
        return None

    async def refresh(self, obj) -> None:
        return None

    async def get(self, model, obj_id):
        return self.rows.get(obj_id)

    async def scalar(self, stmt):
        return None  # no STOP on file, never texted before


async def test_texts_are_capped_per_number_and_per_account(monkeypatch):
    sent: list[str] = []

    async def send_sms(*, to, text, webhook_url, from_number):
        sent.append(to)
        return f"sid{len(sent)}"

    monkeypatch.setattr(sending, "AsyncSessionLocal", _SmsSession())
    monkeypatch.setattr(sending, "platform_ready", lambda: True)
    monkeypatch.setattr(sending.telnyx, "send_sms", send_sms)
    monkeypatch.setattr(sending.telnyx, "number_for", lambda merchant: "+18723428160")
    monkeypatch.setattr(get_settings(), "sms_daily_cap_per_number", 2)
    monkeypatch.setattr(get_settings(), "sms_daily_cap_per_account", 4)
    merchant = make_merchant()
    results = [await sending.send(merchant, "+14155550123", "Your booking is confirmed", kind="confirmation") for _ in range(3)]
    assert [m.status for m in results] == ["sent", "sent", "skipped"] and results[2].error == sending.CAPPED
    others = [await sending.send(merchant, f"+1415555020{i}", "Hi", kind="confirmation") for i in range(3)]
    assert [m.status for m in others] == ["sent", "sent", "skipped"]  # the account's daily cap (4) is reached
    assert len(sent) == 4


# ------------------------------------------------------------------ CSV, iCal, search
@pytest.mark.parametrize("cell", ["=HYPERLINK(\"http://x\")", "+1+1", "-2+3", "@SUM(A1)", "\t=1", "\r=1", "\n=1", "  =cmd|' /C calc'!A0", "＝1"])
def test_csv_cells_that_spreadsheets_would_run_are_neutralised(cell):
    assert safe_cell(cell) == "'" + cell


def test_plain_csv_cells_are_untouched():
    assert [safe_cell(value) for value in ("Acme Dental", "a=b", 12, None)] == ["Acme Dental", "a=b", 12, None]


async def test_catalog_import_refuses_broken_files_and_never_wipes_on_bad_rows():
    merchant = make_merchant(vertical="clinic")
    with pytest.raises(HTTPException) as broken:
        await catalog_service.import_csv(FakeDB(), merchant, "name\n" + '"' + "x" * 200_000 + '"\n')
    assert broken.value.status_code == 422
    db = FakeDB()
    with pytest.raises(HTTPException) as nothing_valid:
        await catalog_service.import_csv(db, merchant, "name,fee\n,12\n", replace=True)
    assert nothing_valid.value.status_code == 422 and db.commits == 0
    assert not any("DELETE" in str(stmt) for stmt in db.statements)


def test_ical_text_cannot_start_a_new_property():
    escaped = _escape("Ann\rATTENDEE:mailto:evil@example.com\r\nX;Y,Z\n")
    assert "\r" not in escaped and "\n" not in escaped and escaped.startswith("Ann\\nATTENDEE")


def test_search_box_wildcards_are_literal():
    compiled = _apply_filters(select(Order), status=None, search="100%_off").compile(dialect=postgresql.dialect())
    assert "ESCAPE" in str(compiled) and "%100\\%\\_off%" in compiled.params.values()


# ------------------------------------------------------------------ logs and errors
def test_stdlib_records_are_scrubbed_and_httpx_request_lines_quiet():
    token = sign_token({"r": "p1"}, typ="pay")
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, 'HTTP Request: GET %s "200 OK"', (
        "https://graph.facebook.com/v21.0/me/messages?access_token=EAAGsecret&recipient=1",), None)
    RedactingFilter().filter(record)
    assert "EAAGsecret" not in record.getMessage() and "access_token=***" in record.getMessage()
    assert token not in scrub(f"pay here https://www.example.com/pay/{token}")
    assert "+14155550123" not in scrub("texted +1 415 555 0123 and owner@example.com")
    install_stdlib_filter()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_public_health_carries_no_error_details(client, monkeypatch):
    async def broken():
        return {"status": "error", "error": "Error 111 connecting to redis://:hunter2@10.0.0.3:6379"}

    monkeypatch.setattr(public, "redis_health", broken)
    body = client.get("/health").json()
    assert body["redis"] == {"status": "error"} and "10.0.0.3" not in str(body)


async def test_unhandled_errors_answer_without_a_stack_trace():
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/api/x", "query_string": b""})
    response = await unhandled_exception_handler(request, RuntimeError("password=hunter2 at /app/secret.py line 3"))
    assert response.status_code == 500 and response.body == b'{"detail":"Internal server error"}'


def test_rate_limit_memory_store_stays_bounded(monkeypatch):
    monkeypatch.setattr(backends, "MAX_MEMORY_KEYS", 100)
    store = backends.MemoryBackend()
    for index in range(500):
        store.hit_sync(f"flood:{index}", 5, 60, now=float(index))
    assert len(store._hits) <= 100
    assert "flood:499" in store._hits  # the newest keys (an active attacker's own) are the ones kept
