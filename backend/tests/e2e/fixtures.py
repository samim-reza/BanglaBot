"""Shared e2e fixtures (imported by ``conftest`` only when ``E2E_DATABASE_URL`` is set).

One app lifespan for the whole run, on an emptied database; every test gets an in-process
HTTP client, a fresh rate-limiter and fake providers, and fails if it touched the network.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import traceback
from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

from tests.e2e import netguard
from tests.e2e.fakes import FakeProviders, WebhookReceiver


async def reset_database(url: str) -> None:
    """Drop and recreate ``public`` (the URL was vetted by ``env.check_target``)."""
    raw = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    conn = await asyncpg.connect(raw)
    try:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()


async def settle_background(timeout: float = 5.0) -> list[str]:
    """Let fire-and-forget work started by a request (SMS, calendar, metering, webhooks) finish.

    Returns the names of tasks still running at the deadline (the lifespan's loops excluded)."""
    from app.finance import recorder

    current = asyncio.current_task()
    pending: list[asyncio.Task] = []
    for _ in range(int(timeout / 0.05)):
        await asyncio.sleep(0.05)
        pending = [
            task for task in asyncio.all_tasks()
            if task is not current and not task.done() and task.get_name() not in LIFESPAN_TASKS
            and not task.get_name().startswith("inbound-media-watchdog")  # a per-call 60 s timer, not pending work
        ]
        if not pending and not recorder._pending:
            return []
    return [getattr(task.get_coro(), "__qualname__", task.get_name()) for task in pending]


#: The app's own background loops (main.lifespan names them).
LIFESPAN_TASKS = frozenset({"auto-call-scheduler", "chat-reaper", "sms-reminders", "billing-jobs", "payment-sweeper", "finance-jobs", "recording-purge"})


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def app() -> AsyncIterator[object]:
    """The real app, booted once on an empty database (create_all + patches + admin seed)."""
    await reset_database(os.environ["E2E_DATABASE_URL"].strip())
    from app.main import app as fastapi_app

    async with fastapi_app.router.lifespan_context(fastapi_app):
        yield fastapi_app


@pytest_asyncio.fixture(loop_scope="session")
async def client(app) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    transport = httpx.ASGITransport(app=app, client=("198.51.100.7", 51000))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _fresh_limits_and_network(providers) -> AsyncIterator[None]:  # noqa: ANN001
    """Each test starts with an empty rate limiter; at the end its background work is let
    finish (still on the fake providers) and the test fails if anything tried the network."""
    from app.core.ratelimit import backends

    backends.memory.reset()
    netguard.take()
    yield
    await settle_background()
    attempts = netguard.take()
    assert not attempts, f"the test tried to reach the network: {attempts}"


@pytest.fixture(autouse=True)
def providers(monkeypatch) -> FakeProviders:  # noqa: ANN001
    """Every test runs on the scripted LLM / STT / TTS (a flow save warms TTS lines in the background, too)."""
    fake = FakeProviders()
    fake.install(monkeypatch)
    return fake


@pytest.fixture
def webhooks(monkeypatch) -> WebhookReceiver:  # noqa: ANN001
    """The owner's endpoint behind the outbound SSRF guard's seams: DNS answers a public
    address, the pinned request lands on a MockTransport."""
    from app.core.security import outbound

    receiver = WebhookReceiver()

    async def resolve(host: str, port: int) -> list[str]:
        return [WebhookReceiver.PUBLIC_IP]

    original = outbound.request

    async def request(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        try:
            return await original(*args, **kwargs)
        except Exception:  # the app logs a generic reason only; keep the real one for the test
            receiver.errors.append(traceback.format_exc())
            raise

    monkeypatch.setattr(outbound, "resolver", resolve)
    monkeypatch.setattr(outbound, "transport", httpx.MockTransport(receiver.handler))
    monkeypatch.setattr(outbound, "request", request)
    return receiver


@pytest.fixture
def sms_outbox(monkeypatch) -> list[dict[str, str]]:  # noqa: ANN001
    """SMS switched on for the platform, with Telnyx's send replaced by this list."""
    from app.services import sms, sms_service, telnyx
    from app.services.sms import policy, reminders, sending

    sent: list[dict[str, str]] = []

    async def send_sms(*, to: str, text: str, webhook_url: str | None = None, from_number: str | None = None) -> str:
        sent.append({"to": to, "text": text, "from": from_number or "", "webhook_url": webhook_url or ""})
        return f"sms-{secrets.token_hex(6)}"

    for module in (policy, sending, reminders, sms, sms_service):
        monkeypatch.setattr(module, "platform_ready", lambda: True)
    monkeypatch.setattr(telnyx, "send_sms", send_sms)
    return sent


__all__ = ["LIFESPAN_TASKS", "_fresh_limits_and_network", "app", "client", "providers", "reset_database", "settle_background", "sms_outbox", "webhooks"]
