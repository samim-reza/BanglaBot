"""Environment-driven settings for the speech server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

SPEECH_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """All tunables; every field maps to a ``SPEECH_*`` environment variable."""

    host: str = "127.0.0.1"
    port: int = 8100
    api_key: str = field(default="", repr=False)
    models_dir: Path = SPEECH_ROOT / "models"
    device: str = "auto"  # auto | cuda | cpu (applies to STT and TTS)
    stt_device: str = ""  # optional per-engine override
    tts_device: str = ""
    stt_precision: str = "auto"  # auto | fp16 | int8 | fp32
    voice_female: str = "af_heart"
    voice_male: str = "am_michael"
    gpu_mem_mb_stt: int = 2048
    gpu_mem_mb_tts: int = 1536
    vad_threshold: float = 0.5
    vad_neg_threshold: float = 0.35
    silence_ms: int = 600
    min_speech_ms: int = 200
    pre_roll_ms: int = 300
    max_utterance_s: float = 25.0
    log_level: str = "info"

    def engine_device(self, engine: str) -> str:
        """Requested device for ``stt`` or ``tts`` (``auto`` | ``cuda`` | ``cpu``)."""
        override = self.stt_device if engine == "stt" else self.tts_device
        return (override or self.device).lower()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Read settings once from the environment."""
    return Settings(
        host=_env("SPEECH_HOST", "127.0.0.1"),
        port=_env_int("SPEECH_PORT", 8100),
        api_key=os.environ.get("SPEECH_SERVER_KEY", "").strip(),
        models_dir=Path(_env("SPEECH_MODELS_DIR", str(SPEECH_ROOT / "models"))).expanduser(),
        device=_env("SPEECH_DEVICE", "auto").lower(),
        stt_device=_env("SPEECH_STT_DEVICE", "").lower(),
        tts_device=_env("SPEECH_TTS_DEVICE", "").lower(),
        stt_precision=_env("SPEECH_STT_PRECISION", "auto").lower(),
        voice_female=_env("SPEECH_VOICE_FEMALE", "af_heart"),
        voice_male=_env("SPEECH_VOICE_MALE", "am_michael"),
        gpu_mem_mb_stt=_env_int("SPEECH_GPU_MEM_MB_STT", 2048),
        gpu_mem_mb_tts=_env_int("SPEECH_GPU_MEM_MB_TTS", 1536),
        vad_threshold=_env_float("SPEECH_VAD_THRESHOLD", 0.5),
        vad_neg_threshold=_env_float("SPEECH_VAD_NEG_THRESHOLD", 0.35),
        silence_ms=_env_int("SPEECH_SILENCE_MS", 600),
        min_speech_ms=_env_int("SPEECH_MIN_SPEECH_MS", 200),
        pre_roll_ms=_env_int("SPEECH_PRE_ROLL_MS", 300),
        max_utterance_s=_env_float("SPEECH_MAX_UTTERANCE_S", 25.0),
        log_level=_env("SPEECH_LOG_LEVEL", "info").lower(),
    )
