"""Gemini text-to-speech (free tier on our key).

``generateContent`` with an AUDIO response returns 24 kHz PCM16 (``audio/L16``,
little-endian) or a WAV; it is resampled to 8 kHz and μ-law encoded here. The
text is sent bare: the TTS models read any instruction ("Say:") aloud. Slower
than Azure/Deepgram (~1–3 s a sentence), so it sits behind them in the chain,
and cached lines never come back here anyway.
"""

from __future__ import annotations

import asyncio
import base64

import httpx

from app.voice.codec import l16_rate, pcm16_to_phone, read_wav
from app.voice.providers.tts.base import CachedTTSEngine, TTSError, TTSUnavailable, normalize_persona
from app.voice.tts_tiers import TieredTTSCache

GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

#: Prebuilt voices the models accept (a caller may pass one directly).
GEMINI_VOICES = frozenset(
    {
        "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe",
        "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
        "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
        "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
    }
)


def decode_inline_audio(mime_type: str, data: bytes) -> bytes:
    """Gemini inline audio (L16 PCM or WAV) → 8 kHz μ-law."""
    if str(mime_type).startswith("audio/wav") or data[:4] == b"RIFF":
        pcm, rate = read_wav(data)
    else:
        pcm, rate = data, l16_rate(mime_type, 24000)
    return pcm16_to_phone(pcm, rate)


class GeminiTTS(CachedTTSEngine):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        cache: TieredTTSCache,
        model: str = "gemini-3.8-flash-lite-tts",
        fallback_model: str | None = "gemini-3.8-flash-tts",
        female_voice: str = "Kore",
        male_voice: str = "Charon",
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self.model = model
        self.models = [m for m in dict.fromkeys([model, fallback_model]) if m]
        self.female_voice = female_voice
        self.male_voice = male_voice
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            transport=transport,
        )

    def resolve_voice(self, *, voice: str | None, persona: str | None, language: str) -> str:
        if voice in GEMINI_VOICES:
            return str(voice)
        return self.female_voice if normalize_persona(persona) == "female" else self.male_voice

    def key_extra(self) -> str:
        return self.model

    @staticmethod
    def _body(text: str, voice: str) -> dict:
        return {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
            },
        }

    async def render(self, text: str, *, voice: str, language: str) -> bytes:
        last_error: TTSError = TTSError("gemini_tts_failed")
        for model in self.models:
            try:
                response = await self._client.post(GENERATE_URL.format(model=model), json=self._body(text, voice))
            except httpx.HTTPError as exc:
                last_error = TTSError(f"gemini_tts_{type(exc).__name__}")
                continue
            if response.status_code == 200:
                return await self._decode(response)
            message = f"gemini_tts_http_{response.status_code} ({model}): {response.text[:160]}"
            if response.status_code in (401, 403):
                raise TTSUnavailable(message)
            # 404 (model gone), 429 (this model's quota), 5xx: the next model may serve.
            last_error = TTSUnavailable(message) if response.status_code == 429 else TTSError(message)
        raise last_error

    async def _decode(self, response: httpx.Response) -> bytes:
        try:
            parts = response.json()["candidates"][0]["content"]["parts"]
            inline = next(part["inlineData"] for part in parts if "inlineData" in part)
            raw = base64.b64decode(inline["data"])
        except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
            raise TTSError(f"gemini_tts_no_audio: {response.text[:160]}") from exc
        if not raw:
            raise TTSError("gemini_tts_empty_audio")
        return await asyncio.to_thread(decode_inline_audio, str(inline.get("mimeType") or ""), raw)


__all__ = ["GEMINI_VOICES", "GeminiTTS", "decode_inline_audio"]
