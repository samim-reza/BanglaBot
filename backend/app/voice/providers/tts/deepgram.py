"""Deepgram Aura-2 text-to-speech (paid, low latency, natural English).

Deepgram renders μ-law 8 kHz with no container, so the bytes go straight to the
phone. Aura-2 speaks English (US, British, Australian, Filipino accents) and a
few European languages and Japanese — not Bangla, so a Bangla line skips it.
"""

from __future__ import annotations

import httpx

from app.voice.providers.tts.azure import is_neural_voice, locale_for_voice
from app.voice.providers.tts.base import CachedTTSEngine, TTSError, TTSUnavailable, normalize_persona, unavailable_status
from app.voice.tts_tiers import TieredTTSCache

SPEAK_URL = "https://api.deepgram.com/v1/speak"

#: English accent (from the account's Azure-style voice locale) → (female, male).
ACCENT_VOICES: dict[str, tuple[str, str]] = {
    "en-GB": ("aura-2-pandora-en", "aura-2-draco-en"),
    "en-IE": ("aura-2-pandora-en", "aura-2-draco-en"),
    "en-AU": ("aura-2-theia-en", "aura-2-hyperion-en"),
    "en-NZ": ("aura-2-theia-en", "aura-2-hyperion-en"),
}
#: Non-English Aura-2 voices: (female, male).
LANGUAGE_VOICES: dict[str, tuple[str, str]] = {
    "es": ("aura-2-celeste-es", "aura-2-javier-es"),
    "nl": ("aura-2-rhea-nl", "aura-2-sander-nl"),
    "fr": ("aura-2-agathe-fr", "aura-2-hector-fr"),
    "de": ("aura-2-viktoria-de", "aura-2-julius-de"),
    "it": ("aura-2-livia-it", "aura-2-elio-it"),
    "ja": ("aura-2-izanami-ja", "aura-2-fujin-ja"),
}


class DeepgramTTS(CachedTTSEngine):
    name = "deepgram"
    output_format = "mulaw8k"
    languages = frozenset({"en", *LANGUAGE_VOICES})

    def __init__(
        self,
        *,
        api_key: str,
        cache: TieredTTSCache,
        female_voice: str = "aura-2-thalia-en",
        male_voice: str = "aura-2-orion-en",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self.female_voice = female_voice
        self.male_voice = male_voice
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={"Authorization": f"Token {api_key}", "Content-Type": "application/json"},
            transport=transport,
        )

    def resolve_voice(self, *, voice: str | None, persona: str | None, language: str) -> str:
        if voice and str(voice).startswith("aura"):
            return str(voice)
        female = normalize_persona(persona) == "female"
        if language in LANGUAGE_VOICES:
            pair = LANGUAGE_VOICES[language]
        else:
            accent = locale_for_voice(str(voice)) if is_neural_voice(voice) else ""
            pair = ACCENT_VOICES.get(accent, (self.female_voice, self.male_voice))
        return pair[0] if female else pair[1]

    async def render(self, text: str, *, voice: str, language: str) -> bytes:
        try:
            response = await self._client.post(
                SPEAK_URL,
                params={"model": voice, "encoding": "mulaw", "sample_rate": 8000, "container": "none"},
                json={"text": text},
            )
        except httpx.HTTPError as exc:
            raise TTSError(f"deepgram_tts_{type(exc).__name__}") from exc
        if response.status_code == 200 and response.content:
            return response.content
        message = f"deepgram_tts_http_{response.status_code}: {response.text[:200]}"
        raise TTSUnavailable(message) if unavailable_status(response.status_code) else TTSError(message)


__all__ = ["DeepgramTTS"]
