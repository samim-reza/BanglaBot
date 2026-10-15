"""The real client address behind ``TRUSTED_PROXY_HOPS`` reverse proxies.

Each trusted proxy appends the address it received the connection from to
``X-Forwarded-For``, so with N trusted hops the client is the N-th entry from
the right; anything further left was sent by the client and can be forged.
0 hops ignores the header (direct exposure). Note: uvicorn's
``--forwarded-allow-ips='*'`` rewrites the socket address to the LEFT-most
(forgeable) entry, which is why the header is parsed here.
"""

from __future__ import annotations

from fastapi import Request

from app.core.config import get_settings

MAX_IP_CHARS = 64


def parse_client_ip(forwarded_for: str | None, peer: str | None, hops: int) -> str:
    peer_ip = (peer or "unknown")[:MAX_IP_CHARS]
    if hops <= 0 or not forwarded_for:
        return peer_ip
    entries = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    if not entries:
        return peer_ip
    index = len(entries) - hops
    chosen = entries[index] if index >= 0 else entries[0]
    return chosen[:MAX_IP_CHARS]


def client_ip(request: Request, *, hops: int | None = None) -> str:
    trusted = get_settings().trusted_proxy_hops if hops is None else hops
    peer = request.client.host if request.client else None
    return parse_client_ip(request.headers.get("x-forwarded-for"), peer, int(trusted or 0))


__all__ = ["client_ip", "parse_client_ip"]
