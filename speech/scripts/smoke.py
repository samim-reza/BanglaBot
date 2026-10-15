"""Standalone smoke test (no server): Kokoro -> mu-law 8 kHz -> VAD -> Parakeet, with timings.

Usage (from ``speech/``)::

    uv run python scripts/smoke.py
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from server.codec import float_to_ulaw, resample, ulaw_to_float  # noqa: E402
from server.config import get_settings  # noqa: E402
from server.device import gpu_memory_mb  # noqa: E402
from server.engines import Engines  # noqa: E402

TEXT = "Hello, this is Sunrise Clinic. Would you like to book an appointment with Dr. Rahman tomorrow at five?"
EXTRA = [
    "Sure, one moment please.",
    "Your appointment is confirmed for tomorrow at five PM.",
    "Could I have your full name and date of birth, please?",
]


_NUMBERS = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten".split())}


def words(text: str) -> list[str]:
    """Lower-case, strip punctuation, spell-out digits the same way ("5" == "five")."""
    return [_NUMBERS.get(w, w) for w in re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()]


def word_error_rate(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    d = np.arange(len(h) + 1)
    for i, rw in enumerate(r, 1):
        prev, d[0] = d.copy(), i
        for j, hw in enumerate(h, 1):
            d[j] = min(prev[j] + 1, d[j - 1] + 1, prev[j - 1] + (rw != hw))
    return float(d[-1]) / max(1, len(r))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    t0 = time.perf_counter()
    engines = Engines.load(get_settings())
    print(f"\nloaded + warmed up in {time.perf_counter() - t0:.1f}s")
    print(f"STT {engines.stt.name} [{engines.stt.precision}] on {engines.stt.device}; "
          f"TTS {engines.tts.name} on {engines.tts.device}")

    choice = engines.tts.resolve("female", "en")
    t = time.perf_counter()
    audio24 = engines.tts.synthesize(TEXT, choice)
    tts_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    ulaw = float_to_ulaw(resample(audio24, 24000, 8000))
    codec_ms = (time.perf_counter() - t) * 1000
    seconds = len(ulaw) / 8000
    print(f"\nTTS  {tts_ms:6.0f} ms for {seconds:.2f}s of audio (RTF {tts_ms / 1000 / seconds:.3f}); "
          f"24k->8k mu-law {codec_ms:.1f} ms, {len(ulaw)} bytes")

    for line in EXTRA:
        t = time.perf_counter()
        a = engines.tts.synthesize(line, engines.tts.resolve("male", "en"))
        print(f"TTS  {(time.perf_counter() - t) * 1000:6.0f} ms  ({len(a) / 24000:.2f}s, male)  {line!r}")

    t = time.perf_counter()
    result = engines.stt.transcribe(ulaw_to_float(ulaw), 8000)
    stt_ms = (time.perf_counter() - t) * 1000
    print(f"\nSTT  {stt_ms:6.0f} ms for {result.audio_seconds:.2f}s (incl. 8k->16k), confidence {result.confidence}")
    print(f"     ref: {TEXT}")
    print(f"     hyp: {result.text}")
    print(f"     WER: {word_error_rate(TEXT, result.text):.1%}")

    # Offline endpointing: 20 ms frames + 1 s of line silence through Silero + the segmenter.
    seg = engines.segmenter(get_settings().silence_ms)
    stream = ulaw + b"\xff" * 8000
    events = []
    for i in range(0, len(stream), 160):
        events += [(i / 8000, ev) for ev in seg.feed(ulaw_to_float(stream[i : i + 160]))]
    for at, ev in events:
        extra = f" ({len(ev.audio) / 8000:.2f}s utterance)" if ev.audio is not None else ""
        print(f"VAD  {ev.kind} at {at:.2f}s{extra}")
    utterance = next((ev.audio for _, ev in events if ev.audio is not None), None)
    if utterance is not None:
        t = time.perf_counter()
        r2 = engines.stt.transcribe(utterance, 8000)
        print(f"STT  {(time.perf_counter() - t) * 1000:6.0f} ms on the VAD-cut utterance: {r2.text!r}")

    vram = gpu_memory_mb()
    print(f"\nVRAM used by this process: {vram} MB" if vram is not None else "\nVRAM: nvidia-smi not available")
    engines.close()
    ok = word_error_rate(TEXT, result.text) <= 0.2 and len(events) >= 2
    print("SMOKE OK" if ok else "SMOKE FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
