"""Persistence of the L2 index: ``manifest.json`` keeps LRU order and pins across
restarts; the audio files on disk stay the source of truth and are re-indexed on load."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

MANIFEST_NAME = "manifest.json"
#: The manifest is rewritten at most this often (it is only LRU ordering; the
#: audio files themselves are the source of truth and are re-indexed on load).
MANIFEST_SAVE_INTERVAL = 5.0


class ManifestMixin:
    """Mixed into :class:`~app.voice.tts_cache.core.TTSCache` (callers hold ``_lock`` where needed)."""

    def _load_manifest(self) -> None:
        entries: dict[str, Any] = {}
        manifest = self.directory / MANIFEST_NAME
        if manifest.exists():
            try:
                raw = json.loads(manifest.read_text("utf-8"))
                found = raw.get("entries") if isinstance(raw, dict) else None
                if isinstance(found, dict):
                    entries = found
                pinned = raw.get("pinned") if isinstance(raw, dict) else None
                if isinstance(pinned, list):
                    self._pinned = {str(key) for key in pinned if key}
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
            tmp.write_text(json.dumps({"entries": self._index, "pinned": sorted(self._pinned)}), "utf-8")
            os.replace(tmp, manifest)
        except OSError as exc:  # pragma: no cover - disk trouble is non-fatal
            logger.warning("tts_cache_manifest_write_failed", error=str(exc))
