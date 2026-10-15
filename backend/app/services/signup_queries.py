"""The admin's signups list: newest first, keyset-paginated, with the account and payment state."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.cursor import decode_cursor, encode_cursor, page_size
from app.models import Merchant, Signup, Subscription
from app.services.signup_service import verify_url


def serialize(record: Signup, merchant: Merchant | None, sub: Subscription | None) -> dict[str, Any]:
    token = decrypt_secret(record.email_token_enc or "") if record.email_verified_at is None else ""
    return {
        "id": record.id,
        "merchant_id": record.merchant_id,
        "business_name": merchant.business_name if merchant else "",
        "owner_name": merchant.owner_name if merchant else "",
        "email": record.email,
        "phone": merchant.phone if merchant else "",
        "region": merchant.region if merchant else "",
        "vertical": record.vertical,
        "tier": record.tier,
        "status": record.status,
        "account_active": bool(merchant.active) if merchant else False,
        "email_verified": record.email_verified_at is not None,
        # No mail provider yet: the admin can pass the link on while the email is unverified.
        "verify_url": verify_url(token) if token else "",
        "paid_at": record.paid_at,
        "subscription": {
            "id": sub.id, "status": sub.status, "amount": float(sub.amount or 0), "currency": sub.currency, "interval": sub.interval,
        } if sub else None,
        "ip": record.ip,
        "admin_note": record.admin_note,
        "decided_by": record.decided_by,
        "decided_at": record.decided_at,
        "created_at": record.created_at,
    }


async def list_signups(db: AsyncSession, *, limit: int = 50, cursor: str = "", status: str = "") -> dict[str, Any]:
    """Raises ``ValueError`` for a malformed cursor."""
    size = page_size(limit)
    stmt = select(Signup)
    if status:
        stmt = stmt.where(Signup.status == status)
    if cursor:
        at, row_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Signup.created_at, Signup.id) < tuple_(at, row_id))
    rows = list(await db.scalars(stmt.order_by(Signup.created_at.desc(), Signup.id.desc()).limit(size + 1)))
    more = len(rows) > size
    rows = rows[:size]
    merchants: dict[str, Merchant] = {}
    subs: dict[str, Subscription] = {}
    if rows:
        merchants = {m.id: m for m in await db.scalars(select(Merchant).where(Merchant.id.in_([r.merchant_id for r in rows])))}
        sub_ids = [r.subscription_id for r in rows if r.subscription_id]
        if sub_ids:
            subs = {s.id: s for s in await db.scalars(select(Subscription).where(Subscription.id.in_(sub_ids)))}
    return {
        "items": [serialize(r, merchants.get(r.merchant_id), subs.get(r.subscription_id or "")) for r in rows],
        "next_cursor": encode_cursor(rows[-1].created_at, rows[-1].id) if more and rows else None,
    }


async def by_merchant(db: AsyncSession, merchant_id: str) -> Signup | None:
    return await db.scalar(select(Signup).where(Signup.merchant_id == merchant_id))


__all__ = ["by_merchant", "list_signups", "serialize"]
