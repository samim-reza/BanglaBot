"""FastAPI dependencies: the logged-in merchant, or the platform admin.

``Depends(require_admin)`` admits any active admin; ``Depends(require_admin("superadmin",
"support"))`` only those roles. Both resolve to an ``AdminPrincipal``.
"""

from __future__ import annotations

import inspect

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ADMIN_ROLES, MERCHANT_ROLE, TYP_SESSION, bearer_payload, require_roles, token_version
from app.db.session import get_db
from app.models import Merchant
from app.services import admin_auth_service
from app.services.admin_user_service import AdminPrincipal

#: Role claim of admin tokens issued before admin users had roles (read as superadmin).
ADMIN_ROLE = "admin"
SESSION_EXPIRED = "Session expired — sign in again"


async def get_current_merchant(
    payload: dict = Depends(bearer_payload),
    db: AsyncSession = Depends(get_db),
) -> Merchant:
    if payload.get("typ") != TYP_SESSION:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    require_roles(payload, {MERCHANT_ROLE})
    merchant = await db.get(Merchant, str(payload.get("sub") or ""))
    if merchant is None:
        raise HTTPException(status_code=401, detail="Merchant account not found")
    if token_version(payload) != int(getattr(merchant, "token_version", 0) or 0):
        raise HTTPException(status_code=401, detail=SESSION_EXPIRED)
    if not merchant.active:
        raise HTTPException(status_code=403, detail="Merchant account is disabled")
    return merchant


class AdminGuard:
    """A dependency resolving the signed-in admin, optionally limited to some roles.

    The same object works both as ``Depends(require_admin)`` and, called with role
    names, as a factory: ``Depends(require_admin("superadmin"))``. FastAPI reads the
    explicit ``__signature__`` below and awaits the call (``markcoroutinefunction``).
    """

    __signature__ = inspect.Signature(
        [
            inspect.Parameter("payload", inspect.Parameter.KEYWORD_ONLY, default=Depends(bearer_payload), annotation=dict),
            inspect.Parameter("db", inspect.Parameter.KEYWORD_ONLY, default=Depends(get_db), annotation=AsyncSession),
        ]
    )

    def __init__(self, roles: tuple[str, ...] = ()) -> None:
        self.roles = tuple(roles)

    def __repr__(self) -> str:
        return f"require_admin{self.roles!r}"

    @inspect.markcoroutinefunction
    def __call__(self, *roles: str, payload: dict | None = None, db: AsyncSession | None = None):
        if payload is None:
            unknown = sorted(set(roles) - set(ADMIN_ROLES))
            if unknown or not roles:
                raise ValueError(f"require_admin() takes admin roles ({', '.join(ADMIN_ROLES)}), got {roles!r}")
            return AdminGuard(tuple(roles))
        return admin_auth_service.resolve(db, payload, self.roles)


require_admin = AdminGuard()

__all__ = ["ADMIN_ROLE", "MERCHANT_ROLE", "AdminGuard", "AdminPrincipal", "get_current_merchant", "require_admin"]
