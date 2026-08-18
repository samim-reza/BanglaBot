"""TTS cost lab — a dev-only page for watching the audio cache pay for itself.

Click once: the line is bought from ElevenLabs and the vendor reports what it
charged. Click again: the same line is served from disk, no request is made at
all, and the charge is zero by construction. That difference is the whole
argument for caching the bot's repeated lines.

Cost comes from the `character-cost` response header on the synthesis call
itself — exact, synchronous, and free. The earlier approach of reading
/v1/user/subscription before and after needed a `user_read` permission our
scoped key does not have, and added two network round-trips to the cache-hit
path, which is precisely the path that should touch nothing.

Never mounted in production (see main.py) — it is unauthenticated and spends
real money on every cache miss.
"""

import asyncio
import hashlib
import re
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from loguru import logger
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.api.routes.tts_lab_sim import run_simulation
from app.voice import audio_join
from app.voice.tts_cache import cache

router = APIRouter(prefix="/api/tts-lab", tags=["tts-lab"])

API_ROOT = "https://api.elevenlabs.io/v1"
# mp3 so the browser can play the result directly; live calls use pcm_16000.
OUTPUT_FORMAT = "mp3_44100_128"
# Slot mode works in raw PCM instead: fragments have to be trimmed, ramped and
# concatenated sample-wise, which you cannot do to an mp3 bitstream. 16 kHz
# matches what the call pipeline actually feeds the Twilio serializer.
SLOT_FORMAT = "pcm_16000"
SLOT_SAMPLE_RATE = 16000
PROVIDER = "elevenlabs"
_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_PAGE = Path(__file__).with_name("tts_lab.html")

# Rendered previews (joined / phone-banded WAVs) live in memory, not in the disk
# cache: they are derived artifacts, and mixing them in would corrupt the very
# clip count this page exists to demonstrate.
_RENDERS: dict[str, bytes] = {}
_RENDER_MAX = 40

# Characters this process has actually been charged, summed from the vendor's
# own header. Exact and instant, unlike the daily usage buckets.
_SESSION_CHARGED = [0]

DEFAULT_TEXT = "আসসালামু আলাইকুম, আমি কি শামীম রেজার সাথে কথা বলছি?"


class SpeakRequest(BaseModel):
    text: str = Field(default=DEFAULT_TEXT, min_length=1, max_length=1000)


