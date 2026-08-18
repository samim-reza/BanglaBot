"""Stitch cached speech fragments into one utterance, and hear it as a phone would.

Joining is deliberately *not* a crossfade. Crossfading overlaps the tail of one
fragment with the head of the next, which smears two different pitch contours
into each other and is audible as a warble. What actually causes clicks at a
splice is the vendor's inconsistent leading/trailing silence and the step
discontinuity at the sample level — so instead we trim each fragment to its
speech, ramp its edges over a few milliseconds, and insert our own deterministic
pause. That only works at clause boundaries, where prosody resets over silence
anyway; mid-clause splicing sounds robotic no matter how it is blended.

All PCM here is 16-bit signed little-endian mono, matching the pcm_* formats the
TTS vendors emit and the pipeline's own frames.
"""

import io
import wave

import numpy as np
from scipy import signal

# G.711 constants, in the 14-bit domain the codec actually works in.
MULAW_BIAS = 0x84
MULAW_CLIP = 8159
# Upper bound of each of the 8 mu-law segments (ITU/Sun reference table).
_SEGMENT_ENDS = np.array([0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF], dtype=np.int32)


def _to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def _to_pcm(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0) * 32767.0
    return clipped.astype("<i2").tobytes()


def trim_silence(pcm: bytes, sample_rate: int, floor_db: float = -45.0) -> bytes:
    """Drop leading/trailing silence, keeping a short margin.

    Vendors pad the start and end of a clip by an inconsistent amount. Left in,
    that padding becomes an unpredictable gap in the middle of a joined line.
    """
    samples = _to_float(pcm)
    if samples.size == 0:
        return pcm

    frame = max(1, sample_rate // 100)  # 10 ms
    usable = samples.size - (samples.size % frame)
    if usable < frame:
        return pcm
    rms = np.sqrt((samples[:usable].reshape(-1, frame) ** 2).mean(axis=1) + 1e-12)
    loud = np.nonzero(20 * np.log10(rms) > floor_db)[0]
    if loud.size == 0:
        return pcm  # all quiet — hand it back rather than returning nothing

    margin = max(1, sample_rate // 200)  # 5 ms
    start = max(0, loud[0] * frame - margin)
    end = min(samples.size, (loud[-1] + 1) * frame + margin)
    return _to_pcm(samples[start:end])


def _ramp_edges(samples: np.ndarray, sample_rate: int, ramp_ms: float) -> np.ndarray:
    """Fade the first and last few ms so a splice cannot click."""
    n = int(sample_rate * ramp_ms / 1000)
    if n <= 0 or samples.size < 2 * n:
        return samples
    out = samples.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def join(
    fragments: list[bytes],
    sample_rate: int,
    gap_ms: float = 180.0,
    ramp_ms: float = 12.0,
) -> bytes:
    """Concatenate fragments with a fixed pause between them."""
    pieces = [f for f in fragments if f]
    if not pieces:
        return b""
    gap = np.zeros(int(sample_rate * gap_ms / 1000), dtype=np.float32)
    out: list[np.ndarray] = []
    for i, fragment in enumerate(pieces):
        if i:
            out.append(gap)
        trimmed = _to_float(trim_silence(fragment, sample_rate))
        out.append(_ramp_edges(trimmed, sample_rate, ramp_ms))
    return _to_pcm(np.concatenate(out))


def mulaw_roundtrip(samples: np.ndarray) -> np.ndarray:
    """Quantize through G.711 mu-law and back, adding the codec's own noise.

    Follows the ITU/Sun reference: the encoder drops to 14 bits *before*
    biasing, so doing the arithmetic in the 16-bit domain gives a subtly
    different mantissa on ~1 sample in 200. Verified bit-exact against the
    stdlib audioop implementation, which this replaces because audioop is gone
    in Python 3.13.
    """
    pcm = np.clip(samples * 32768.0, -32768, 32767).astype(np.int32)
    narrow = pcm >> 2  # 16-bit -> 14-bit, arithmetic shift as in the reference
    mask = np.where(narrow < 0, 0x7F, 0xFF).astype(np.int32)
    magnitude = np.minimum(np.abs(narrow), MULAW_CLIP) + (MULAW_BIAS >> 2)
    # search(): index of the first segment end that is >= the magnitude.
    segment = (magnitude[:, None] > _SEGMENT_ENDS[None, :]).sum(axis=1).astype(np.int32)
    encoded = np.where(
        segment >= 8,
        0x7F ^ mask,
        ((segment << 4) | ((magnitude >> (segment + 1)) & 0x0F)) ^ mask,
    )

    decoded = ~encoded & 0xFF
    value = ((decoded & 0x0F) << 3) + MULAW_BIAS
    value = value << ((decoded & 0x70) >> 4)
    value = np.where(decoded & 0x80, MULAW_BIAS - value, value - MULAW_BIAS)
    return (value.astype(np.float32) / 32768.0).astype(np.float32)


def to_phone_band(pcm: bytes, sample_rate: int) -> bytes:
    """Render audio as the customer hears it on a call, at the original rate.

    A phone line is not just quieter — it is band-limited to roughly
    300–3400 Hz and quantized to 8-bit mu-law at 8 kHz. Judging a splice on
    studio-rate audio flatters it; this is the only signal that matters.
    """
    samples = _to_float(pcm)
    if samples.size == 0:
        return pcm

    # 300 Hz high-pass: the band's low cut, which removes most chest warmth.
    sos = signal.butter(4, 300.0, btype="highpass", fs=sample_rate, output="sos")
    filtered = signal.sosfilt(sos, samples).astype(np.float32)

    # Down to 8 kHz (resample_poly anti-aliases, giving the ~4 kHz top) and back.
    if sample_rate % 8000 == 0:
        factor = sample_rate // 8000
        narrow = signal.resample_poly(filtered, 1, factor).astype(np.float32)
        narrow = mulaw_roundtrip(narrow)
        wide = signal.resample_poly(narrow, factor, 1).astype(np.float32)
    else:
        narrow = signal.resample_poly(filtered, 8000, sample_rate).astype(np.float32)
        narrow = mulaw_roundtrip(narrow)
        wide = signal.resample_poly(narrow, sample_rate, 8000).astype(np.float32)
    return _to_pcm(wide[: samples.size])


def wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw PCM in a WAV container so a browser will play it."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def duration_ms(pcm: bytes, sample_rate: int) -> int:
    return round(len(pcm) / 2 / sample_rate * 1000)
