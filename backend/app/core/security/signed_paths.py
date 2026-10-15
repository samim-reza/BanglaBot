"""HMAC-signed URL path segments for webhooks whose sender can't sign requests.

A path such as ``/telnyx/inbound/{sig}`` carries ``sig`` = the first 32 hex
chars of HMAC-SHA256(key, scope). The key is ``TELNYX_WEBHOOK_SECRET`` or, when
unset, derived from ``ADMIN_TOKEN_SECRET`` (and, while rotating, the previous
secret — so in-flight calls keep their callbacks). Checks are constant-time.
"""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import get_settings
from app.core.security.tokens import signing_secrets

SIG_HEX_CHARS = 32
_DERIVE_LABEL = b"signed-webhook-paths:v1"


def _keys() -> list[bytes]:
    explicit = get_settings().telnyx_webhook_secret
    if explicit:
        return [explicit.encode("utf-8")]
    return [hmac.new(secret, _DERIVE_LABEL, hashlib.sha256).digest() for secret in signing_secrets()]


def _sig(key: bytes, scope: str) -> str:
    return hmac.new(key, scope.encode("utf-8"), hashlib.sha256).hexdigest()[:SIG_HEX_CHARS]


def path_signature(scope: str) -> str:
    return _sig(_keys()[0], scope)


def verify_path_signature(scope: str, sig: str | None) -> bool:
    candidate = str(sig or "")
    if len(candidate) != SIG_HEX_CHARS or not candidate.isascii():
        return False
    ok = False
    for key in _keys():
        ok |= hmac.compare_digest(_sig(key, scope), candidate)
    return ok


__all__ = ["SIG_HEX_CHARS", "path_signature", "verify_path_signature"]
