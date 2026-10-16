"""Server-side requests to addresses an account owner typed (webhook URL, iCal links).

Owners control these URLs, so every request is checked against SSRF:

- ``check_url`` (no network): http / https only, a host name, no ``user:pass@``,
  no ``localhost`` / ``*.internal`` style names, and a literal IP must be public.
- ``resolve_public``: every DNS answer must be a public address — private,
  loopback, link-local (cloud metadata 169.254.169.254), CGNAT, multicast,
  reserved, IPv4-mapped / NAT64 / 6to4 forms of those, ``::1`` and ``fc00::/7``
  are refused.
- ``request``: resolves once and connects to that pinned address (the ``Host``
  header and TLS SNI keep the name, so certificates still verify), so a DNS
  answer that changes between the check and the connect (rebinding) can't reach
  an internal address. Redirects are re-checked hop by hop; bodies are capped.

``OUTBOUND_ALLOW_PRIVATE=true`` (development only — production refuses to boot
with it) lets a developer point a webhook at ``localhost``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from typing import Any

import httpx

from app.core.config import get_settings

SCHEMES = ("http", "https")
MAX_REDIRECTS = 3
DEFAULT_MAX_BYTES = 1_000_000
USER_AGENT = "callisa-outbound/1"
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".intranet", ".lan", ".home.arpa", ".corp")
BLOCKED_NAMES = frozenset({"localhost", "metadata", "metadata.google.internal", "instance-data"})
#: Ranges ``is_global`` lets through but that still reach internal hosts.
EXTRA_BLOCKED = tuple(
    ipaddress.ip_network(net)
    for net in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32", "100.64.0.0/10", "192.0.0.0/24", "198.18.0.0/15")
)
_WIRE_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})
_NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+)){0,3}$", re.IGNORECASE)

#: Test seams: ``resolver(host, port) -> [ip, ...]`` and an httpx transport.
resolver: Any = None
transport: httpx.AsyncBaseTransport | None = None


class UnsafeURLError(ValueError):
    """The URL may not be fetched; the message is safe to show the owner."""


def allow_private() -> bool:
    return bool(getattr(get_settings(), "outbound_allow_private", False))


def is_public_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    try:
        ip = ipaddress.ip_address(str(value).split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
    return not any(ip in net for net in EXTRA_BLOCKED if net.version == ip.version)


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def check_url(url: str, *, schemes: tuple[str, ...] = SCHEMES) -> httpx.URL:
    """The parsed URL when it is safe to try; ``UnsafeURLError`` otherwise (no DNS lookup)."""
    text = str(url or "").strip()
    try:
        parsed = httpx.URL(text)
    except (httpx.InvalidURL, ValueError, TypeError) as exc:
        raise UnsafeURLError("That isn't a valid web address") from exc
    if parsed.scheme not in schemes:
        raise UnsafeURLError("Use an http:// or https:// address")
    host = (parsed.host or "").rstrip(".").lower()
    if not host:
        raise UnsafeURLError("That address has no host name")
    if parsed.userinfo:
        raise UnsafeURLError("Don't put a user name or password in the address")
    if parsed.port is not None and not 0 < parsed.port < 65536:
        raise UnsafeURLError("That address has an invalid port")
    if allow_private():
        return parsed
    literal = _literal_ip(host)
    if literal is not None:
        if not is_public_ip(literal):
            raise UnsafeURLError("That address points to a private network")
        return parsed
    if _NUMERIC_HOST.match(host) or host in BLOCKED_NAMES or host.endswith(BLOCKED_SUFFIXES) or "." not in host:
        raise UnsafeURLError("That address points to a private network")
    return parsed


async def _system_resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def resolve_public(host: str, port: int) -> list[str]:
    """The host's addresses, all public; ``UnsafeURLError`` if any is not (or none resolve)."""
    literal = _literal_ip(host)
    if literal is not None:
        addresses = [str(literal)]
    else:
        lookup = resolver or _system_resolve
        try:
            addresses = list(dict.fromkeys(await lookup(host, port)))
        except (OSError, UnicodeError) as exc:
            raise UnsafeURLError("Couldn't find that address") from exc
    if not addresses:
        raise UnsafeURLError("Couldn't find that address")
    if not allow_private() and not all(is_public_ip(address) for address in addresses):
        raise UnsafeURLError("That address points to a private network")
    return addresses


def _port(parsed: httpx.URL) -> int:
    return parsed.port or (443 if parsed.scheme == "https" else 80)


async def _pinned(parsed: httpx.URL) -> tuple[httpx.URL, dict[str, str], dict[str, Any]]:
    """(URL with the vetted IP as host, Host header, request extensions for TLS SNI)."""
    host = parsed.raw_host.decode("ascii")
    address = (await resolve_public(host, _port(parsed)))[0]
    pinned = parsed.copy_with(host=address)
    name = f"[{host}]" if ":" in host else host
    host_header = name if parsed.port is None else f"{name}:{parsed.port}"
    extensions: dict[str, Any] = {"sni_hostname": host} if parsed.scheme == "https" else {}
    return pinned, {"Host": host_header}, extensions


async def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise UnsafeURLError("The response is too large")
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise UnsafeURLError("The response is too large")
    return bytes(body)


async def request(
    method: str,
    url: str,
    *,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 6.0,
    max_bytes: int = DEFAULT_MAX_BYTES,
    follow_redirects: bool = False,
) -> httpx.Response:
    """One guarded request; the returned response's body is already read (≤ ``max_bytes``).

    Raises ``UnsafeURLError`` for refused addresses / oversized bodies and
    ``httpx.HTTPError`` for network failures.
    """
    current = check_url(url)
    hops = MAX_REDIRECTS if follow_redirects else 0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False, transport=transport) as client:
        for _ in range(hops + 1):
            pinned, host_header, extensions = await _pinned(current)
            send_headers = {"User-Agent": USER_AGENT, **(headers or {}), **host_header}
            req = client.build_request(method, pinned, content=content, headers=send_headers, extensions=extensions)
            response = await client.send(req, stream=True)
            try:
                location = response.headers.get("location", "")
                if follow_redirects and response.is_redirect and location:
                    current = check_url(str(current.join(location)))
                    method, content = ("GET", None) if response.status_code in (301, 302, 303) else (method, content)
                    continue
                body = await _read_capped(response, max_bytes)
            finally:
                await response.aclose()
            # The body is already decoded: drop the headers that describe the wire encoding.
            kept = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in _WIRE_HEADERS]
            return httpx.Response(response.status_code, headers=kept, content=body, request=httpx.Request(method, str(current)))
    raise UnsafeURLError("Too many redirects")


def describe_error(exc: BaseException) -> str:
    """What to tell the owner about a failed request — never internal details."""
    if isinstance(exc, UnsafeURLError):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return "The address took too long to answer"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"The address answered HTTP {exc.response.status_code}"
    return "Couldn't reach that address"


__all__ = ["UnsafeURLError", "allow_private", "check_url", "describe_error", "is_public_ip", "request", "resolve_public"]
