"""Silero VAD (ONNX, CPU) with per-stream recurrent state."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort

from .codec import Float32Array
from .device import CPU_EP, session_options

#: Silero v5/v6 window sizes and context lengths per sample rate.
_WINDOW = {8000: 256, 16000: 512}
_CONTEXT = {8000: 32, 16000: 64}


class SileroVad:
    """One shared ONNX session (thread-safe ``run``); state lives in :class:`VadStream`."""

    def __init__(self, model_path: Path) -> None:
        opts = session_options(threads=1)
        self.session = ort.InferenceSession(str(model_path), sess_options=opts, providers=[CPU_EP])

    def stream(self, sample_rate: int = 8000) -> VadStream:
        if sample_rate not in _WINDOW:
            raise ValueError(f"Silero VAD supports 8000 or 16000 Hz, not {sample_rate}")
        return VadStream(self.session, sample_rate)


class VadStream:
    """Feeds arbitrary-length audio, returns one speech probability per Silero window."""

    def __init__(self, session: ort.InferenceSession, sample_rate: int) -> None:
        self._session = session
        self.sample_rate = sample_rate
        self.window = _WINDOW[sample_rate]
        self._context_len = _CONTEXT[sample_rate]
        self._sr = np.array(sample_rate, dtype=np.int64)
        self.reset()

    @property
    def window_ms(self) -> float:
        return 1000.0 * self.window / self.sample_rate

    def reset(self) -> None:
        """Forget recurrent state and any partial window."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(self._context_len, dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)

    def process(self, samples: Float32Array) -> list[tuple[float, Float32Array]]:
        """Return ``(probability, window_samples)`` for every complete window now available."""
        buf = np.concatenate([self._pending, samples]) if self._pending.size else samples
        out: list[tuple[float, Float32Array]] = []
        n_full = len(buf) // self.window
        for i in range(n_full):
            chunk = buf[i * self.window : (i + 1) * self.window]
            frame = np.concatenate([self._context, chunk])[None, :]
            prob, self._state = self._session.run(None, {"input": frame, "state": self._state, "sr": self._sr})
            self._context = chunk[-self._context_len :]
            out.append((float(prob[0][0]), chunk))
        self._pending = buf[n_full * self.window :].copy()
        return out
