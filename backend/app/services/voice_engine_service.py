"""The voice engine at a glance (admin): provider chains, free-quota state, caches, speech server, and quick tests."""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.pipeline.compiled import PIPELINES
from app.voice.codec import ulaw_to_pcm16, wav_bytes
from app.voice.providers.llm.endpoints import resolve_links
from app.voice.providers.llm.quota import QUOTAS
from app.voice.providers.settings import get_provider_settings, parse_chain
from app.voice.providers.stt import configured_providers as stt_configured
from app.voice.providers.stt import stt_chain_for
from app.voice.providers.stt.health import http_base
from app.voice.providers.tts import configured_providers as tts_configured
from app.voice.providers.tts import tts_chain_for, tts_stats


async def speech_server_status() -> dict[str, Any]:
    pset = get_provider_settings()
    if not pset.speech_server_url:
        return {"configured": False}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            response = await client.get(f"{http_base(pset.speech_server_url)}/health")
        body = response.json() if response.status_code == 200 else {}
        return {"configured": True, "up": response.status_code == 200, "ms": int((time.monotonic() - started) * 1000), **body}
    except (httpx.HTTPError, ValueError):
        return {"configured": True, "up": False}


async def status() -> dict[str, Any]:
    pset = get_provider_settings()
    quotas = QUOTAS.snapshot()
    links = resolve_links(allow_paid=True)
    return {
        "llm": {
            "allow_paid": pset.llm_allow_paid,
            "prompt_profile": pset.llm_prompt_profile,
            "chain": [
                {"key": link.key, "provider": link.provider, "model": link.model, "paid": link.paid, "usable": pset.llm_allow_paid or not link.paid, **quotas.get(link.key, {"available": True})}
                for link in links
            ],
            "unconfigured": [entry for entry in parse_chain(pset.llm_chain) if entry not in {link.key for link in links}],
        },
        "stt": {lang: {"chain": stt_chain_for(lang), "ready": stt_configured(lang)} for lang in ("en",)},
        "tts": {
            **{lang: {"chain": tts_chain_for(lang), "ready": tts_configured(lang)} for lang in ("en",)},
            "stats": tts_stats(),
        },
        "speech_server": await speech_server_status(),
        "pipelines": PIPELINES.stats(),
        "keys": {
            "groq": bool(pset.groq_api_key),
            "gemini": bool(pset.gemini_api_key),
            "deepgram": bool(pset.deepgram_api_key),
            "openai": bool(get_settings().openai_api_key),
            "azure": bool(get_settings().azure_speech_key),
            "shared_audio_cache": bool(pset.supabase_url and pset.supabase_secret_key),
        },
    }


async def test_tts(text: str, language: str) -> dict[str, Any]:
    from app.voice.providers.tts import get_tts_for

    engine = get_tts_for(language)
    started = time.monotonic()
    audio, provider, source = await engine.synthesize_ex(text, language=language)
    wav = wav_bytes(ulaw_to_pcm16(audio), 8000)
    return {
        "ms": int((time.monotonic() - started) * 1000),
        "bytes": len(audio),
        "seconds": round(len(audio) / 8000, 2),
        "provider": provider,
        "source": source,  # "synth" (paid) or a cache tier
        "audio_wav_b64": base64.b64encode(wav).decode("ascii"),
        "stats": engine.stats(),
    }


async def test_llm() -> dict[str, Any]:
    from app.voice.providers.llm import llm_for_call

    llm = llm_for_call(flow_key="admin:test", max_output_tokens=40)
    started = time.monotonic()
    reply = await llm.complete([{"role": "system", "content": "Reply with one short friendly sentence."}, {"role": "user", "content": "Say hello to the admin."}])
    return {"ms": int((time.monotonic() - started) * 1000), "model": llm.stats()["model"], "provider": llm.stats()["provider"], "text": reply.content[:200]}


__all__ = ["speech_server_status", "status", "test_llm", "test_tts"]
