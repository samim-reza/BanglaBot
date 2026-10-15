"""``TTSCache``: the L1 memory LRU and L2 disk LRU with pins, stats and the async API."""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import structlog

from app.voice.tts_cache.manifest import ManifestMixin

logger = structlog.get_logger(__name__)

#: Default L1 budget: ~32 MB of μ-law is ~70 minutes of hot lines.
HOT_MAX_ENTRIES = 4096
HOT_MAX_BYTES = 32 * 1024 * 1024


def normalize_text(text: str) -> str:
    """Whitespace-insensitive key text so trivial spacing differences share audio."""
    return " ".join(str(text or "").split())


class TTSCache(ManifestMixin):
    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        max_entries: int = 5000,
        max_bytes: int = 500 * 1024 * 1024,
        hot_max_bytes: int = HOT_MAX_BYTES,
        hot_max_entries: int = HOT_MAX_ENTRIES,
    ) -> None:
        self.directory = Path(directory)
        self.max_entries = max(1, int(max_entries))
        self.max_bytes = max(1, int(max_bytes))
        self.hot_max_bytes = max(0, int(hot_max_bytes))
        self.hot_max_entries = max(0, int(hot_max_entries))
        self._lock = threading.Lock()
        # key -> {"size": int, "last_used": float}; oldest first.
        self._index: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._pinned: set[str] = set()
        self._total_bytes = 0
        self.hits = 0
        self.hot_hits = 0
        self.disk_hits = 0
        self.misses = 0
        self.evictions = 0
        self._hot: OrderedDict[str, bytes] = OrderedDict()
        self._hot_bytes = 0
        self._dirty = False
        self._last_manifest_save = 0.0
        self.directory.mkdir(parents=True, exist_ok=True)
        self._load_manifest()

    # ------------------------------------------------------------------ keys
    @staticmethod
    def make_key(*, provider: str, voice: str, language: str, output_format: str, text: str, extra: str = "") -> str:
        material = "\x1f".join([provider, voice, language, output_format, extra, normalize_text(text)])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.bin"

    # ------------------------------------------------------------------ LRU
    def _over_limits(self) -> bool:
        return len(self._index) > self.max_entries or self._total_bytes > self.max_bytes

    def _enforce_limits(self) -> None:
        if not self._over_limits():
            return
        for key in list(self._index):  # oldest first
            if not self._over_limits():
                break
            if key in self._pinned:
                continue
            meta = self._index.pop(key)
            self._total_bytes -= int(meta.get("size", 0))
            self.evictions += 1
            self._hot_drop(key)
            try:
                self._path(key).unlink(missing_ok=True)
            except OSError:
                pass

    def _hot_drop(self, key: str) -> None:
        data = self._hot.pop(key, None)
        if data is not None:
            self._hot_bytes -= len(data)

    def _hot_put(self, key: str, data: bytes) -> None:
        self._hot_drop(key)
        if len(data) > self.hot_max_bytes:
            return
        self._hot[key] = data
        self._hot_bytes += len(data)
        while self._hot and (len(self._hot) > self.hot_max_entries or self._hot_bytes > self.hot_max_bytes):
            _, old = self._hot.popitem(last=False)
            self._hot_bytes -= len(old)

    def _touch(self, key: str) -> None:
        meta = self._index.get(key)
        if meta is not None:
            meta["last_used"] = time.time()
            self._index.move_to_end(key)

    # --------------------------------------------------------------- lookups
    def get_hot(self, key: str) -> bytes | None:
        """Memory-only lookup (no disk, safe on the event loop)."""
        with self._lock:
            data = self._hot.get(key)
            if data is None:
                return None
            self._hot.move_to_end(key)
            self._touch(key)
            self.hits += 1
            self.hot_hits += 1
            return data

    def lookup(self, key: str) -> tuple[bytes | None, str]:
        """``(audio, tier)`` with tier ``"l1"`` / ``"l2"``, or ``(None, "")`` on a miss."""
        with self._lock:
            meta = self._index.get(key)
            if meta is None:
                self.misses += 1
                return None, ""
            hot = self._hot.get(key)
            if hot is not None:
                self._hot.move_to_end(key)
                self._touch(key)
                self.hits += 1
                self.hot_hits += 1
                return hot, "l1"
            try:
                data = self._path(key).read_bytes()
            except OSError:
                # File vanished underneath us: drop the stale index row.
                self._total_bytes -= int(meta.get("size", 0))
                self._index.pop(key, None)
                self.misses += 1
                return None, ""
            self._touch(key)
            self._hot_put(key, data)
            self.hits += 1
            self.disk_hits += 1
            return data, "l2"

    def get(self, key: str) -> bytes | None:
        return self.lookup(key)[0]

    def put(self, key: str, data: bytes) -> None:
        if not data:
            return
        with self._lock:
            try:
                self._path(key).write_bytes(data)
            except OSError as exc:  # pragma: no cover
                logger.warning("tts_cache_write_failed", error=str(exc))
                return
            previous = self._index.pop(key, None)
            if previous is not None:
                self._total_bytes -= int(previous.get("size", 0))
            self._index[key] = {"size": len(data), "last_used": time.time()}
            self._total_bytes += len(data)
            self._hot_put(key, data)
            self._enforce_limits()
            self._maybe_save_manifest()

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._index

    # ------------------------------------------------------------------ pins
    def pin(self, keys: Iterable[str]) -> int:
        """Never evict these keys (present now or written later). Returns how many were new."""
        with self._lock:
            before = len(self._pinned)
            self._pinned.update(key for key in keys if key)
            added = len(self._pinned) - before
            if added:
                self._save_manifest()
            return added

    def unpin(self, keys: Iterable[str]) -> int:
        with self._lock:
            before = len(self._pinned)
            self._pinned.difference_update(keys)
            removed = before - len(self._pinned)
            if removed:
                self._enforce_limits()
                self._save_manifest()
            return removed

    def is_pinned(self, key: str) -> bool:
        with self._lock:
            return key in self._pinned

    # ----------------------------------------------------------------- stats
    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._index),
                "bytes": self._total_bytes,
                "max_entries": self.max_entries,
                "max_bytes": self.max_bytes,
                "hits": self.hits,
                "hot_hits": self.hot_hits,
                "disk_hits": self.disk_hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "hot_entries": len(self._hot),
                "hot_bytes": self._hot_bytes,
                "hot_max_bytes": self.hot_max_bytes,
                "pinned": len(self._pinned),
            }

    def clear(self) -> None:
        """Drop every cached clip (pins are kept: they are intent, not data)."""
        with self._lock:
            for key in list(self._index):
                self._path(key).unlink(missing_ok=True)
            self._index.clear()
            self._hot.clear()
            self._hot_bytes = 0
            self._total_bytes = 0
            self._save_manifest()

    # ------------------------------------------------------------ async API
    async def aget(self, key: str) -> bytes | None:
        hot = self.get_hot(key)
        if hot is not None:
            return hot
        return await asyncio.to_thread(self.get, key)

    async def alookup(self, key: str) -> tuple[bytes | None, str]:
        hot = self.get_hot(key)
        if hot is not None:
            return hot, "l1"
        return await asyncio.to_thread(self.lookup, key)

    async def aput(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.put, key, data)
