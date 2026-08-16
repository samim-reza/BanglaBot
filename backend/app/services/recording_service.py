"""Streams Twilio call recordings through the backend (Twilio media needs auth)."""

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import CallLog


async def save_recording(db: AsyncSession, call_sid: str, recording_sid: str) -> None:
    """Store the recording SID on the call log when Twilio's webhook fires."""
    log = (
        await db.execute(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
    ).scalar_one_or_none()
    if not log:
        logger.warning(f"Recording callback for unknown call sid {call_sid}")
        return
    log.recording_sid = recording_sid
    await db.commit()


async def stream_recording(recording_sid: str) -> StreamingResponse:
    """Proxy the MP3 from Twilio with account credentials, streamed to the client."""
    settings = get_settings()
    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}"
        f"/Recordings/{recording_sid}.mp3"
    )
    client = httpx.AsyncClient(
        auth=(settings.twilio_account_sid, settings.twilio_auth_token), timeout=30.0
    )
    request = client.build_request("GET", url)
    response = await client.send(request, stream=True)
    if response.status_code != 200:
        await response.aclose()
        await client.aclose()
        raise HTTPException(404, "রেকর্ডিং পাওয়া যায়নি")

    async def body():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(body(), media_type="audio/mpeg")
