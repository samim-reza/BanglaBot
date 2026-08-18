"""Disk-backed cache for synthesized speech, sized for production call volume.

The bot repeats itself. The greeting, the order-readback frame and the confirm
question are byte-identical on every call, so re-buying them from a
per-character TTS vendor on every call is the largest single line in the bill.

Design, and the failure it answers:

- Blobs on disk under ``root/xx/<sha256>`` (fan-out on the first byte keeps
  directories small at hundreds of thousands of clips). Audio is far too big
  for Redis next to JSON payloads, and clips are worth keeping across restarts.
- A SQLite manifest — *deliberately a sibling of the blob root, not inside
  it* — records what every clip is (text, voice, model, size, cost, usage).
  An ``rm -rf`` of the audio directory then loses no knowledge: every lost
  clip is listed with the exact text needed to re-buy it and what that costs.
- LRU eviction against a byte cap. The long tail (customer names) grows
  forever; hot lines (greetings, frames) are re-touched constantly and never
  age out. Pinned rows are never evicted.
- Single-flight: concurrent misses on the same text buy once; everyone else
  awaits the same purchase. A cold cache under load must not stampede the
  vendor.
- A buy semaphore, because the vendor caps concurrent synthesis (ElevenLabs
  free plan: 2). Rebuild storms and traffic spikes queue instead of erroring.
- Integrity: the manifest knows each clip's size; a short read (torn write,
  truncated disk) is treated as a miss and the file discarded, never played.
- Counters live in the manifest, so stats are O(1) — no directory walks on a
  hot path.

Single-process by design (matches the single-worker deployment). A second
worker would only mean an occasional duplicate purchase, never corruption:
blob writes are atomic renames and SQLite serializes writers.
"""

import asyncio
import hashlib
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from loguru import logger

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / ".tts-cache"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    key TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT '',
    voice_id TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    output_format TEXT NOT NULL DEFAULT '',
    text TEXT,                       -- NULL for adopted orphan files
    bytes INTEGER NOT NULL,
    chars INTEGER NOT NULL DEFAULT 0,
    cost_chars INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    missing INTEGER NOT NULL DEFAULT 0,  -- file lost/corrupt; text says how to re-buy
    created_at REAL NOT NULL,
    last_access REAL NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_clips_lru ON clips (pinned, missing, last_access);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v INTEGER NOT NULL);
