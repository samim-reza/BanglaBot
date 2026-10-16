"""Call policy shared by every call path: what a call status means, how long a call
may run, and the gates in front of placing one (telephony configured, voice plan)."""

from __future__ import annotations

from fastapi import HTTPException

from app.core.addons import entitlements
from app.core.config import get_settings
from app.core.plans import CHANNEL_VOICE
from app.models import Merchant

#: Call statuses meaning the call is still live (leave the record alone).
LIVE_CALL_STATUSES = frozenset({"queued", "initiated", "ringing", "in-progress"})
FAILED_CALL_STATUSES = frozenset({"no-answer", "busy", "failed", "canceled"})
#: Extra seconds past ``time_limit`` before a "calling" record counts as stale.
STALE_CALL_GRACE_SECONDS = 120


def call_time_limit(merchant: Merchant, *, inbound: bool = False) -> int:
    configured = int(getattr(merchant, "max_call_seconds", 0) or 0)
    if configured > 0:
        return configured
    settings = get_settings()
    return int(settings.voice_max_inbound_call_seconds if inbound else settings.voice_max_call_seconds)


def require_telephony() -> None:
    settings = get_settings()
    if not settings.telnyx_api_key or not settings.telnyx_texml_app_id:
        raise HTTPException(status_code=503, detail="Telnyx is not configured (TELNYX_API_KEY / TELNYX_TEXML_APP_ID)")
    if not settings.telnyx_from_number:
        raise HTTPException(status_code=503, detail="TELNYX_FROM_NUMBER is not configured")


def require_voice(merchant: Merchant) -> None:
    """Phone calls need a voice plan (a chat-only plan has no phone agent)."""
    if not entitlements(merchant).has_channel(CHANNEL_VOICE):
        raise HTTPException(status_code=403, detail="Phone calls aren't in your plan — upgrade to a voice plan")