class Fragment(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    # "slot" fragments carry per-order data (name, product, amount); "fixed"
    # ones are the frame around them. Labelling only — both cache identically.
    kind: str = Field(default="fixed", pattern="^(fixed|slot)$")


class SlotsRequest(BaseModel):
    fragments: list[Fragment] = Field(min_length=1, max_length=12)
    whole_text: str = Field(default="", max_length=1000)
    gap_ms: float = Field(default=180.0, ge=0, le=1000)
    phone_band: bool = False
    compare_whole: bool = True


def _usage() -> dict | None:
    """Vendor-side character totals, or None if unreadable.

    Buckets are daily and land roughly five seconds behind a request, so this
    is the running total — never the per-request charge. Kept out of the
    synthesis path for that reason and exposed on its own endpoint.
    """
    settings = get_settings()
    now = int(time.time() * 1000)
    try:
        response = httpx.get(
            f"{API_ROOT}/usage/character-stats",
            headers={"xi-api-key": settings.elevenlabs_api_key},
            params={"start_unix": now - 30 * 86_400_000, "end_unix": now},
            timeout=15,
        )
        response.raise_for_status()
        series = response.json().get("usage", {}).get("All") or []
        return {
            "today": int(series[-1]) if series else 0,
            "last_30d": int(sum(series)),
        }
    except Exception as exc:  # noqa: BLE001 — the readout is a nicety, not the test
        logger.warning(f"tts-lab: could not read ElevenLabs usage: {exc}")
        return None


def _synthesize(text: str, output_format: str = OUTPUT_FORMAT) -> tuple[bytes, int | None]:
    """Buy one line. Returns (audio, characters charged by the vendor)."""
    settings = get_settings()
    response = httpx.post(
        f"{API_ROOT}/text-to-speech/{settings.elevenlabs_voice_id}",
        params={"output_format": output_format},
        headers={"xi-api-key": settings.elevenlabs_api_key},
        json={"text": text, "model_id": settings.elevenlabs_model},
        timeout=60,
    )
    if response.status_code != 200:
        detail = response.text[:300]
        logger.error(f"tts-lab: ElevenLabs HTTP {response.status_code}: {detail}")
        raise HTTPException(status_code=502, detail=f"ElevenLabs {response.status_code}: {detail}")
    # Authoritative per-request charge; falls back to our own count if absent.
    try:
        cost = int(response.headers["character-cost"])
    except (KeyError, TypeError, ValueError):
        cost = None
    _SESSION_CHARGED[0] += cost if cost is not None else len(text)
    return response.content, cost


@router.get("", response_class=HTMLResponse)
async def page():
    return HTMLResponse(_PAGE.read_text(encoding="utf-8"))


@router.post("/speak")
async def speak(payload: SpeakRequest):
    settings = get_settings()
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY / VOICE_ID not configured")

    text = payload.text.strip()
    identity = dict(
        provider=PROVIDER,
        voice_id=settings.elevenlabs_voice_id,
        model=settings.elevenlabs_model,
        output_format=OUTPUT_FORMAT,
    )
    key = cache.key(text, **identity)

    started = time.perf_counter()
    # get_or_buy: a hit touches no network; concurrent misses on one text buy
    # once; purchases queue behind the vendor-concurrency gate.
    audio, cached, charged = await cache.get_or_buy(
        text, **identity, buy=lambda: asyncio.to_thread(_synthesize, text)
    )

    return {
        "cached": cached,
        "text": text,
        "chars": len(text),
        "voice_id": settings.elevenlabs_voice_id,
        "model": settings.elevenlabs_model,
        "credits_used": charged,
        "session_charged": _SESSION_CHARGED[0],
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "bytes": len(audio),
        "audio_url": f"/api/tts-lab/audio/{key}",
        "cache_key": key,
        "cache": cache.stats(),
    }


@router.get("/audio/{key}")
async def audio(key: str):
    # The key lands in a filesystem path — reject anything that is not a digest.
    if not _KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="bad key")
    clip = cache.get(key, touch=False)
    if clip is None:
        raise HTTPException(status_code=404, detail="not cached")
    return Response(content=clip, media_type="audio/mpeg")


def _fragment_identity() -> dict:
    settings = get_settings()
    return dict(
        provider=PROVIDER,
        voice_id=settings.elevenlabs_voice_id,
        model=settings.elevenlabs_model,
        output_format=SLOT_FORMAT,
    )


async def _buy(text: str, *, pin: bool = False) -> tuple[bytes, bool, int]:
    """Fragment PCM from disk or the vendor. Returns (audio, cached, charged).

    Fixed fragments are pinned: they are the phrase bank, and eviction should
    only ever chase the long tail of slot values.
    """
    return await cache.get_or_buy(
        text,
        **_fragment_identity(),
        buy=lambda: asyncio.to_thread(_synthesize, text, SLOT_FORMAT),
        pin=pin,
    )


def _render(pcm: bytes, phone_band: bool) -> dict:
    """Make PCM playable in a browser, optionally degraded to the phone band."""
    if phone_band:
        pcm = audio_join.to_phone_band(pcm, SLOT_SAMPLE_RATE)
    wav = audio_join.wav_bytes(pcm, SLOT_SAMPLE_RATE)
    key = hashlib.sha256(wav).hexdigest()
    if key not in _RENDERS and len(_RENDERS) >= _RENDER_MAX:
        _RENDERS.pop(next(iter(_RENDERS)))
    _RENDERS[key] = wav
    return {
        "audio_url": f"/api/tts-lab/render/{key}",
        "duration_ms": audio_join.duration_ms(pcm, SLOT_SAMPLE_RATE),
    }


