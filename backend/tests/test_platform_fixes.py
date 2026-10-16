"""Regressions for bugs the end-to-end suite (tests/e2e) found — DB-free, so they run in the
normal suite too: blank REDIS_URL, the widget's LLM gate, chat-channel call logs left
"in-progress", and the salon's SMS / calendar wording (its catalog item is the stylist)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import public
from app.core import redis as redis_module
from app.core.config import get_settings
from app.core.ratelimit import backends
from app.main import app
from app.models import CallLog, CatalogItem, Order, OrderStatus
from app.services.calls import store as call_store
from app.voice.providers import llm as llm_pkg
from tests.security_fakes import make_merchant

KEY = "w" * 24


@pytest.fixture(autouse=True)
def _fresh_limits():
    backends.memory.reset()
    yield
    backends.memory.reset()


# ------------------------------------------------------------------ Redis
@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["", "   ", "not-a-redis-url"])
async def test_a_blank_or_bad_redis_url_boots_without_redis(monkeypatch, url):
    monkeypatch.setattr(get_settings(), "redis_url", url)
    monkeypatch.setattr(redis_module, "redis_client", object())
    await redis_module.connect_redis()  # must not raise: the app runs without Redis
    assert redis_module.redis_client is None
    assert await redis_module.redis_health() == {"status": "disabled"}


# ------------------------------------------------------------------ widget
def test_widget_start_needs_an_llm_chain_not_an_openai_key(monkeypatch):
    async def shop(key):  # noqa: ANN001, ANN202
        return make_merchant(widget_enabled=True, widget_key=KEY, plan="trial")

    reached: list[bool] = []

    def database():  # noqa: ANN202
        reached.append(True)
        raise RuntimeError("past the LLM gate")

    monkeypatch.setattr(public, "_widget_merchant", shop)
    monkeypatch.setattr(public, "AsyncSessionLocal", database)
    monkeypatch.setattr(get_settings(), "openai_api_key", None)
    client = TestClient(app)
    monkeypatch.setattr(llm_pkg, "llm_configured", lambda merchant=None: False)
    assert client.post(f"/api/public/widget/{KEY}/start").status_code == 503 and not reached
    # A free chain (Groq / Gemini) without any OpenAI key is enough.
    monkeypatch.setattr(llm_pkg, "llm_configured", lambda merchant=None: True)
    with pytest.raises(RuntimeError, match="past the LLM gate"):
        client.post(f"/api/public/widget/{KEY}/start")
    assert reached


# ------------------------------------------------------------------ call logs of chats
class _Session:
    def __init__(self, log: CallLog) -> None:
        self.log = log

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *exc) -> bool:  # noqa: ANN002
        return False

    async def get(self, model, obj_id):  # noqa: ANN001, ANN201
        return self.log

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("direction", "expected"),
    [("inbound", "completed"), ("widget", "completed"), ("whatsapp", "completed"), ("messenger", "completed"),
     ("instagram", "completed"), ("chat", "completed"), ("web", "completed"), ("outbound", "in-progress")],
)
async def test_a_finished_conversation_settles_its_call_log(monkeypatch, direction, expected):
    from app.finance import recorder

    log = CallLog(id="log1", merchant_id="m1", direction=direction, call_status="in-progress", duration_secs=0)
    monkeypatch.setattr(call_store, "AsyncSessionLocal", lambda: _Session(log))
    monkeypatch.setattr(recorder, "schedule_call", lambda *args, **kwargs: None)
    await call_store.DbCallStore(order_id="", call_log_id="log1", merchant_id="m1").save_usage(duration_secs=42)
    assert log.call_status == expected and log.duration_secs == 42


# ------------------------------------------------------------------ salon wording
def _salon_booking(**details) -> Order:  # noqa: ANN003
    return Order(
        id="o1", merchant_id="m1", kind="booking", customer_name="Ana Lopez", customer_phone="+12125550111", status=OrderStatus.confirmed,
        scheduled_at=datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc), catalog_item_id="st-maya", items_summary="Haircut — Maya",
        details=details, notes="", address="", total_amount=45, currency="USD", payment_status="not_required", payment_url="",
    )


def test_salon_texts_name_the_service_and_the_stylist():
    from app.services.sms.composer import compose

    salon = make_merchant(vertical="salon", business_name="Glow")
    # After a call: the details carry both; the catalog item (passed as item_name) is the stylist.
    booked = compose("confirmation", _salon_booking(service="Haircut", staff="Maya"), salon, item_name="Maya")
    assert booked.startswith("Glow: your Haircut with Maya is booked for Sun, Oct 18 at 11 AM."), booked
    # A booking typed in the portal has the service only; the stylist comes from the catalog item.
    reminder = compose("reminder", _salon_booking(service="Haircut"), salon, item_name="Maya")
    assert reminder.startswith("Reminder from Glow: your Haircut with Maya is on"), reminder


def test_salon_calendar_events_name_the_service_with_the_stylist():
    from app.services.calendar.ics_feed import event_for

    salon = make_merchant(vertical="salon", business_name="Glow")
    record = _salon_booking(service="Haircut", staff="Maya", duration_minutes=45)
    record.updated_at = None
    event = event_for(record, salon, CatalogItem(id="st-maya", name="Maya", kind="staff", data={}))
    assert event.summary == "Haircut with Maya · Ana Lopez"


def test_per_calendar_feeds_follow_what_a_record_is_booked_against():
    from app.api.routes.integrations.summary import _booked_kind
    from app.verticals import get_vertical

    assert _booked_kind(get_vertical("salon")) == "staff"  # a salon books the stylist, not the service
    assert _booked_kind(get_vertical("clinic")) == get_vertical("clinic").catalog_kind
    assert _booked_kind(SimpleNamespace(record_fields=(), catalog_kind="")) == ""


# ------------------------------------------------------------------ catalog CSV templates
def test_every_catalog_template_imports_as_downloaded():
    import csv
    import io

    from app.services.catalog_service import csv_template
    from app.verticals import VERTICALS
    from app.verticals.forms import split_catalog

    for vertical in VERTICALS.values():
        merchant = make_merchant(vertical=vertical.key)
        for kind in vertical.kinds:
            header, example = list(csv.reader(io.StringIO(csv_template(merchant, kind.kind))))[:2]
            assert "…" not in ",".join(example), (vertical.key, kind.kind, example)  # hints are not values (no bogus iCal link)
            split_catalog(vertical, {key: value for key, value in zip(header, example) if value.strip()}, kind=kind.kind)


# ------------------------------------------------------------------ call lines (concurrency)
@pytest.mark.asyncio
@pytest.mark.parametrize("final", ["no-answer", "busy", "failed", "completed"])
async def test_the_final_call_status_gives_the_line_back(monkeypatch, final):
    from app.services import concurrency
    from app.services.calls import callbacks
    from tests.security_fakes import FakeDB

    monkeypatch.setattr(concurrency, "_local", {})
    order = Order(id="o1", merchant_id="m1", status=OrderStatus.calling, kind="order", details={}, flow_data={})
    log = CallLog(id="log1", merchant_id="m1", order_id="o1", direction="outbound", call_status="ringing", outcome="", twilio_call_sid="v3:x")
    merchant = make_merchant(id="m1", plan="starter")
    assert await concurrency.acquire(merchant, "log1") and await concurrency.in_use(merchant) == 1
    # An unanswered call never reaches the media stream, so no bridge frees its slot.
    await callbacks.apply_status_callback(FakeDB(order, scalars=[log]), "o1", "v3:x", final, 0)
    assert await concurrency.in_use(merchant) == 0


@pytest.mark.asyncio
async def test_a_batch_waits_for_a_line_instead_of_skipping_the_record(monkeypatch):
    from app.services import dialer_service as dialer
    from app.services.dialer import batch as dialer_batch

    monkeypatch.setattr(get_settings(), "bulk_call_gap_seconds", 0.0)
    monkeypatch.setattr(dialer_batch, "SLOT_POLL_SECONDS", 0.01)
    attempts: dict[str, int] = {}

    async def dial(run, order_id):  # noqa: ANN001, ANN202
        attempts[order_id] = attempts.get(order_id, 0) + 1
        return "busy" if order_id == "o3" and attempts[order_id] < 3 else "started"  # the plan's 2 lines are taken twice

    async def no_live_calls(merchant_id):  # noqa: ANN001, ANN202
        return 0

    monkeypatch.setattr(dialer_batch, "_dial_one", dial)
    monkeypatch.setattr(dialer_batch, "_live_calls", no_live_calls)
    run = dialer.BulkCallRun(merchant_id="m1", order_ids=["o1", "o2", "o3"], statuses=dialer.DEFAULT_BATCH_STATUSES)
    await dialer_batch._run_batch(run)
    assert (run.state, run.started, run.skipped) == ("done", 3, 0) and attempts["o3"] == 3
