"""Auth dependencies: resolve the current merchant or platform admin from JWT."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models import Merchant, PlatformAdmin

bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated"):
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


def _payload(creds: HTTPAuthorizationCredentials | None) -> dict:
    if not creds:
        raise _unauthorized()
    try:
        return decode_token(creds.credentials)
    except Exception:
        raise _unauthorized("Invalid or expired token")


async def get_current_merchant(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Merchant:
    payload = _payload(creds)
    if payload.get("role") != "merchant":
        raise _unauthorized("Merchant account required")
    merchant = await db.get(Merchant, payload.get("sub"))
    if not merchant or not merchant.active:
        raise _unauthorized("Account not found or disabled")
    return merchant


async def get_current_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> PlatformAdmin:
    payload = _payload(creds)
    if payload.get("role") != "admin":
        raise _unauthorized("Admin account required")
    admin = await db.get(PlatformAdmin, payload.get("sub"))
    if not admin:
        raise _unauthorized("Admin not found")
    return admin
