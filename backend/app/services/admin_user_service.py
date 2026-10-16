"""Platform admin users: the signed-in principal, CRUD, first-superadmin seeding, TOTP setup.

While the ``admin_users`` table is empty the env login (``ADMIN_USERNAME`` /
``ADMIN_PASSWORD``) is the fallback; boot seeds the first superadmin from it, after
which admins are managed here and the env credentials no longer sign in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import memo
from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.cursor import decode_cursor, encode_cursor, page_size
from app.core.security import totp
from app.core.security.passwords import hash_password
from app.core.security.policy import PasswordPolicyError, validate_new_password
from app.core.security.sessions import ADMIN_ROLES, ROLE_SUPERADMIN
from app.models.admin_user import AdminUser

logger = structlog.get_logger(__name__)

ENV_ADMIN_PREFIX = "env:"
TOTP_ISSUER = "Callisa Admin"
_HAS_USERS_KEY = "admin_users:any"


@dataclass(frozen=True)
class AdminPrincipal:
    """The admin behind a request. ``id`` is the admin_users id, or ``env:<username>``."""

    id: str
    username: str
    role: str
    via_env: bool = False

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style reads for code written against the old token-payload dict."""
        return {"sub": self.id, "role": self.role, "username": self.username}.get(key, default)

    @property
    def audit_actor(self) -> dict[str, str]:
        return {"actor_type": "admin", "actor_id": self.id}


def env_principal(username: str) -> AdminPrincipal:
    return AdminPrincipal(id=f"{ENV_ADMIN_PREFIX}{username}", username=username, role=ROLE_SUPERADMIN, via_env=True)


def principal_of(user: AdminUser) -> AdminPrincipal:
    return AdminPrincipal(id=user.id, username=user.username, role=user.role)


def serialize(user: AdminUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "active": bool(user.active),
        "totp_enabled": bool(user.totp_enabled),
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


def check_role(role: str) -> str:
    value = str(role or "").strip().lower()
    if value not in ADMIN_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {', '.join(ADMIN_ROLES)}")
    return value


def check_password(password: str, username: str) -> None:
    try:
        validate_new_password(password, username=username)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ------------------------------------------------------------------ lookups
async def has_admin_users(db: AsyncSession) -> bool:
    known = memo.get(_HAS_USERS_KEY)
    if known is not None:
        return bool(known)
    found = await db.scalar(select(AdminUser.id).limit(1)) is not None
    memo.put(_HAS_USERS_KEY, found, ttl=60 if found else 5)
    return found


def forget_has_admin_users() -> None:
    memo.drop(_HAS_USERS_KEY)


async def get_by_username(db: AsyncSession, username: str) -> AdminUser | None:
    return await db.scalar(select(AdminUser).where(AdminUser.username == str(username or "").strip()))


async def get_or_404(db: AsyncSession, admin_id: str) -> AdminUser:
    user = await db.get(AdminUser, admin_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Admin not found")
    return user


async def active_superadmins(db: AsyncSession, *, excluding: str | None = None) -> int:
    stmt = select(func.count(AdminUser.id)).where(AdminUser.role == ROLE_SUPERADMIN, AdminUser.active.is_(True))
    if excluding:
        stmt = stmt.where(AdminUser.id != excluding)
    return int(await db.scalar(stmt) or 0)


async def list_admins(db: AsyncSession, *, limit: int = 50, cursor: str = "") -> dict[str, Any]:
    size = page_size(limit)
    stmt = select(AdminUser)
    if cursor:
        try:
            at, row_id = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid cursor") from exc
        stmt = stmt.where(tuple_(AdminUser.created_at, AdminUser.id) > tuple_(at, row_id))
    rows = list(await db.scalars(stmt.order_by(AdminUser.created_at, AdminUser.id).limit(size + 1)))
    more = len(rows) > size
    rows = rows[:size]
    return {"items": [serialize(row) for row in rows], "next_cursor": encode_cursor(rows[-1].created_at, rows[-1].id) if more and rows else None}


# ------------------------------------------------------------------ changes
async def create_admin(db: AsyncSession, *, username: str, password: str, role: str) -> AdminUser:
    name = str(username or "").strip()
    role = check_role(role)
    check_password(password, name)
    if await get_by_username(db, name) is not None:
        raise HTTPException(status_code=409, detail="Username is already taken")
    user = AdminUser(username=name, password_hash=hash_password(password), role=role, active=True, token_version=0)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Username is already taken") from exc
    await db.refresh(user)
    forget_has_admin_users()
    return user


async def guard_last_superadmin(db: AsyncSession, user: AdminUser, *, new_role: str | None = None, deactivate: bool = False) -> None:
    losing = user.role == ROLE_SUPERADMIN and user.active and (deactivate or (new_role is not None and new_role != ROLE_SUPERADMIN))
    if losing and await active_superadmins(db, excluding=user.id) == 0:
        raise HTTPException(status_code=409, detail="Keep at least one active superadmin")


def set_password(user: AdminUser, password: str) -> None:
    check_password(password, user.username)
    user.password_hash = hash_password(password)
    user.token_version = int(user.token_version or 0) + 1


def revoke_sessions(user: AdminUser) -> None:
    user.token_version = int(user.token_version or 0) + 1


# ------------------------------------------------------------------ TOTP
def totp_secret_of(user: AdminUser) -> str:
    return decrypt_secret(user.totp_secret or "")


def begin_totp_setup(user: AdminUser) -> dict[str, str]:
    """New (not yet enabled) secret; returned once so the admin can scan it."""
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="Two-factor sign-in is already on")
    secret = totp.generate_secret()
    user.totp_secret = encrypt_secret(secret)
    user.totp_last_step = 0
    return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, account=user.username, issuer=TOTP_ISSUER)}


def accept_totp(user: AdminUser, code: str) -> bool:
    """Check a code against the admin's secret and burn its time step (no replays)."""
    secret = totp_secret_of(user)
    if not secret:
        return False
    step = totp.verify_totp(secret, code, last_step=int(user.totp_last_step or 0))
    if step is None:
        return False
    user.totp_last_step = step
    return True


# ------------------------------------------------------------------ boot
async def seed_from_env(session_factory: Any = None) -> bool:
    """Create the first superadmin from ADMIN_USERNAME / ADMIN_PASSWORD when there is none."""
    if session_factory is None:
        from app.db.session import AsyncSessionLocal

        session_factory = AsyncSessionLocal
    settings = get_settings()
    username = str(settings.admin_username or "").strip()
    if not username or not settings.admin_password:
        return False
    try:
        async with session_factory() as session:
            if await session.scalar(select(AdminUser.id).limit(1)) is not None:
                return False
            session.add(AdminUser(username=username, password_hash=hash_password(settings.admin_password), role=ROLE_SUPERADMIN))
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — env login keeps working while the table is empty
        await logger.awarning("admin_seed_failed", error=str(exc)[:200])
        return False
    forget_has_admin_users()
    await logger.ainfo("admin_seeded", username=username, role=ROLE_SUPERADMIN)
    return True


__all__ = [
    "AdminPrincipal",
    "accept_totp",
    "begin_totp_setup",
    "create_admin",
    "env_principal",
    "get_by_username",
    "get_or_404",
    "guard_last_superadmin",
    "has_admin_users",
    "list_admins",
    "principal_of",
    "revoke_sessions",
    "seed_from_env",
    "serialize",
    "set_password",
]
