"""Request rate limits: 429 with ``Retry-After`` when a key is over its budget."""

from __future__ import annotations

import math

from fastapi import HTTPException, Request

from app.core.ratelimit import backends
from app.core.ratelimit.ip import client_ip

DEFAULT_DETAIL = "Too many requests — please try again in a little while."


def too_many(retry_after: float, detail: str = DEFAULT_DETAIL) -> HTTPException:
    return HTTPException(status_code=429, detail=detail, headers={"Retry-After": str(max(1, math.ceil(retry_after)))})


async def enforce(key: str, max_hits: int, per_seconds: float, *, detail: str = DEFAULT_DETAIL) -> None:
    """Count one hit on ``key`` (Redis or memory); raise 429 when over ``max_hits`` per window."""
    retry = await backends.call("hit", key, int(max_hits), float(per_seconds))
    if retry:
        raise too_many(retry, detail)


async def rate_limit(request: Request, bucket: str, *, max_hits: int, per_seconds: float, key: str | None = None) -> None:
    """Per-client limit: ``bucket`` + the client IP (or an explicit ``key``, e.g. an account id)."""
    await enforce(f"{bucket}:{key if key is not None else client_ip(request)}", max_hits, per_seconds)


def limit(request: Request, bucket: str, *, max_hits: int, per_seconds: float) -> None:
    """Synchronous per-IP limit (this process's memory) for callers that can't await."""
    retry = backends.memory.hit_sync(f"{bucket}:{client_ip(request)}", int(max_hits), float(per_seconds))
    if retry:
        raise too_many(retry)


__all__ = ["enforce", "limit", "rate_limit", "too_many"]
