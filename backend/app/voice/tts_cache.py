"""LRU cache for synthesized speech.

Every fixed line the agent speaks (greeting, "are you still there?", working
phrase, goodbye, recaps that repeat word for word) is synthesized **once** and
replayed from here, so the same sentence is never billed to the TTS provider
twice. Entries are keyed by provider + voice + language + output format + the
normalized text, stored as raw audio files on disk, and evicted least-recently
-used first when either the entry count or the byte budget is exceeded.

The index lives in memory as an insertion-ordered dict (oldest first) and is
persisted to ``manifest.json`` next to the audio files so hits survive a
restart. All file I/O is small and synchronous; the async wrappers hand it to a
thread so the call loop never blocks on disk.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

MANIFEST_NAME = "manifest.json"
#: The manifest is rewritten at most this often (it is only LRU ordering; the
#: audio files themselves are the source of truth and are re-indexed on load).
MANIFEST_SAVE_INTERVAL = 5.0
#: In-memory layer for the hottest lines (greetings, questions): no disk, no thread hop.
HOT_MAX_ENTRIES = 256
HOT_MAX_BYTES = 16 * 1024 * 1024


def normalize_text(text: str) -> str:
    """Whitespace-insensitive key text so trivial spacing differences share audio."""
    return " ".join(str(text or "").split())


class TTSCache:
    def __init__(self, directory: str | os.PathLike[str], *, max_entries: int = 5000, max_bytes: int = 500 * 1024 * 1024) -> None:
        self.directory = Path(directory)
        self.max_entries = max(1, int(max_entries))
        self.max_bytes = max(1, int(max_bytes))
        self._lock = threading.Lock()
        # key -> {"size": int, "last_used": float}; oldest first.
        self._index: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._total_bytes = 0
        self.hits = 0
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

    # ------------------------------------------------------------- manifest
    def _load_manifest(self) -> None:
        entries: dict[str, Any] = {}
        manifest = self.directory / MANIFEST_NAME
        if manifest.exists():
            try:
                raw = json.loads(manifest.read_text("utf-8"))
                found = raw.get("entries") if isinstance(raw, dict) else None
                if isinstance(found, dict):
                    entries = found
            except (OSError, ValueError) as exc:
                logger.warning("tts_cache_manifest_unreadable", error=str(exc))
        # Audio files are the truth: anything written after the last manifest save
        # is re-indexed by its modification time.
        rows: list[tuple[str, int, float]] = []
        for path in self.directory.glob("*.bin"):
            key = path.stem
            try:
                stat = path.stat()
            except OSError:
                continue
            meta = entries.get(key) if isinstance(entries.get(key), dict) else None
            last_used = float(meta.get("last_used", stat.st_mtime)) if meta else float(stat.st_mtime)
            rows.append((key, stat.st_size, last_used))
        # Oldest first so the OrderedDict reflects real LRU order.
        for key, size, last_used in sorted(rows, key=lambda row: row[2]):
            self._index[key] = {"size": size, "last_used": last_used}
            self._total_bytes += size
        self._enforce_limits()

    def _maybe_save_manifest(self) -> None:
        self._dirty = True
        if time.monotonic() - self._last_manifest_save >= MANIFEST_SAVE_INTERVAL:
            self._save_manifest()

    def flush(self) -> None:
        """Write the manifest now (shutdown)."""
        with self._lock:
            if self._dirty:
                self._save_manifest()

    def _save_manifest(self) -> None:
        self._dirty = False
        self._last_manifest_save = time.monotonic()
        manifest = self.directory / MANIFEST_NAME
        tmp = manifest.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps({"entries": self._index}), "utf-8")
            os.replace(tmp, manifest)
        except OSError as exc:  # pragma: no cover - disk trouble is non-fatal
            logger.warning("tts_cache_manifest_write_failed", error=str(exc))

    # ------------------------------------------------------------------ LRU
    def _enforce_limits(self) -> None:
        while self._index and (len(self._index) > self.max_entries or self._total_bytes > self.max_bytes):
            key, meta = self._index.popitem(last=False)
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
        self._hot[key] = data
        self._hot_bytes += len(data)
        while self._hot and (len(self._hot) > HOT_MAX_ENTRIES or self._hot_bytes > HOT_MAX_BYTES):
            _, old = self._hot.popitem(last=False)
            self._hot_bytes -= len(old)

    def get_hot(self, key: str) -> bytes | None:
        """Memory-only lookup (no disk, safe on the event loop)."""
        with self._lock:
            data = self._hot.get(key)
            if data is None:
                return None
            self._hot.move_to_end(key)
            meta = self._index.get(key)
            if meta is not None:
                meta["last_used"] = time.time()
                self._index.move_to_end(key)
            self.hits += 1
            return data

    def get(self, key: str) -> bytes | None:
        with self._lock:
            meta = self._index.get(key)
            if meta is None:
                self.misses += 1
                return None
            hot = self._hot.get(key)
            if hot is not None:
                self._hot.move_to_end(key)
                meta["last_used"] = time.time()
                self._index.move_to_end(key)
                self.hits += 1
                return hot
            path = self._path(key)
            try:
                data = path.read_bytes()
            except OSError:
                # File vanished underneath us: drop the stale index row.
                self._total_bytes -= int(meta.get("size", 0))
                self._index.pop(key, None)
                self.misses += 1
                return None
            meta["last_used"] = time.time()
            self._index.move_to_end(key)
            self._hot_put(key, data)
            self.hits += 1
            return data

    def put(self, key: str, data: bytes) -> None:
        if not data:
            return
        with self._lock:
            path = self._path(key)
            try:
                path.write_bytes(data)
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

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._index),
                "bytes": self._total_bytes,
                "max_entries": self.max_entries,
                "max_bytes": self.max_bytes,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
            }

    def clear(self) -> None:
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

    async def aput(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.put, key, data)
