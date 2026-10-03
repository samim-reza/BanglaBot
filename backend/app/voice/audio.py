"""Small, dependency-free audio helpers for the phone media bridge.

μ-law decoding is a 256-entry table (no ``audioop``, which is gone in 3.13),
so the RMS gate that drives barge-in and the silence watchdog costs a few
microseconds per 20 ms frame.
"""

from __future__ import annotations

import base64
import math
import re

# Telnyx media streaming (PCMU): 8 kHz μ-law, one frame per 20 ms.
FRAME_BYTES = 160
FRAME_SECONDS = 0.02


def _mulaw_to_linear(byte: int) -> int:
    byte = ~byte & 0xFF
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


_MULAW_TABLE: tuple[int, ...] = tuple(_mulaw_to_linear(i) for i in range(256))


def pcm_rms(payload_b64: str) -> int:
    """RMS of one base64 μ-law payload as 16-bit linear amplitude."""
    try:
        data = base64.b64decode(payload_b64)
    except Exception:  # noqa: BLE001
        return 0
    if not data:
        return 0
    total = 0
    for byte in data:
        sample = _MULAW_TABLE[byte]
        total += sample * sample
    return int(math.sqrt(total / len(data)))


class AmbientNoiseTracker:
    """Rolling estimate of the caller line's background RMS (asymmetric EMA)."""

    def __init__(self, initial: float = 150.0, *, rise: float = 0.004, fall: float = 0.12) -> None:
        self.value = float(initial)
        self._rise = rise
        self._fall = fall

    def update(self, rms: int) -> float:
        alpha = self._rise if rms > self.value else self._fall
        self.value += (float(rms) - self.value) * alpha
        return self.value

    def gate(self, minimum: int, factor: float, cap: int) -> int:
        return int(max(minimum, min(max(cap, minimum), self.value * factor)))


# Sentence boundary: Latin/Bangla terminators followed by whitespace (decimals like 2.50 survive).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[।.?!])\s+")


def split_sentences(text: str, *, max_chars: int = 320) -> list[str]:
    """Unicode-aware sentence split so the first sentence can play while the rest synthesizes."""
    text = " ".join(str(text or "").split())
    if not text:
        return []
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and (len(part) < 8 or len(merged[-1]) < 8) and len(merged[-1]) + len(part) <= max_chars:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged or [text]


#: Lines up to this length are synthesized in ONE request so the voice keeps its
#: natural prosody across sentences; only long replies are chunked so the first
#: part can start playing while the rest is synthesized.
SPEECH_UNIT_MAX_CHARS = 240


def speech_units(text: str, *, max_chars: int = SPEECH_UNIT_MAX_CHARS) -> list[str]:
    """How an utterance is cut into TTS requests: whole when short, else sentence groups."""
    text = " ".join(str(text or "").split())
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    units: list[str] = []
    for sentence in split_sentences(text, max_chars=max_chars):
        if units and len(units[-1]) + 1 + len(sentence) <= max_chars:
            units[-1] = f"{units[-1]} {sentence}"
        else:
            units.append(sentence)
    return units


def sentence_units(lines) -> list[str]:
    """The exact TTS units the bridge will request for ``lines`` (cache warming
    must key on the same text the speaker synthesizes)."""
    units: list[str] = []
    for line in lines:
        for unit in speech_units(line):
            if unit not in units:
                units.append(unit)
    return units


#: μ-law byte values that decode to (near) digital silence.
_ULAW_SILENCE = frozenset({0xFF, 0x7F, 0xFE, 0x7E})


def trim_ulaw_silence(audio: bytes, *, keep_leading_ms: int = 40, keep_trailing_ms: int = 100, sample_rate: int = 8000) -> bytes:
    """Cut the silence a TTS engine pads around a clip so consecutive lines flow
    without a robotic gap; a little is kept so words never start abruptly."""
    if not audio:
        return audio
    n = len(audio)
    lead = 0
    while lead < n and audio[lead] in _ULAW_SILENCE:
        lead += 1
    trail = 0
    while trail < n - lead and audio[n - 1 - trail] in _ULAW_SILENCE:
        trail += 1
    if lead == n:
        return audio[: min(n, sample_rate * keep_trailing_ms // 1000)]
    keep_lead = sample_rate * keep_leading_ms // 1000
    keep_trail = sample_rate * keep_trailing_ms // 1000
    start = max(0, lead - keep_lead)
    end = n - max(0, trail - keep_trail)
    return audio[start:end]


def clean_spoken_text(text: str | None) -> str:
    """Strip markup/emoji-ish noise the model might emit; single-spaced."""
    cleaned = str(text or "")
    cleaned = re.sub(r"<[^>]{1,40}>", "", cleaned)
    cleaned = re.sub(r"[*_#`]+", "", cleaned)
    return " ".join(cleaned.split()).strip()


def goodbye_hangup_delay_seconds(text: str) -> float:
    """How long to wait after TTS finishes before hanging up (mark fallback)."""
    words = len(str(text or "").split())
    return max(5.0, min(30.0, (words / 2.2) + 3.0))
