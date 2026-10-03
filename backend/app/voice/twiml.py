"""TeXML (Telnyx's TwiML dialect) builders: the media stream (inbound + outbound),
transfers, hang-ups — plus the callback URLs Telnyx posts to."""

from __future__ import annotations

from html import escape
from typing import Any

from app.core.config import get_settings
from app.core.security import sign_media_stream_token


class PublicUrlMissing(RuntimeError):
    pass


def public_base_url() -> str:
    base = str(get_settings().public_base_url or "").strip().rstrip("/")
    if not base:
        raise PublicUrlMissing("PUBLIC_BASE_URL is not set; Telnyx cannot reach this server")
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base


def stream_url() -> str:
    base = public_base_url()
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):] + "/telnyx/media"
    return "ws://" + base[len("http://"):] + "/telnyx/media"


def status_callback_url(order_id: str) -> str:
    return f"{public_base_url()}/telnyx/status/{order_id}"


def recording_callback_url(order_id: str) -> str:
    return f"{public_base_url()}/telnyx/recording/{order_id}"


def amd_callback_url(order_id: str) -> str:
    return f"{public_base_url()}/telnyx/amd/{order_id}"


def _param(name: str, value: Any) -> str:
    return f'<Parameter name="{escape(name)}" value="{escape(str(value if value is not None else ""))}"/>'


def log_recording_callback_url(call_log_id: str) -> str:
    return f"{public_base_url()}/telnyx/recording-log/{call_log_id}"


def stream_twiml(*, call_log_id: str, order_id: str = "") -> str:
    """``<Connect><Stream>`` with the signed media token; the bridge speaks the greeting.

    ``bidirectionalMode="rtp"`` lets the bridge stream 8 kHz μ-law frames back (the
    default mode only plays whole MP3 files)."""
    params = {
        "order_id": order_id,
        "call_log_id": call_log_id,
        "media_token": sign_media_stream_token(order_id=order_id, call_log_id=call_log_id),
    }
    parameters = "".join(_param(key, value) for key, value in params.items())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect>"
        f'<Stream url="{escape(stream_url())}" bidirectionalMode="rtp" bidirectionalCodec="PCMU">{parameters}</Stream>'
        "</Connect></Response>"
    )


def dial_twiml(number: str, *, caller_id: str | None = None, timeout_seconds: int = 25) -> str:
    """Hand the live call to a human line; hang up when that leg ends."""
    caller_attr = f' callerId="{escape(caller_id)}"' if caller_id else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Dial timeout="{int(timeout_seconds)}"{caller_attr}>{escape(number)}</Dial><Hangup/></Response>'
    )


def hangup_twiml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


def say_twiml(message: str, *, language: str = "en-US") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Say language="{escape(language)}">{escape(message)}</Say><Hangup/></Response>'
    )
