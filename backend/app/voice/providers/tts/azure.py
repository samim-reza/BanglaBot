"""Azure Speech text-to-speech (paid, every language we speak, best Bangla).

Azure returns ``raw-8khz-8bit-mono-mulaw`` directly, which is exactly what a
phone media stream plays, so no resampling happens on the call path. The voice
is chosen per *persona* (female / male) and per language, so a bilingual
merchant keeps one consistent "person" whether the customer speaks Bangla or
English. Cache keys are unchanged from the pre-provider ``voice/tts.py`` so
clips already on disk keep hitting.
"""

from __future__ import annotations

import asyncio
from xml.sax.saxutils import escape

import httpx

from app.voice.languages import BANGLA, ENGLISH, normalize_language
from app.voice.providers.tts.base import (
    DEFAULT_PERSONA,
    CachedTTSEngine,
    TTSError,
    TTSUnavailable,
    normalize_persona,
    unavailable_status,
)
from app.voice.tts_tiers import TieredTTSCache

PROVIDER = "azure"
OUTPUT_FORMAT = "raw-8khz-8bit-mono-mulaw"

#: One "person" per persona, spoken through the right neural voice per language.
VOICE_PERSONAS: dict[str, dict[str, str]] = {
    "female": {ENGLISH: "en-US-AvaNeural", BANGLA: "bn-BD-NabanitaNeural"},
    "male": {ENGLISH: "en-US-AndrewNeural", BANGLA: "bn-BD-PradeepNeural"},
}
#: English accents by locale (the account's region picks one): (female, male).
ENGLISH_ACCENTS: dict[str, tuple[str, str]] = {
    "en-US": ("en-US-AvaNeural", "en-US-AndrewNeural"),
    "en-GB": ("en-GB-SoniaNeural", "en-GB-RyanNeural"),
    "en-CA": ("en-CA-ClaraNeural", "en-CA-LiamNeural"),
    "en-AU": ("en-AU-NatashaNeural", "en-AU-WilliamNeural"),
    "en-NZ": ("en-NZ-MollyNeural", "en-NZ-MitchellNeural"),
    "en-IE": ("en-IE-EmilyNeural", "en-IE-ConnorNeural"),
    "en-IN": ("en-IN-NeerjaNeural", "en-IN-PrabhatNeural"),
    "en-SG": ("en-SG-LunaNeural", "en-SG-WayneNeural"),
    "en-ZA": ("en-ZA-LeahNeural", "en-ZA-LukeNeural"),
    "en-NG": ("en-NG-EzinneNeural", "en-NG-AbeoNeural"),
}


def voice_for(persona: str, language: str | None, accent: str | None = None) -> str:
    """Neural voice for a persona in a language; English follows the account's accent."""
    persona = normalize_persona(persona)
    lang = normalize_language(language)
    if lang == ENGLISH and accent in ENGLISH_ACCENTS:
        female, male = ENGLISH_ACCENTS[accent]  # type: ignore[index]
        return female if persona == "female" else male
    voices = VOICE_PERSONAS.get(persona, VOICE_PERSONAS[DEFAULT_PERSONA])
    return voices.get(lang, voices[BANGLA])


def is_neural_voice(voice: str | None) -> bool:
    """``en-GB-SoniaNeural`` style names (Azure and edge-tts share them)."""
    return bool(voice) and str(voice).endswith("Neural") and str(voice).count("-") >= 2


def locale_for_voice(voice: str) -> str:
    parts = voice.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else "en-US"


class AzureTTS(CachedTTSEngine):
    name = PROVIDER
    output_format = OUTPUT_FORMAT

    def __init__(
        self,
        *,
        key: str,
        region: str,
        cache: TieredTTSCache,
        speaking_rate: str = "0%",
        timeout_seconds: float = 12.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self.region = region
        self.speaking_rate = speaking_rate
        self.endpoint = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                "User-Agent": "banglabot-voice-agent",
            },
            transport=transport,
        )

    def resolve_voice(self, *, voice: str | None, persona: str | None, language: str) -> str:
        if is_neural_voice(voice):
            return str(voice)
        return voice_for(persona or DEFAULT_PERSONA, language)

    def key_language(self, voice: str, language: str) -> str:
        return locale_for_voice(voice)

    def key_extra(self) -> str:
        return self.speaking_rate

    def _ssml(self, text: str, *, voice: str) -> str:
        locale = locale_for_voice(voice)
        body = escape(" ".join(str(text or "").split()))
        if self.speaking_rate and self.speaking_rate not in {"0%", "+0%", "default", "medium"}:
            body = f'<prosody rate="{escape(self.speaking_rate)}">{body}</prosody>'
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">'
            f'<voice name="{voice}">{body}</voice></speak>'
        )

    async def render(self, text: str, *, voice: str, language: str) -> bytes:
        ssml = self._ssml(text, voice=voice).encode("utf-8")
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                response = await self._client.post(self.endpoint, content=ssml)
            except httpx.HTTPError as exc:
                last_error = TTSError(f"azure_tts_{type(exc).__name__}")
            else:
                if response.status_code == 200 and response.content:
                    return response.content
                message = f"azure_tts_http_{response.status_code}: {response.text[:200]}"
                if response.status_code in (401, 403):
                    raise TTSUnavailable(message)
                last_error = TTSUnavailable(message) if unavailable_status(response.status_code) else TTSError(message)
                if response.status_code < 500 and response.status_code != 429:
                    break
            await asyncio.sleep(0.2 * attempt)
        raise last_error or TTSError("azure_tts_failed")


__all__ = ["ENGLISH_ACCENTS", "OUTPUT_FORMAT", "VOICE_PERSONAS", "AzureTTS", "is_neural_voice", "locale_for_voice", "voice_for"]
