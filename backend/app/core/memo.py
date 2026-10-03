"""Tiny in-process TTL memo for hot, rarely-changing reads on the call path.

Inbound calls must answer fast (the caller hears ringing until our webhook
returns), so the account behind a dialed number and the account's catalog are
memoized here and dropped whenever they are edited. Single-process (the dev
server runs one worker); every entry also expires on its own.
"""

from __future__ import annotations

import time
from typing import Any

_store: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 120.0


def get(key: str) -> Any | None:
    entry = _store.get(key)
    if entry is None:
        return None
    expires, value = entry
    if time.monotonic() > expires:
        _store.pop(key, None)
        return None
    return value


def put(key: str, value: Any, ttl: float = DEFAULT_TTL) -> None:
    if len(_store) > 5000:
        now = time.monotonic()
        for stale in [k for k, (exp, _) in _store.items() if exp < now]:
            _store.pop(stale, None)
    _store[key] = (time.monotonic() + ttl, value)


def drop(prefix: str) -> None:
    for key in [k for k in _store if k.startswith(prefix)]:
        _store.pop(key, None)


def clear() -> None:
    _store.clear()


__all__ = ["clear", "drop", "get", "put"]
