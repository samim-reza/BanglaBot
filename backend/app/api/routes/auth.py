from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.core import cache
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import Merchant, PlatformAdmin
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.merchant import MerchantOut
from app.schemas.platform import MerchantSelfUpdate, SignupRequest
from app.services import audit_service, billing_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Brute-force lockout: this many failures per username+IP within the window
# blocks further attempts until the window expires.
MAX_LOGIN_FAILURES = 5
LOCKOUT_SECONDS = 600
LOCKOUT_MESSAGE = "অনেকবার ভুল চেষ্টা হয়েছে — ১০ মিনিট পরে আবার চেষ্টা করুন"


def _lockout_key(role: str, username: str, request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"loginfail:{role}:{username.lower()}:{ip}"


async def _check_not_locked(key: str) -> None:
    count = await cache.get_json(key)
    if isinstance(count, int) and count >= MAX_LOGIN_FAILURES:
        raise HTTPException(429, LOCKOUT_MESSAGE)


async def _register_failure(key: str) -> None:
    if await cache.incr_with_ttl(key, LOCKOUT_SECONDS) >= MAX_LOGIN_FAILURES:
        raise HTTPException(429, LOCKOUT_MESSAGE)


@router.post("/signup", response_model=TokenResponse)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    settings_row = await billing_service.get_settings_row(db)
    if not settings_row.signup_enabled:
        raise HTTPException(403, "সাইন আপ বন্ধ আছে")
    exists = (
        await db.execute(select(Merchant).where(Merchant.username == body.username))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "এই ইউজারনেম আগে থেকেই আছে")
    merchant = Merchant(
        business_name=body.business_name,
        owner_name=body.owner_name,
        username=body.username,
        password_hash=hash_password(body.password),
        phone=body.phone,
        email=body.email,
    )
    db.add(merchant)
    try:
        await db.flush()
        await billing_service.start_trial(db, merchant, settings_row)
        audit_service.record(
            db,
            actor_role="merchant",
            actor_id=merchant.id,
            actor_name=merchant.business_name,
            action="signup",
            detail=f"{merchant.business_name} সাইন আপ করে ফ্রি ট্রায়াল শুরু করেছেন",
            merchant_id=merchant.id,
        )
        await db.commit()
    except IntegrityError:
        # Concurrent signup with the same username slipped past the pre-check.
        await db.rollback()
        raise HTTPException(409, "এই ইউজারনেম আগে থেকেই আছে")
    await db.refresh(merchant)
    return TokenResponse(
        access_token=create_access_token(merchant.id, "merchant"),
        role="merchant",
        name=merchant.business_name,
    )


@router.post("/login", response_model=TokenResponse)
async def merchant_login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    lockout_key = _lockout_key("merchant", body.username, request)
    await _check_not_locked(lockout_key)
    merchant = (
        await db.execute(select(Merchant).where(Merchant.username == body.username))
    ).scalar_one_or_none()
    if not merchant or not verify_password(body.password, merchant.password_hash):
        await _register_failure(lockout_key)
        raise HTTPException(401, "ভুল ইউজারনেম বা পাসওয়ার্ড")
    await cache.delete(lockout_key)
    if not merchant.active:
        raise HTTPException(403, "অ্যাকাউন্টটি নিষ্ক্রিয় করা হয়েছে")
    audit_service.record(
        db,
        actor_role="merchant",
        actor_id=merchant.id,
        actor_name=merchant.business_name,
        action="login",
        detail=f"{merchant.business_name} লগ ইন করেছেন",
        merchant_id=merchant.id,
    )
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(merchant.id, "merchant"),
        role="merchant",
        name=merchant.business_name,
    )


@router.post("/admin/login", response_model=TokenResponse)
async def admin_login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    lockout_key = _lockout_key("admin", body.username, request)
    await _check_not_locked(lockout_key)
    admin = (
        await db.execute(select(PlatformAdmin).where(PlatformAdmin.username == body.username))
    ).scalar_one_or_none()
    if not admin or not verify_password(body.password, admin.password_hash):
        await _register_failure(lockout_key)
        raise HTTPException(401, "ভুল ইউজারনেম বা পাসওয়ার্ড")
    await cache.delete(lockout_key)
    audit_service.record(
        db,
        actor_role="admin",
        actor_id=admin.id,
        actor_name=admin.name,
        action="login",
        detail=f"{admin.name} অ্যাডমিন প্যানেলে লগ ইন করেছেন",
    )
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(admin.id, "admin"), role="admin", name=admin.name
    )


@router.get("/me", response_model=MerchantOut)
async def me(merchant: Merchant = Depends(get_current_merchant)):
    return merchant


@router.patch("/me", response_model=MerchantOut)
async def update_me(
    body: MerchantSelfUpdate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    data.pop("current_password", None)
    password = data.pop("password", None)
    if password:
        if not body.current_password or not verify_password(
            body.current_password, merchant.password_hash
        ):
            raise HTTPException(400, "বর্তমান পাসওয়ার্ড সঠিক নয়")
        merchant.password_hash = hash_password(password)
    for field, value in data.items():
        setattr(merchant, field, value)
    await db.commit()
    await db.refresh(merchant)
    return merchant
