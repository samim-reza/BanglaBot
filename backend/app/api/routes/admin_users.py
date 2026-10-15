"""Admin users: superadmins manage the console's admins; every admin manages their own
password, two-factor sign-in (TOTP) and sessions under ``/me``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal, require_admin
from app.core.ratelimit import rate_limit
from app.core.security import ROLE_SUPERADMIN, issue_admin_token, verify_password
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.admin_users import AdminUserCreate, AdminUserUpdate, PasswordChangeIn, TotpCodeIn
from app.services import admin_user_service as admins
from app.services import audit_service as audit

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])
superadmin_only = require_admin(ROLE_SUPERADMIN)


async def _me(db: AsyncSession, admin: AdminPrincipal) -> AdminUser:
    if admin.via_env:
        raise HTTPException(status_code=409, detail="Signed in with the setup login — create an admin user first")
    return await admins.get_or_404(db, admin.id)


def _token(user: AdminUser) -> str:
    return issue_admin_token(sub=user.id, username=user.username, role=user.role, ver=int(user.token_version or 0))


def _audit(db: AsyncSession, request: Request, admin: AdminPrincipal, action: str, user: AdminUser, **meta) -> None:
    audit.stage(db, action=action, **admin.audit_actor, target_type="admin_user", target_id=user.id, request=request, meta=meta or None)


# ------------------------------------------------------------------ the signed-in admin
@router.get("/me")
async def me(admin: AdminPrincipal = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if admin.via_env:
        return {"id": admin.id, "username": admin.username, "role": admin.role, "setup_login": True, "totp_enabled": False}
    return {**admins.serialize(await _me(db, admin)), "setup_login": False}


@router.post("/me/password")
async def change_my_password(
    data: PasswordChangeIn, request: Request, admin: AdminPrincipal = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Other sessions are signed out; ``token`` keeps this browser signed in."""
    await rate_limit(request, "admin-password", max_hits=5, per_seconds=900, key=admin.id)
    user = await _me(db, admin)
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    admins.set_password(user, data.new_password)
    _audit(db, request, admin, "admin_user.password_changed", user)
    await db.commit()
    return {"ok": True, "token": _token(user)}


@router.post("/me/logout-all")
async def logout_all(request: Request, admin: AdminPrincipal = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await _me(db, admin)
    admins.revoke_sessions(user)
    _audit(db, request, admin, "admin_user.sessions_revoked", user)
    await db.commit()
    return {"ok": True, "token": _token(user)}


@router.post("/me/totp/setup")
async def totp_setup(admin: AdminPrincipal = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """A new secret + ``otpauth://`` URI to scan; nothing changes at sign-in until it is enabled."""
    user = await _me(db, admin)
    setup = admins.begin_totp_setup(user)
    await db.commit()
    return setup


@router.post("/me/totp/enable")
async def totp_enable(data: TotpCodeIn, request: Request, admin: AdminPrincipal = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await rate_limit(request, "admin-totp", max_hits=5, per_seconds=300, key=admin.id)
    user = await _me(db, admin)
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="Two-factor sign-in is already on")
    if not admins.accept_totp(user, data.code):
        raise HTTPException(status_code=400, detail="That code didn't match — check the time on your phone and try again")
    user.totp_enabled = True
    _audit(db, request, admin, "admin_user.totp_enabled", user)
    await db.commit()
    return admins.serialize(user)


@router.post("/me/totp/disable")
async def totp_disable(data: TotpCodeIn, request: Request, admin: AdminPrincipal = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await rate_limit(request, "admin-totp", max_hits=5, per_seconds=300, key=admin.id)
    user = await _me(db, admin)
    if not user.totp_enabled or not admins.accept_totp(user, data.code):
        raise HTTPException(status_code=400, detail="That code didn't match")
    user.totp_enabled = False
    user.totp_secret = None
    _audit(db, request, admin, "admin_user.totp_disabled", user)
    await db.commit()
    return admins.serialize(user)


# ------------------------------------------------------------------ managing admins (superadmin)
@router.get("")
async def list_admin_users(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str = Query(default="", max_length=200),
    _: AdminPrincipal = Depends(superadmin_only),
    db: AsyncSession = Depends(get_db),
):
    return await admins.list_admins(db, limit=limit, cursor=cursor)


@router.post("", status_code=201)
async def create_admin_user(
    data: AdminUserCreate, request: Request, admin: AdminPrincipal = Depends(superadmin_only), db: AsyncSession = Depends(get_db)
):
    user = await admins.create_admin(db, username=data.username, password=data.password, role=data.role)
    await audit.record(action="admin_user.created", **admin.audit_actor, target_type="admin_user", target_id=user.id, request=request, meta={"username": user.username, "role": user.role})
    return admins.serialize(user)


@router.patch("/{admin_id}")
async def update_admin_user(
    admin_id: str,
    data: AdminUserUpdate,
    request: Request,
    admin: AdminPrincipal = Depends(superadmin_only),
    db: AsyncSession = Depends(get_db),
):
    user = await admins.get_or_404(db, admin_id)
    changes: dict[str, object] = {}
    role = admins.check_role(data.role) if data.role is not None else None
    await admins.guard_last_superadmin(db, user, new_role=role, deactivate=data.active is False)
    if role is not None and role != user.role:
        changes["role"] = [user.role, role]
        user.role = role
        admins.revoke_sessions(user)
    if data.active is not None and data.active != user.active:
        changes["active"] = data.active
        user.active = data.active
        admins.revoke_sessions(user)
    if data.password:
        admins.set_password(user, data.password)
        changes["password"] = "reset"
    if data.reset_totp and (user.totp_enabled or user.totp_secret):
        user.totp_enabled, user.totp_secret, user.totp_last_step = False, None, 0
        changes["totp"] = "reset"
    if changes:
        _audit(db, request, admin, "admin_user.updated", user, changes=changes)
        await db.commit()
        await db.refresh(user)
    return admins.serialize(user)


@router.delete("/{admin_id}", status_code=204)
async def delete_admin_user(
    admin_id: str, request: Request, admin: AdminPrincipal = Depends(superadmin_only), db: AsyncSession = Depends(get_db)
):
    user = await admins.get_or_404(db, admin_id)
    if user.id == admin.id:
        raise HTTPException(status_code=409, detail="You can't delete your own admin account")
    await admins.guard_last_superadmin(db, user, deactivate=True)
    _audit(db, request, admin, "admin_user.deleted", user, username=user.username, role=user.role)
    await db.delete(user)
    await db.commit()
    return Response(status_code=204)
