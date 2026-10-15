"""Admin sign-in (password → optional TOTP → session token) and resolving an admin
session back to its principal on each request."""

from __future__ import annotations

import hmac
from collections.abc import Iterable

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.core.ratelimit import lockout
from app.core.security.passwords import hash_password, needs_rehash, verify_password
from app.core.security.sessions import ROLE_SUPERADMIN, issue_admin_token
from app.core.security.tokens import TYP_ADMIN, token_version
from app.models.admin_user import AdminUser
from app.services import admin_user_service as admins
from app.services import audit_service as audit

INVALID_LOGIN = "Invalid username or password"
TOTP_REQUIRED = "Two-factor code required"
#: Response header telling the console to ask for the authenticator code.
TOTP_HEADER = "X-2FA-Required"
SESSION_EXPIRED = "Session expired — sign in again"

_dummy_hash: str | None = None


def _equalize_timing(password: str) -> None:
    """Spend one hash verification on an unknown username, like a known one would."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password-0000")
    verify_password(password, _dummy_hash)


async def _failed(request: Request, username: str, reason: str) -> HTTPException:
    locked_for = await lockout.record_failure(lockout.ADMIN_LOGIN, username)
    await audit.record(
        action="admin.login_failed",
        actor_type=audit.ACTOR_ADMIN,
        actor_id=username[:80],
        request=request,
        meta={"reason": reason, "locked_seconds": locked_for},
    )
    return HTTPException(status_code=401, detail=INVALID_LOGIN)


async def _succeeded(request: Request, principal: admins.AdminPrincipal, username: str) -> None:
    await lockout.record_success(lockout.ADMIN_LOGIN, username)
    await audit.record(action="admin.login", **principal.audit_actor, request=request, meta={"via": "env" if principal.via_env else "user"})


async def login(db: AsyncSession, request: Request, *, username: str, password: str, code: str = "") -> str:
    """A session token, or 401 / 429. 401 with ``X-2FA-Required: totp`` asks for the code."""
    username = str(username or "").strip()
    await lockout.before_attempt(request, lockout.ADMIN_LOGIN, username)
    if not await admins.has_admin_users(db):
        settings = get_settings()
        username_ok = hmac.compare_digest(username.encode(), str(settings.admin_username).encode())
        password_ok = hmac.compare_digest(str(password).encode(), str(settings.admin_password).encode())
        if not (username_ok and password_ok):
            raise await _failed(request, username, "bad_credentials")
        principal = admins.env_principal(username)
        await _succeeded(request, principal, username)
        return issue_admin_token(sub=principal.id, username=username, role=ROLE_SUPERADMIN, env=True)

    user = await admins.get_by_username(db, username)
    if user is None:
        _equalize_timing(password)
        raise await _failed(request, username, "unknown_user")
    if not verify_password(password, user.password_hash):
        raise await _failed(request, username, "bad_password")
    if not user.active:
        raise await _failed(request, username, "inactive")
    if user.totp_enabled:
        if not str(code or "").strip():
            raise HTTPException(status_code=401, detail=TOTP_REQUIRED, headers={TOTP_HEADER: "totp"})
        if not admins.accept_totp(user, code):
            raise await _failed(request, username, "bad_totp")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    await db.commit()
    await _succeeded(request, admins.principal_of(user), username)
    return issue_admin_token(sub=user.id, username=user.username, role=user.role, ver=int(user.token_version or 0))


async def resolve(db: AsyncSession, payload: dict, roles: Iterable[str] = ()) -> admins.AdminPrincipal:
    """The admin a verified token belongs to; 401 when revoked, 403 when the role doesn't fit."""
    if payload.get("typ") != TYP_ADMIN:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    subject = str(payload.get("sub") or "")
    if payload.get("legacy"):
        # Issued before admin users existed (role "admin"): the same-named admin, or the env admin.
        principal = await _legacy_principal(db, subject)
    elif payload.get("env"):
        if await admins.has_admin_users(db):
            raise HTTPException(status_code=401, detail=SESSION_EXPIRED)
        principal = admins.env_principal(str(payload.get("username") or subject.removeprefix(admins.ENV_ADMIN_PREFIX)))
    else:
        user = await db.get(AdminUser, subject) if subject else None
        if user is None or not user.active or token_version(payload) != int(user.token_version or 0):
            raise HTTPException(status_code=401, detail=SESSION_EXPIRED)
        principal = admins.principal_of(user)
    allowed = set(roles)
    if allowed and principal.role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return principal


async def _legacy_principal(db: AsyncSession, username: str) -> admins.AdminPrincipal:
    if not await admins.has_admin_users(db):
        return admins.env_principal(username)
    user = await admins.get_by_username(db, username)
    if user is None or not user.active or int(user.token_version or 0) != 0:
        raise HTTPException(status_code=401, detail=SESSION_EXPIRED)
    return admins.principal_of(user)


__all__ = ["SESSION_EXPIRED", "TOTP_HEADER", "TOTP_REQUIRED", "login", "resolve"]
