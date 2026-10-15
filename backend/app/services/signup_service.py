"""Self-serve signup: account (inactive) + pending subscription + checkout link.

Abuse controls: rate limits per IP and per email, a honeypot field (bots get a
normal-looking answer and nothing is created), duplicate email / username
checks, the password policy, audit events. After the "paid" payment event the
signup waits for the admin — unless ``signup.auto_activate`` is on (optionally
also waiting for the verified email). No mail provider is wired: the
verification link is mailed when SMTP is configured, otherwise the admin sees it
in the signups list and passes it on.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta

import structlog
from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.addons import stored
from app.core.crypto import encrypt_secret, lookup_hash, lookup_hashes
from app.core.datetime_utils import utcnow
from app.core.ratelimit import client_ip, rate_limit
from app.core.regions import REGIONS, region_defaults
from app.core.security import hash_password
from app.db.base import new_id
from app.models import Merchant, Signup, Subscription
from app.schemas.signup import SignupIn
from app.services import audit_service, auth_service, catalog_plans, checkout_port, subscription_service
from app.services.pricing import QuoteError, build_quote

logger = structlog.get_logger(__name__)

EMAIL_TOKEN_PURPOSE = "signup-email"
EMAIL_TOKEN_DAYS = 7
VERIFY_PATH = "/signup/verify"
STATUS_PENDING_PAYMENT = "pending_payment"
STATUS_AWAITING_APPROVAL = "awaiting_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUSES = (STATUS_PENDING_PAYMENT, STATUS_AWAITING_APPROVAL, STATUS_APPROVED, STATUS_REJECTED)
INVALID_LINK = "This link is invalid or has expired"


def verify_url(token: str) -> str:
    return f"{checkout_port.frontend_base()}{VERIFY_PATH}?token={token}"


async def check_available(db: AsyncSession, *, email: str, username: str) -> None:
    taken = await db.scalar(select(Merchant.id).where(func.lower(Merchant.username) == username.lower()).limit(1))
    if taken:
        raise HTTPException(status_code=409, detail="That username is taken")
    taken = await db.scalar(select(Merchant.id).where(func.lower(Merchant.email) == email.lower()).limit(1))
    if taken:
        raise HTTPException(status_code=409, detail="An account with this email already exists — sign in instead")


async def _send_verification(merchant: Merchant, token: str) -> None:
    from app.core.email import send_email, smtp_configured

    if not smtp_configured():
        await logger.ainfo("signup_verification_pending", merchant=merchant.id, hint="link shown in the admin signups list")
        return
    body = f"Hi {merchant.owner_name},\n\nConfirm your email for {merchant.business_name}:\n{verify_url(token)}\n"
    try:
        await asyncio.to_thread(send_email, to=merchant.email, subject="Confirm your email", body=body)
    except Exception as exc:  # noqa: BLE001 — the admin can still pass the link on
        await logger.awarning("signup_verification_mail_failed", merchant=merchant.id, error=str(exc)[:200])


def _decoy() -> dict[str, str]:
    return {"checkout_url": "", "reference": new_id(), "status": STATUS_PENDING_PAYMENT}


async def signup(db: AsyncSession, request: Request, data: SignupIn) -> dict[str, str]:
    await rate_limit(request, "signup", max_hits=5, per_seconds=3600)
    if data.website:
        await logger.ainfo("signup_honeypot", ip=client_ip(request))
        return _decoy()
    await rate_limit(request, "signup-email", max_hits=3, per_seconds=86400, key=data.email)
    await catalog_plans.ensure_fresh()
    if data.vertical not in catalog_plans.offered_verticals():
        raise HTTPException(status_code=422, detail="That business type isn't open for signup")
    if data.region.upper() not in REGIONS:
        raise HTTPException(status_code=422, detail="Unknown region")
    username = data.username or data.email
    if len(username) > 80:
        raise HTTPException(status_code=422, detail="Choose a username (your email is too long to sign in with)")
    auth_service.require_password_policy(data.password, username=username, email=data.email)
    try:
        quote = build_quote(data.tier, data.interval, data.addons, vertical=data.vertical)
    except QuoteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await check_available(db, email=data.email, username=username)

    preset = region_defaults(data.region)
    merchant = Merchant(
        id=new_id(), business_name=data.business_name, owner_name=data.owner_name, username=username,
        password_hash=hash_password(data.password), phone=data.phone, email=data.email, vertical=data.vertical,
        vertical_config={}, knowledge="", inbound_number="", region=preset["region"], timezone=preset["timezone"],
        currency=preset["currency"], emergency_number=preset["emergency_number"], language="en",
        supported_languages=["en"], voice_persona="female", plan=quote.tier.key, addons=stored(quote.addons),
        widget_settings={}, active=False,
    )
    sub = subscription_service.from_quote(merchant.id, quote, kind=subscription_service.KIND_SIGNUP)
    token = secrets.token_urlsafe(32)
    record = Signup(
        id=new_id(), merchant_id=merchant.id, subscription_id=sub.id, email=data.email, status=STATUS_PENDING_PAYMENT,
        vertical=data.vertical, tier=quote.tier.key, email_token_hash=lookup_hash(token, purpose=EMAIL_TOKEN_PURPOSE),
        email_token_enc=encrypt_secret(token), ip=client_ip(request),
    )
    db.add(merchant)
    await db.flush()  # the account row first: the other rows reference it
    db.add(sub)
    db.add(record)
    if quote.total > 0:
        try:
            checkout = await checkout_port.create_checkout(
                db, merchant_id=merchant.id, subscription_id=sub.id, amount=sub.amount, currency=sub.currency,
                description=f"{quote.tier.name} plan ({quote.interval}ly)", return_path=checkout_port.SIGNUP_RETURN_PATH,
            )
        except checkout_port.PaymentsUnavailable as exc:
            await db.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        sub.payment_provider, sub.payment_ref, url = checkout.provider, checkout.payment_id, checkout.url
    else:
        now = utcnow()
        await subscription_service.activate(db, sub, now=now, provider="free", payment_ref="")
        await on_subscription_active(db, sub, now=now)
        url = checkout_port.return_url(checkout_port.SIGNUP_RETURN_PATH, sub.id)
    audit_service.stage(
        db, action="signup.created", actor_type=audit_service.ACTOR_MERCHANT, actor_id=merchant.id, target_type="merchant",
        target_id=merchant.id, merchant_id=merchant.id, request=request,
        meta={"tier": quote.tier.key, "interval": quote.interval, "vertical": data.vertical, "total": str(quote.total)},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="That username or email is already registered") from exc
    await _send_verification(merchant, token)
    return {"checkout_url": url, "reference": sub.id, "status": record.status}


# --------------------------------------------------------------------------- after signup
async def verify_email(db: AsyncSession, request: Request, token: str, *, now: datetime | None = None) -> dict[str, object]:
    await rate_limit(request, "signup-verify", max_hits=20, per_seconds=3600)
    moment = now or utcnow()
    record = await db.scalar(select(Signup).where(Signup.email_token_hash.in_(lookup_hashes(token, purpose=EMAIL_TOKEN_PURPOSE))))
    if record is None or record.status == STATUS_REJECTED:
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    if record.email_verified_at is None:
        created = record.created_at or moment
        if created + timedelta(days=EMAIL_TOKEN_DAYS) < moment:
            raise HTTPException(status_code=400, detail=INVALID_LINK)
        record.email_verified_at = moment
        record.email_token_enc = ""
        audit_service.stage(db, action="signup.email_verified", actor_type=audit_service.ACTOR_MERCHANT, actor_id=record.merchant_id,
                            target_type="merchant", target_id=record.merchant_id, merchant_id=record.merchant_id, request=request)
        await maybe_activate(db, record, now=moment)
        await db.commit()
    return {"verified": True, "status": record.status}


async def on_subscription_active(db: AsyncSession, sub: Subscription, *, now: datetime) -> None:
    """A signup's subscription was paid: wait for approval, or go live (``signup.auto_activate``)."""
    if sub.kind != subscription_service.KIND_SIGNUP:
        return
    record = await db.scalar(select(Signup).where(Signup.subscription_id == sub.id))
    if record is None or record.status in (STATUS_APPROVED, STATUS_REJECTED):
        return
    record.paid_at = now
    record.status = STATUS_AWAITING_APPROVAL
    await maybe_activate(db, record, now=now)


