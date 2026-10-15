"""A light energy voice-activity detector for utterance-based transcription.

Providers like Groq Whisper transcribe whole files, not streams, so the backend
has to decide when the caller started and stopped talking. This works on the
same 20 ms μ-law frames Telnyx sends: an adaptive noise floor (falls fast,
rises slowly — and much more slowly inside an utterance, so speech doesn't
raise its own bar, yet steady line noise that tripped it still escapes), a few
voiced frames to start, a pre-roll so the first syllable is kept, a short
hangover so word endings are kept, and an end-of-utterance silence long enough
that a mid-sentence pause doesn't split the turn (every split is a separate,
minimum-billed request).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.voice.audio import FRAME_BYTES, ulaw_rms

FRAME_MS = 20


@dataclass(slots=True)
class VADEvent:
    #: start | end | discard (speech too short to transcribe)
    type: str
    audio: bytes = b""

    @property
    def seconds(self) -> float:
        return len(self.audio) / 8000


class EnergyVAD:
    def __init__(
        self,
        *,
        min_rms: int = 400,
        factor: float = 3.0,
        cap_rms: int = 3000,
        start_ms: int = 60,
        min_speech_ms: int = 200,
        hangover_ms: int = 250,
        end_silence_ms: int = 600,
        preroll_ms: int = 300,
        max_utterance_ms: int = 30_000,
        floor_rise: float = 0.01,
        floor_rise_in_speech: float = 0.002,
        floor_fall: float = 0.12,
    ) -> None:
        self.min_rms = min_rms
        self.factor = factor
        self.cap_rms = cap_rms
        self.start_frames = max(1, start_ms // FRAME_MS)
        self.min_speech_frames = max(1, min_speech_ms // FRAME_MS)
        self.hangover_frames = max(0, hangover_ms // FRAME_MS)
        self.end_silence_frames = max(1, end_silence_ms // FRAME_MS)
        self.max_frames = max(1, max_utterance_ms // FRAME_MS)
        self.floor = 150.0
        self.floor_rise = floor_rise
        self.floor_rise_in_speech = floor_rise_in_speech
        self.floor_fall = floor_fall
        self._preroll: deque[bytes] = deque(maxlen=max(1, preroll_ms // FRAME_MS))
        self._remainder = b""
        self.reset()

    def reset(self) -> None:
        """Forget the current utterance (barge-in clear, provider switch)."""
        self.in_speech = False
        self._onset = 0
        self._frames: list[bytes] = []
        self._voiced = 0
        self._silence_run = 0
        self._last_voiced_index = -1
        self._preroll.clear()

    @property
    def threshold(self) -> int:
        return int(max(self.min_rms, min(max(self.cap_rms, self.min_rms), self.floor * self.factor)))

    def _adapt(self, rms: int, rise: float) -> None:
        alpha = rise if rms > self.floor else self.floor_fall
        self.floor += (rms - self.floor) * alpha

    def push(self, ulaw: bytes) -> list[VADEvent]:
        """Feed μ-law audio (any length); returns the events it completed."""
        data = self._remainder + ulaw
        whole = len(data) - len(data) % FRAME_BYTES
        self._remainder = data[whole:]
        events: list[VADEvent] = []
        for offset in range(0, whole, FRAME_BYTES):
            event = self._frame(data[offset : offset + FRAME_BYTES])
            if event is not None:
                events.append(event)
        return events

    def _frame(self, frame: bytes) -> VADEvent | None:
        rms = ulaw_rms(frame)
        voiced = rms >= self.threshold
        self._adapt(rms, self.floor_rise_in_speech if self.in_speech else self.floor_rise)
        if not self.in_speech:
            self._preroll.append(frame)
            self._onset = self._onset + 1 if voiced else 0
            if self._onset < self.start_frames:
                return None
            self.in_speech = True
            self._frames = list(self._preroll)
            self._preroll.clear()
            self._voiced = self._onset
            self._last_voiced_index = len(self._frames) - 1
            self._silence_run = 0
            return VADEvent("start")
        self._frames.append(frame)
        if voiced:
            self._voiced += 1
            self._silence_run = 0
            self._last_voiced_index = len(self._frames) - 1
        else:
            self._silence_run += 1
        if self._silence_run < self.end_silence_frames and len(self._frames) < self.max_frames:
            return None
        return self._finish()

    def _finish(self) -> VADEvent:
        keep = min(len(self._frames), self._last_voiced_index + 1 + self.hangover_frames)
        audio = b"".join(self._frames[:keep])
        enough = self._voiced >= self.min_speech_frames
        self.in_speech = False
        self._onset = 0
        self._frames = []
        self._voiced = 0
        self._silence_run = 0
        self._last_voiced_index = -1
        return VADEvent("end", audio) if enough else VADEvent("discard")

    def flush(self) -> VADEvent | None:
        """End an utterance in progress (session closing)."""
        return self._finish() if self.in_speech else None


__all__ = ["EnergyVAD", "VADEvent"]
