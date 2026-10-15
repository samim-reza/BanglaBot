"""Kokoro-82M text-to-speech via kokoro-onnx, plus voice/language resolution."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import onnxruntime as ort
from kokoro_onnx import Kokoro

from .codec import Float32Array
from .device import cpu_threads, providers_for, session_options
from .models import TTS_NAME, ModelPaths

log = logging.getLogger("speech.tts")

SAMPLE_RATE = 24000
SHRINK_ABOVE_CHARS = 120

#: language -> (espeak code, default female voice, default male voice)
LANGUAGES: dict[str, tuple[str, str, str]] = {
    "en-us": ("en-us", "af_heart", "am_michael"),
    "en-gb": ("en-gb", "bf_emma", "bm_george"),
    "es": ("es", "ef_dora", "em_alex"),
    "fr": ("fr-fr", "ff_siwis", "ff_siwis"),
    "hi": ("hi", "hf_alpha", "hm_omega"),
    "it": ("it", "if_sara", "im_nicola"),
    "pt": ("pt-br", "pf_dora", "pm_alex"),
}
_VOICE_PREFIX_LANG = {"a": "en-us", "b": "en-gb", "e": "es", "f": "fr", "h": "hi", "i": "it", "p": "pt"}


@dataclass(frozen=True)
class VoiceChoice:
    voice: str  # Kokoro voice id
    espeak: str  # phonemizer language


def normalize_language(language: str | None) -> str:
    """``en``/``en-US``/``EN_us`` -> ``en-us``; ``en-GB`` -> ``en-gb``; ``pt-BR`` -> ``pt``."""
    code = (language or "en").strip().lower().replace("_", "-")
    if code in ("", "en") or code.startswith("en-us"):
        return "en-us"
    if code.startswith("en-"):
        return "en-gb" if code in ("en-gb", "en-uk", "en-ie") else "en-us"
    return code.split("-")[0]


class _ArenaSession:
    """Passes RunOptions to every ``run`` so large inputs can hand GPU memory back afterwards.

    Kokoro's activations grow with output length; without shrinking, ORT's arena keeps the
    high-water mark forever. Short replies (the common case) skip the shrink and its ~10% cost.
    """

    def __init__(self, session: ort.InferenceSession) -> None:
        self._session = session
        self._model_path = session._model_path
        self.shrink = False
        self._plain = ort.RunOptions()
        self._shrinking = ort.RunOptions()
        self._shrinking.add_run_config_entry("memory.enable_memory_arena_shrinkage", "gpu:0")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    def run(self, output_names: Any, feeds: Any, run_options: Any = None) -> Any:
        return self._session.run(output_names, feeds, self._shrinking if self.shrink else self._plain)


class KokoroEngine:
    """Thread-safe Kokoro wrapper returning float32 audio at 24 kHz."""

    def __init__(self, paths: ModelPaths, device: str, gpu_mem_mb: int, female: str, male: str) -> None:
        started = time.perf_counter()
        threads = cpu_threads() if device == "cpu" else 2
        session = ort.InferenceSession(
            str(paths.kokoro_model), sess_options=session_options(threads), providers=providers_for(device, gpu_mem_mb)
        )
        self.device = "cuda" if session.get_providers()[0] == "CUDAExecutionProvider" else "cpu"
        self._session = _ArenaSession(session)
        self._kokoro = Kokoro.from_session(self._session, str(paths.kokoro_voices))  # type: ignore[arg-type]
        self.name = TTS_NAME
        self.voices: list[str] = sorted(self._kokoro.voices.keys())
        self.female = female if female in self.voices else "af_heart"
        self.male = male if male in self.voices else "am_michael"
        self._lock = threading.Lock()
        log.info("kokoro on %s loaded in %.1fs", self.device, time.perf_counter() - started)

    def resolve(self, voice: str | None, language: str | None) -> VoiceChoice:
        """Map ``female``/``male``/a Kokoro id plus a language to a concrete voice + phonemizer."""
        lang = normalize_language(language)
        if lang not in LANGUAGES:
            supported = "en, en-gb, es, fr, hi, it, pt"
            raise ValueError(f"language {language!r} is not supported by Kokoro (supported: {supported})")
        espeak, female, male = LANGUAGES[lang]
        if lang == "en-us":
            female, male = self.female, self.male
        name = (voice or "female").strip()
        if name.lower() in ("female", "male", ""):
            return VoiceChoice(male if name.lower() == "male" else female, espeak)
        if name not in self.voices:
            raise ValueError(f"unknown voice {name!r}; use female, male or one of: {', '.join(self.voices)}")
        if lang == "en-us" and (language or "en").strip().lower() in ("en", ""):
            # Plain "en" + an explicit voice: follow the voice's own accent (b* voices are British).
            espeak = LANGUAGES[_VOICE_PREFIX_LANG.get(name[0], "en-us")][0]
        return VoiceChoice(name, espeak)

    def synthesize(self, text: str, choice: VoiceChoice, speed: float = 1.0) -> Float32Array:
        """Synthesize ``text``; returns mono float32 at :data:`SAMPLE_RATE`."""
        speed = float(min(2.0, max(0.5, speed)))
        with self._lock:
            self._session.shrink = self.device == "cuda" and len(text) > SHRINK_ABOVE_CHARS
            audio, _ = self._kokoro.create(text, voice=choice.voice, speed=speed, lang=choice.espeak)
        return np.asarray(audio, dtype=np.float32)

    def warmup(self) -> None:
        choice = self.resolve("female", "en")
        for text in ("Hello there.", "Thanks for calling, how can I help you today?"):
            self.synthesize(text, choice)
