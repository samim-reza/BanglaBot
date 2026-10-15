"""Counter stores for the limiter: Redis when connected, else this process's memory.

Both expose the same small async API. A Redis error never fails a request: the
call falls back to the in-memory store.
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

MAX_MEMORY_KEYS = 50_000


class MemoryBackend:
    """Sliding-window hit logs + expiring counters, single process."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._values: dict[str, tuple[float, int]] = {}

    def reset(self) -> None:
        self._hits.clear()
        self._values.clear()

    def _prune(self, now: float) -> None:
        if len(self._hits) > MAX_MEMORY_KEYS:
            for key in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]:
                self._hits.pop(key, None)
        if len(self._values) > MAX_MEMORY_KEYS:
            for key in [k for k, (expires, _) in self._values.items() if expires <= now]:
                self._values.pop(key, None)

    def hit_sync(self, key: str, max_hits: int, window: float, *, now: float | None = None) -> float:
        """Record a hit; 0 when allowed, else seconds until the window has room."""
        now = time.monotonic() if now is None else now
        log = self._hits.setdefault(key, deque())
        while log and now - log[0] >= window:
            log.popleft()
        if len(log) >= max_hits:
            return max(0.001, window - (now - log[0]))
        log.append(now)
        self._prune(now)
        return 0.0

    async def hit(self, key: str, max_hits: int, window: float) -> float:
        return self.hit_sync(key, max_hits, window)

    async def get(self, key: str) -> tuple[int, float]:
        """(value, seconds left) of a counter; (0, 0) when absent or expired."""
        now = time.monotonic()
        entry = self._values.get(key)
        if entry is None or entry[0] <= now:
            self._values.pop(key, None)
            return 0, 0.0
        return entry[1], entry[0] - now

    async def incr(self, key: str, ttl: float) -> int:
        value, left = await self.get(key)
        now = time.monotonic()
        self._values[key] = (now + (left or ttl), value + 1)
        self._prune(now)
        return value + 1

    async def put(self, key: str, value: int, ttl: float) -> None:
        self._values[key] = (time.monotonic() + ttl, int(value))

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._values.pop(key, None)
            self._hits.pop(key, None)


class RedisBackend:
    """Fixed-window counters (INCR + EXPIRE) shared by every worker / instance."""

    def __init__(self, client: Any, prefix: str = "rl:") -> None:
        self.client = client
        self.prefix = prefix

    async def hit(self, key: str, max_hits: int, window: float) -> float:
        name = self.prefix + "hit:" + key
        count = int(await self.client.incr(name))
        if count == 1:
            await self.client.expire(name, max(1, math.ceil(window)))
        if count > max_hits:
            ttl = await self.client.ttl(name)
            if ttl is None or int(ttl) < 0:
                await self.client.expire(name, max(1, math.ceil(window)))
                ttl = window
            return float(max(1, int(ttl)))
        return 0.0

    async def get(self, key: str) -> tuple[int, float]:
        name = self.prefix + key
        value = await self.client.get(name)
        if value is None:
            return 0, 0.0
        ttl = await self.client.ttl(name)
        return int(value), float(max(0, int(ttl or 0)))

    async def incr(self, key: str, ttl: float) -> int:
        name = self.prefix + key
        value = int(await self.client.incr(name))
        if value == 1:
            await self.client.expire(name, max(1, math.ceil(ttl)))
        return value

    async def put(self, key: str, value: int, ttl: float) -> None:
        await self.client.set(self.prefix + key, int(value), ex=max(1, math.ceil(ttl)))

    async def delete(self, *keys: str) -> None:
        if keys:
            await self.client.delete(*[self.prefix + key for key in keys])
            await self.client.delete(*[self.prefix + "hit:" + key for key in keys])


memory = MemoryBackend()
_redis_backend: RedisBackend | None = None


def current() -> MemoryBackend | RedisBackend:
    """Redis when the app connected to it at startup, else memory."""
    global _redis_backend
    from app.core import redis as redis_module

    client = redis_module.redis_client
    if client is None:
        return memory
    if _redis_backend is None or _redis_backend.client is not client:
        _redis_backend = RedisBackend(client)
    return _redis_backend


async def call(method: str, *args: Any) -> Any:
    """Run a backend method on the current store, falling back to memory on a Redis error."""
    store = current()
    try:
        return await getattr(store, method)(*args)
    except Exception as exc:  # noqa: BLE001 — limiter must never take a request down
        if store is memory:
            raise
        await logger.awarning("ratelimit_redis_failed", error=str(exc)[:200])
        return await getattr(memory, method)(*args)


__all__ = ["MemoryBackend", "RedisBackend", "call", "current", "memory"]
