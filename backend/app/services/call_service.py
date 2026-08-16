"""Originates Twilio confirmation calls and applies call-status updates."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client as TwilioClient

from app.core import cache
from app.core.config import get_settings
from app.models import CallLog, Merchant, Order, OrderStatus
from app.services import voice_tiers

# Extra time past the call cap before a "calling" order counts as stale.
STALE_CALL_GRACE_SECONDS = 120

# Twilio statuses meaning the call is still live (leave the order alone).
LIVE_CALL_STATUSES = ("queued", "initiated", "ringing", "in-progress")


def call_time_limit(merchant: Merchant) -> int:
    """The merchant's own cap on one call, falling back to the platform default."""
    return merchant.max_call_seconds or get_settings().max_call_seconds


def twilio_client() -> TwilioClient:
    settings = get_settings()
    return TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)


def normalize_bd_phone(phone: str) -> str:
    """Normalize a Bangladeshi number to E.164 (+880...)."""
    digits = phone.strip().replace(" ", "").replace("-", "")
    if digits.startswith("+"):
        return digits
    if digits.startswith("880"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+880{digits[1:]}"
    return f"+880{digits}"


async def start_confirmation_call(db: AsyncSession, order: Order, merchant: Merchant) -> CallLog:
    settings = get_settings()
    if not settings.public_base_url:
        raise HTTPException(500, "PUBLIC_BASE_URL is not set (start ngrok and update .env)")
    if order.status == OrderStatus.calling:
        raise HTTPException(409, "এই অর্ডারের জন্য একটি কল ইতিমধ্যে চলছে")

    base = settings.public_base_url.rstrip("/")
    try:
        call = twilio_client().calls.create(
            to=normalize_bd_phone(order.customer_phone),
            from_=settings.twilio_phone_number,
            url=f"{base}/twilio/twiml/{order.id}",
            method="POST",
            status_callback=f"{base}/twilio/status/{order.id}",
            status_callback_event=["completed", "no-answer", "busy", "failed"],
            record=True,
            recording_status_callback=f"{base}/twilio/recording/{order.id}",
            recording_status_callback_event=["completed"],
            time_limit=call_time_limit(merchant),
        )
    except Exception as exc:  # noqa: BLE001 — order must not get stuck in "calling"
        logger.error(f"Twilio call create failed for order {order.id}: {exc}")
        raise HTTPException(502, "কল শুরু করা যায়নি — একটু পরে আবার চেষ্টা করুন")
    logger.info(f"Started confirmation call {call.sid} for order {order.id}")

    log = CallLog(
        order_id=order.id,
        merchant_id=order.merchant_id,
        twilio_call_sid=call.sid,
        call_status="initiated",
        # Snapshot the tier now: a later tier change must not reprice this call.
        voice_tier=merchant.voice_tier or voice_tiers.DEFAULT_TIER_KEY,
    )
    order.status = OrderStatus.calling
    order.call_attempts += 1
    order.last_call_at = datetime.now(timezone.utc)
    db.add(log)
    await db.commit()
    await db.refresh(log)
    await cache.delete_prefix(f"insights:{order.merchant_id}:")
    return log


async def apply_status_callback(
    db: AsyncSession, order_id: str, call_sid: str, call_status: str, duration: int
) -> None:
    """Handle Twilio's final call status; settle orders stuck in 'calling'."""
    log = (
        await db.execute(select(CallLog).where(CallLog.twilio_call_sid == call_sid))
    ).scalar_one_or_none()
    if log:
        log.call_status = call_status
        log.duration_secs = duration
        # Plan-quota charge: duration × the call's snapshotted voice-tier multiplier.
        log.billed_secs = voice_tiers.billed_seconds(duration, log.voice_tier)
        # Automatic cost attribution: price the finished call at current rates.
        from app.services import finance_service

        await finance_service.compute_call_cost(db, log)

    order = await db.get(Order, order_id)
    if order and order.status == OrderStatus.calling:
        if call_status in ("no-answer", "busy", "failed", "canceled"):
            order.status = OrderStatus.no_answer
        elif call_status == "completed" and not (log and log.outcome):
            # Call happened but the agent recorded no clear outcome.
            order.status = OrderStatus.needs_review
    await db.commit()
    if log:
        await cache.delete_prefix(f"insights:{log.merchant_id}:")


async def reconcile_stale_calls(db: AsyncSession, merchant: Merchant) -> int:
    """Settle orders stuck in "calling" whose Twilio status callback never arrived.

    A call cannot outlive its time_limit, so any order still "calling" well past
    that cap is stale (lost webhook — e.g. the ngrok URL changed mid-call). We ask
    Twilio for the call's real status and settle the order the same way the
    status callback would have. Returns the number of orders settled.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=call_time_limit(merchant) + STALE_CALL_GRACE_SECONDS
    )
    stuck = (
        (
            await db.execute(
                select(Order).where(
                    Order.merchant_id == merchant.id,
                    Order.status == OrderStatus.calling,
                    Order.last_call_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    if not stuck:
        return 0

    from app.services import finance_service

    settled = 0
    for order in stuck:
        log = (
            await db.execute(
                select(CallLog)
                .where(CallLog.order_id == order.id)
                .order_by(CallLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        call_status, duration = "", 0
        if log and log.twilio_call_sid:
            try:
                call = twilio_client().calls(log.twilio_call_sid).fetch()
                call_status = str(call.status or "")
                duration = int(call.duration or 0)
            except Exception as exc:  # noqa: BLE001 — settle anyway, the call is long over
                logger.warning(f"Stale-call lookup failed for {log.twilio_call_sid}: {exc}")
        if call_status in LIVE_CALL_STATUSES:
            continue  # genuinely still running (merchant cap raised recently?)

        if log:
            if call_status:
                log.call_status = call_status
            if duration:
                log.duration_secs = duration
                log.billed_secs = voice_tiers.billed_seconds(duration, log.voice_tier)
                await finance_service.compute_call_cost(db, log)
        if call_status in ("no-answer", "busy", "failed", "canceled"):
            order.status = OrderStatus.no_answer
        else:
            # Completed without a recorded outcome, or Twilio unreachable.
            order.status = OrderStatus.needs_review
        settled += 1
        logger.info(
            f"Settled stale calling order {order.id} (twilio status: {call_status or 'unknown'})"
        )
    if settled:
        await db.commit()
        await cache.delete_prefix(f"insights:{merchant.id}:")
    return settled
