"""Tiny in-process sliding-window rate limiter for public endpoints (single worker)."""

from __future__ import annotations

import time
from collections import deque

from fastapi import HTTPException, Request

_hits: dict[str, deque[float]] = {}


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit(request: Request, bucket: str, *, max_hits: int, per_seconds: float) -> None:
    key = f"{bucket}:{client_ip(request)}"
    now = time.monotonic()
    window = _hits.setdefault(key, deque())
    while window and now - window[0] > per_seconds:
        window.popleft()
    if len(window) >= max_hits:
        raise HTTPException(status_code=429, detail="Too many requests — please try again in a little while.")
    window.append(now)
    if len(_hits) > 20000:
        for stale in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
            _hits.pop(stale, None)


__all__ = ["client_ip", "limit"]
