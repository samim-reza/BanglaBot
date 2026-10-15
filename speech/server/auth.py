"""Shared-secret auth: ``X-Speech-Key`` header (or ``?key=`` on the websocket)."""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request
from starlette.websockets import WebSocket

from .config import get_settings

HEADER = "X-Speech-Key"


def key_ok(provided: str | None) -> bool:
    """True when no key is configured, or ``provided`` matches it (constant-time)."""
    expected = get_settings().api_key
    if not expected:
        return True
    return bool(provided) and hmac.compare_digest(str(provided).encode(), expected.encode())


async def require_key(request: Request) -> None:
    """FastAPI dependency for HTTP routes."""
    if not key_ok(request.headers.get(HEADER)):
        raise HTTPException(status_code=401, detail="missing or invalid X-Speech-Key")


def websocket_key_ok(websocket: WebSocket) -> bool:
    return key_ok(websocket.headers.get(HEADER) or websocket.query_params.get("key"))
