"""Azure Speech text-to-speech for the phone line, with the LRU cache in front.

Azure returns ``raw-8khz-8bit-mono-mulaw`` directly, which is exactly what a
Twilio Media Stream plays, so no resampling happens on the call path. The
voice is chosen per *persona* (female / male) and per language, so a bilingual
merchant keeps one consistent "person" whether the customer speaks Bangla or
English.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable
from xml.sax.saxutils import escape

import httpx
import structlog

from app.core.config import get_settings
from app.voice.languages import BANGLA, ENGLISH, normalize_language
from app.voice.tts_cache import TTSCache

logger = structlog.get_logger(__name__)

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
DEFAULT_PERSONA = "female"


def normalize_persona(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in VOICE_PERSONAS else DEFAULT_PERSONA


def voice_for(persona: str, language: str | None, accent: str | None = None) -> str:
    """Neural voice for a persona in a language; English follows the account's accent."""
    persona = normalize_persona(persona)
    lang = normalize_language(language)
    if lang == ENGLISH and accent in ENGLISH_ACCENTS:
        female, male = ENGLISH_ACCENTS[accent]  # type: ignore[index]
        return female if persona == "female" else male
    voices = VOICE_PERSONAS.get(persona, VOICE_PERSONAS[DEFAULT_PERSONA])
    return voices.get(lang, voices[BANGLA])


def _locale_for_voice(voice: str) -> str:
    parts = voice.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else "en-US"


class TTSError(RuntimeError):
    pass


class AzureSpeechTTS:
    def __init__(
        self,
        *,
        key: str,
        region: str,
        cache: TTSCache,
        speaking_rate: str = "0%",
        timeout_seconds: float = 12.0,
    ) -> None:
        self.key = key
        self.region = region
        self.cache = cache
        self.speaking_rate = speaking_rate
        self.endpoint = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                "User-Agent": "banglabot-confirmation-agent",
            },
        )
        self.synth_count = 0
        self.synth_chars = 0
        self.synth_seconds = 0.0

    def cache_key(self, text: str, *, voice: str) -> str:
        return TTSCache.make_key(
            provider=PROVIDER,
            voice=voice,
            language=_locale_for_voice(voice),
            output_format=OUTPUT_FORMAT,
            text=text,
            extra=self.speaking_rate,
        )

    def _ssml(self, text: str, *, voice: str) -> str:
        locale = _locale_for_voice(voice)
        body = escape(" ".join(str(text or "").split()))
        if self.speaking_rate and self.speaking_rate not in {"0%", "+0%", "default", "medium"}:
            body = f'<prosody rate="{escape(self.speaking_rate)}">{body}</prosody>'
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">'
            f'<voice name="{voice}">{body}</voice></speak>'
        )

    async def _request(self, ssml: str) -> bytes:
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                response = await self._client.post(self.endpoint, content=ssml.encode("utf-8"))
                if response.status_code == 200 and response.content:
                    return response.content
                last_error = TTSError(f"azure_tts_http_{response.status_code}: {response.text[:200]}")
                if response.status_code < 500 and response.status_code != 429:
                    break
            except httpx.HTTPError as exc:
                last_error = exc
            await asyncio.sleep(0.2 * attempt)
        raise TTSError(str(last_error or "azure_tts_failed"))

    async def synthesize(
        self,
        text: str,
        *,
        language: str | None = None,
        persona: str | None = None,
        voice: str | None = None,
    ) -> bytes:
        """Return μ-law 8 kHz audio for ``text``; cached lines never hit Azure."""
        text = " ".join(str(text or "").split())
        if not text:
            return b""
        voice = voice or voice_for(persona or DEFAULT_PERSONA, language)
        key = self.cache_key(text, voice=voice)
        cached = await self.cache.aget(key)
        if cached is not None:
            return cached
        started = time.monotonic()
        audio = await self._request(self._ssml(text, voice=voice))
        elapsed = time.monotonic() - started
        self.synth_count += 1
        self.synth_chars += len(text)
        self.synth_seconds += elapsed
        await self.cache.aput(key, audio)
        await logger.adebug("azure_tts_synthesized", voice=voice, chars=len(text), ms=int(elapsed * 1000), bytes=len(audio))
        return audio

    async def warm(self, lines: Iterable[str], *, language: str | None, persona: str | None, voice: str | None = None) -> int:
        """Pre-synthesize fixed lines (greeting, still-there, goodbye…) before they are needed."""
        count = 0
        voice = voice or voice_for(persona or DEFAULT_PERSONA, language)
        for line in lines:
            if not line:
                continue
            try:
                if self.cache.contains(self.cache_key(line, voice=voice)):
                    continue
                await self.synthesize(line, language=language, persona=persona, voice=voice)
                count += 1
            except TTSError as exc:
                await logger.awarning("azure_tts_warm_failed", error=str(exc), preview=str(line)[:60])
        return count

    def stats(self) -> dict[str, Any]:
        return {
            "synth_count": self.synth_count,
            "synth_chars": self.synth_chars,
            "synth_seconds": round(self.synth_seconds, 3),
            "cache": self.cache.stats(),
        }

    async def aclose(self) -> None:
        await self._client.aclose()


_tts: AzureSpeechTTS | None = None


def get_tts() -> AzureSpeechTTS:
    """Process-wide TTS client + cache (one keepalive pool, one LRU index)."""
    global _tts
    if _tts is None:
        settings = get_settings()
        if not settings.azure_speech_key:
            raise TTSError("AZURE_SPEECH_KEY is not configured")
        cache = TTSCache(
            settings.tts_cache_dir,
            max_entries=settings.tts_cache_max_entries,
            max_bytes=int(settings.tts_cache_max_mb) * 1024 * 1024,
        )
        _tts = AzureSpeechTTS(
            key=settings.azure_speech_key,
            region=settings.azure_speech_region,
            cache=cache,
            speaking_rate=settings.tts_speaking_rate,
        )
    return _tts


def tts_configured() -> bool:
    return bool(get_settings().azure_speech_key)
