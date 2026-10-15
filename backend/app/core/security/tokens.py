"""Compact signed tokens: ``base64url(JSON claims).hex(HMAC-SHA256)``.

Every token carries ``typ`` (what it may be used for — checked at each use),
``iat``, ``jti`` and ``exp``; session tokens also carry ``ver``, compared with
the account's ``token_version`` so a password change or "sign out everywhere"
revokes them. Tokens are signed with ``ADMIN_TOKEN_SECRET``; while rotating,
``ADMIN_TOKEN_SECRET_PREVIOUS`` still verifies the ones it signed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Iterable

from fastapi import HTTPException

from app.core.config import get_settings

TYP_SESSION = "session"
TYP_ADMIN = "admin"
TYP_MEDIA_STREAM = "media_stream"
TYP_GOOGLE_OAUTH = "google_oauth"
TYP_PAY = "pay"
TYP_VERIFY = "verify"

#: Merchant session default (``MERCHANT_SESSION_TTL_HOURS`` overrides it per login).
DEFAULT_TOKEN_TTL_SECONDS = 60 * 60 * 72
#: The role old admin tokens carried (before admin users had roles).
LEGACY_ADMIN_ROLE = "admin"


def signing_secrets() -> list[bytes]:
    """The current secret first, then the one being rotated out (if any)."""
    settings = get_settings()
    out = [settings.admin_token_secret.encode("utf-8")]
    previous = settings.admin_token_secret_previous
    if previous and previous != settings.admin_token_secret:
        out.append(previous.encode("utf-8"))
    return out


def _signature(body: str, secret: bytes) -> str:
    return hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()


def _invalid(detail: str = "Invalid token") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def sign_token(payload: dict, *, ttl_seconds: int | None = DEFAULT_TOKEN_TTL_SECONDS, typ: str | None = None) -> str:
    claims = dict(payload)
    if typ:
        claims["typ"] = typ
    claims.setdefault("typ", TYP_SESSION)
    now = int(time.time())
    claims.setdefault("iat", now)
    claims.setdefault("jti", secrets.token_urlsafe(9))
    if ttl_seconds:
        claims["exp"] = now + int(ttl_seconds)
    # Unpadded base64url: the token travels in URLs (OAuth state, signed links) without escaping.
    body = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{body}.{_signature(body, signing_secrets()[0])}"


def _decode(token: str) -> dict:
    try:
        body, signature = str(token or "").split(".", 1)
        body.encode("ascii")
        signature.encode("ascii")  # compare_digest rejects non-ASCII str
    except (ValueError, UnicodeEncodeError) as exc:
        raise _invalid() from exc
    if not any(hmac.compare_digest(signature, _signature(body, secret)) for secret in signing_secrets()):
        raise _invalid()
    try:
        padded = body + "=" * (-len(body) % 4)  # tokens issued before the switch kept their padding
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except ValueError as exc:
        raise _invalid() from exc
    if not isinstance(payload, dict):
        raise _invalid()
    exp = payload.get("exp")
    if exp is not None:
        try:
            expired = int(exp) < time.time()
        except (TypeError, ValueError) as exc:
            raise _invalid() from exc
        if expired:
            raise _invalid("Token expired")
    return payload


def _legacy_typ(payload: dict) -> str:
    return TYP_ADMIN if payload.get("role") == LEGACY_ADMIN_ROLE else TYP_SESSION


def verify_token(token: str, *, typ: str | Iterable[str] | None = None, legacy_ok: bool = False) -> dict:
    """The claims of a valid, unexpired token.

    ``typ`` restricts what kind of token is accepted. ``legacy_ok`` lets bearer
    sessions issued before tokens had a ``typ`` through (until they expire); they
    come back marked ``legacy`` with the ``typ`` their role implies.
    """
    payload = _decode(token)
    if "typ" not in payload:
        if not legacy_ok:
            raise _invalid()
        payload = {**payload, "typ": _legacy_typ(payload), "legacy": True}
    if typ is not None:
        allowed = {typ} if isinstance(typ, str) else set(typ)
        if payload.get("typ") not in allowed:
            raise _invalid()
    return payload


def token_version(payload: dict) -> int:
    try:
        return int(payload.get("ver") or 0)
    except (TypeError, ValueError):
        return -1


__all__ = [
    "DEFAULT_TOKEN_TTL_SECONDS",
    "LEGACY_ADMIN_ROLE",
    "TYP_ADMIN",
    "TYP_GOOGLE_OAUTH",
    "TYP_MEDIA_STREAM",
    "TYP_PAY",
    "TYP_SESSION",
    "TYP_VERIFY",
    "sign_token",
    "signing_secrets",
    "token_version",
    "verify_token",
]
