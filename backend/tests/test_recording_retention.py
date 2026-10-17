"""Recordings past the account's retention (30 days, 12 months with Pro / the add-on) are gone."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.services import telnyx
from app.services.calls import retention
from tests.security_fakes import make_merchant

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def _log(days_old: int, sid: str = "rec-1") -> SimpleNamespace:
    return SimpleNamespace(id=f"log-{days_old}", recording_sid=sid, created_at=NOW - timedelta(days=days_old))


def test_retention_follows_the_plan_and_the_add_on():
    assert retention.retention_days(make_merchant(plan="starter")) == 30
    assert retention.retention_days(make_merchant(plan="pro")) == 365
    assert retention.retention_days(make_merchant(plan="starter", addons={"_v": 1, "recording_retention": 1})) == 365


def test_expired_recordings_are_refused_with_410():
    starter = make_merchant(plan="starter")
    retention.ensure_available(_log(29), starter, NOW)
    with pytest.raises(HTTPException) as exc:
        retention.ensure_available(_log(31), starter, NOW)
    assert exc.value.status_code == 410 and "30 days" in exc.value.detail
    retention.ensure_available(_log(200), make_merchant(plan="pro"), NOW)


class _Rows:
    def __init__(self, rows: list[tuple[Any, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, Any]]:
        return self._rows


class _Session:
    def __init__(self, rows: list[tuple[Any, Any]]) -> None:
        self.rows, self.commits = rows, 0

    async def execute(self, _statement: Any) -> _Rows:
        return _Rows(self.rows)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_purge_deletes_only_what_is_past_each_accounts_retention(monkeypatch: pytest.MonkeyPatch):
    deleted: list[str] = []

    async def delete_recording(sid: str) -> None:
        if sid == "rec-broken":
            raise telnyx.TelnyxError("server error", 500)
        deleted.append(sid)

    monkeypatch.setattr(telnyx, "delete_recording", delete_recording)
    starter, pro = make_merchant(id="m1", plan="starter"), make_merchant(id="m2", plan="pro")
    old_starter, old_pro, broken = _log(40, "rec-old"), _log(40, "rec-pro"), _log(45, "rec-broken")
    session = _Session([(old_starter, starter), (old_pro, pro), (broken, starter)])
    assert await retention.purge_once(session, NOW) == 1
    assert deleted == ["rec-old"] and old_starter.recording_sid == "" and old_pro.recording_sid == "rec-pro"
    assert broken.recording_sid == "rec-broken" and session.commits == 1  # a failed delete is retried next sweep
