"""Loads every model once and runs inference off the event loop (one worker per model)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TypeVar

import numpy as np

from .codec import Float32Array, float_to_pcm16, float_to_ulaw, resample
from .config import Settings
from .device import gpu_memory_mb, preload_cuda_libs, resolve_device
from .models import ModelPaths
from .segmenter import SegmenterConfig, UtteranceSegmenter
from .stt import ParakeetEngine, SttResult
from .tts import SAMPLE_RATE as TTS_RATE
from .tts import KokoroEngine, VoiceChoice
from .vad import SileroVad

log = logging.getLogger("speech.engines")
T = TypeVar("T")

FORMATS = {"ulaw8k": "audio/basic", "pcm16_24k": "audio/L16;rate=24000"}


@dataclass
class Engines:
    settings: Settings
    stt: ParakeetEngine
    tts: KokoroEngine
    vad: SileroVad
    started_at: float = field(default_factory=time.time)
    vram_mb: int | None = None
    _stt_pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(1, thread_name_prefix="stt"))
    _tts_pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(1, thread_name_prefix="tts"))

    @classmethod
    def load(cls, settings: Settings) -> Engines:
        """Blocking: pick devices, load + warm up all models."""
        paths = ModelPaths(settings.models_dir)
        missing = paths.missing([])
        if missing or not any(paths.parakeet_ready(p) for p in ("fp16", "int8", "fp32")):
            raise FileNotFoundError(f"models missing in {paths.root}: run `uv run python scripts/download_models.py`")
        preload_cuda_libs()
        stt_device = resolve_device(settings.engine_device("stt"), paths.silero)
        tts_device = resolve_device(settings.engine_device("tts"), paths.silero)
        vad = SileroVad(paths.silero)
        stt = ParakeetEngine(paths, stt_device, settings.stt_precision, settings.gpu_mem_mb_stt)
        tts = KokoroEngine(paths, tts_device, settings.gpu_mem_mb_tts, settings.voice_female, settings.voice_male)
        started = time.perf_counter()
        stt.warmup()
        tts.warmup()
        blank = np.zeros(2400, dtype=np.float32)  # build the resampling filters once
        resample(blank, TTS_RATE, 8000)
        resample(blank, 8000, 16000)
        log.info("warm-up done in %.1fs", time.perf_counter() - started)
        engines = cls(settings=settings, stt=stt, tts=tts, vad=vad)
        engines.vram_mb = gpu_memory_mb() if "cuda" in (stt.device, tts.device) else 0
        return engines

    @property
    def device(self) -> str:
        return "cuda" if "cuda" in (self.stt.device, self.tts.device) else "cpu"

    def segmenter(self, silence_ms: int) -> UtteranceSegmenter:
        s = self.settings
        config = SegmenterConfig(
            threshold=s.vad_threshold,
            neg_threshold=s.vad_neg_threshold,
            silence_ms=silence_ms,
            min_speech_ms=s.min_speech_ms,
            pre_roll_ms=s.pre_roll_ms,
            max_utterance_s=s.max_utterance_s,
        )
        return UtteranceSegmenter(self.vad.stream(8000), config)

    async def _run(self, pool: ThreadPoolExecutor, fn: Callable[..., T], *args: object) -> T:
        return await asyncio.get_running_loop().run_in_executor(pool, fn, *args)

    async def transcribe(self, audio: Float32Array, sample_rate: int) -> SttResult:
        return await self._run(self._stt_pool, self.stt.transcribe, audio, sample_rate)

    async def run_stt_job(self, fn: Callable[[], T]) -> T:
        """Run arbitrary blocking STT-side work (e.g. decode + transcribe an upload)."""
        return await self._run(self._stt_pool, fn)

    async def render(self, text: str, choice: VoiceChoice, speed: float, fmt: str) -> bytes:
        return await self._run(self._tts_pool, self._render_sync, text, choice, speed, fmt)

    def _render_sync(self, text: str, choice: VoiceChoice, speed: float, fmt: str) -> bytes:
        audio = self.tts.synthesize(text, choice, speed)
        return encode_audio(audio, fmt)

    def close(self) -> None:
        self._stt_pool.shutdown(wait=False, cancel_futures=True)
        self._tts_pool.shutdown(wait=False, cancel_futures=True)


def encode_audio(audio_24k: Float32Array, fmt: str) -> bytes:
    """24 kHz float -> ``ulaw8k`` (G.711 mu-law, 8 kHz) or ``pcm16_24k`` (little-endian int16)."""
    if fmt == "ulaw8k":
        return float_to_ulaw(resample(audio_24k, TTS_RATE, 8000))
    if fmt == "pcm16_24k":
        return float_to_pcm16(audio_24k).astype("<i2").tobytes()
    raise ValueError(f"unknown format {fmt!r}; use one of {sorted(FORMATS)}")


def silence(fmt: str, seconds: float) -> bytes:
    """Encoded silence used between streamed sentences."""
    if fmt == "ulaw8k":
        return b"\xff" * int(8000 * seconds)
    return b"\x00\x00" * int(TTS_RATE * seconds)
