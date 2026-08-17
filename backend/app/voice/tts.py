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


def _credentials_missing(provider: str) -> bool:
    """True when the provider a tier points at has no key/credentials configured."""
    settings = get_settings()
    return (
        (provider == "azure" and not settings.azure_speech_key)
        or (provider == "elevenlabs" and not settings.elevenlabs_api_key)
        or (provider == "gemini" and not settings.gemini_api_key)
        or (provider == "google" and not settings.google_credentials_path)
    )


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
        if _credentials_missing(tier.provider):
            fallback = voice_tiers.get_tier(voice_tiers.DEFAULT_TIER_KEY)
            logger.warning(
                f"Voice tier '{tier.key}' needs {tier.provider} but no key is set — "
                f"falling back to '{fallback.key}'"
            )
            tier = fallback
        if _credentials_missing(tier.provider):
            # The default tier is unconfigured too — let TTS_PROVIDER decide
            # rather than handing a service an empty API key.
            logger.error(
                f"Default voice tier '{tier.key}' also has no {tier.provider} key — "
                f"falling back to TTS_PROVIDER={provider}"
            )
        else:
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

    if provider == "azure":
        from pipecat.services.azure.tts import AzureTTSService

        # Either a plain neural voice ("bn-BD-PradeepNeural") or a Dragon HD
        # Omni one ("bn-IN-Tanishaa:DragonHDOmniLatestNeural"). HD voices reject
        # some SSML, so never set style/prosody params here.
        voice = model_override or settings.azure_tts_voice
        # bn-IN-* is Indian Bengali; bn-BD-* (and the default) is Bangladeshi.
        language = Language.BN_IN if voice.startswith("bn-IN") else Language.BN_BD
        return AzureTTSService(
            api_key=settings.azure_speech_key,
            region=settings.azure_speech_region,
            # Azure honours the rate we ask for, so pick 16k for a cleaner
            # signal and let the Twilio serializer resample down to 8k.
            sample_rate=16000,
            settings=AzureTTSService.Settings(voice=voice, language=language),
        )

    if provider == "google":
        from pipecat.services.google.tts import GoogleTTSService

        # Chirp 3 HD voices (bn-IN only — Google has no bn-BD locale).
        return GoogleTTSService(
            credentials_path=settings.google_credentials_path,
            voice_id=model_override or settings.google_tts_voice,
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
