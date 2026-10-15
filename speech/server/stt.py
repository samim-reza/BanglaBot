"""Parakeet TDT 0.6B v2 speech-to-text via onnx-asr."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
import onnx_asr

from .codec import Float32Array, resample
from .device import cpu_threads, providers_for, session_options
from .models import STT_NAME, ModelPaths

log = logging.getLogger("speech.stt")

SAMPLE_RATE = 16000
#: On CUDA, every new encoder input shape re-plans ~70 cuDNN convolutions (~150 ms), while a
#: repeated shape runs in ~20-40 ms. Padding to a few fixed lengths (with the true length passed
#: to the encoder, which masks the padding) keeps the GPU on the fast path.
CUDA_BUCKETS_S = (8.0, 16.0, 25.0)
MIN_SECONDS = 0.1
SUPPORTED_LANGUAGES = ("en",)


@dataclass(frozen=True)
class SttResult:
    text: str
    confidence: float
    audio_seconds: float


def check_language(language: str | None) -> None:
    """Parakeet TDT v2 is English-only; refuse other languages so callers can fall back."""
    code = (language or "en").strip().lower().replace("_", "-").split("-")[0]
    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f"language {language!r} not supported by local STT (English only: Parakeet TDT 0.6B v2)")


def resolve_precision(paths: ModelPaths, device: str, requested: str) -> str:
    """Pick the Parakeet weights: fp16 on CUDA, int8 on CPU, else whatever is on disk."""
    if requested != "auto":
        if not paths.parakeet_ready(requested):
            raise FileNotFoundError(
                f"Parakeet {requested} files missing in {paths.parakeet}; "
                f"run: uv run python scripts/download_models.py --precision {requested}"
            )
        return requested
    order = ("fp16", "int8", "fp32") if device == "cuda" else ("int8", "fp32", "fp16")
    for precision in order:
        if paths.parakeet_ready(precision):
            return precision
    raise FileNotFoundError(f"No Parakeet weights in {paths.parakeet}; run scripts/download_models.py")


class ParakeetEngine:
    """Thread-safe wrapper; decode whole utterances (one call per utterance)."""

    def __init__(self, paths: ModelPaths, device: str, precision: str, gpu_mem_mb: int) -> None:
        self.precision = resolve_precision(paths, device, precision)
        threads = cpu_threads() if device == "cpu" else 2
        started = time.perf_counter()
        model = onnx_asr.load_model(
            STT_NAME,
            paths.parakeet,
            quantization=None if self.precision == "fp32" else self.precision,
            sess_options=session_options(threads),
            providers=providers_for(device, gpu_mem_mb),
        )
        self._asr = model.asr
        self.device = "cuda" if device == "cuda" and self._uses_cuda() else "cpu"
        self.name = STT_NAME
        self._buckets = CUDA_BUCKETS_S if self.device == "cuda" else ()
        self._max_seconds = CUDA_BUCKETS_S[-1]
        self._lock = threading.Lock()
        log.info("parakeet %s on %s loaded in %.1fs", self.precision, self.device, time.perf_counter() - started)

    def _uses_cuda(self) -> bool:
        encoder = getattr(self._asr, "_encoder", None)
        return bool(encoder is not None and encoder.get_providers()[0] == "CUDAExecutionProvider")

    def warmup(self) -> None:
        """Run each padded shape once so the first real call is fast."""
        noise = (np.random.default_rng(0).standard_normal(SAMPLE_RATE) * 0.01).astype(np.float32)
        # End on bucket 0 so the most common (short) shape is the one left planned.
        order: list[int | None] = [*range(len(self._buckets)), 0] if self._buckets else [None]
        for index in order:
            self._decode(noise, bucket_index=index)

    def transcribe(self, audio: Float32Array, sample_rate: int) -> SttResult:
        """Transcribe mono float audio at any sample rate (resampled to 16 kHz)."""
        x = resample(audio, sample_rate, SAMPLE_RATE) if sample_rate != SAMPLE_RATE else audio
        seconds = len(x) / SAMPLE_RATE
        if seconds < MIN_SECONDS:
            return SttResult("", 0.0, round(seconds, 3))
        window = int(self._max_seconds * SAMPLE_RATE)
        texts: list[str] = []
        logprobs: list[float] = []
        for start in range(0, len(x), window):
            piece = x[start : start + window]
            if len(piece) < MIN_SECONDS * SAMPLE_RATE:
                continue
            text, probs = self._decode(piece, bucket_index=self._bucket_for(len(piece)))
            if text:
                texts.append(text)
            logprobs.extend(probs)
        confidence = float(np.exp(np.mean(logprobs))) if logprobs else 0.0
        return SttResult(" ".join(texts).strip(), round(confidence, 4), round(seconds, 3))

    def _bucket_for(self, n_samples: int) -> int | None:
        for index, seconds in enumerate(self._buckets):
            if n_samples <= seconds * SAMPLE_RATE:
                return index
        return None

    def _decode(self, x: Float32Array, bucket_index: int | None) -> tuple[str, list[float]]:
        length = len(x)
        width = int(self._buckets[bucket_index] * SAMPLE_RATE) if bucket_index is not None else length
        waveforms = np.zeros((1, max(width, length)), dtype=np.float32)
        waveforms[0, :length] = x
        lens = np.array([length], dtype=np.int64)
        with self._lock:
            result = next(iter(self._asr.recognize_batch(waveforms, lens, need_logprobs=True)))
        return result.text.strip(), list(result.logprobs or [])
