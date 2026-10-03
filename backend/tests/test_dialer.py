"""Bulk dialer: batch loop, cancellation, config abort, schedule roll-over. No DB."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models import OrderStatus
from app.services import dialer_service as dialer


@pytest.fixture
def fast(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "bulk_call_gap_seconds", 0.0)
    monkeypatch.setattr(settings, "bulk_call_max_concurrent", 2)
    monkeypatch.setattr(dialer, "SLOT_POLL_SECONDS", 0.01)
    monkeypatch.setattr(dialer, "_runs", {})
    return settings


def _run(order_ids, **kwargs):
    return dialer.BulkCallRun(merchant_id="m1", order_ids=list(order_ids), statuses=dialer.DEFAULT_BATCH_STATUSES, **kwargs)


async def test_batch_dials_every_order_and_counts_outcomes(fast, monkeypatch):
    outcomes = {"o1": "started", "o2": "failed", "o3": "skipped", "o4": "started"}
    dialed: list[str] = []

    async def fake_dial(run, order_id):
        dialed.append(order_id)
        return outcomes[order_id]

    async def no_live_calls(merchant_id):
        return 0

    monkeypatch.setattr(dialer, "_dial_one", fake_dial)
    monkeypatch.setattr(dialer, "_live_calls", no_live_calls)
    run = _run(outcomes)
    await dialer._run_batch(run)
    assert dialed == ["o1", "o2", "o3", "o4"]
    assert (run.state, run.started, run.failed, run.skipped) == ("done", 2, 1, 1)
    assert run.finished_at is not None and not run.active


async def test_batch_waits_for_a_free_slot(fast, monkeypatch):
    live = {"count": 2}  # both slots busy at first
    checks = {"n": 0}

    async def live_calls(merchant_id):
        checks["n"] += 1
        if checks["n"] >= 3:
            live["count"] = 1  # one call settled
        return live["count"]

    async def fake_dial(run, order_id):
        return "started"

    monkeypatch.setattr(dialer, "_live_calls", live_calls)
    monkeypatch.setattr(dialer, "_dial_one", fake_dial)
    run = _run(["o1"])
    await dialer._run_batch(run)
    assert run.state == "done" and run.started == 1
    assert checks["n"] >= 3


async def test_cancel_stops_dialing_new_orders(fast, monkeypatch):
    dialed: list[str] = []

    async def fake_dial(run, order_id):
        dialed.append(order_id)
        run.cancel_event.set()  # "user pressed Stop" right after the first call
        return "started"

    async def no_live_calls(merchant_id):
        return 0

    monkeypatch.setattr(dialer, "_dial_one", fake_dial)
    monkeypatch.setattr(dialer, "_live_calls", no_live_calls)
    run = _run(["o1", "o2", "o3"])
    await dialer._run_batch(run)
    assert dialed == ["o1"]
    assert run.state == "cancelled" and run.started == 1


async def test_config_error_aborts_the_whole_batch(fast, monkeypatch):
    async def fake_dial(run, order_id):
        raise dialer.BatchAborted("TWILIO_FROM_NUMBER is not configured")

    async def no_live_calls(merchant_id):
        return 0

    monkeypatch.setattr(dialer, "_dial_one", fake_dial)
    monkeypatch.setattr(dialer, "_live_calls", no_live_calls)
    run = _run(["o1", "o2"])
    await dialer._run_batch(run)
    assert run.state == "failed"
    assert "TWILIO_FROM_NUMBER" in run.error


async def test_wait_for_slot_survives_a_db_hiccup_then_cancels(fast, monkeypatch):
    async def broken(merchant_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(dialer, "_live_calls", broken)
    run = _run(["o1"])
    asyncio.get_running_loop().call_later(0.03, run.cancel_event.set)
    assert await dialer._wait_for_slot(run) is False


def test_normalize_statuses_rejects_settled_orders():
    assert dialer._normalize_statuses(None) == dialer.DEFAULT_BATCH_STATUSES
    assert dialer._normalize_statuses([OrderStatus.pending, OrderStatus.pending, OrderStatus.needs_review]) == (
        OrderStatus.pending,
        OrderStatus.needs_review,
    )
    with pytest.raises(HTTPException) as exc:
        dialer._normalize_statuses([OrderStatus.confirmed])
    assert exc.value.status_code == 422


def test_serialize_run_shape():
    run = _run(["o1", "o2"], source="scheduled")
    payload = dialer.serialize_run(run)
    assert payload["total"] == 2 and payload["state"] == "queued" and payload["source"] == "scheduled"
    assert set(payload) == {"id", "state", "source", "total", "started", "failed", "skipped", "error", "created_at", "finished_at"}
    assert dialer.serialize_run(None) is None


def test_next_daily_rolls_to_the_same_time_after_now():
    at = datetime(2026, 8, 29, 5, 0, tzinfo=timezone.utc)  # 11:00 Dhaka
    now = datetime(2026, 8, 31, 5, 30, tzinfo=timezone.utc)
    assert dialer.next_daily(at, now) == datetime(2026, 9, 1, 5, 0, tzinfo=timezone.utc)
    future = now + timedelta(hours=1)
    assert dialer.next_daily(future, now) == future


async def test_cancel_batch_only_touches_active_runs(fast):
    finished = _run(["o1"])
    finished.state = "done"
    dialer._runs["m1"] = finished
    assert await dialer.cancel_batch("m1") is finished
    assert not finished.cancel_event.is_set()
    assert await dialer.cancel_batch("nobody") is None
