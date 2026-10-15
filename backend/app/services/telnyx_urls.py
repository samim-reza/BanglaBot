"""Signed Telnyx webhook URLs (Telnyx can't sign TeXML callbacks on a pretrial account).

The TeXML app's voice URL is ``/telnyx/inbound/{sig}`` with ``sig`` over
``telnyx:inbound``; per-call callbacks carry a signature over their own kind and
id (``telnyx:status:<order id>``, ``telnyx:recording-log:<call log id>``, ...), so
one leaked URL can't be replayed against another call. The routes check the
signature (constant time) before reading anything else.
"""

from __future__ import annotations

from app.core.security.signed_paths import path_signature, verify_path_signature
from app.voice.twiml import public_base_url

INBOUND = "inbound"
SMS_EVENTS = "sms-events"
#: Callback kinds whose URL ends in ``/{id}/{sig}``.
STATUS, RECORDING, AMD, RECORDING_LOG, SMS_STATUS, TEXML = "status", "recording", "amd", "recording-log", "sms-status", "texml"


def scope(kind: str, value: str | None = None) -> str:
    return f"telnyx:{kind}" if value is None else f"telnyx:{kind}:{value}"


def sign(kind: str, value: str | None = None) -> str:
    return path_signature(scope(kind, value))


def verify(kind: str, value: str | None, sig: str | None) -> bool:
    return verify_path_signature(scope(kind, value), sig)


def _base(base: str | None) -> str:
    return (base or public_base_url()).rstrip("/")


def inbound_url(base: str | None = None) -> str:
    """The TeXML application's voice webhook."""
    return f"{_base(base)}/telnyx/{INBOUND}/{sign(INBOUND)}"


def sms_events_url(base: str | None = None) -> str:
    """The messaging profile's webhook (set in the Telnyx portal)."""
    return f"{_base(base)}/telnyx/{SMS_EVENTS}/{sign(SMS_EVENTS)}"


def callback_url(kind: str, value: str, base: str | None = None) -> str:
    return f"{_base(base)}/telnyx/{kind}/{value}/{sign(kind, value)}"


def status_callback_url(order_id: str) -> str:
    return callback_url(STATUS, order_id)


def recording_callback_url(order_id: str) -> str:
    return callback_url(RECORDING, order_id)


def amd_callback_url(order_id: str) -> str:
    return callback_url(AMD, order_id)


def log_recording_callback_url(call_log_id: str) -> str:
    return callback_url(RECORDING_LOG, call_log_id)


def sms_status_url(message_id: str, base: str | None = None) -> str:
    return callback_url(SMS_STATUS, message_id, base)


def texml_url(order_id: str) -> str:
    return callback_url(TEXML, order_id)


def mask(url: str) -> str:
    """The URL with its signature shortened, for logs and terminal output."""
    head, _, tail = url.rpartition("/")
    return f"{head}/{tail[:4]}…" if len(tail) >= 8 else url


__all__ = [
    "amd_callback_url",
    "callback_url",
    "inbound_url",
    "log_recording_callback_url",
    "mask",
    "recording_callback_url",
    "sign",
    "sms_events_url",
    "sms_status_url",
    "status_callback_url",
    "texml_url",
    "verify",
]
