"""Password hashing: argon2id for new hashes, legacy PBKDF2 hashes still verify.

``needs_rehash`` tells a login handler to replace an old (PBKDF2, or argon2 with
outdated parameters) hash with a fresh one while it holds the plaintext.
Parameters fit a 512 MB server: ~19 MiB and ~50 ms per hash.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_PBKDF2_SCHEME = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 200_000

_hasher = PasswordHasher(time_cost=3, memory_cost=19 * 1024, parallelism=1, hash_len=32, salt_len=16)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _verify_pbkdf2(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt, expected = password_hash.split("$", 3)
        rounds = int(iterations)
    except ValueError:
        return False
    if scheme != _PBKDF2_SCHEME or rounds < 1:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), rounds)
    return hmac.compare_digest(digest.hex(), expected)


def verify_password(password: str, password_hash: str) -> bool:
    stored = str(password_hash or "")
    if stored.startswith("$argon2"):
        try:
            return _hasher.verify(stored, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    if stored.startswith(_PBKDF2_SCHEME + "$"):
        return _verify_pbkdf2(password, stored)
    return False


def needs_rehash(password_hash: str) -> bool:
    """True for legacy PBKDF2 hashes and argon2 hashes made with other parameters."""
    stored = str(password_hash or "")
    if not stored.startswith("$argon2"):
        return True
    try:
        return _hasher.check_needs_rehash(stored)
    except (InvalidHashError, ValueError):
        return True


def legacy_pbkdf2_hash(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """A hash in the pre-argon2 format (tests and migration tooling only)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), iterations)
    return f"{_PBKDF2_SCHEME}${iterations}${salt}${digest.hex()}"


__all__ = ["hash_password", "legacy_pbkdf2_hash", "needs_rehash", "verify_password"]
