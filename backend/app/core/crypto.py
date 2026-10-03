"""Symmetric encryption for integration secrets at rest (e.g. Google refresh tokens).

Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from ``ENCRYPTION_SECRET``
(falling back to the token-signing secret, so development works out of the box).
Rotating the secret makes stored credentials unreadable — owners reconnect.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.encryption_secret or settings.admin_token_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(f"integrations:{secret}".encode("utf-8")).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def decrypt(value: str) -> str:
    """The plaintext, or "" when the value is empty or was encrypted with another secret."""
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


__all__ = ["decrypt", "encrypt"]
