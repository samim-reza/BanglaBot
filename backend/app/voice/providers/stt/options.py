"""Speech-to-text knobs (models, endpointing, noise filtering), read from ``.env``.

Keys and chains live in :mod:`app.voice.providers.settings`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import _settings_env_files


class STTOptions(BaseSettings):
    model_config = SettingsConfigDict(env_file=_settings_env_files(), env_file_encoding="utf-8", extra="ignore")

    # --- Deepgram streaming ------------------------------------------------------------
    deepgram_stt_model: str = "nova-3"
    #: Silence (ms) after which Deepgram marks a final as ``speech_final``.
    deepgram_endpointing_ms: int = 300
    #: Gap (ms) between words that ends an utterance (``UtteranceEnd``).
    deepgram_utterance_end_ms: int = 1000
    #: Business / catalog names boosted per call (Deepgram allows ~100 / 500 tokens).
    deepgram_max_keyterms: int = 40

    # --- Groq Whisper (utterance-based, backend VAD) -------------------------------------
    groq_stt_model: str = "whisper-large-v3-turbo"
    #: Segments all scoring below this average log-prob are noise (Whisper's own -1.0).
    groq_noise_logprob: float = -1.0
    #: Trailing silence (ms) that ends an utterance for the backend VAD and the local server.
    stt_end_silence_ms: int = 600

    # --- connecting ------------------------------------------------------------------------
    stt_connect_timeout_seconds: float = 5.0
    #: How long a provider that failed to connect is skipped by later calls.
    stt_connect_failure_pause_seconds: float = 20.0


@lru_cache
def get_stt_options() -> STTOptions:
    return STTOptions()


__all__ = ["STTOptions", "get_stt_options"]