"""
_COUNTERS = ("total_bytes", "clips", "hits", "misses", "evictions", "bytes_served", "chars_bought")


def normalize(text: str) -> str:
    """Whitespace-collapse only. Punctuation changes how a line is spoken, so
    it stays part of the identity; ragged spacing does not."""
    return " ".join(text.split())


class TTSCache:
    def __init__(
        self,
        root: Path | str = DEFAULT_ROOT,
        *,
        manifest_path: Path | str | None = None,
        max_bytes: int = 4 * 1024**3,
        buy_concurrency: int = 2,
    ):
        self.root = Path(root)
        # Sibling by default, so wiping the blobs cannot take the ledger with it.
        self.manifest_path = (
            Path(manifest_path)
            if manifest_path
            else self.root.parent / (self.root.name + "-manifest.db")
        )
        self.max_bytes = max_bytes
        self.buy_concurrency = buy_concurrency
        self._db: sqlite3.Connection | None = None
        self._db_lock = threading.RLock()
        # Single-flight state; created lazily on the loop that first buys.
        self._inflight: dict[str, asyncio.Future] = {}
        self._inflight_lock: asyncio.Lock | None = None
        self._buy_gate: asyncio.Semaphore | None = None

    # ── manifest plumbing ────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        if self._db is None:
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.manifest_path, check_same_thread=False)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.execute("PRAGMA busy_timeout=5000")
            db.executescript(_SCHEMA)
            db.executemany(
                "INSERT OR IGNORE INTO meta (k, v) VALUES (?, 0)", [(c,) for c in _COUNTERS]
            )
            db.commit()
            self._db = db
        return self._db

    def _bump(self, db: sqlite3.Connection, counter: str, delta: int) -> None:
        db.execute("UPDATE meta SET v = v + ? WHERE k = ?", (delta, counter))

    # ── keys and paths ───────────────────────────────────────────────────

    def key(self, text: str, *, provider: str, voice_id: str, model: str, output_format: str) -> str:
        fingerprint = "\x1f".join([provider, voice_id, model, output_format, normalize(text)])
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / key

    # ── core sync API ────────────────────────────────────────────────────

    def get(self, key: str, *, touch: bool = True) -> bytes | None:
        """Read one clip; verifies size against the manifest before serving."""
        path = self._path(key)
        try:
            audio = path.read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            audio = None

        with self._db_lock:
            db = self._conn()
            row = db.execute("SELECT bytes, missing FROM clips WHERE key = ?", (key,)).fetchone()
            corrupt = audio is not None and row is not None and row[0] != len(audio)
            if corrupt:
                logger.warning(f"tts-cache: size mismatch for {key[:12]}… — dropping corrupt clip")
                path.unlink(missing_ok=True)
                audio = None
            if audio is None:
                if row and not row[1]:
                    # Present per the manifest but gone/corrupt on disk → record
                    # the loss exactly once so rebuild knows about it.
                    db.execute("UPDATE clips SET missing = 1 WHERE key = ?", (key,))
                    self._bump(db, "total_bytes", -row[0])
                    self._bump(db, "clips", -1)
                self._bump(db, "misses", 1)
            elif touch:
                db.execute(
                    "UPDATE clips SET last_access = ?, hits = hits + 1 WHERE key = ?",
                    (time.time(), key),
                )
                self._bump(db, "hits", 1)
                self._bump(db, "bytes_served", len(audio))
            db.commit()
        return audio

    def put(
        self,
        key: str,
        audio: bytes,
        *,
        text: str | None = None,
        provider: str = "",
        voice_id: str = "",
        model: str = "",
        output_format: str = "",
        cost_chars: int = 0,
        pin: bool = False,
    ) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(audio)
            os.replace(tmp, path)  # atomic: a half-written clip is never servable
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

        now = time.time()
        with self._db_lock:
            db = self._conn()
            old = db.execute("SELECT bytes, missing FROM clips WHERE key = ?", (key,)).fetchone()
            if old and not old[1]:
                self._bump(db, "total_bytes", -old[0])
                self._bump(db, "clips", -1)
            db.execute(
                """INSERT INTO clips (key, provider, voice_id, model, output_format, text,
                                      bytes, chars, cost_chars, pinned, missing,
                                      created_at, last_access, hits)
                   VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,0)
                   ON CONFLICT(key) DO UPDATE SET
                       bytes=excluded.bytes, missing=0, last_access=excluded.last_access,
                       text=COALESCE(excluded.text, clips.text),
                       cost_chars=clips.cost_chars + excluded.cost_chars,
                       pinned=MAX(clips.pinned, excluded.pinned)""",
                (
                    key, provider, voice_id, model, output_format, text,
                    len(audio), len(normalize(text)) if text else 0, cost_chars,
                    1 if pin else 0, now, now,
                ),
            )
            self._bump(db, "total_bytes", len(audio))
            self._bump(db, "clips", 1)
            if cost_chars:
                self._bump(db, "chars_bought", cost_chars)
            db.commit()
            self._ensure_capacity(db)

    def _ensure_capacity(self, db: sqlite3.Connection) -> None:
        """Evict cold, unpinned clips until resident bytes fit the cap."""
        total = db.execute("SELECT v FROM meta WHERE k='total_bytes'").fetchone()[0]
        if total <= self.max_bytes:
            return
        target = int(self.max_bytes * 0.9)  # hysteresis: don't evict one clip per put
        evicted = 0
        while total > target:
            rows = db.execute(
                """SELECT key, bytes FROM clips WHERE pinned=0 AND missing=0
                   ORDER BY last_access ASC LIMIT 256"""
            ).fetchall()
            if not rows:
                break
            for key, size in rows:
                if key in self._inflight:
                    continue
                self._path(key).unlink(missing_ok=True)
                db.execute("DELETE FROM clips WHERE key = ?", (key,))
                total -= size
                evicted += 1
                if total <= target:
                    break
        if evicted:
            db.execute("UPDATE meta SET v = ? WHERE k='total_bytes'", (total,))
            self._bump(db, "clips", -evicted)
            self._bump(db, "evictions", evicted)
            db.commit()
            logger.info(f"tts-cache: evicted {evicted} cold clips to stay under cap")

    # ── async wrappers and single-flight ─────────────────────────────────

    async def aget(self, key: str, *, touch: bool = True) -> bytes | None:
        return await asyncio.to_thread(self.get, key, touch=touch)

    async def aput(self, key: str, audio: bytes, **kw) -> None:
        await asyncio.to_thread(self.put, key, audio, **kw)

    async def get_or_buy(
        self,
        text: str,
        *,
        provider: str,
        voice_id: str,
        model: str,
        output_format: str,
        buy,  # async () -> (bytes, cost_chars | None)
        pin: bool = False,
    ) -> tuple[bytes, bool, int]:
        """Serve from disk, or buy exactly once no matter how many callers race.

        Returns (audio, was_cached, chars_charged).
        """
        key = self.key(
            text, provider=provider, voice_id=voice_id, model=model, output_format=output_format
        )
        audio = await self.aget(key)
        if audio is not None:
            return audio, True, 0

        if self._inflight_lock is None:
            self._inflight_lock = asyncio.Lock()
            self._buy_gate = asyncio.Semaphore(self.buy_concurrency)

        async with self._inflight_lock:
            future = self._inflight.get(key)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
                leader = True
            else:
                leader = False

        if not leader:
            audio = await asyncio.shield(future)
            return audio, True, 0  # someone else paid within this same window

        try:
            async with self._buy_gate:
                audio, cost = await buy()
            cost = cost if cost is not None else len(normalize(text))
            await self.aput(
                key, audio, text=text, provider=provider, voice_id=voice_id, model=model,
                output_format=output_format, cost_chars=cost, pin=pin,
            )
            future.set_result(audio)
            return audio, False, cost
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved: with no followers, GC would warn
            raise
        finally:
            async with self._inflight_lock:
                self._inflight.pop(key, None)

    # ── operations: stats, sweep, rebuild, clear ─────────────────────────

    def stats(self) -> dict:
        with self._db_lock:
            db = self._conn()
            meta = dict(db.execute("SELECT k, v FROM meta").fetchall())
        lookups = meta["hits"] + meta["misses"]
        return {
            "clips": meta["clips"],
            "bytes": meta["total_bytes"],
            "hits": meta["hits"],
            "misses": meta["misses"],
            "hit_rate": round(meta["hits"] / lookups, 4) if lookups else None,
            "evictions": meta["evictions"],
            "bytes_served": meta["bytes_served"],
            "chars_bought": meta["chars_bought"],
            "max_bytes": self.max_bytes,
        }

    def sweep(self) -> dict:
        """Reconcile disk and manifest in both directions; returns a report."""
        with self._db_lock:
            db = self._conn()
            on_disk: dict[str, int] = {}
            if self.root.exists():
                for shard in self.root.iterdir():
                    if not shard.is_dir():
                        continue
                    for blob in shard.iterdir():
                        if blob.is_file() and not blob.name.endswith(".part"):
                            on_disk[blob.name] = blob.stat().st_size
            known = {
                row[0]: (row[1], row[2])
                for row in db.execute("SELECT key, bytes, missing FROM clips").fetchall()
            }
            now = time.time()
            adopted = sum(1 for k in on_disk if k not in known)
            for key, size in on_disk.items():
                if key not in known:
                    # Orphan blob: servable (key-addressed) but text unknown, so
                    # it can never be re-bought if lost. Adopt it for accounting.
                    db.execute(
                        """INSERT INTO clips (key, text, bytes, created_at, last_access)
                           VALUES (?, NULL, ?, ?, ?)""",
                        (key, size, now, now),
                    )
            lost = 0
            for key, (size, missing) in known.items():
                if key not in on_disk and not missing:
                    db.execute("UPDATE clips SET missing = 1 WHERE key = ?", (key,))
                    lost += 1
                elif key in on_disk and missing:
                    db.execute("UPDATE clips SET missing = 0 WHERE key = ?", (key,))
            total = sum(on_disk.values())
            db.execute("UPDATE meta SET v = ? WHERE k='total_bytes'", (total,))
            db.execute("UPDATE meta SET v = ? WHERE k='clips'", (len(on_disk),))
            db.commit()
            rebuildable, rebuild_chars = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(chars),0) FROM clips WHERE missing=1 AND text IS NOT NULL"
            ).fetchone()
        return {
            "files_on_disk": len(on_disk),
            "resident_bytes": total,
            "adopted_orphans": adopted,
            "newly_missing": lost,
            "rebuildable_clips": rebuildable,
            "rebuild_cost_chars": rebuild_chars,
        }

    def missing_rows(self, *, provider: str | None = None, limit: int = 1000) -> list[dict]:
        """Lost-but-rebuildable clips, most-used first — the re-warm shopping list."""
        query = """SELECT key, provider, voice_id, model, output_format, text, chars, hits, pinned
                   FROM clips WHERE missing=1 AND text IS NOT NULL"""
        args: list = []
        if provider:
            query += " AND provider = ?"
            args.append(provider)
        query += " ORDER BY pinned DESC, hits DESC LIMIT ?"
        args.append(limit)
        with self._db_lock:
            rows = self._conn().execute(query, args).fetchall()
        cols = ("key", "provider", "voice_id", "model", "output_format", "text", "chars", "hits", "pinned")
        return [dict(zip(cols, row)) for row in rows]

    async def rebuild(self, buyers: dict, *, limit: int = 100) -> dict:
        """Re-buy lost clips through per-provider buyers, hottest first.

        buyers: {provider: async (row) -> (bytes, cost_chars | None)}.
        Purchases flow through get_or_buy, so the concurrency gate applies and
        a clip that came back some other way is not bought twice.
        """
        bought = skipped = 0
        chars = 0
        for row in self.missing_rows(limit=limit):
            buyer = buyers.get(row["provider"])
            if buyer is None:
                skipped += 1
                continue
            _, cached, cost = await self.get_or_buy(
                row["text"],
                provider=row["provider"], voice_id=row["voice_id"],
                model=row["model"], output_format=row["output_format"],
                buy=lambda row=row, buyer=buyer: buyer(row),
                pin=bool(row["pinned"]),
            )
            if not cached:
                bought += 1
                chars += cost
        return {"bought": bought, "chars_charged": chars, "skipped_no_buyer": skipped}

    def clear(self) -> int:
        """Drop every clip and reset the ledger. Returns clips removed."""
        with self._db_lock:
            db = self._conn()
            removed = db.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
            db.execute("DELETE FROM clips")
            db.execute("UPDATE meta SET v = 0")
            db.commit()
        if self.root.exists():
            for shard in self.root.iterdir():
                if shard.is_dir():
                    for blob in shard.iterdir():
                        blob.unlink(missing_ok=True)
                    shard.rmdir()
        return removed

    def close(self) -> None:
        with self._db_lock:
            if self._db is not None:
                self._db.close()
                self._db = None


def _default_cache() -> TTSCache:
    from app.core.config import get_settings

    settings = get_settings()
    return TTSCache(
        max_bytes=settings.tts_cache_max_mb * 1024 * 1024,
        buy_concurrency=settings.tts_buy_concurrency,
    )


# Default instance used by the live call path and the lab.
cache = _default_cache()
