"""End-to-end suite: the real API, real SQL and the real engine against a THROWAWAY Postgres.

Run it on its own, from ``backend/``::

    E2E_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/callisa_e2e venv/bin/python -m pytest tests/e2e -q

Skipped unless ``E2E_DATABASE_URL`` is set, so the normal ``pytest -q`` stays database-free.
The database's ``public`` schema is DROPPED at the start of the run: only a loopback server
whose database name contains "e2e" or "test" is accepted. The run is hermetic: the ``.env``
files are not read, every provider key is blank, LLM / STT / TTS are scripted fakes
(``fakes.py``) and any socket to anything but that database fails the test (``netguard.py``).
All tests share one event loop and one app lifespan (boot → bootstrap → background jobs).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.e2e import env

E2E_URL = os.environ.get("E2E_DATABASE_URL", "").strip()
HERE = Path(__file__).resolve().parent

if E2E_URL:
    DB_HOST, DB_PORT = env.check_target(E2E_URL)
    env.configure_environment(E2E_URL)


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    from pytest_asyncio import is_async_test

    skip = pytest.mark.skip(reason="e2e: set E2E_DATABASE_URL to a throwaway Postgres to run")
    session_loop = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if HERE not in Path(str(item.fspath)).resolve().parents:
            continue
        if not E2E_URL:
            item.add_marker(skip)
        elif is_async_test(item):
            item.add_marker(session_loop, append=False)


if E2E_URL:
    from tests.e2e import netguard
    from tests.e2e.fixtures import _fresh_limits_and_network, app, client, providers, sms_outbox, webhooks

    @pytest.fixture(scope="session", autouse=True)
    def _network_guard():
        netguard.install(DB_HOST, DB_PORT)
        yield
        netguard.uninstall()

#: The shared fixtures (``fixtures.py``), re-exported for pytest when the suite is enabled.
__all__ = ["_fresh_limits_and_network", "_network_guard", "app", "client", "providers", "sms_outbox", "webhooks"]
