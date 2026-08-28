"""Optional async Redis client.

The app runs fine without Redis: ``connect_redis`` only logs a warning when the
server is unreachable and every helper degrades to a no-op.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from redis.asyncio import Redis

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

redis_client: Redis | None = None


async def connect_redis() -> None:
    global redis_client
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001 — optional dependency
        await logger.awarning("redis_unavailable", error=str(exc))
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001
            pass
        redis_client = None
        return
    redis_client = client
    await logger.ainfo("redis_connected")


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:  # noqa: BLE001
            pass
        redis_client = None


async def redis_health() -> dict[str, Any]:
    if redis_client is None:
        return {"status": "disabled"}
    try:
        await redis_client.ping()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}


async def get_json(key: str) -> Any | None:
    if redis_client is None:
        return None
    try:
        value = await redis_client.get(key)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("redis_get_failed", key=key, error=str(exc))
        return None
    return json.loads(value) if value else None


async def set_json(key: str, value: Any, ttl_seconds: int = 60) -> None:
    if redis_client is None:
        return
    try:
        await redis_client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("redis_set_failed", key=key, error=str(exc))


async def delete_key(key: str) -> None:
    if redis_client is None:
        return
    try:
        await redis_client.delete(key)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("redis_delete_failed", key=key, error=str(exc))
