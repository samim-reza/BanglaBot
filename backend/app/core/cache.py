"""Shared cache: Redis when reachable, an in-process TTL store otherwise.

Modeled on SloancodeAI's core.redis, scoped down for BanglaBot: one shared
async client, JSON helpers, counters for rate limiting, prefix invalidation.
The in-memory fallback keeps local dev working with no Redis installed, at the
cost of per-process scope — fine for a single-worker deployment.
"""

import fnmatch
import json
import time
from typing import Any

from loguru import logger

from app.core.config import get_settings

_redis = None  # redis.asyncio.Redis when connected
_memory: dict[str, tuple[float, str]] = {}  # key -> (expires_at, json payload)
_MEMORY_MAX_KEYS = 5000


async def connect_cache() -> None:
    """Try Redis once at startup; fall back to the in-process store quietly."""
    global _redis
    settings = get_settings()
    if not settings.redis_url:
        logger.info("REDIS_URL empty — using in-process cache")
        return
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
        _redis = client
        logger.info(f"Redis cache connected ({settings.redis_url})")
    except Exception as exc:  # noqa: BLE001 — cache is an optimization, never fatal
        _redis = None
        logger.warning(f"Redis unavailable — using in-process cache ({exc})")


async def close_cache() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:  # noqa: BLE001
            pass
        _redis = None
    _memory.clear()


def cache_backend() -> str:
    return "redis" if _redis is not None else "memory"


def _memory_get(key: str) -> str | None:
    entry = _memory.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if time.monotonic() >= expires_at:
        _memory.pop(key, None)
        return None
    return payload


def _memory_set(key: str, payload: str, ttl: int) -> None:
    if len(_memory) >= _MEMORY_MAX_KEYS:
        now = time.monotonic()
        for stale in [k for k, (exp, _) in _memory.items() if exp <= now]:
            _memory.pop(stale, None)
        if len(_memory) >= _MEMORY_MAX_KEYS:  # still full of live keys: drop oldest
            _memory.pop(next(iter(_memory)), None)
    _memory[key] = (time.monotonic() + ttl, payload)


async def get_json(key: str) -> Any | None:
    if _redis is not None:
        try:
            value = await _redis.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"cache get failed ({key}): {exc}")
            return None
        return json.loads(value) if value else None
    payload = _memory_get(key)
    return json.loads(payload) if payload else None


async def set_json(key: str, value: Any, ttl_seconds: int = 60) -> None:
    payload = json.dumps(value, ensure_ascii=False, default=str)
    if _redis is not None:
        try:
            await _redis.set(key, payload, ex=ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"cache set failed ({key}): {exc}")
        return
    _memory_set(key, payload, ttl_seconds)


async def delete(*keys: str) -> None:
    if not keys:
        return
    if _redis is not None:
        try:
            await _redis.delete(*keys)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"cache delete failed: {exc}")
        return
    for key in keys:
        _memory.pop(key, None)


async def delete_prefix(prefix: str) -> None:
    """Drop every key starting with the prefix (used for invalidation)."""
    if _redis is not None:
        try:
            async for key in _redis.scan_iter(match=f"{prefix}*", count=100):
                await _redis.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"cache prefix delete failed ({prefix}): {exc}")
        return
    for key in [k for k in _memory if fnmatch.fnmatch(k, f"{prefix}*")]:
        _memory.pop(key, None)


async def incr_with_ttl(key: str, ttl_seconds: int) -> int:
    """Increment a counter, starting its TTL on first increment (rate limiting)."""
    if _redis is not None:
        try:
            count = await _redis.incr(key)
            if count == 1:
                await _redis.expire(key, ttl_seconds)
            return int(count)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"cache incr failed ({key}): {exc}")
            return 0  # fail open: a broken cache must not lock everyone out
    current = _memory_get(key)
    if current is None:
        _memory_set(key, "1", ttl_seconds)
        return 1
    entry = _memory[key]
    count = int(current) + 1
    _memory[key] = (entry[0], str(count))  # keep the original expiry
    return count
