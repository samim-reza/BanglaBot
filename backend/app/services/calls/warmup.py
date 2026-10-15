"""Pre-call warm-up: synthesize the greeting and scripted lines while the phone rings."""

from __future__ import annotations

import asyncio

import structlog

from app.core.config import get_settings
from app.core.regions import region_of
from app.flows.context import DIRECTION_OUTBOUND, CallContext
from app.models import Merchant
from app.verticals import flow_for, vertical_for
from app.voice import prepared

logger = structlog.get_logger(__name__)


async def _warm_call_lines(ctx: CallContext, merchant: Merchant) -> None:
    """Synthesize the greeting and every scripted line while the phone rings."""
    try:
        from app.voice.audio import sentence_units
        from app.voice.languages import ack_lines, normalize_language
        from app.voice.llm import warm_connection
        from app.voice.tts import get_tts_for, normalize_persona, tts_configured, voice_for

        settings = get_settings()
        asyncio.create_task(warm_connection(settings.openai_api_key))
        language = normalize_language(merchant.language)
        if not tts_configured(language):
            return
        tts = get_tts_for(language)
        flow = flow_for(merchant, ctx.direction)
        persona = normalize_persona(merchant.voice_persona)
        voice = voice_for(persona, language, region_of(merchant).accent)
        lines = sentence_units(list(flow.prefetch_lines(ctx, language)) + list(ack_lines(language)))
        await tts.warm(lines, language=language, persona=persona, voice=voice)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("call_line_warm_failed", error=str(exc))
    # E-commerce: the confirmation question is composed by the model now, while
    # the phone rings, so the first caller turn is answered from the cache.
    if ctx.record is not None and vertical_for(merchant).key == "ecommerce" and ctx.direction == DIRECTION_OUTBOUND:
        try:
            await prepared.prepare_call_lines(ctx.record, merchant)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("call_line_prepare_failed", error=str(exc))
