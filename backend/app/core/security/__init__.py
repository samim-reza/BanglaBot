"""Passwords, signed tokens, sessions, 2FA and signed webhook paths.

Modules: ``passwords`` (argon2id + legacy PBKDF2), ``policy`` (what a new
password must satisfy), ``tokens`` (signed claims with typ / ver / rotation),
``sessions`` (owner + admin sessions, bearer header), ``media`` (media-stream
tokens), ``totp`` (RFC 6238), ``signed_paths`` (HMAC'd webhook URLs) and
``boot_guard`` (no default secrets in production). Everything commonly used is
re-exported here, so ``from app.core.security import ...`` keeps working.
"""

from app.core.security.media import MEDIA_STREAM_TOKEN_TTL_SECONDS, sign_media_stream_token, verify_media_stream_token
from app.core.security.passwords import hash_password, needs_rehash, verify_password
from app.core.security.policy import PasswordPolicyError, validate_new_password
from app.core.security.sessions import (
    ADMIN_ROLES,
    MERCHANT_ROLE,
    ROLE_FINANCE,
    ROLE_SUPERADMIN,
    ROLE_SUPPORT,
    bearer_payload,
    issue_admin_token,
    issue_merchant_token,
    require_roles,
)
from app.core.security.tokens import (
    DEFAULT_TOKEN_TTL_SECONDS,
    TYP_ADMIN,
    TYP_GOOGLE_OAUTH,
    TYP_MEDIA_STREAM,
    TYP_PAY,
    TYP_SESSION,
    TYP_VERIFY,
    sign_token,
    token_version,
    verify_token,
)

__all__ = [
    "ADMIN_ROLES",
    "DEFAULT_TOKEN_TTL_SECONDS",
    "MEDIA_STREAM_TOKEN_TTL_SECONDS",
    "MERCHANT_ROLE",
    "PasswordPolicyError",
    "ROLE_FINANCE",
    "ROLE_SUPERADMIN",
    "ROLE_SUPPORT",
    "TYP_ADMIN",
    "TYP_GOOGLE_OAUTH",
    "TYP_MEDIA_STREAM",
    "TYP_PAY",
    "TYP_SESSION",
    "TYP_VERIFY",
    "bearer_payload",
    "hash_password",
    "issue_admin_token",
    "issue_merchant_token",
    "needs_rehash",
    "require_roles",
    "sign_media_stream_token",
    "sign_token",
    "token_version",
    "validate_new_password",
    "verify_media_stream_token",
    "verify_password",
    "verify_token",
]
