"""Per-merchant call-behavior settings: background-noise filtering (VAD),
barge-in protection and the silent-caller auto-drop.

Defaults live HERE in code — not in .env. A merchant's picks in Settings
(stored on the merchant row) override them; values are read at call start,
so a change applies from the next call.
"""

from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

# --- Background-noise filter (how strict the voice detector is) ---
DEFAULT_NOISE_MODE = "normal"
NOISE_MODES: dict[str, VADParams] = {
    # Everyday indoor calls (pipecat's defaults).
    "normal": VADParams(confidence=0.7, start_secs=0.2, stop_secs=0.2, min_volume=0.6),
    # Loud shops/street noise: only clear, sustained speech counts.
    "noisy": VADParams(confidence=0.85, start_secs=0.4, stop_secs=0.6, min_volume=0.85),
}

# --- Barge-in (customer talking over the agent) ---
DEFAULT_BARGE_IN_MODE = "protected"
BARGE_IN_MODES = ("normal", "protected", "off")
_PROTECTED_MIN_WORDS = 3
_NEVER_INTERRUPT_WORDS = 1000  # effectively: never interrupt while the agent speaks

# --- Silent-caller auto-drop (order becomes callable again) ---
DEFAULT_SILENCE_HANGUP_SECS = 10
SILENCE_HANGUP_MIN, SILENCE_HANGUP_MAX = 5, 30


def vad_params(mode: str | None) -> VADParams:
    return NOISE_MODES.get(mode or "", NOISE_MODES[DEFAULT_NOISE_MODE])


def is_valid_noise_mode(mode: str) -> bool:
    return mode in NOISE_MODES


def turn_strategies(mode: str | None) -> UserTurnStrategies | None:
    """Turn-taking strategies for the barge-in mode; None = pipecat defaults
    (VAD + transcription — any detected speech interrupts the agent)."""
    mode = mode or DEFAULT_BARGE_IN_MODE
    if mode == "protected":
        # Interrupt only after a few clear transcribed words — coughs, "হুম"
        # and background chatter no longer cut the agent off mid-sentence.
        return UserTurnStrategies(
            start=[MinWordsUserTurnStartStrategy(min_words=_PROTECTED_MIN_WORDS)]
        )
    if mode == "off":
        return UserTurnStrategies(
            start=[MinWordsUserTurnStartStrategy(min_words=_NEVER_INTERRUPT_WORDS)]
        )
    return None


def is_valid_barge_in_mode(mode: str) -> bool:
    return mode in BARGE_IN_MODES


def silence_hangup_secs(value: int | None) -> int:
    """Clamp a merchant's stored value to the allowed range (bad/unset → default)."""
    if not value or not (SILENCE_HANGUP_MIN <= value <= SILENCE_HANGUP_MAX):
        return DEFAULT_SILENCE_HANGUP_SECS
    return int(value)
