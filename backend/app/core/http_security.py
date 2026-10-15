"""HTTP hardening middleware (pure ASGI, so websockets pass straight through).

- ``SecurityHeadersMiddleware``: nosniff, referrer policy, no framing (except the
  public widget), HSTS in production, ``no-store`` on auth / admin responses.
- ``BodySizeLimitMiddleware``: 413 for bodies over the limit — a small limit on
  public and webhook endpoints, a larger one (CSV imports) everywhere else.
- ``SplitCORSMiddleware``: the chat widget's endpoints answer any website without
  credentials; everything else only the portal's own origins (``cors_origins``).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Embedded on customers' websites: any origin, no credentials, may be framed.
PUBLIC_WIDGET_PREFIXES = ("/api/public/widget",)
#: Bodies here are small (forms, chat lines, provider webhooks).
SMALL_BODY_PREFIXES = ("/api/public/", "/telnyx/", "/twilio/", "/api/meta/")
NO_STORE_PREFIXES = ("/api/auth/", "/api/admin/")
DEV_ORIGINS = ("http://localhost:3000", "http://localhost:5173")
DEV_ORIGIN_REGEX = r"https://.*\.(ngrok-free\.app|ngrok\.io|trycloudflare\.com)"
HSTS_VALUE = "max-age=31536000; includeSubDomains"


def _www_variants(origin: str) -> list[str]:
    parts = urlsplit(origin)
    host = parts.hostname or ""
    if not parts.scheme or not host or host == "localhost" or host.replace(".", "").isdigit():
        return [origin]
    port = f":{parts.port}" if parts.port else ""
    other = host[4:] if host.startswith("www.") else f"www.{host}"
    return [f"{parts.scheme}://{host}{port}", f"{parts.scheme}://{other}{port}"]


def cors_origins(frontend_origin: str, *, production: bool) -> tuple[list[str], str | None]:
    """Allowed origins (FRONTEND_ORIGIN entries + their www / apex twins) and, outside
    production, localhost dev servers and tunnel domains."""
    origins: list[str] = []
    for raw in str(frontend_origin or "").split(","):
        raw = raw.strip().rstrip("/")
        for origin in _www_variants(raw) if raw else []:
            if origin not in origins:
                origins.append(origin)
    if production:
        return origins, None
    for origin in DEV_ORIGINS:
        if origin not in origins:
            origins.append(origin)
    return origins, DEV_ORIGIN_REGEX


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        frameable = path.startswith(PUBLIC_WIDGET_PREFIXES)
        no_store = path.startswith(NO_STORE_PREFIXES)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                if not frameable:
                    headers.setdefault("X-Frame-Options", "DENY")
                    headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
                if no_store:
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int, max_small_bytes: int, small_prefixes: tuple[str, ...] = SMALL_BODY_PREFIXES) -> None:
        self.app = app
        self.max_bytes = int(max_bytes)
        self.max_small_bytes = int(max_small_bytes)
        self.small_prefixes = small_prefixes

    def limit_for(self, path: str) -> int:
        return self.max_small_bytes if path.startswith(self.small_prefixes) else self.max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope.get("path", ""))
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                too_big = int(declared) > limit
            except ValueError:
                too_big = False
            if too_big:
                await JSONResponse({"detail": "Request body too large"}, status_code=413)(scope, receive, send)
                return
        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Raised inside the route's body read: becomes a normal 413 response.
                    raise HTTPException(status_code=413, detail="Request body too large")
            return message

        await self.app(scope, counting_receive, send)


class SplitCORSMiddleware:
    """Public widget paths: ``Access-Control-Allow-Origin: *`` without credentials;
    every other path goes through Starlette's CORS with the portal's origins."""

    def __init__(self, app: ASGIApp, *, public_prefixes: tuple[str, ...] = PUBLIC_WIDGET_PREFIXES, **cors: Any) -> None:
        self.app = app
        self.public_prefixes = public_prefixes
        self.cors = CORSMiddleware(app, **cors)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self.public_prefixes):
            await self.cors(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if scope.get("method") == "OPTIONS" and "access-control-request-method" in headers:
            preflight = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "600",
            }
            await Response(status_code=204, headers=preflight)(scope, receive, send)
            return

        async def send_public(message: Message) -> None:
            if message["type"] == "http.response.start":
                out = MutableHeaders(scope=message)
                out["Access-Control-Allow-Origin"] = "*"
                if "access-control-allow-credentials" in out:
                    del out["access-control-allow-credentials"]
            await send(message)

        await self.app(scope, receive, send_public)


__all__ = ["BodySizeLimitMiddleware", "SecurityHeadersMiddleware", "SplitCORSMiddleware", "cors_origins"]
