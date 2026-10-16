"""Admin: live calls (with hang-up), the voice engine's state and quick tests, system health."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import get_settings
from app.core.redis import redis_health
from app.core.security import boot_guard
from app.db.session import get_db
from app.services import live_calls, voice_engine_service
from app.services import telnyx as telnyx_service

router = APIRouter(prefix="/api/admin", tags=["admin-system"])


class TTSTest(BaseModel):
    text: str = Field(default="Hello, thank you for calling. How can I help you today?", max_length=300)
    language: str = "en"


@router.get("/live-calls")
async def list_live_calls(admin=Depends(require_admin)):  # noqa: ANN001
    rows = live_calls.snapshot()
    return {"items": rows, "total": len(rows)}


@router.post("/live-calls/{call_log_id}/hangup")
async def hang_up(call_log_id: str, admin=Depends(require_admin("superadmin", "support"))):  # noqa: ANN001
    if not await live_calls.hang_up(call_log_id):
        raise HTTPException(status_code=404, detail="That call has already ended")
    return {"ok": True}


@router.get("/voice-engine")
async def voice_engine(admin=Depends(require_admin)):  # noqa: ANN001
    return await voice_engine_service.status()


@router.post("/voice-engine/test-tts")
async def test_tts(data: TTSTest, admin=Depends(require_admin("superadmin"))):  # noqa: ANN001
    try:
        return await voice_engine_service.test_tts(data.text, data.language)
    except Exception as exc:  # noqa: BLE001 — report the provider error to the admin
        raise HTTPException(status_code=502, detail=f"TTS failed: {str(exc)[:200]}") from exc


@router.post("/voice-engine/test-llm")
async def test_llm(admin=Depends(require_admin("superadmin"))):  # noqa: ANN001
    try:
        return await voice_engine_service.test_llm()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM failed: {str(exc)[:200]}") from exc


@router.get("/system/health")
async def health(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):  # noqa: ANN001
    settings = get_settings()
    started = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        database = {"up": True, "ms": int((time.monotonic() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001
        database = {"up": False, "error": str(exc)[:120]}
    return {
        "database": database,
        "redis": await redis_health(),
        "speech_server": await voice_engine_service.speech_server_status(),
        "telnyx": {"voice": telnyx_service.voice_ready(), "configured": telnyx_service.configured(), "signatures_enforced": boot_guard.webhook_signatures_enforced(settings)},
        "live_calls": live_calls.count(),
        "environment": settings.environment,
    }
