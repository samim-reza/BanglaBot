"""TTS: ElevenLabs only (Bengali via eleven_v3 / multilingual models).

A cached startup probe warns loudly if the key/plan can't synthesize —
on ElevenLabs' free plan the API returns 402 and calls would be silent.
"""

import time

import aiohttp
import httpx
from loguru import logger
from pipecat.services.elevenlabs.tts import ElevenLabsHttpTTSService
from pipecat.transcriptions.language import Language

from app.core.config import get_settings

# Cached ElevenLabs health probe: (checked_at, usable)
_el_probe: tuple[float, bool] | None = None
_EL_PROBE_TTL = 300  # re-check every 5 minutes


def elevenlabs_usable() -> bool:
    """Probe a tiny synthesis so a broken key/plan is visible in the logs."""
    global _el_probe
    if _el_probe and time.time() - _el_probe[0] < _EL_PROBE_TTL:
        return _el_probe[1]
    settings = get_settings()
    try:
        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}",
            params={"output_format": "pcm_16000"},
            headers={"xi-api-key": settings.elevenlabs_api_key},
            json={"text": "ঠিক আছে।", "model_id": settings.elevenlabs_model},
            timeout=10,
        )
        usable = response.status_code == 200
        if not usable:
            logger.error(
                f"ElevenLabs TTS NOT usable (HTTP {response.status_code}): "
                f"{response.text[:200]} — calls will have no voice!"
            )
    except Exception as e:
        usable = False
        logger.error(f"ElevenLabs probe failed: {e}")
    _el_probe = (time.time(), usable)
    return usable


def create_tts_service(tier_key: str | None = None):
    """Build the TTS service for a call.

    With a tier key (the merchant's chosen voice rank) the tier catalog picks
    provider + model; without one the TTS_PROVIDER env decides (legacy/admin
    override). A tier pointing at an unconfigured provider falls back to the
    standard tier so calls never go silent.
    """
    from app.services import voice_tiers

    settings = get_settings()

    provider = settings.tts_provider.lower()
    model_override: str | None = None
    if tier_key:
        tier = voice_tiers.get_tier(tier_key)
        if tier.mode == "static":
            # Static calls never open a media stream; if we get here anyway,
            # run the default AI voice rather than failing the call.
            tier = voice_tiers.get_tier(voice_tiers.DEFAULT_TIER_KEY)
        if tier.provider == "elevenlabs" and not settings.elevenlabs_api_key:
            logger.warning(
                f"Voice tier '{tier.key}' needs ElevenLabs but no key is set — "
                "falling back to the standard tier"
            )
            tier = voice_tiers.get_tier(voice_tiers.DEFAULT_TIER_KEY)
        provider = tier.provider
        model_override = tier.model

    if provider == "gemini":
        from pipecat.services.google.tts import GeminiTTSService

        return GeminiTTSService(
            api_key=settings.gemini_api_key,
            model=model_override or settings.gemini_tts_model,
            voice_id=settings.gemini_tts_voice,
            sample_rate=24000,  # Gemini always outputs 24kHz; serializer resamples to 8k
            # Without this the 24kHz audio is tagged with the pipeline's 8kHz rate and
            # plays ~3x slow/deep on the phone.
            params=GeminiTTSService.InputParams(
                language=Language.BN,
                prompt=(
                    "Speak in natural, fluent Bangladeshi Bengali (bn-BD) like a native "
                    "speaker from Dhaka — warm, polite female customer-care tone."
                ),
            ),
        )

    if provider == "google":
        from pipecat.services.google.tts import GoogleTTSService

        return GoogleTTSService(
            credentials_path=settings.google_credentials_path,
            voice_id=settings.google_tts_voice,
            params=GoogleTTSService.InputParams(language=Language.BN_IN),
        )

    elevenlabs_usable()  # log a clear error early if the key/plan is broken
    # HTTP streaming, not the websocket service: eleven_v3 rejects the
    # stream-input websocket with HTTP 403 (verified 2026-08-16).
    return ElevenLabsHttpTTSService(
        api_key=settings.elevenlabs_api_key,
        voice_id=settings.elevenlabs_voice_id,
        model=model_override or settings.elevenlabs_model,
        aiohttp_session=aiohttp.ClientSession(),
        params=ElevenLabsHttpTTSService.InputParams(language=Language.BN),
    )
