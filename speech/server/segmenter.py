"""Turn a stream of VAD probabilities into utterances (endpointing)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

from .codec import Float32Array
from .vad import VadStream


@dataclass(frozen=True)
class SegmenterConfig:
    threshold: float = 0.5  # probability that starts / keeps speech
    neg_threshold: float = 0.35  # below this counts as silence
    silence_ms: int = 600  # trailing silence that ends an utterance
    min_speech_ms: int = 200  # shorter blips are dropped
    pre_roll_ms: int = 300  # audio kept from before the trigger
    trailing_ms: int = 200  # silence kept after the last speech
    max_utterance_s: float = 25.0  # force a cut (Parakeet's comfortable limit)


@dataclass(frozen=True)
class SegmentEvent:
    kind: Literal["speech_started", "speech_stopped"]
    audio: Float32Array | None = None  # whole utterance (on speech_stopped)
    forced: bool = False  # cut because of max_utterance_s


class _State(Enum):
    IDLE = "idle"
    PENDING = "pending"  # triggered, not yet long enough to count as speech
    SPEAKING = "speaking"


class UtteranceSegmenter:
    """Stateful endpointer: feed audio, get ``speech_started`` / ``speech_stopped`` events."""

    def __init__(self, vad: VadStream, config: SegmenterConfig) -> None:
        self.vad = vad
        self.config = config
        self._win_ms = vad.window_ms
        self._preroll: deque[Float32Array] = deque(maxlen=max(1, round(config.pre_roll_ms / self._win_ms)))
        self.reset()

    @property
    def speaking(self) -> bool:
        return self._state is _State.SPEAKING

    def reset(self) -> None:
        """Drop the current utterance and VAD state (the ``clear`` message)."""
        self.vad.reset()
        self._state = _State.IDLE
        self._chunks: list[Float32Array] = []
        self._voiced_ms = 0.0
        self._gap_ms = 0.0
        self._samples = 0
        self._preroll.clear()

    def feed(self, samples: Float32Array) -> list[SegmentEvent]:
        events: list[SegmentEvent] = []
        for prob, chunk in self.vad.process(samples):
            event = self._step(prob, chunk)
            if event is not None:
                events.append(event)
        return events

    def _step(self, prob: float, chunk: Float32Array) -> SegmentEvent | None:
        cfg = self.config
        if self._state is _State.IDLE:
            if prob < cfg.threshold:
                self._preroll.append(chunk)
                return None
            self._state = _State.PENDING
            self._chunks = [*self._preroll, chunk]
            self._samples = sum(len(c) for c in self._chunks)
            self._preroll.clear()
            self._voiced_ms, self._gap_ms = self._win_ms, 0.0
            return self._maybe_start()

        self._chunks.append(chunk)
        self._samples += len(chunk)
        if self._state is _State.PENDING:
            if prob >= cfg.neg_threshold:
                self._voiced_ms += self._win_ms
                self._gap_ms = 0.0
                return self._maybe_start()
            self._gap_ms += self._win_ms
            if self._gap_ms >= cfg.silence_ms:  # it was a blip: forget it
                self._abandon()
            return None

        # SPEAKING
        if prob >= cfg.threshold:
            self._gap_ms = 0.0
        elif self._gap_ms > 0 or prob < cfg.neg_threshold:
            self._gap_ms += self._win_ms
        if self._gap_ms >= cfg.silence_ms:
            return self._finish(forced=False)
        if self._samples >= cfg.max_utterance_s * self.vad.sample_rate:
            return self._finish(forced=True)
        return None

    def _maybe_start(self) -> SegmentEvent | None:
        if self._voiced_ms >= self.config.min_speech_ms:
            self._state = _State.SPEAKING
            return SegmentEvent("speech_started")
        return None

    def _abandon(self) -> None:
        tail = self._chunks[-self._preroll.maxlen :] if self._preroll.maxlen else []
        self._state, self._chunks, self._samples = _State.IDLE, [], 0
        self._preroll.extend(tail)

    def _finish(self, *, forced: bool) -> SegmentEvent:
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
        drop_ms = max(0.0, self._gap_ms - self.config.trailing_ms)
        drop = int(drop_ms * self.vad.sample_rate / 1000)
        if 0 < drop < len(audio):
            audio = audio[:-drop]
        tail = self._chunks[-self._preroll.maxlen :] if not forced and self._preroll.maxlen else []
        self._state, self._chunks, self._samples = _State.IDLE, [], 0
        self._voiced_ms = self._gap_ms = 0.0
        self._preroll.clear()
        self._preroll.extend(tail)
        return SegmentEvent("speech_stopped", audio=audio, forced=forced)
