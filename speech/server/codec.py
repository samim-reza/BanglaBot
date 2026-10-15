"""Audio codecs in pure NumPy: G.711 mu-law, polyphase resampling, WAV parsing.

(Python's ``audioop`` was removed in 3.13, so nothing here relies on it.)
"""

from __future__ import annotations

import struct
from functools import lru_cache
from math import gcd

import numpy as np
import numpy.typing as npt

Float32Array = npt.NDArray[np.float32]

_ULAW_BIAS = 0x84
_ULAW_CLIP = 32635


def _build_ulaw_decode_table() -> npt.NDArray[np.int16]:
    u = (~np.arange(256, dtype=np.int32)) & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    magnitude = (((mantissa << 3) + _ULAW_BIAS) << exponent) - _ULAW_BIAS
    return np.where(sign != 0, -magnitude, magnitude).astype(np.int16)


def _build_exponent_table() -> npt.NDArray[np.int32]:
    table = np.zeros(256, dtype=np.int32)
    table[1:] = np.floor(np.log2(np.arange(1, 256))).astype(np.int32)
    return table


_ULAW_DECODE = _build_ulaw_decode_table()
_ULAW_EXP = _build_exponent_table()


def ulaw_to_pcm16(data: bytes) -> npt.NDArray[np.int16]:
    """Decode G.711 mu-law bytes to int16 PCM."""
    return _ULAW_DECODE[np.frombuffer(data, dtype=np.uint8)]


def ulaw_to_float(data: bytes) -> Float32Array:
    """Decode G.711 mu-law bytes to float32 in [-1, 1]."""
    return ulaw_to_pcm16(data).astype(np.float32) / 32768.0


def pcm16_to_ulaw(pcm: npt.NDArray[np.int16]) -> bytes:
    """Encode int16 PCM to G.711 mu-law bytes."""
    x = pcm.astype(np.int32)
    sign = (x < 0).astype(np.int32) << 7
    mag = np.minimum(np.abs(x), _ULAW_CLIP) + _ULAW_BIAS
    exponent = _ULAW_EXP[mag >> 7]
    mantissa = (mag >> (exponent + 3)) & 0x0F
    return ((~(sign | (exponent << 4) | mantissa)) & 0xFF).astype(np.uint8).tobytes()


def float_to_pcm16(x: Float32Array) -> npt.NDArray[np.int16]:
    """Clip float audio to [-1, 1] and convert to int16."""
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16)


def float_to_ulaw(x: Float32Array) -> bytes:
    return pcm16_to_ulaw(float_to_pcm16(x))


