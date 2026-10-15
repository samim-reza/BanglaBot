"""The local open-source speech server (``speech/``, laptop GPU) as a TTS provider.

``POST {SPEECH_SERVER_URL}/tts`` returns raw 8 kHz μ-law. The server picks its
own voice per persona, so the persona (not an Azure voice name) is sent and
keyed. A cached health probe keeps a sleeping laptop from stalling a call.
"""

from __future__ import annotations

import httpx

from app.voice.providers.stt.health import http_base, speech_server_healthy
from app.voice.providers.tts.base import CachedTTSEngine, TTSError, TTSUnavailable, normalize_persona, unavailable_status
from app.voice.tts_tiers import TieredTTSCache


class LocalTTS(CachedTTSEngine):
    name = "local"

    def __init__(
        self,
        *,
        base_url: str,
        cache: TieredTTSCache,
        key: str | None = None,
        timeout_seconds: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
        probe_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self.base_url = http_base(base_url)
        self.key = key
        self._probe_transport = probe_transport
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=1.0),
            headers={"X-Speech-Key": key} if key else {},
            transport=transport,
        )

    def resolve_voice(self, *, voice: str | None, persona: str | None, language: str) -> str:
        if voice and str(voice).startswith("local:"):
            return str(voice)[len("local:") :]
        return normalize_persona(persona)

    async def render(self, text: str, *, voice: str, language: str) -> bytes:
        if not await speech_server_healthy(self.base_url, self.key, transport=self._probe_transport):
            raise TTSUnavailable("local_speech_server_down")
        try:
            response = await self._client.post(
                f"{self.base_url}/tts",
                json={"text": text, "voice": voice, "language": language, "format": "ulaw8k"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise TTSUnavailable(f"local_tts_{type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise TTSError(f"local_tts_{type(exc).__name__}") from exc
        if response.status_code == 200 and response.content:
            return response.content
        message = f"local_tts_http_{response.status_code}: {response.text[:160]}"
        raise TTSUnavailable(message) if unavailable_status(response.status_code) or response.status_code == 503 else TTSError(message)


__all__ = ["LocalTTS"]