async def maybe_activate(db: AsyncSession, record: Signup, *, now: datetime) -> None:
    settings = catalog_plans.signup_settings()
    if record.status != STATUS_AWAITING_APPROVAL or not settings["auto_activate"]:
        return
    if settings["require_verified_email"] and record.email_verified_at is None:
        return
    await approve(db, record, by="system", now=now)


async def approve(db: AsyncSession, record: Signup, *, by: str, now: datetime | None = None, note: str = "", mark_paid: bool = False) -> Signup:
    if record.status == STATUS_APPROVED:
        raise HTTPException(status_code=409, detail="Already approved")
    moment = now or utcnow()
    merchant = await db.get(Merchant, record.merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Account not found")
    sub = await db.get(Subscription, record.subscription_id) if record.subscription_id else None
    if mark_paid and sub is not None and sub.status == subscription_service.STATUS_PENDING:
        await subscription_service.activate(db, sub, now=moment, provider="manual", payment_ref=f"manual:{by}"[:255])
        record.paid_at = moment
    merchant.active = True
    record.status, record.decided_by, record.decided_at = STATUS_APPROVED, str(by)[:80], moment
    record.admin_note = note.strip()
    return record


async def reject(db: AsyncSession, record: Signup, *, by: str, now: datetime | None = None, note: str = "") -> Signup:
    """The account stays disabled; its subscription is cancelled (a paid one needs a manual refund)."""
    if record.status == STATUS_APPROVED:
        raise HTTPException(status_code=409, detail="Already approved — disable the account instead")
    moment = now or utcnow()
    sub = await db.get(Subscription, record.subscription_id) if record.subscription_id else None
    if sub is not None and sub.status != subscription_service.STATUS_CANCELLED:
        sub.status, sub.cancelled_at = subscription_service.STATUS_CANCELLED, moment
    record.status, record.decided_by, record.decided_at = STATUS_REJECTED, str(by)[:80], moment
    record.admin_note = note.strip()
    return record


async def status_of(db: AsyncSession, reference: str) -> dict[str, object]:
    """What the "thanks" page shows after checkout (reference = the subscription id)."""
    record = await db.scalar(select(Signup).where(Signup.subscription_id == reference)) if reference else None
    if record is None:
        raise HTTPException(status_code=404, detail="Signup not found")
    return {"status": record.status, "email_verified": record.email_verified_at is not None, "paid": record.paid_at is not None}


__all__ = [
    "STATUSES",
    "approve",
    "check_available",
    "maybe_activate",
    "on_subscription_active",
    "reject",
    "signup",
    "status_of",
    "verify_email",
    "verify_url",
]
