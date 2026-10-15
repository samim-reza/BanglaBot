"""L3 of the speech cache: one shared bucket in Supabase Storage.

Render's disk is wiped on every deploy and each instance has its own, so a line
synthesized once is uploaded here and every later process downloads it instead
of paying the TTS provider again. Objects are ``{bucket}/{key}.ulaw`` (raw
8 kHz μ-law; the key already hashes provider, voice, format and text).

Reads are bounded by a short timeout and a circuit breaker so a slow or broken
storage tier never delays a call; writes are fire-and-forget background tasks.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_KEY_RE = re.compile(r"^[0-9a-f]{16,128}$")
#: Consecutive read failures that open the breaker, and for how long.
BREAKER_ERRORS = 3
BREAKER_SECONDS = 60.0
#: Background uploads beyond this many in flight are dropped (they retry next miss).
MAX_PENDING_UPLOADS = 32


class SupabaseTTSStore:
    def __init__(
        self,
        *,
        base_url: str,
        secret_key: str,
        bucket: str = "tts-cache",
        read_timeout: float = 0.8,
        write_timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.bucket = bucket
        self.object_base = f"{base_url.rstrip('/')}/storage/v1/object/{bucket}"
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(write_timeout, connect=min(2.0, write_timeout)),
            headers={"Authorization": f"Bearer {secret_key}", "apikey": secret_key},
            transport=transport,
        )
        self._pending: set[asyncio.Task[bool]] = set()
        self._consecutive_errors = 0
        self._down_until = 0.0
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.writes = 0
        self.write_errors = 0
        self.dropped_writes = 0
        self.bytes_read = 0
        self.bytes_written = 0

    def _url(self, key: str) -> str:
        if not _KEY_RE.match(key):
            raise ValueError("cache keys are hex digests")
        return f"{self.object_base}/{key}.ulaw"

    @property
    def available(self) -> bool:
        return time.monotonic() >= self._down_until

    def _read_failed(self, reason: str) -> None:
        self.errors += 1
        self._consecutive_errors += 1
        if self._consecutive_errors >= BREAKER_ERRORS:
            self._down_until = time.monotonic() + BREAKER_SECONDS
            self._consecutive_errors = 0
            logger.warning("tts_shared_cache_paused", reason=reason, seconds=BREAKER_SECONDS)

    async def get(self, key: str) -> bytes | None:
        """The clip for ``key`` or ``None`` (miss, timeout, error or breaker open)."""
        if not self.available:
            return None
        try:
            response = await self._client.get(self._url(key), timeout=self.read_timeout)
        except (httpx.HTTPError, ValueError) as exc:
            self._read_failed(type(exc).__name__)
            return None
        if response.status_code == 200 and response.content:
            self._consecutive_errors = 0
            self.hits += 1
            self.bytes_read += len(response.content)
            return response.content
        # Supabase answers a missing object with 400 {"statusCode":"404"} or a plain 404.
        if response.status_code in (400, 404):
            self._consecutive_errors = 0
            self.misses += 1
            return None
        self._read_failed(f"http_{response.status_code}")
        return None

    async def put(self, key: str, data: bytes) -> bool:
        if not data:
            return False
        try:
            response = await self._client.post(
                self._url(key),
                content=data,
                headers={"x-upsert": "true", "content-type": "application/octet-stream"},
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.write_errors += 1
            await logger.ainfo("tts_shared_cache_upload_failed", error=type(exc).__name__)
            return False
        if response.status_code in (200, 201):
            self.writes += 1
            self.bytes_written += len(data)
            return True
        self.write_errors += 1
        await logger.ainfo("tts_shared_cache_upload_failed", status=response.status_code, detail=response.text[:120])
        return False

    def put_background(self, key: str, data: bytes) -> None:
        """Upload without waiting (never blocks a call)."""
        if len(self._pending) >= MAX_PENDING_UPLOADS:
            self.dropped_writes += 1
            return
        task = asyncio.create_task(self.put(key, data))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def drain(self) -> None:
        """Wait for pending uploads (shutdown, tests)."""
        if self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)

    def stats(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "available": self.available,
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "writes": self.writes,
            "write_errors": self.write_errors,
            "dropped_writes": self.dropped_writes,
            "pending_writes": len(self._pending),
            "bytes_read": self.bytes_read,
            "bytes_written": self.bytes_written,
        }

    async def aclose(self) -> None:
        await self.drain()
        await self._client.aclose()


__all__ = ["SupabaseTTSStore"]
