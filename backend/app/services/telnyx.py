"""Telnyx REST client: TeXML calls (create / update / fetch / record), recordings and SMS.

TeXML is Telnyx's TwiML dialect, so calls are driven exactly like before: the
call runs the TeXML we hand it (``<Connect><Stream>`` to the media websocket) and
Telnyx posts Twilio-style form callbacks (CallSid, CallStatus, AnsweredBy, ...).

The account-scoped TeXML endpoints need the account SID (the Telnyx user id).
``TELNYX_ACCOUNT_SID`` sets it; otherwise it is learned from the first webhook or
media stream (``AccountSid`` / ``start.user_id``) and logged so it can be pinned.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx
import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

API_BASE = "https://api.telnyx.com/v2"
#: ``twilio_call_sid`` column width; longer Telnyx call ids are stored (and matched) truncated.
SID_COLUMN_WIDTH = 64

_learned_account_sid: str | None = None


class TelnyxError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 0) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def configured() -> bool:
    return bool(get_settings().telnyx_api_key)


def voice_ready() -> bool:
    settings = get_settings()
    return bool(settings.telnyx_api_key and settings.telnyx_texml_app_id and settings.telnyx_from_number)


def sid_key(call_sid: str | None) -> str:
    """A call id as stored in (and looked up from) the ``twilio_call_sid`` column."""
    return str(call_sid or "")[:SID_COLUMN_WIDTH]


def account_sid() -> str | None:
    return get_settings().telnyx_account_sid or _learned_account_sid


def remember_account_sid(value: str | None) -> None:
    """Keep the account SID a webhook or media stream told us about."""
    global _learned_account_sid
    value = str(value or "").strip()
    if not value or get_settings().telnyx_account_sid or value == _learned_account_sid:
        return
    _learned_account_sid = value
    logger.info("telnyx_account_sid_learned", account_sid=value, hint="set TELNYX_ACCOUNT_SID to this value")


def _headers() -> dict[str, str]:
    key = get_settings().telnyx_api_key
    if not key:
        raise TelnyxError("TELNYX_API_KEY is not configured")
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    errors = body.get("errors") if isinstance(body, dict) else None
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        return str(first.get("detail") or first.get("title") or first.get("code") or body)[:300]
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])[:300]
    return f"HTTP {response.status_code}"


async def _request(method: str, path: str, *, json: Any = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        response = await client.request(method, f"{API_BASE}{path}", headers=_headers(), json=json, data=data)
    if response.status_code >= 400:
        raise TelnyxError(_error_detail(response), response.status_code)
    if not response.content:
        return {}
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _account_path(suffix: str) -> str:
    sid = account_sid()
    if not sid:
        raise TelnyxError("Telnyx account SID unknown yet (set TELNYX_ACCOUNT_SID)")
    return f"/texml/Accounts/{sid}{suffix}"


def _form(values: dict[str, Any]) -> dict[str, str]:
    """TeXML update endpoints take form fields; drop empties, stringify booleans."""
    out: dict[str, str] = {}
    for key, value in values.items():
        if value is None or value == "":
            continue
        out[key] = ("true" if value else "false") if isinstance(value, bool) else str(value)
    return out


# --------------------------------------------------------------------------- calls
def number_for(merchant: Any) -> str:
    """The number an account calls and texts from: its own Telnyx number (its inbound
    number) when it has one, else the platform number. Every number must belong to this
    Telnyx account — on the TeXML app for calls, on the messaging profile for SMS."""
    from app.core.regions import normalize_phone, region_of

    own = str(getattr(merchant, "inbound_number", "") or "").strip()
    if own:
        return normalize_phone(own, region_of(merchant))
    return str(get_settings().telnyx_from_number or "")


async def create_call(
    *,
    to: str,
    texml: str,
    status_callback: str | None = None,
    recording_callback: str | None = None,
    amd_callback: str | None = None,
    time_limit: int | None = None,
    from_number: str | None = None,
) -> str:
    """Dial ``to`` from ``from_number`` (default: the platform number) running ``texml``. Returns the call SID ("" if
    Telnyx didn't say; the media stream reports it once the call is answered)."""
    settings = get_settings()
    if not settings.telnyx_texml_app_id:
        raise TelnyxError("TELNYX_TEXML_APP_ID is not configured")
    if account_sid():
        body: dict[str, Any] = {
            "ApplicationSid": settings.telnyx_texml_app_id,
            "To": to,
            "From": from_number or settings.telnyx_from_number,
            "Texml": texml,
        }
        if status_callback:
            body.update(StatusCallback=status_callback, StatusCallbackMethod="POST", StatusCallbackEvent="completed")
        if recording_callback:
            body.update(
                Record=True,
                RecordingStatusCallback=recording_callback,
                RecordingStatusCallbackMethod="POST",
                RecordingStatusCallbackEvent="completed",
            )
        if amd_callback:
            body.update(
                MachineDetection="Enable",
                AsyncAmd=True,
                AsyncAmdStatusCallback=amd_callback,
                AsyncAmdStatusCallbackMethod="POST",
                MachineDetectionTimeout=15000,
            )
        if time_limit:
            body["TimeLimit"] = max(30, min(14400, int(time_limit)))
        result = await _request("POST", _account_path("/Calls"), json=body)
    else:
        # Before the account SID is known only the application endpoint works; it has no
        # status / recording / AMD callbacks (stale records are settled by the sweeper).
        result = await _request(
            "POST",
            f"/texml/calls/{settings.telnyx_texml_app_id}",
            json={"To": to, "From": from_number or settings.telnyx_from_number, "Texml": texml},
        )
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    return str(data.get("call_sid") or data.get("sid") or "")


async def update_call(call_sid: str, *, texml: str | None = None, status: str | None = None) -> None:
    await _request("POST", _account_path(f"/Calls/{call_sid}"), data=_form({"Texml": texml, "Status": status}))


async def hangup_call(call_sid: str) -> None:
    await update_call(call_sid, status="completed")


async def fetch_call(call_sid: str) -> dict[str, Any]:
    """``status`` / ``duration`` / ``answered_by`` of one call."""
    result = await _request("GET", _account_path(f"/Calls/{call_sid}"))
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    try:
        duration = int(float(data.get("duration") or 0))
    except (TypeError, ValueError):
        duration = 0
    return {
        "status": str(data.get("status") or ""),
        "duration": duration,
        "answered_by": str(data.get("answered_by") or ""),
    }


async def start_recording(call_sid: str, *, callback: str) -> None:
    await _request(
        "POST",
        _account_path(f"/Calls/{call_sid}/Recordings.json"),
        data=_form(
            {
                "RecordingStatusCallback": callback,
                "RecordingStatusCallbackMethod": "POST",
                "RecordingStatusCallbackEvent": "completed",
                "RecordingChannels": "dual",
                "PlayBeep": False,
            }
        ),
    )


async def download_recording(recording_sid: str) -> tuple[bytes, str]:
    """The recording's audio (a fresh presigned link is looked up each time)."""
    media_url = ""
    if account_sid():
        try:
            result = await _request("GET", _account_path(f"/Recordings/{recording_sid}.json"))
            media_url = str(result.get("media_url") or "")
        except TelnyxError:
            media_url = ""
    if not media_url:
        result = await _request("GET", f"/recordings/{recording_sid}")
        urls = (result.get("data") or {}).get("download_urls") or {}
        media_url = str(urls.get("mp3") or urls.get("wav") or "")
    if not media_url:
        raise TelnyxError("Recording not available yet", 404)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
        response = await client.get(media_url)
        if response.status_code in (401, 403):
            response = await client.get(media_url, headers=_headers())
    if response.status_code == 404:
        raise TelnyxError("Recording not available yet", 404)
    if response.status_code != 200:
        raise TelnyxError(f"Recording download failed ({response.status_code})", response.status_code)
    content_type = response.headers.get("content-type", "") or ("audio/wav" if media_url.split("?")[0].endswith(".wav") else "audio/mpeg")
    return response.content, content_type


async def point_app_at(voice_url: str) -> None:
    """Set the TeXML application's voice webhook (inbound calls)."""
    settings = get_settings()
    if not settings.telnyx_texml_app_id:
        raise TelnyxError("TELNYX_TEXML_APP_ID is not configured")
    await _request(
        "PATCH",
        f"/texml_applications/{settings.telnyx_texml_app_id}",
        json={"voice_url": voice_url, "voice_method": "post"},
    )


# --------------------------------------------------------------------------- SMS
async def send_sms(*, to: str, text: str, webhook_url: str | None = None, from_number: str | None = None) -> str:
    settings = get_settings()
    body: dict[str, Any] = {"to": to, "text": text}
    sender = from_number or settings.telnyx_sms_from or settings.telnyx_from_number
    if sender:
        body["from"] = sender
    if settings.telnyx_messaging_profile_id:
        body["messaging_profile_id"] = settings.telnyx_messaging_profile_id
    if webhook_url:
        body["webhook_url"] = webhook_url
    result = await _request("POST", "/messages", json=body)
    return str((result.get("data") or {}).get("id") or "")


# --------------------------------------------------------------------------- webhooks
SIGNATURE_TOLERANCE_SECONDS = 300


def verify_signature(raw_body: bytes, signature: str, timestamp: str) -> bool:
    """Ed25519 check of ``{timestamp}|{body}`` against the account's public key."""
    public_key = get_settings().telnyx_public_key
    if not public_key or not signature or not timestamp:
        return False
    try:
        if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
            return False
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        key.verify(base64.b64decode(signature), timestamp.encode() + b"|" + raw_body)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


__all__ = [
    "TelnyxError",
    "account_sid",
    "configured",
    "create_call",
    "download_recording",
    "fetch_call",
    "hangup_call",
    "point_app_at",
    "remember_account_sid",
    "send_sms",
    "sid_key",
    "start_recording",
    "update_call",
    "verify_signature",
    "voice_ready",
]
