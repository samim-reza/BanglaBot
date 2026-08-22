"""Opening audio in the merchant's own TTS voice, served to Twilio <Play>.

The opening must reach the caller within ~2 seconds of answering AND sound
like the same agent that continues the call. Twilio <Say> is instant but uses
a different (Google) voice; the media-stream TTS is the right voice but pays
pipeline start-up latency. This module closes the gap:

- The greeting is synthesized once through the provider's plain REST API into
  the shared TTS audio cache — prefetched while the phone is still RINGING —
  and the TwiML <Play>s it before <Connect><Stream>. No pipeline involved.
- The flow's first question is prefetched into the same cache under the SAME
  identity the live pipeline service uses, so the agent's opening
  TTSSpeakFrame replays from disk instead of a vendor round-trip.

One-shot REST synthesis exists for azure and elevenlabs. Tiers on other
providers (gemini/google) fall back to Twilio <Say> for the greeting only —
same behavior, different voice.
"""

from xml.sax.saxutils import escape

import httpx
from loguru import logger

from app.core.config import get_settings
from app.flows import get_flow
from app.models import Merchant, Order
from app.voice import audio_join
from app.voice.tts_cache import cache

# Matches the sample rate the live Azure pipeline service is built with, so
# opening clips and live-call clips share cache entries.
_AZURE_RATE = 16000
# ElevenLabs greeting clips are only used by <Play>; 16k is its cleanest PCM.
_EL_RATE = 16000


def _resolve(merchant: Merchant):
    """(provider, voice_id, model) for one-shot synthesis, or None.

    Mirrors create_tts_service's tier resolution (static → default tier,
    missing credentials → default tier) without constructing a service.
    """
    from app.services import voice_tiers
    from app.voice.tts import _credentials_missing

    settings = get_settings()
    tier = voice_tiers.get_tier(merchant.voice_tier or voice_tiers.DEFAULT_TIER_KEY)
    if tier.mode == "static":
        return None
    if _credentials_missing(tier.provider):
        tier = voice_tiers.get_tier(voice_tiers.DEFAULT_TIER_KEY)
        if _credentials_missing(tier.provider):
            return None
    if tier.provider == "azure":
        voice = tier.model or settings.azure_tts_voice
        # Identity matches tts.create_tts_service's azure _build call exactly.
        return ("azure", voice, "")
    if tier.provider == "elevenlabs":
        return ("elevenlabs", settings.elevenlabs_voice_id, tier.model or settings.elevenlabs_model)
    return None  # gemini/google have no one-shot REST path here — <Say> fallback


def supported(merchant: Merchant) -> bool:
    """True when the greeting can be served in the merchant's own agent voice."""
    return _resolve(merchant) is not None


def _texts(order: Order, merchant: Merchant) -> tuple[str, str]:
    """(greeting, first question) — must match what the call actually speaks."""
    from app.voice.prompts import opening_greeting

    flow = get_flow(merchant.service_type)
    return opening_greeting(merchant), flow.opening_question_bn(order, merchant)


async def _buy_azure(text: str, voice: str) -> tuple[bytes, int | None]:
    settings = get_settings()
    lang = "bn-IN" if voice.startswith("bn-IN") else "bn-BD"
    ssml = (
        f'<speak version="1.0" xml:lang="{lang}">'
        f'<voice name="{voice}">{escape(text)}</voice></speak>'
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://{settings.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={
                "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "raw-16khz-16bit-mono-pcm",
                "User-Agent": "BanglaBot",
            },
            content=ssml.encode("utf-8"),
        )
    response.raise_for_status()
    return response.content, None


async def _buy_elevenlabs(text: str, voice_id: str, model: str, rate: int) -> tuple[bytes, int | None]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            params={"output_format": f"pcm_{rate}"},
            headers={"xi-api-key": settings.elevenlabs_api_key},
            json={"text": text, "model_id": model},
        )
    response.raise_for_status()
    try:
        cost = int(response.headers["character-cost"])
    except (KeyError, TypeError, ValueError):
        cost = None
    return response.content, cost


async def _pcm(text: str, provider: str, voice_id: str, model: str, rate: int) -> bytes:
    """One clip from disk or the vendor, through the shared single-flight cache."""
    if provider == "azure":
        buy = lambda: _buy_azure(text, voice_id)  # noqa: E731
    else:
        buy = lambda: _buy_elevenlabs(text, voice_id, model, rate)  # noqa: E731
    audio, was_cached, _cost = await cache.get_or_buy(
        text,
        provider=provider,
        voice_id=voice_id,
        model=model,
        output_format=f"pcm_{rate}",
        buy=buy,
    )
    if not was_cached:
        logger.info(f"opening: bought {provider} clip ({len(text)} chars)")
    return audio


def _rate_for(provider: str) -> int:
    return _AZURE_RATE if provider == "azure" else _EL_RATE


async def greeting_wav(order: Order, merchant: Merchant) -> bytes | None:
    """The greeting as a WAV in the merchant's agent voice, for <Play>."""
    resolved = _resolve(merchant)
    if not resolved:
        return None
    provider, voice_id, model = resolved
    rate = _rate_for(provider)
    greeting, _question = _texts(order, merchant)
    try:
        pcm = await _pcm(greeting, provider, voice_id, model, rate)
    except Exception as exc:  # noqa: BLE001 — Twilio skips a failed <Play>
        logger.error(f"opening: greeting synthesis failed ({provider}): {exc}")
        return None
    return audio_join.wav_bytes(pcm, rate)


async def prefetch(order_id: str) -> None:
    """Warm the cache during ringing: greeting (for <Play>) + first question
    (for the pipeline's opening TTSSpeakFrame). Fire-and-forget; never raises."""
    try:
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            order = await db.get(Order, order_id)
            merchant = await db.get(Merchant, order.merchant_id) if order else None
        if not order or not merchant:
            return
        resolved = _resolve(merchant)
        if not resolved:
            return
        provider, voice_id, model = resolved
        rate = _rate_for(provider)
        greeting, question = _texts(order, merchant)
        await _pcm(greeting, provider, voice_id, model, rate)
        # The question replays through the live pipeline service, whose cache
        # identity uses the pipeline sample rate: azure is built at 16k; the
        # elevenlabs service inherits the 8k pipeline rate.
        question_rate = _AZURE_RATE if provider == "azure" else 8000
        await _pcm(question, provider, voice_id, model, question_rate)
        logger.info(f"opening: prefetched greeting+question for order {order_id}")
    except Exception as exc:  # noqa: BLE001 — prefetch must never break a call
        logger.warning(f"opening: prefetch failed for order {order_id}: {exc}")
