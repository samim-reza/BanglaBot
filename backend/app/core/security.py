"""Password hashing, signed session tokens and the bearer-token dependencies.

Passwords are PBKDF2-HMAC-SHA256 with a random salt (no native extension
needed). Tokens are compact HMAC-signed JSON (``body.signature``) — enough for
a single-secret deployment with merchant and admin roles.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Header, HTTPException

from app.core.config import get_settings

_PBKDF2_ITERATIONS = 200_000
DEFAULT_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
MEDIA_STREAM_TOKEN_TTL_SECONDS = 15 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt, expected = str(password_hash or "").split("$", 3)
        rounds = int(iterations)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), rounds)
    return hmac.compare_digest(digest.hex(), expected)


def _signature(body: str) -> str:
    secret = get_settings().admin_token_secret.encode()
    return hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()


def sign_token(payload: dict, *, ttl_seconds: int | None = DEFAULT_TOKEN_TTL_SECONDS) -> str:
    body_payload = dict(payload)
    if ttl_seconds:
        body_payload["exp"] = int(time.time()) + int(ttl_seconds)
    body = base64.urlsafe_b64encode(json.dumps(body_payload, separators=(",", ":")).encode()).decode()
    return f"{body}.{_signature(body)}"


def verify_token(token: str) -> dict:
    try:
        body, signature = str(token or "").split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if not hmac.compare_digest(signature, _signature(body)):
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode()).decode())
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    exp = payload.get("exp")
    if exp is not None:
        try:
            if int(exp) < time.time():
                raise HTTPException(status_code=401, detail="Token expired")
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc
    return payload


def sign_media_stream_token(*, order_id: str, call_log_id: str, ttl_seconds: int = MEDIA_STREAM_TOKEN_TTL_SECONDS) -> str:
    """Token carried in the Twilio ``<Stream>`` parameters; ties a socket to one call."""
    return sign_token(
        {"typ": "media_stream", "order_id": str(order_id), "call_log_id": str(call_log_id)},
        ttl_seconds=ttl_seconds,
    )


def verify_media_stream_token(token: str, *, order_id: str, call_log_id: str) -> None:
    payload = verify_token(token)
    if payload.get("typ") != "media_stream":
        raise HTTPException(status_code=403, detail="Invalid media token")
    if str(payload.get("order_id")) != str(order_id) or str(payload.get("call_log_id")) != str(call_log_id):
        raise HTTPException(status_code=403, detail="Media token does not match call")


async def bearer_payload(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    return verify_token(authorization.removeprefix("Bearer ").strip())


def require_roles(payload: dict, allowed_roles: set[str]) -> None:
    if payload.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
