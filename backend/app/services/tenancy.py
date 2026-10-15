"""Tenant isolation: an account only ever sees its own rows.

``owned`` loads one row by id and answers 404 — never 403, so ids of other
accounts can't be probed — when it is missing or belongs to another account.
``scoped`` adds the ``merchant_id`` filter to a list query.
"""

from __future__ import annotations

from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


def _merchant_id(merchant_or_id: Any) -> str:
    value = getattr(merchant_or_id, "id", merchant_or_id)
    return str(value or "")


async def owned(db: AsyncSession, model: type[T], obj_id: Any, merchant_id: Any, *, detail: str = "Not found") -> T:
    """The ``model`` row ``obj_id`` if it belongs to ``merchant_id`` (an id or a Merchant), else 404."""
    owner = _merchant_id(merchant_id)
    if not obj_id or not owner:
        raise HTTPException(status_code=404, detail=detail)
    row = await db.get(model, str(obj_id))
    if row is None or str(getattr(row, "merchant_id", "") or "") != owner:
        raise HTTPException(status_code=404, detail=detail)
    return row


def scoped(stmt: Any, model: Any, merchant_id: Any) -> Any:
    """``stmt`` limited to one account's rows."""
    return stmt.where(model.merchant_id == _merchant_id(merchant_id))


__all__ = ["owned", "scoped"]
