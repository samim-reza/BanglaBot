"""Fakes shared by the security tests: an in-memory AsyncSession stand-in, a session
factory for best-effort writers (audit log), and a fully populated Merchant row."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from app.models import Merchant


class FakeResult(list):
    def __iter__(self):
        return super().__iter__()


class FakeDB:
    """Rows by (model, id) for ``get``; queued answers for ``scalar`` / ``scalars``."""

    def __init__(self, *rows: Any, scalars: list[Any] | None = None, scalar_rows: list[list[Any]] | None = None) -> None:
        self.rows: dict[tuple[type, str], Any] = {}
        for row in rows:
            self.put(row)
        self.scalar_queue: deque[Any] = deque(scalars or [])
        self.scalars_queue: deque[list[Any]] = deque(scalar_rows or [])
        self.statements: list[Any] = []
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    def put(self, row: Any) -> None:
        self.rows[(type(row), str(row.id))] = row

    async def get(self, model: type, obj_id: Any) -> Any:
        return self.rows.get((model, str(obj_id)))

    async def scalar(self, stmt: Any) -> Any:
        self.statements.append(stmt)
        return self.scalar_queue.popleft() if self.scalar_queue else None

    async def scalars(self, stmt: Any) -> FakeResult:
        self.statements.append(stmt)
        return FakeResult(self.scalars_queue.popleft() if self.scalars_queue else [])

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            obj.id = f"new{len(self.added) + 1}"
        self.added.append(obj)
        if getattr(obj, "id", None):
            self.put(obj)

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, obj: Any) -> None:
        return None

    async def flush(self) -> None:
        return None


class FakeSessionFactory:
    """``factory()`` → an async context manager collecting what was added / committed."""

    def __init__(self, fail: bool = False) -> None:
        self.added: list[Any] = []
        self.commits = 0
        self.fail = fail

    def __call__(self) -> "FakeSessionFactory":
        return self

    async def __aenter__(self) -> "FakeSessionFactory":
        if self.fail:
            raise ConnectionError("database unreachable")
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def db_override(db: FakeDB):
    async def _get_db():
        yield db

    return _get_db


def make_merchant(**overrides: Any) -> Merchant:
    """A Merchant instance (never persisted) with every field the API serializes."""
    values: dict[str, Any] = dict(
        id="m1", business_name="Demo Shop", owner_name="Owner", username="demo", password_hash="", phone="",
        email="owner@example.com", vertical="ecommerce", vertical_config={}, knowledge="", inbound_number="",
        region="BD", timezone="Asia/Dhaka", currency="BDT", emergency_number="999", support_phone="",
        custom_greeting="", language="en", supported_languages=["en", "bn"], voice_persona="female",
        verify_address=False, max_call_seconds=0, silence_hangup_secs=10, active=True, plan="trial",
        widget_enabled=False, widget_key="", widget_settings={}, webhook_url="", sms_settings={},
        calendar_settings={}, addons={"_v": 1}, channel_settings={}, auto_call_repeat_daily=False,
        token_version=0, created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return Merchant(**values)
