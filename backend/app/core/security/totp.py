"""Time-based one-time passwords (RFC 6238 over RFC 4226 HOTP) for admin 2FA.

Secrets are base32 (what authenticator apps scan); codes are 6 digits every
30 s. ``verify_totp`` accepts one step of clock drift either way and returns the
matched time step, so the caller can refuse a code that was already used.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP_SECONDS = 30
DIGITS = 6
_ALGORITHMS = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}


def generate_secret(num_bytes: int = 20) -> str:
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode("ascii").rstrip("=")


def _key(secret_b32: str) -> bytes:
    cleaned = "".join(str(secret_b32 or "").split()).upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def hotp(key: bytes, counter: int, *, digits: int = DIGITS, algorithm: str = "sha1") -> str:
    digest = hmac.new(key, struct.pack(">Q", int(counter)), _ALGORITHMS[algorithm]).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def time_step(at: float | None = None, *, step: int = STEP_SECONDS) -> int:
    return int((time.time() if at is None else at) // step)


def totp(secret_b32: str, *, at: float | None = None, step: int = STEP_SECONDS, digits: int = DIGITS, algorithm: str = "sha1") -> str:
    return hotp(_key(secret_b32), time_step(at, step=step), digits=digits, algorithm=algorithm)


def verify_totp(secret_b32: str, code: str, *, at: float | None = None, window: int = 1, last_step: int = 0) -> int | None:
    """The time step ``code`` belongs to, or None (wrong, expired, or not newer than ``last_step``)."""
    candidate = "".join(str(code or "").split())
    if not (candidate.isascii() and candidate.isdigit()) or len(candidate) != DIGITS:
        return None
    try:
        key = _key(secret_b32)
    except (ValueError, TypeError):
        return None
    current = time_step(at)
    matched: int | None = None
    for offset in range(-window, window + 1):
        counter = current + offset
        # Compare every candidate (constant work), remember the match.
        if hmac.compare_digest(hotp(key, counter), candidate) and counter > int(last_step or 0):
            matched = counter
    return matched


def provisioning_uri(secret_b32: str, *, account: str, issuer: str) -> str:
    """``otpauth://`` URI for a QR code / manual entry in an authenticator app."""
    label = quote(f"{issuer}:{account}", safe="")
    query = urlencode({"secret": secret_b32, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"


__all__ = ["generate_secret", "hotp", "provisioning_uri", "time_step", "totp", "verify_totp"]
