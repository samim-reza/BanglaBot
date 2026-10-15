"""Microsoft Edge "Read aloud" voices through ``edge-tts`` (free, unofficial).

Same neural voices as Azure (en-US-AvaNeural, bn-BD-NabanitaNeural…) without a
key, but it is an undocumented consumer endpoint: fine for testing and as the
last link of the chain, never something to depend on. It streams MP3, which
``miniaudio`` decodes and resamples to 8 kHz before μ-law encoding.
"""

from __future__ import annotations

import asyncio
import importlib.util

from app.voice.codec import mp3_to_phone
from app.voice.providers.tts.azure import is_neural_voice, voice_for
from app.voice.providers.tts.base import DEFAULT_PERSONA, CachedTTSEngine, TTSError
from app.voice.tts_tiers import TieredTTSCache


def edge_rate(speaking_rate: str | None) -> str:
    """Azure SSML rate ("0%", "-10%") → edge-tts rate ("+0%", "-10%")."""
    value = str(speaking_rate or "").strip()
    if not value or value in {"default", "medium"}:
        return "+0%"
    if not value.endswith("%"):
        value = f"{value}%"
    return value if value[0] in "+-" else f"+{value}"


def edge_available() -> bool:
    """Both packages installed (checked without importing them)."""
    return all(importlib.util.find_spec(name) is not None for name in ("edge_tts", "miniaudio"))


class EdgeTTS(CachedTTSEngine):
    name = "edge"

    def __init__(self, *, cache: TieredTTSCache, speaking_rate: str = "0%", timeout_seconds: float = 15.0) -> None:
        super().__init__(cache=cache)
        self.rate = edge_rate(speaking_rate)
        self.timeout_seconds = timeout_seconds

    def resolve_voice(self, *, voice: str | None, persona: str | None, language: str) -> str:
        if is_neural_voice(voice):
            return str(voice)
        return voice_for(persona or DEFAULT_PERSONA, language)

    def key_extra(self) -> str:
        return self.rate

    async def render(self, text: str, *, voice: str, language: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice, rate=self.rate, connect_timeout=5, receive_timeout=int(self.timeout_seconds))
        mp3 = bytearray()
        try:
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    mp3 += chunk["data"]
        except Exception as exc:  # noqa: BLE001 — aiohttp / edge_tts errors vary by version
            raise TTSError(f"edge_tts_{type(exc).__name__}: {str(exc)[:120]}") from exc
        if not mp3:
            raise TTSError("edge_tts_no_audio")
        return await asyncio.to_thread(mp3_to_phone, bytes(mp3))

    async def aclose(self) -> None:
        return None


__all__ = ["EdgeTTS", "edge_available", "edge_rate"]
