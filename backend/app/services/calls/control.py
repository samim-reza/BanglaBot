"""Live call control through Telnyx: transfer to a human, hang up, look a call up,
and fetch its recording for the UI."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.regions import Region, normalize_phone
from app.models import CallLog
from app.services import telnyx
from app.voice.twiml import dial_twiml


async def fetch_call_details(call_sid: str) -> dict[str, Any]:
    """Live view of one call: status, answered_by (Telnyx reports no forwarded_from)."""
    if not call_sid or not telnyx.configured():
        return {}
    details = await telnyx.fetch_call(call_sid)
    return {"status": details["status"], "answered_by": details["answered_by"], "forwarded_from": ""}


async def redirect_call_to_human(call_sid: str, number: str, region: Region | str | None = None, caller_id: str = "") -> bool:
    settings = get_settings()
    if not telnyx.configured():
        return False
    texml = dial_twiml(normalize_phone(number, region), caller_id=caller_id or settings.telnyx_from_number)
    await telnyx.update_call(call_sid, texml=texml)
    return True


async def complete_call(call_sid: str) -> None:
    if not telnyx.configured():
        return
    await telnyx.hangup_call(call_sid)


async def fetch_recording(log: CallLog) -> tuple[bytes, str]:
    """Download a call recording from Telnyx for proxying to the UI."""
    if not log.recording_sid:
        raise HTTPException(status_code=404, detail="No recording for this call")
    if not telnyx.configured():
        raise HTTPException(status_code=500, detail="TELNYX_API_KEY is not configured")
    try:
        return await telnyx.download_recording(log.recording_sid)
    except telnyx.TelnyxError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Recording not available yet") from exc
        raise HTTPException(status_code=502, detail=f"Telnyx recording fetch failed: {exc.detail}") from exc
