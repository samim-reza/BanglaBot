"""Calls in progress in this process — for the admin's live view and its hang-up button.

Bridges register when they start and unregister when they end. The registry
holds weak references, so a finished call can never be kept alive by it.
"""

from __future__ import annotations

import time
import weakref
from typing import Any

from app.core.log_redaction import scrub

_live: "weakref.WeakValueDictionary[str, Any]" = weakref.WeakValueDictionary()


def register(bridge: Any) -> None:
    if getattr(bridge, "call_log_id", ""):
        _live[str(bridge.call_log_id)] = bridge


def unregister(call_log_id: str) -> None:
    _live.pop(str(call_log_id), None)


def count(merchant_id: str | None = None) -> int:
    return sum(1 for bridge in list(_live.values()) if merchant_id is None or str(getattr(bridge.merchant, "id", "")) == merchant_id)


def _row(call_log_id: str, bridge: Any) -> dict[str, Any]:
    runtime = getattr(getattr(bridge, "agent", None), "runtime", None)
    llm = getattr(bridge, "_llm", None)
    stt = getattr(bridge, "_stt", None)
    merchant = getattr(bridge, "merchant", None)
    return {
        "call_log_id": call_log_id,
        "merchant_id": str(getattr(merchant, "id", "") or ""),
        "business": str(getattr(merchant, "business_name", "") or ""),
        "vertical": str(getattr(merchant, "vertical", "") or ""),
        "direction": getattr(bridge.ctx, "direction", ""),
        "caller": scrub(str(getattr(bridge.ctx, "caller_number", "") or "")),
        "seconds": int(time.monotonic() - float(getattr(bridge, "started_at", time.monotonic()))),
        "stage": getattr(runtime, "stage", ""),
        "language": getattr(bridge, "primary_language", ""),
        "llm": getattr(getattr(llm, "last_link", None), "key", "") or getattr(llm, "model", ""),
        "stt": getattr(stt, "name", ""),
        "closing": bool(getattr(bridge, "closing", False)),
    }


def snapshot() -> list[dict[str, Any]]:
    rows = [_row(call_log_id, bridge) for call_log_id, bridge in list(_live.items())]
    return sorted(rows, key=lambda row: -row["seconds"])


async def hang_up(call_log_id: str) -> bool:
    """End a live call now (closes the media socket; the carrier leg is hung up too when known)."""
    bridge = _live.get(str(call_log_id))
    if bridge is None:
        return False
    call_sid = str(getattr(bridge, "call_sid", "") or "")
    if call_sid:
        try:
            from app.services import telnyx

            await telnyx.hangup_call(call_sid)
        except Exception:  # noqa: BLE001 — closing the socket below still ends our side
            pass
    bridge.closing = True
    await bridge._safe_close()
    return True


__all__ = ["count", "hang_up", "register", "snapshot", "unregister"]
