"""No real network in the e2e run: a socket may only reach the throwaway database.

``socket.socket.connect`` / ``connect_ex`` / ``socket.getaddrinfo`` are wrapped
for the whole session. Anything else is refused AND recorded, so code that
swallows connection errors ("an optimization only") still fails the test that
caused it (the autouse fixture in ``conftest`` asserts the record is empty).
"""

from __future__ import annotations

import socket
from typing import Any

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})

#: Every refused attempt: ``"host:port"`` strings, cleared per test.
blocked: list[str] = []

_allowed: set[tuple[str, int]] = set()
_originals: dict[str, Any] = {}


def _allowed_address(address: Any) -> bool:
    if not isinstance(address, tuple) or len(address) < 2:
        return True  # AF_UNIX paths (and socketpair) are local by construction
    host, port = str(address[0]), int(address[1])
    return (host, port) in _allowed or (host in LOOPBACK and ("*", port) in _allowed)


def _refuse(target: str) -> ConnectionRefusedError:
    blocked.append(target)
    return ConnectionRefusedError(f"e2e network guard: connection to {target} refused (only the throwaway database is reachable)")


def install(db_host: str, db_port: int) -> None:
    """Allow only ``db_host:db_port`` (and its loopback aliases); idempotent."""
    if _originals:
        return
    _allowed.add((db_host, int(db_port)))
    _allowed.add(("*", int(db_port)) if db_host in LOOPBACK else (db_host, int(db_port)))
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    _originals.update(connect=original_connect, connect_ex=original_connect_ex, getaddrinfo=original_getaddrinfo)

    def connect(self: socket.socket, address: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _allowed_address(address):
            raise _refuse(f"{address[0]}:{address[1]}")
        return original_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _allowed_address(address):
            _refuse(f"{address[0]}:{address[1]}")
            return 111  # ECONNREFUSED
        return original_connect_ex(self, address)

    def getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        name = host.decode() if isinstance(host, bytes) else str(host or "")
        if name and name not in LOOPBACK and name != db_host:
            blocked.append(f"{name}:{port}")
            raise socket.gaierror(socket.EAI_NONAME, f"e2e network guard: DNS lookup of {name} refused")
        return original_getaddrinfo(host, port, *args, **kwargs)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]


def uninstall() -> None:
    if not _originals:
        return
    socket.socket.connect = _originals.pop("connect")  # type: ignore[method-assign]
    socket.socket.connect_ex = _originals.pop("connect_ex")  # type: ignore[method-assign]
    socket.getaddrinfo = _originals.pop("getaddrinfo")  # type: ignore[assignment]
    _allowed.clear()


def take() -> list[str]:
    """The attempts recorded since the last call (and forget them)."""
    out = list(blocked)
    blocked.clear()
    return out


__all__ = ["blocked", "install", "take", "uninstall"]
