"""Symmetric encryption for secrets at rest (Google / Messenger tokens, webhook
secrets, calendar feed tokens, TOTP secrets) and peppered lookup hashes.

Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from ``ENCRYPTION_SECRET``.
New values are always encrypted with that key; decryption also tries
``ENCRYPTION_SECRET_PREVIOUS`` and keys derived from ``ADMIN_TOKEN_SECRET`` (+
its previous value) — the fallback older deployments encrypted with — so setting
or rotating the secret doesn't strand stored credentials.

``encrypt_secret`` / ``decrypt_secret`` mark ciphertext with an ``enc:`` prefix
so a column can hold legacy plaintext and encrypted values side by side.
``lookup_hashes`` gives HMAC-SHA256 digests (server pepper) for finding a row
by a secret without storing the secret itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings

ENC_PREFIX = "enc:"


def _secrets() -> list[str]:
    settings = get_settings()
    candidates = [
        settings.encryption_secret or settings.admin_token_secret,
        getattr(settings, "encryption_secret_previous", None),
        settings.admin_token_secret,
        getattr(settings, "admin_token_secret_previous", None),
    ]
    out: list[str] = []
    for value in candidates:
        if value and value not in out:
            out.append(value)
    return out


def _fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(f"integrations:{secret}".encode("utf-8")).digest())


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(_fernet_key(secret)) for secret in _secrets()])


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def decrypt(value: str) -> str:
    """The plaintext, or "" when the value is empty or was encrypted with an unknown secret."""
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def encrypt_secret(value: str) -> str:
    """``enc:<fernet>`` for a column that may also hold legacy plaintext."""
    return ENC_PREFIX + encrypt(value) if value else ""


def decrypt_secret(stored: str) -> str:
    """Plaintext of an ``enc:`` value; legacy plaintext (no prefix) comes back as-is."""
    value = str(stored or "")
    if not value.startswith(ENC_PREFIX):
        return value
    return decrypt(value[len(ENC_PREFIX):])


def is_encrypted(stored: str) -> bool:
    return str(stored or "").startswith(ENC_PREFIX)


def lookup_hashes(value: str, *, purpose: str) -> list[str]:
    """Peppered HMAC-SHA256 of ``value`` under each known secret, current first."""
    data = f"{purpose}:{value}".encode("utf-8")
    return [hmac.new(f"lookup:{secret}".encode("utf-8"), data, hashlib.sha256).hexdigest() for secret in _secrets()]


def lookup_hash(value: str, *, purpose: str) -> str:
    return lookup_hashes(value, purpose=purpose)[0]


__all__ = [
    "ENC_PREFIX",
    "decrypt",
    "decrypt_secret",
    "encrypt",
    "encrypt_secret",
    "is_encrypted",
    "lookup_hash",
    "lookup_hashes",
]
