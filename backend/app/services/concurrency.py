"""Concurrent-call limit per account: ``max_concurrent_calls`` from the tier (+ add-on grants).

``await acquire(merchant, call_id)`` → ``True`` when the call may go ahead (and
holds a slot), ``False`` when the account is at its limit. ``await release(merchant,
call_id)`` frees the slot; it is idempotent. Slots live in Redis (a sorted set
per account, updated atomically by a Lua script) when Redis is connected — so
every worker shares the count — and in this process's memory otherwise or when
Redis errors. A slot older than ``STALE_SECONDS`` is dropped on its own, so a
crashed call never blocks an account for good.

Integration (the voice bridge / dialer own these call sites):

* inbound: ``inbound_call`` in ``app/api/routes/telnyx.py`` (before answering) —
  ``if not await concurrency.acquire(merchant, call_log_id)``: answer "all lines
  are busy" / reject and don't start the agent;
* outbound: ``_dial_one`` in ``app/services/dialer/batch.py`` (and the manual
  call endpoint) before originating; release when the origination fails;
* both: in ``CallBridge.run`` (``app/voice/bridge/lifecycle.py``), ``acquire`` next to
  ``live_calls.register(self)`` (idempotent if the webhook already took the slot)
  and ``await concurrency.release(merchant, call_log_id)`` next to
  ``live_calls.unregister(...)`` in its ``finally``.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

import structlog

from app.core import redis as redis_store
from app.core.entitlements import entitlements

logger = structlog.get_logger(__name__)

#: Longest a call can hold a slot (the inbound hard cap is 8 minutes; generous margin).
STALE_SECONDS = 2 * 3600
KEY_PREFIX = "concurrency:"

# KEYS[1] = set; ARGV = now, stale_before, limit, call_id, ttl → 1 acquired / 0 full
_ACQUIRE_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[2])
if redis.call('ZSCORE', KEYS[1], ARGV[4]) then return 1 end
if tonumber(ARGV[3]) >= 0 and redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""

#: In-process slots: {merchant_id: {call_id: started_at (epoch seconds)}}.
_local: dict[str, dict[str, float]] = {}
#: Slots taken without a call id, per account (released last-in first-out).
_anonymous: dict[str, list[str]] = {}


def limit_for(merchant: Any) -> int | None:
    """The account's concurrent-call limit; ``None`` = unlimited."""
    value = entitlements(merchant).max_concurrent_calls
    return None if value is None else max(0, int(value))


def _merchant_id(merchant: Any) -> str:
    return str(getattr(merchant, "id", merchant) or "")


def _local_acquire(merchant_id: str, call_id: str, limit: int | None, now: float) -> bool:
    slots = _local.setdefault(merchant_id, {})
    for stale in [cid for cid, started in slots.items() if started < now - STALE_SECONDS]:
        slots.pop(stale, None)
    if call_id in slots:
        return True
    if limit is not None and len(slots) >= limit:
        return False
    slots[call_id] = now
    return True


async def acquire(merchant: Any, call_id: str | None = None) -> bool:
    """Take a slot for ``call_id`` (any unique id; the call log id is ideal)."""
    merchant_id = _merchant_id(merchant)
    if not merchant_id:
        return False
    limit = limit_for(merchant)
    if limit == 0:
        return False
    cid = str(call_id or "") or f"anon-{secrets.token_hex(6)}"
    now = time.time()
    client = redis_store.redis_client
    acquired: bool | None = None
    if client is not None:
        try:
            result = await client.eval(
                _ACQUIRE_LUA, 1, KEY_PREFIX + merchant_id, now, now - STALE_SECONDS, -1 if limit is None else limit, cid, STALE_SECONDS
            )
            acquired = bool(int(result))
        except Exception as exc:  # noqa: BLE001 — fall back to this process's count
            await logger.awarning("concurrency_redis_failed", error=str(exc)[:200])
    if acquired is None:
        acquired = _local_acquire(merchant_id, cid, limit, now)
    if acquired and not call_id:
        _anonymous.setdefault(merchant_id, []).append(cid)
    if not acquired:
        await logger.ainfo("concurrency_limit_reached", merchant=merchant_id, limit=limit)
    return acquired


async def release(merchant: Any, call_id: str | None = None) -> None:
    """Free the slot of ``call_id`` (or the last anonymous one). Safe to call twice."""
    merchant_id = _merchant_id(merchant)
    cid = str(call_id or "")
    if not cid:
        pending = _anonymous.get(merchant_id) or []
        if not pending:
            return
        cid = pending.pop()
    _local.get(merchant_id, {}).pop(cid, None)
    client = redis_store.redis_client
    if client is not None:
        try:
            await client.zrem(KEY_PREFIX + merchant_id, cid)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("concurrency_redis_release_failed", error=str(exc)[:200])


async def in_use(merchant: Any) -> int:
    """Live slots of the account (Redis when connected, else this process)."""
    merchant_id = _merchant_id(merchant)
    client = redis_store.redis_client
    if client is not None:
        try:
            key = KEY_PREFIX + merchant_id
            await client.zremrangebyscore(key, "-inf", time.time() - STALE_SECONDS)
            return int(await client.zcard(key))
        except Exception:  # noqa: BLE001
            pass
    return len(_local.get(merchant_id, {}))


def reset() -> None:
    """Forget every in-process slot (tests)."""
    _local.clear()
    _anonymous.clear()


__all__ = ["STALE_SECONDS", "acquire", "in_use", "limit_for", "release", "reset"]
