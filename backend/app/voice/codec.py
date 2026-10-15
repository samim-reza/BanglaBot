"""Audio format conversion for the speech providers.

The phone path is 8 kHz μ-law both ways. Providers that don't speak it natively
need conversions: Gemini returns 24 kHz PCM16, edge-tts returns MP3, Groq
Whisper wants a WAV file. Everything here works on bytes, is dependency-free
at import time, and uses ``miniaudio`` (C, optional) for resampling and MP3
decoding when it is installed, with a pure-Python resampler as the fallback.
"""

from __future__ import annotations

import io
import math
import sys
import wave
from array import array
from functools import lru_cache

PHONE_RATE = 8000
_BIG_ENDIAN = sys.byteorder == "big"
_ULAW_BIAS = 0x84
_ULAW_CLIP = 32635


def _ulaw_byte_to_linear(byte: int) -> int:
    byte = ~byte & 0xFF
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    sample = (((mantissa << 3) + _ULAW_BIAS) << exponent) - _ULAW_BIAS
    return -sample if sign else sample


#: μ-law byte → 16-bit linear sample (G.711).
ULAW_TO_LINEAR: tuple[int, ...] = tuple(_ulaw_byte_to_linear(i) for i in range(256))


def linear_to_ulaw(sample: int) -> int:
    """One signed 16-bit sample → μ-law byte (G.711)."""
    sign = 0x80 if sample < 0 else 0
    magnitude = min(-sample if sample < 0 else sample, _ULAW_CLIP) + _ULAW_BIAS
    exponent = 7
    mask = 0x4000
    while exponent > 0 and not magnitude & mask:
        exponent -= 1
        mask >>= 1
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


@lru_cache(maxsize=1)
def _encode_table() -> bytes:
    """Unsigned 16-bit view of a sample → μ-law byte (built once, ~40 ms)."""
    return bytes(linear_to_ulaw(i - 65536 if i >= 32768 else i) for i in range(65536))


def _samples(pcm: bytes, typecode: str = "h") -> array:
    out = array(typecode)
    out.frombytes(bytes(pcm[: len(pcm) - (len(pcm) % 2)]))
    if _BIG_ENDIAN:
        out.byteswap()
    return out


def _to_bytes(samples: array) -> bytes:
    if _BIG_ENDIAN:
        samples = array(samples.typecode, samples)
        samples.byteswap()
    return samples.tobytes()


def ulaw_to_pcm16(data: bytes) -> bytes:
    """μ-law bytes → little-endian signed 16-bit PCM (same sample rate)."""
    return _to_bytes(array("h", map(ULAW_TO_LINEAR.__getitem__, data)))


def pcm16_to_ulaw(pcm: bytes) -> bytes:
    """Little-endian signed 16-bit PCM → μ-law bytes (same sample rate)."""
    table = _encode_table()
    return bytes(map(table.__getitem__, _samples(pcm, "H")))


# ------------------------------------------------------------------ resampling
def _clamp16(value: float) -> int:
    sample = int(round(value))
    return 32767 if sample > 32767 else -32768 if sample < -32768 else sample


@lru_cache(maxsize=8)
def _lowpass_kernel(factor: int) -> tuple[float, ...]:
    """Hamming-windowed sinc low-pass for decimating by ``factor``."""
    taps = 8 * factor + 1
    cutoff = 0.45 / factor
    center = (taps - 1) / 2
    kernel = []
    for n in range(taps):
        x = n - center
        sinc = 2 * cutoff if x == 0 else math.sin(2 * math.pi * cutoff * x) / (math.pi * x)
        kernel.append(sinc * (0.54 - 0.46 * math.cos(2 * math.pi * n / (taps - 1))))
    total = sum(kernel)
    return tuple(value / total for value in kernel)


def _resample_python(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Pure-Python fallback: FIR decimation for integer ratios, else linear interpolation."""
    samples = _samples(pcm)
    count = len(samples)
    out = array("h")
    if src_rate > dst_rate and src_rate % dst_rate == 0:
        factor = src_rate // dst_rate
        kernel = _lowpass_kernel(factor)
        half = len(kernel) // 2
        for i in range(0, count, factor):
            lo = i - half
            acc = 0.0
            for k, coeff in enumerate(kernel):
                j = lo + k
                if 0 <= j < count:
                    acc += coeff * samples[j]
            out.append(_clamp16(acc))
        return _to_bytes(out)
    ratio = src_rate / dst_rate
    for i in range(int(count / ratio)):
        pos = i * ratio
        j = int(pos)
        frac = pos - j
        nxt = samples[j + 1] if j + 1 < count else samples[j]
        out.append(_clamp16(samples[j] * (1.0 - frac) + nxt * frac))
    return _to_bytes(out)


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Mono PCM16 sample-rate conversion (miniaudio when installed)."""
    if src_rate == dst_rate or not pcm:
        return bytes(pcm)
    try:
        import miniaudio
    except ImportError:  # pragma: no cover - miniaudio is in requirements
        return _resample_python(pcm, src_rate, dst_rate)
    fmt = miniaudio.SampleFormat.SIGNED16
    return bytes(miniaudio.convert_frames(fmt, 1, src_rate, bytes(pcm[: len(pcm) - len(pcm) % 2]), fmt, 1, dst_rate))


def pcm16_to_phone(pcm: bytes, rate: int) -> bytes:
    """Mono PCM16 at any rate → 8 kHz μ-law, ready for the phone line."""
    return pcm16_to_ulaw(resample_pcm16(pcm, rate, PHONE_RATE))


def mp3_to_phone(mp3: bytes) -> bytes:
    """MP3 (edge-tts) → 8 kHz μ-law; miniaudio decodes and resamples in one pass."""
    import miniaudio

    decoded = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=PHONE_RATE)
    return pcm16_to_ulaw(_to_bytes(array("h", decoded.samples)))


# ------------------------------------------------------------------ containers
def wav_bytes(pcm: bytes, rate: int, channels: int = 1) -> bytes:
    """Wrap PCM16 in a WAV container (Whisper upload)."""
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm)
    return out.getvalue()


def read_wav(data: bytes) -> tuple[bytes, int]:
    """WAV → (mono PCM16, sample rate); stereo is down-mixed."""
    with wave.open(io.BytesIO(data), "rb") as reader:
        if reader.getsampwidth() != 2:
            raise ValueError("only 16-bit WAV is supported")
        rate = reader.getframerate()
        channels = reader.getnchannels()
        pcm = reader.readframes(reader.getnframes())
    if channels == 2:
        stereo = _samples(pcm)
        pcm = _to_bytes(array("h", ((stereo[i] + stereo[i + 1]) // 2 for i in range(0, len(stereo) - 1, 2))))
    return pcm, rate


def l16_rate(mime_type: str, default: int = 24000) -> int:
    """Sample rate from ``audio/L16;codec=pcm;rate=24000`` style MIME types."""
    for part in str(mime_type or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name.lower() == "rate" and value.strip().isdigit():
            return int(value.strip())
    return default


def b64_decoded_len(payload: str) -> int:
    """Bytes a base64 string decodes to, without decoding it (audio metering)."""
    size = len(payload)
    if not size:
        return 0
    return size * 3 // 4 - payload.count("=", max(0, size - 2))


__all__ = [
    "PHONE_RATE",
    "ULAW_TO_LINEAR",
    "b64_decoded_len",
    "l16_rate",
    "linear_to_ulaw",
    "mp3_to_phone",
    "pcm16_to_phone",
    "pcm16_to_ulaw",
    "read_wav",
    "resample_pcm16",
    "ulaw_to_pcm16",
    "wav_bytes",
]
