"""Concurrent-call slots per account: tier limit + add-ons, idempotent release, stale slots,
and the in-process fallback when Redis fails. No Redis server, no database."""

from __future__ import annotations

import pytest

from app.core import redis as redis_store
from app.services import concurrency
from tests.billing_fakes import account, reset_catalog


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(redis_store, "redis_client", None)
    concurrency.reset()
    reset_catalog()
    yield
    concurrency.reset()


async def test_slots_follow_the_tier_limit_and_free_up_on_release():
    shop = account("starter")  # 2 at once
    assert await concurrency.acquire(shop, "c1") and await concurrency.acquire(shop, "c2")
    assert await concurrency.acquire(shop, "c3") is False
    assert await concurrency.acquire(shop, "c1") is True  # the same call again holds one slot
    assert await concurrency.in_use(shop) == 2
    await concurrency.release(shop, "c1")
    await concurrency.release(shop, "c1")  # twice is harmless
    assert await concurrency.acquire(shop, "c3") is True
    other = account("starter", id="m2")
    assert await concurrency.acquire(other, "x1")  # limits are per account


async def test_add_ons_raise_the_limit_and_chat_plans_have_no_calls():
    busy = account("starter", {"concurrent_call": 1})
    assert concurrency.limit_for(busy) == 3
    assert all([await concurrency.acquire(busy, f"c{i}") for i in range(3)])
    assert await concurrency.acquire(busy, "c4") is False
    assert await concurrency.acquire(account("chat", id="m3"), "c1") is False


async def test_anonymous_slots_and_stale_slots(monkeypatch):
    shop = account("starter")
    assert await concurrency.acquire(shop) and await concurrency.acquire(shop)
    assert await concurrency.acquire(shop) is False
    await concurrency.release(shop)
    assert await concurrency.acquire(shop) is True
    clock = [1_000_000.0]
    monkeypatch.setattr(concurrency.time, "time", lambda: clock[0])
    concurrency.reset()
    assert await concurrency.acquire(shop, "a") and await concurrency.acquire(shop, "b")
    clock[0] += concurrency.STALE_SECONDS + 1  # both calls crashed without releasing
    assert await concurrency.acquire(shop, "c") is True


class BrokenRedis:
    async def eval(self, *args):
        raise ConnectionError("redis down")

    async def zrem(self, *args):
        raise ConnectionError("redis down")


class ScriptedRedis:
    def __init__(self, answer: int) -> None:
        self.answer = answer
        self.calls: list[tuple] = []

    async def eval(self, script, numkeys, key, now, stale_before, limit, call_id, ttl):
        self.calls.append((key, limit, call_id, ttl))
        return self.answer

    async def zrem(self, key, call_id):
        self.calls.append(("zrem", key, call_id))


async def test_redis_is_used_when_connected_and_memory_when_it_fails(monkeypatch):
    shop = account("starter")
    scripted = ScriptedRedis(0)
    monkeypatch.setattr(redis_store, "redis_client", scripted)
    assert await concurrency.acquire(shop, "c1") is False
    assert scripted.calls[0] == ("concurrency:m1", 2, "c1", concurrency.STALE_SECONDS)
    await concurrency.release(shop, "c1")
    assert scripted.calls[-1] == ("zrem", "concurrency:m1", "c1")
    monkeypatch.setattr(redis_store, "redis_client", BrokenRedis())
    assert await concurrency.acquire(shop, "c1") and await concurrency.acquire(shop, "c2")
    assert await concurrency.acquire(shop, "c3") is False
