"""Account-owner sign-in, password change and "sign out everywhere".

Sign-in is throttled per IP and username with a growing lockout; a successful
sign-in transparently upgrades an old password hash and secrets still stored in
plaintext. Changing the password (or signing out everywhere) bumps the account's
``token_version``, which revokes every session issued before.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import lockout, rate_limit
from app.core.security import PasswordPolicyError, hash_password, issue_merchant_token, needs_rehash, validate_new_password, verify_password
from app.models import Merchant
from app.services import audit_service as audit

INVALID_LOGIN = "Invalid username or password"

_dummy_hash: str | None = None


def _equalize_timing(password: str) -> None:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password-0000")
    verify_password(password, _dummy_hash)


async def _inactive_reason(db: AsyncSession, merchant: Merchant) -> str:
    """Why an inactive account can't sign in — a new self-serve account is waiting, not disabled."""
    from app.models.signup import Signup

    status = await db.scalar(select(Signup.status).where(Signup.merchant_id == merchant.id))
    if status == "pending_payment":
        return "Your account is waiting for payment — finish checkout to activate it."
    if status == "awaiting_approval":
        return "Thanks for signing up! Your account is being reviewed and will be activated shortly."
    return "This account is disabled"


async def login(db: AsyncSession, request: Request, *, username: str, password: str) -> Merchant:
    name = str(username or "").strip()
    await lockout.before_attempt(request, lockout.MERCHANT_LOGIN, name)
    merchant = await db.scalar(select(Merchant).where(Merchant.username == name))
    if merchant is None:
        _equalize_timing(password)
    if merchant is None or not verify_password(password, merchant.password_hash):
        await lockout.record_failure(lockout.MERCHANT_LOGIN, name)
        raise HTTPException(status_code=401, detail=INVALID_LOGIN)
    if not merchant.active:
        raise HTTPException(status_code=403, detail=await _inactive_reason(db, merchant))
    changed = False
    if needs_rehash(merchant.password_hash):
        merchant.password_hash = hash_password(password)
        changed = True
    upgrade = getattr(merchant, "upgrade_stored_secrets", None)
    if callable(upgrade) and upgrade():
        changed = True
    if changed:
        await db.commit()
    await lockout.record_success(lockout.MERCHANT_LOGIN, name)
    return merchant


def require_password_policy(password: str, *, username: str = "", email: str = "") -> None:
    """422 with a readable reason when ``password`` breaks the policy."""
    try:
        validate_new_password(password, username=username, email=email)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def check_new_password(merchant: Merchant, password: str) -> None:
    require_password_policy(password, username=merchant.username, email=getattr(merchant, "email", "") or "")


def revoke_sessions(merchant: Merchant) -> None:
    merchant.token_version = int(getattr(merchant, "token_version", 0) or 0) + 1


async def change_password(db: AsyncSession, request: Request, merchant: Merchant, *, current: str, new: str) -> str:
    """Set a new password, revoke older sessions; returns a fresh token for this browser."""
    await rate_limit(request, "password-change", max_hits=5, per_seconds=900, key=merchant.id)
    if not verify_password(current, merchant.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    check_new_password(merchant, new)
    if verify_password(new, merchant.password_hash):
        raise HTTPException(status_code=422, detail="Choose a different password from the current one")
    merchant.password_hash = hash_password(new)
    revoke_sessions(merchant)
    audit.stage(
        db,
        action="merchant.password_changed",
        actor_type=audit.ACTOR_MERCHANT,
        actor_id=merchant.id,
        target_type="merchant",
        target_id=merchant.id,
        merchant_id=merchant.id,
        request=request,
    )
    await db.commit()
    return issue_merchant_token(merchant)


async def sign_out_everywhere(db: AsyncSession, request: Request, merchant: Merchant) -> str:
    revoke_sessions(merchant)
    audit.stage(
        db,
        action="merchant.sessions_revoked",
        actor_type=audit.ACTOR_MERCHANT,
        actor_id=merchant.id,
        target_type="merchant",
        target_id=merchant.id,
        merchant_id=merchant.id,
        request=request,
    )
    await db.commit()
    return issue_merchant_token(merchant)


__all__ = ["change_password", "check_new_password", "login", "require_password_policy", "revoke_sessions", "sign_out_everywhere"]
