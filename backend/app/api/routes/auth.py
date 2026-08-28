"""Merchant login and self-service settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MERCHANT_ROLE, get_current_merchant
from app.core.security import hash_password, sign_token, verify_password
from app.db.session import get_db
from app.flows.ecommerce import flow_preview_steps
from app.models import Merchant
from app.schemas.auth import ChangePasswordRequest, FlowPreview, LoginRequest, MerchantLoginResponse
from app.schemas.merchant import MerchantOut, MerchantSettingsUpdate

router = APIRouter(prefix="/api/auth", tags=["auth"])


def merchant_out(merchant: Merchant) -> MerchantOut:
    return MerchantOut.model_validate(merchant)


def apply_settings(merchant: Merchant, data: MerchantSettingsUpdate) -> None:
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        setattr(merchant, key, value)
    if merchant.language not in (merchant.supported_languages or []):
        merchant.supported_languages = [merchant.language] + [
            code for code in (merchant.supported_languages or []) if code != merchant.language
        ]


@router.post("/login", response_model=MerchantLoginResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    merchant = await db.scalar(select(Merchant).where(Merchant.username == data.username.strip()))
    if merchant is None or not verify_password(data.password, merchant.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not merchant.active:
        raise HTTPException(status_code=403, detail="Merchant account is disabled")
    token = sign_token({"sub": merchant.id, "role": MERCHANT_ROLE, "username": merchant.username})
    return MerchantLoginResponse(token=token, merchant=merchant_out(merchant))


@router.get("/me", response_model=MerchantOut)
async def me(merchant: Merchant = Depends(get_current_merchant)):
    return merchant_out(merchant)


@router.patch("/me", response_model=MerchantOut)
async def update_me(
    data: MerchantSettingsUpdate,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    apply_settings(merchant, data)
    await db.commit()
    await db.refresh(merchant)
    return merchant_out(merchant)


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, merchant.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    merchant.password_hash = hash_password(data.new_password)
    await db.commit()
    return {"ok": True}


@router.get("/flow-preview", response_model=FlowPreview)
async def flow_preview(merchant: Merchant = Depends(get_current_merchant)):
    return FlowPreview(steps=flow_preview_steps(merchant))