@lru_cache(maxsize=16)
def _polyphase_bank(up: int, down: int) -> tuple[Float32Array, int]:
    """Kaiser-windowed sinc low-pass split into ``up`` phases; returns (bank[up, K], half_len)."""
    max_rate = max(up, down)
    half_len = 12 * max_rate
    n = np.arange(-half_len, half_len + 1, dtype=np.float64)
    cutoff = 0.95 / max_rate  # relative to the Nyquist of the upsampled signal
    h = cutoff * np.sinc(cutoff * n) * np.kaiser(len(n), 8.0)
    h *= up / h.sum()
    taps = -(-len(h) // up)
    h = np.concatenate([h, np.zeros(taps * up - len(h))])
    return h.reshape(taps, up).T.astype(np.float32).copy(), half_len


def resample(x: Float32Array, src_rate: int, dst_rate: int) -> Float32Array:
    """Band-limited rational resampling (polyphase FIR, zero group delay)."""
    x = np.asarray(x, dtype=np.float32)
    if src_rate == dst_rate or x.size == 0:
        return x
    g = gcd(src_rate, dst_rate)
    up, down = dst_rate // g, src_rate // g
    bank, half_len = _polyphase_bank(up, down)
    n_out = -(-len(x) * up // down)
    t = np.arange(n_out) * down + half_len  # position in the (virtual) upsampled signal
    if up <= 8:  # telephony ratios (24k->8k, 8k->16k): one C-level convolution per phase
        phases = np.stack([np.convolve(x, bank[p]) for p in range(up)])
        return phases[t % up, t // up].astype(np.float32)
    taps = bank.shape[1]
    padded = np.concatenate([np.zeros(taps, np.float32), x, np.zeros(taps, np.float32)])
    out = np.empty(n_out, dtype=np.float32)
    offsets = np.arange(taps)
    block = max(1024, (1 << 22) // taps)
    for start in range(0, n_out, block):
        tb = t[start : start + block]
        idx = (tb // up)[:, None] - offsets[None, :] + taps
        out[start : start + len(tb)] = np.einsum("ij,ij->i", bank[tb % up], padded[idx])
    return out


def read_wav(data: bytes) -> tuple[Float32Array, int]:
    """Parse a RIFF/WAVE file (PCM 8/16/24/32, float, mu-law, A-law) to mono float32."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    pos, fmt, payload = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos : pos + 4], struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        body = data[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            payload = body
        pos += 8 + size + (size & 1)
    if fmt is None or payload is None or len(fmt) < 16:
        raise ValueError("WAV is missing its fmt or data chunk")
    tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", fmt[:16])
    if tag == 0xFFFE and len(fmt) >= 26:  # WAVE_FORMAT_EXTENSIBLE: real tag is the GUID prefix
        tag = struct.unpack("<H", fmt[24:26])[0]
    channels = max(1, channels)
    samples = _decode_wav_samples(payload, tag, bits)
    usable = len(samples) - len(samples) % channels
    mono = samples[:usable].reshape(-1, channels).mean(axis=1) if channels > 1 else samples
    return mono.astype(np.float32), int(rate)


def _decode_wav_samples(payload: bytes, tag: int, bits: int) -> Float32Array:
    if tag == 7:
        return ulaw_to_float(payload)
    if tag == 6:
        return _alaw_to_float(payload)
    if tag == 3:
        dtype = np.float32 if bits == 32 else np.float64
        width = 4 if bits == 32 else 8
        return np.frombuffer(payload[: len(payload) // width * width], dtype=dtype).astype(np.float32)
    if tag != 1:
        raise ValueError(f"unsupported WAV format tag {tag}")
    if bits == 8:
        return (np.frombuffer(payload, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if bits == 16:
        return np.frombuffer(payload[: len(payload) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    if bits == 24:
        raw = np.frombuffer(payload[: len(payload) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        ints = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
        ints = np.where(ints & 0x800000, ints - (1 << 24), ints)
        return ints.astype(np.float32) / float(1 << 23)
    if bits == 32:
        return np.frombuffer(payload[: len(payload) // 4 * 4], dtype="<i4").astype(np.float32) / float(1 << 31)
    raise ValueError(f"unsupported PCM bit depth {bits}")


def _alaw_to_float(payload: bytes) -> Float32Array:
    a = np.frombuffer(payload, dtype=np.uint8).astype(np.int32) ^ 0x55
    sign = a & 0x80
    exponent = (a >> 4) & 0x07
    mantissa = a & 0x0F
    mag = np.where(exponent == 0, (mantissa << 4) + 8, ((mantissa << 4) + 0x108) << np.maximum(exponent - 1, 0))
    return np.where(sign != 0, mag, -mag).astype(np.float32) / 32768.0


def write_wav_pcm16(x: Float32Array, rate: int) -> bytes:
    """Encode mono float audio as a 16-bit PCM WAV (used by the test scripts)."""
    pcm = float_to_pcm16(x).astype("<i2").tobytes()
    fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, rate, rate * 2, 2, 16)
    header = struct.pack("<4sI4s", b"RIFF", 36 + len(pcm), b"WAVE") + fmt_chunk + struct.pack("<4sI", b"data", len(pcm))
    return header + pcm
