"""Session tokens for account owners and platform admins, and the bearer header reader."""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

from app.core.config import get_settings
from app.core.security.tokens import TYP_ADMIN, TYP_SESSION, sign_token, verify_token

MERCHANT_ROLE = "merchant"
ROLE_SUPERADMIN = "superadmin"
ROLE_SUPPORT = "support"
ROLE_FINANCE = "finance"
ADMIN_ROLES = (ROLE_SUPERADMIN, ROLE_SUPPORT, ROLE_FINANCE)
#: An admin's "open this account's portal" session.
IMPERSONATION_TTL_SECONDS = 2 * 3600


def merchant_session_ttl() -> int:
    return max(1, int(get_settings().merchant_session_ttl_hours)) * 3600


def admin_session_ttl() -> int:
    return max(1, int(get_settings().admin_session_ttl_hours)) * 3600


def issue_merchant_token(merchant: Any, *, impersonated_by: str | None = None) -> str:
    claims: dict[str, Any] = {
        "sub": str(merchant.id),
        "role": MERCHANT_ROLE,
        "username": str(getattr(merchant, "username", "") or ""),
        "ver": int(getattr(merchant, "token_version", 0) or 0),
    }
    ttl = merchant_session_ttl()
    if impersonated_by:
        claims["imp"] = str(impersonated_by)
        ttl = IMPERSONATION_TTL_SECONDS
    return sign_token(claims, ttl_seconds=ttl, typ=TYP_SESSION)


def issue_admin_token(*, sub: str, username: str, role: str, ver: int = 0, env: bool = False) -> str:
    claims: dict[str, Any] = {"sub": str(sub), "username": username, "role": role, "ver": int(ver or 0)}
    if env:
        claims["env"] = True
    return sign_token(claims, ttl_seconds=admin_session_ttl(), typ=TYP_ADMIN)


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    return authorization.removeprefix("Bearer ").strip()


async def bearer_payload(authorization: str | None = Header(default=None)) -> dict:
    """Claims of the request's session token (owner or admin; never a media / pay token)."""
    return verify_token(bearer_token(authorization), typ=(TYP_SESSION, TYP_ADMIN), legacy_ok=True)


def require_roles(payload: dict, allowed_roles: set[str]) -> None:
    if payload.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


__all__ = [
    "ADMIN_ROLES",
    "IMPERSONATION_TTL_SECONDS",
    "MERCHANT_ROLE",
    "ROLE_FINANCE",
    "ROLE_SUPERADMIN",
    "ROLE_SUPPORT",
    "admin_session_ttl",
    "bearer_payload",
    "bearer_token",
    "issue_admin_token",
    "issue_merchant_token",
    "merchant_session_ttl",
    "require_roles",
]
