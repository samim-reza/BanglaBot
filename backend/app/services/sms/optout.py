"""SMS opt-outs (US carrier / CTIA / 10DLC rules): the reply keywords, the opt-out list,
and the "Reply STOP to opt out." notice on an account's first text to a number.

An opt-out is kept per (our sending number, customer number) and remembers the account
it was meant for: texts from that number, or from that account, to the customer are
skipped (and logged as skipped) until they reply START.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.models import Message, SmsOptOut

STOP_WORDS = frozenset({"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"})
START_WORDS = frozenset({"START", "UNSTOP", "YES"})
HELP_WORDS = frozenset({"HELP", "INFO"})
#: A keyword is the whole reply (punctuation and spaces aside): "Stop." / "stop all" count,
#: "cancel my appointment" does not.
MAX_KEYWORD_CHARS = 24

NOTICE = "Reply STOP to opt out."
OPTED_OUT = "Opted out: this number replied STOP (texts resume if it replies START)."
#: Statuses of a text that actually went out (a skipped / failed one doesn't count as "texted before").
WENT_OUT = ("queued", "sent", "delivered", "read", "undelivered")
SEGMENT = 160
_CALL_LINE = re.compile(r"\s*Call \+?[\d\s().-]{6,} to change\.")


# ------------------------------------------------------------------ keywords (pure)
def keyword_of(text: Any) -> str:
    """The reply as a keyword candidate: letters only, upper-case ("" when it's a sentence)."""
    raw = str(text or "").strip()
    if not raw or len(raw) > MAX_KEYWORD_CHARS:
        return ""
    return re.sub(r"[^A-Z]", "", raw.upper())


def action_of(text: Any) -> str:
    """``stop`` | ``start`` | ``help`` for a keyword reply, else ""."""
    word = keyword_of(text)
    if word in STOP_WORDS:
        return "stop"
    if word in START_WORDS:
        return "start"
    if word in HELP_WORDS:
        return "help"
    return ""


def canonical(number: Any) -> str:
    """``+15551234567`` from any formatting ("" when there are no digits)."""
    digits = re.sub(r"\D", "", str(number or ""))
    return f"+{digits}" if digits else ""


# ------------------------------------------------------------------ the notice (pure)
def with_notice(body: str, *, may_drop_call_line: bool = False) -> str:
    """``body`` + " Reply STOP to opt out." — kept to one 160-character segment when the body
    fits one: the "Call ... to change." line makes room when ``may_drop_call_line`` (the
    account texts from its own number, which customers can call back)."""
    text = str(body or "").rstrip()
    if not text or "reply stop" in text.lower():
        return text
    joined = f"{text} {NOTICE}"
    if len(joined) <= SEGMENT or len(text) > SEGMENT or not may_drop_call_line:
        return joined
    trimmed = _CALL_LINE.sub("", text).rstrip()
    if trimmed != text and len(f"{trimmed} {NOTICE}") <= SEGMENT:
        return f"{trimmed} {NOTICE}"
    return joined


def help_text(business: str, phone: str = "") -> str:
    """The HELP reply: who is texting, how to reach them, how to stop (one segment)."""
    contact = f" Call {phone}." if phone else ""
    tail = f" Msg&data rates may apply. {NOTICE}"
    room = SEGMENT - len(f": booking & order texts.{contact}{tail}")
    name = (business or "Callisa").strip()[: max(10, room)].strip()
    return f"{name}: booking & order texts.{contact}{tail}"


# ------------------------------------------------------------------ the list (DB, caller's session)
def sender_for(merchant: Any) -> str:
    """The number an account's texts go out from (as ``telnyx.send_sms`` picks it)."""
    from app.services import telnyx

    settings = get_settings()
    return canonical(telnyx.number_for(merchant) or settings.telnyx_sms_from or settings.telnyx_from_number or "")


async def is_opted_out(session: Any, *, sender: str, phone: str, merchant_id: str = "") -> bool:
    phone = canonical(phone)
    if not phone:
        return False
    scope = [SmsOptOut.sender_number == canonical(sender)]
    if merchant_id:
        scope.append(SmsOptOut.merchant_id == merchant_id)
    found = await session.scalar(select(SmsOptOut.id).where(SmsOptOut.phone == phone, or_(*scope)).limit(1))
    return found is not None


async def has_texted(session: Any, *, merchant_id: str, phone: str) -> bool:
    """Has this account already texted this number (anything that went out)?"""
    found = await session.scalar(
        select(Message.id).where(Message.merchant_id == merchant_id, Message.to_number == phone, Message.status.in_(WENT_OUT)).limit(1)
    )
    return found is not None


async def record(session: Any, *, sender: str, phone: str, merchant_id: str | None, keyword: str) -> None:
    """Add (or refresh) an opt-out; the caller commits."""
    values = {"sender_number": canonical(sender), "phone": canonical(phone), "merchant_id": merchant_id or None, "keyword": keyword[:16]}
    stmt = pg_insert(SmsOptOut).values(**values)
    await session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_sms_opt_outs_sender_phone",
            set_={"merchant_id": stmt.excluded.merchant_id, "keyword": stmt.excluded.keyword, "created_at": utcnow()},
        )
    )


async def remove(session: Any, *, sender: str, phone: str, merchant_id: str | None = None) -> None:
    """START: texts from this number (and from ``merchant_id``'s account, which an opt-out also
    covers) to them resume; the caller commits."""
    scope = [SmsOptOut.sender_number == canonical(sender)]
    if merchant_id:
        scope.append(SmsOptOut.merchant_id == merchant_id)
    await session.execute(delete(SmsOptOut).where(SmsOptOut.phone == canonical(phone), or_(*scope)))


__all__ = [
    "HELP_WORDS", "NOTICE", "OPTED_OUT", "START_WORDS", "STOP_WORDS", "action_of", "canonical", "has_texted", "help_text",
    "is_opted_out", "keyword_of", "record", "remove", "sender_for", "with_notice",
]
