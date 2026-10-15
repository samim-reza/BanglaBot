"""Which speech providers are worth trying right now.

* A tiny process-wide breaker: a session that hits an auth/quota error (or a
  provider that fails to connect) marks its provider down for a while, so the
  bridge's reconnect lands on the next provider in the chain instead.
* A cached ``GET /health`` probe for the local open-source speech server, so a
  laptop that went to sleep costs a call at most ~300 ms once, not per line.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_down_until: dict[str, float] = {}
#: url → (expires_at, healthy, body)
_probe_cache: dict[str, tuple[float, bool, dict[str, Any]]] = {}

PROBE_TIMEOUT_SECONDS = 0.3
PROBE_TTL_OK = 30.0
PROBE_TTL_DOWN = 10.0


# ------------------------------------------------------------------ breaker
def mark_down(name: str, seconds: float = 60.0, *, reason: str = "") -> None:
    _down_until[name] = time.monotonic() + max(0.0, seconds)
    logger.warning("speech_provider_paused", provider=name, seconds=seconds, reason=reason[:120])


def is_down(name: str) -> bool:
    until = _down_until.get(name)
    if until is None:
        return False
    if time.monotonic() >= until:
        _down_until.pop(name, None)
        return False
    return True


def reset() -> None:
    """Forget every breaker and probe (tests)."""
    _down_until.clear()
    _probe_cache.clear()


# ------------------------------------------------------------ local server
def http_base(url: str) -> str:
    return url.rstrip("/")


def ws_base(url: str) -> str:
    base = http_base(url)
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :]
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :]
    return base


async def speech_server_healthy(
    url: str | None,
    key: str | None = None,
    *,
    timeout: float = PROBE_TIMEOUT_SECONDS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """``GET {url}/health`` → ``{"ok": true}``, cached (30 s up / 10 s down)."""
    if not url:
        return False
    base = http_base(url)
    now = time.monotonic()
    cached = _probe_cache.get(base)
    if cached is not None and cached[0] > now:
        return cached[1]
    healthy = False
    body: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await client.get(f"{base}/health", headers={"X-Speech-Key": key} if key else None)
        if response.status_code == 200:
            parsed = response.json()
            body = parsed if isinstance(parsed, dict) else {}
            healthy = bool(body.get("ok"))
    except (httpx.HTTPError, ValueError):
        healthy = False
    _probe_cache[base] = (now + (PROBE_TTL_OK if healthy else PROBE_TTL_DOWN), healthy, body)
    if not healthy and (cached is None or cached[1]):
        await logger.ainfo("speech_server_unreachable", url=base)
    return healthy


def speech_server_info(url: str | None) -> dict[str, Any]:
    """The last ``/health`` body (device, models) for admin views."""
    cached = _probe_cache.get(http_base(url)) if url else None
    return dict(cached[2]) if cached else {}


__all__ = ["http_base", "is_down", "mark_down", "reset", "speech_server_healthy", "speech_server_info", "ws_base"]