@router.post("/slots")
async def slots(payload: SlotsRequest):
    """Synthesize a line as cached frame + variable slot, and price it against
    buying the whole sentence every call."""
    settings = get_settings()
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY / VOICE_ID not configured")

    started = time.perf_counter()
    reported: list[dict] = []
    pieces: list[bytes] = []
    charged_split = 0
    for fragment in payload.fragments:
        text = fragment.text.strip()
        audio, cached, charged = await _buy(text, pin=fragment.kind == "fixed")
        pieces.append(audio)
        charged_split += charged
        reported.append(
            {
                "text": text,
                "kind": fragment.kind,
                "chars": len(text),
                "cached": cached,
                "duration_ms": audio_join.duration_ms(audio, SLOT_SAMPLE_RATE),
            }
        )

    joined = audio_join.join(pieces, SLOT_SAMPLE_RATE, gap_ms=payload.gap_ms)
    split = {"charged_chars": charged_split, **_render(joined, payload.phone_band)}

    whole = None
    if payload.compare_whole:
        whole_text = (
            payload.whole_text.strip()
            or " ".join(f.text.strip() for f in payload.fragments)
        )
        audio, cached, charged = await _buy(whole_text)
        whole = {
            "text": whole_text,
            "chars": len(whole_text),
            "cached": cached,
            "charged_chars": charged,
            **_render(audio, payload.phone_band),
        }

    return {
        "fragments": reported,
        "split": split,
        "whole": whole,
        "gap_ms": payload.gap_ms,
        "phone_band": payload.phone_band,
        "credits_used": charged_split + (whole["charged_chars"] if whole else 0),
        "session_charged": _SESSION_CHARGED[0],
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "cache": cache.stats(),
    }


@router.get("/render/{key}")
async def render(key: str):
    if not _KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="bad key")
    wav = _RENDERS.get(key)
    if wav is None:
        raise HTTPException(status_code=404, detail="render expired — generate again")
    return Response(content=wav, media_type="audio/wav")


@router.get("/usage")
async def usage():
    """Vendor-side totals. Separate from synthesis so a cache hit stays offline."""
    return {"usage": _usage(), "session_charged": _SESSION_CHARGED[0], "cache": cache.stats()}


class SimRequest(BaseModel):
    calls_per_day: int = Field(default=2000, ge=100, le=20_000)
    days: int = Field(default=3, ge=1, le=5)
    cap_mb: int = Field(default=512, ge=64, le=8192)
    merchants: int = Field(default=150, ge=5, le=1000)
    wipe_last_day: bool = True
    seed: int = 7


@router.post("/simulate")
async def simulate(payload: SimRequest):
    """Run realistic multi-day traffic against a THROWAWAY cache instance.

    Synthetic vendor — spends nothing, never touches the real cache. 10k-call
    days take a minute or two each; the defaults answer quickly.
    """
    return await asyncio.to_thread(
        run_simulation,
        calls_per_day=payload.calls_per_day,
        days=payload.days,
        cap_mb=payload.cap_mb,
        merchants=payload.merchants,
        wipe_last_day=payload.wipe_last_day,
        seed=payload.seed,
    )


@router.post("/sweep")
async def sweep():
    """Reconcile disk and manifest; reports lost clips and their re-buy cost."""
    return await asyncio.to_thread(cache.sweep)


class RebuildRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=500)
    confirm: bool = False  # False = dry run: report what it WOULD cost


@router.post("/rebuild")
async def rebuild(payload: RebuildRequest):
    """Re-buy lost clips (hottest first). Dry-run unless confirm=true — every
    rebuilt clip is a real vendor charge."""
    rows = cache.missing_rows(provider=PROVIDER, limit=payload.limit)
    if not payload.confirm:
        return {
            "dry_run": True,
            "clips": len(rows),
            "chars_to_buy": sum(r["chars"] for r in rows),
            "hottest": [{"text": r["text"], "hits": r["hits"]} for r in rows[:10]],
        }

    async def buyer(row):
        return await asyncio.to_thread(_synthesize, row["text"], row["output_format"])

    result = await cache.rebuild({PROVIDER: buyer}, limit=payload.limit)
    return {"dry_run": False, **result, "cache": cache.stats()}


@router.post("/clear")
async def clear():
    _RENDERS.clear()
    return {"removed": cache.clear(), "cache": cache.stats()}
