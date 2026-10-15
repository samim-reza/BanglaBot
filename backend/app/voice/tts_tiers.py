"""The speech cache as one object: L1 memory → L2 disk → L3 shared bucket → synthesize.

"Never pay twice for the same sentence":

* a hit in any tier is returned without calling a provider (an L3 hit is copied
  down to L1/L2 so the next one is local);
* concurrent requests for the same key share ONE synthesis (an in-flight task
  per key), so ten calls ringing at once with the same greeting pay once;
* the synthesis task is shielded: a barge-in that cancels the waiting caller
  does not throw away audio that was already paid for — it is still cached;
* new audio goes to L2 immediately and to L3 in the background.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

import structlog

from app.voice.tts_cache import TTSCache
from app.voice.tts_shared_cache import SupabaseTTSStore

logger = structlog.get_logger(__name__)

TIERS = ("l1", "l2", "l3")


class TieredTTSCache:
    def __init__(self, local: TTSCache, shared: SupabaseTTSStore | None = None, *, shared_timeout: float = 0.8) -> None:
        self.local = local
        self.shared = shared
        self.shared_timeout = shared_timeout
        self._inflight: dict[str, asyncio.Task[tuple[bytes, str]]] = {}
        self.tier_hits: dict[str, int] = {tier: 0 for tier in TIERS}
        self.inflight_joins = 0
        self.misses = 0
        self.synthesized = 0
        self.synth_bytes = 0
        self.served_bytes = 0

    # ---------------------------------------------------------------- lookups
    def contains(self, key: str) -> bool:
        """Local (L1/L2) presence only — no network."""
        return self.local.contains(key)

    async def get(self, key: str) -> tuple[bytes | None, str]:
        """``(audio, tier)`` from L1 → L2 → L3, or ``(None, "")``."""
        data, tier = await self.local.alookup(key)
        if data is None and self.shared is not None:
            try:
                data = await asyncio.wait_for(self.shared.get(key), timeout=self.shared_timeout + 0.2)
            except asyncio.TimeoutError:
                data = None
            if data:
                tier = "l3"
                await self.local.aput(key, data)
        if data is None:
            return None, ""
        self.tier_hits[tier] += 1
        self.served_bytes += len(data)
        return data, tier

    async def get_or_create(self, key: str, factory: Callable[[], Awaitable[bytes]]) -> tuple[bytes, str]:
        """Cached audio for ``key``, else ``factory()`` once — however many callers ask.

        Returns ``(audio, source)``: ``l1`` / ``l2`` / ``l3`` (cache tier),
        ``synth`` (this caller triggered the synthesis) or ``inflight`` (joined
        another caller's synthesis).
        """
        hot = self.local.get_hot(key)
        if hot is not None:
            self.tier_hits["l1"] += 1
            self.served_bytes += len(hot)
            return hot, "l1"
        task = self._inflight.get(key)
        joined = task is not None
        if task is None:
            task = asyncio.ensure_future(self._resolve(key, factory))
            self._inflight[key] = task
            task.add_done_callback(lambda done, k=key: self._settle(k, done))
        else:
            self.inflight_joins += 1
        data, source = await asyncio.shield(task)
        if joined and source == "synth":
            return data, "inflight"
        return data, source

    def _settle(self, key: str, task: asyncio.Task[tuple[bytes, str]]) -> None:
        if self._inflight.get(key) is task:
            del self._inflight[key]
        if not task.cancelled():
            task.exception()  # mark retrieved: every waiter may have been cancelled

    async def _resolve(self, key: str, factory: Callable[[], Awaitable[bytes]]) -> tuple[bytes, str]:
        data, tier = await self.get(key)
        if data is not None:
            return data, tier
        self.misses += 1
        audio = await factory()
        if not audio:
            return b"", "synth"
        self.synthesized += 1
        self.synth_bytes += len(audio)
        await self.local.aput(key, audio)
        if self.shared is not None:
            self.shared.put_background(key, audio)
        return audio, "synth"

    def inflight(self) -> int:
        return len(self._inflight)

    # ------------------------------------------------------------------ pins
    def pin(self, keys: Iterable[str]) -> int:
        return self.local.pin(keys)

    def unpin(self, keys: Iterable[str]) -> int:
        return self.local.unpin(keys)

    # ------------------------------------------------------------- lifecycle
    def flush(self) -> None:
        self.local.flush()

    def stats(self) -> dict[str, Any]:
        local = self.local.stats()
        hits = sum(self.tier_hits.values()) + self.inflight_joins
        lookups = hits + self.misses
        return {
            "hits": dict(self.tier_hits, inflight=self.inflight_joins),
            "misses": self.misses,
            "hit_rate": round(hits / lookups, 4) if lookups else 0.0,
            "synthesized": self.synthesized,
            "synth_bytes": self.synth_bytes,
            "served_bytes": self.served_bytes,
            "entries": local["entries"],
            "bytes": local["bytes"],
            "pinned": local["pinned"],
            "local": local,
            "shared": self.shared.stats() if self.shared is not None else None,
        }

    async def aclose(self) -> None:
        self.flush()
        if self.shared is not None:
            await self.shared.aclose()


__all__ = ["TIERS", "TieredTTSCache"]
