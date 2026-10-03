"""Chat channels beyond the website widget: WhatsApp (via Twilio) and Facebook Messenger.

Every conversation runs the same :class:`~app.voice.text_session.TextSession`
as the website chat — same flow, fast paths, bookings and SMS confirmations.
A conversation is keyed by (account, channel, customer) and lives for the text
session's idle timeout; the next message after that starts a new one.

* WhatsApp: the account's WhatsApp sender (a Twilio WhatsApp number the admin
  assigns) posts each message to ``/twilio/whatsapp``; the reply goes back as
  TwiML in the same response.
* Messenger: the owner connects a Facebook Page (Page ID + Page access token);
  Meta posts to ``/api/meta/webhook`` and replies go out through the Send API.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
from typing import Any
from xml.sax.saxutils import escape

import httpx
import structlog
from sqlalchemy import select

from app.core.addons import entitlements
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.plans import CHANNEL_MESSENGER, CHANNEL_WHATSAPP
from app.db.session import AsyncSessionLocal
from app.flows.context import DIRECTION_INBOUND
from app.models import CallLog, Merchant
from app.verticals import flow_for
from app.voice import text_session

logger = structlog.get_logger(__name__)

GRAPH_URL = "https://graph.facebook.com"
#: Messenger rejects text over 2,000 characters; WhatsApp allows 1,600 per Twilio message.
MAX_REPLY_CHARS = {CHANNEL_MESSENGER: 2000, CHANNEL_WHATSAPP: 1600}
GREETING_ONLY = re.compile(r"^\s*(hi+|hello+|hey+|hiya|good (morning|afternoon|evening)|salam|assalamu ?alaikum|হ্যালো|সালাম)[\s!.,]*$", re.I)

_threads: dict[tuple[str, str, str], str] = {}
_client: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    """Shared client for the Graph API (swapped for a mock in tests)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    return _client


# --------------------------------------------------------------------------- account view
def settings_of(merchant: Any) -> dict[str, Any]:
    raw = getattr(merchant, "channel_settings", None)
    return {key: dict(value) for key, value in raw.items() if isinstance(value, dict)} if isinstance(raw, dict) else {}


def channel_view(merchant: Any) -> dict[str, Any]:
    """What the portal may show about the account's chat channels (never the tokens)."""
    config = settings_of(merchant)
    whatsapp = config.get("whatsapp") or {}
    messenger = config.get("messenger") or {}
    return {
        "whatsapp": {"number": str(whatsapp.get("number") or "")},
        "messenger": {
            "page_id": str(messenger.get("page_id") or ""),
            "page_name": str(messenger.get("page_name") or ""),
            "connected": bool(messenger.get("token_enc")),
        },
    }


def platform_status() -> dict[str, Any]:
    settings = get_settings()
    base = str(settings.public_base_url or "").rstrip("/")
    return {
        "whatsapp_ready": bool(settings.twilio_account_sid and settings.twilio_auth_token),
        "whatsapp_webhook": f"{base}/twilio/whatsapp" if base else "",
        "messenger_ready": bool(settings.meta_app_secret and settings.meta_verify_token),
        "messenger_webhook": f"{base}/api/meta/webhook" if base else "",
    }


def bare_number(value: str) -> str:
    return str(value or "").replace("whatsapp:", "").strip()


# --------------------------------------------------------------------------- conversations
async def _start(merchant: Merchant, channel: str, customer: str, caller_number: str) -> text_session.TextSession:
    from app.services.call_service import DbCallStore
    from app.services.context_service import build_context

    async with AsyncSessionLocal() as session:
        flow = flow_for(merchant, DIRECTION_INBOUND)
        log = CallLog(
            order_id=None,
            merchant_id=merchant.id,
            call_status="in-progress",
            language=merchant.language or "en",
            direction=channel,
            flow=flow.key,
            caller_number=caller_number,
        )
        session.add(log)
        await session.flush()
        ctx = await build_context(session, merchant, direction=DIRECTION_INBOUND, caller_number=caller_number)
        await session.commit()
    ctx.channel = "chat"
    store = DbCallStore(order_id="", call_log_id=log.id, merchant_id=merchant.id, currency=merchant.currency, source=channel)
    chat = text_session.TextSession(merchant=merchant, ctx=ctx, flow=flow, store=store, call_log_id=log.id)
    text_session.register(chat)
    _threads[(merchant.id, channel, customer)] = chat.id
    return chat


async def converse(merchant: Merchant, channel: str, customer: str, text: str, *, caller_number: str = "") -> list[str]:
    """One customer message in, the agent's reply messages out."""
    key = (merchant.id, channel, customer)
    chat = text_session.get(_threads.get(key, ""))
    if chat is None or chat.ended:
        chat = await _start(merchant, channel, customer, caller_number)
        opening = await chat.start()
        if GREETING_ONLY.match(text or ""):
            chat.transcript.append(("Customer", " ".join(text.split())))
            return opening
    replies = await chat.say(text)
    if chat.ended:
        _threads.pop(key, None)
    return replies


def _clip(messages: list[str], channel: str) -> list[str]:
    limit = MAX_REPLY_CHARS.get(channel, 1600)
    return [message[:limit] for message in messages if message.strip()]


# --------------------------------------------------------------------------- WhatsApp (Twilio)
async def whatsapp_merchant(to_number: str) -> Merchant | None:
    number = bare_number(to_number)
    if not number:
        return None
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(Merchant).where(Merchant.channel_settings["whatsapp"]["number"].astext == number, Merchant.active.is_(True))
        )


def twiml_messages(messages: list[str]) -> str:
    body = "".join(f"<Message>{escape(message)}</Message>" for message in _clip(messages, CHANNEL_WHATSAPP))
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'


async def handle_whatsapp(form: dict[str, str]) -> str:
    """Twilio's inbound WhatsApp message → TwiML with the agent's reply."""
    merchant = await whatsapp_merchant(form.get("To", ""))
    sender = bare_number(form.get("From", ""))
    text = str(form.get("Body") or "").strip()
    if merchant is None or not sender:
        await logger.awarning("whatsapp_unrouted", to=form.get("To", ""))
        return twiml_messages([])
    if not entitlements(merchant).has_channel(CHANNEL_WHATSAPP):
        await logger.ainfo("whatsapp_not_entitled", merchant=merchant.id)
        return twiml_messages([])
    if not text:
        return twiml_messages(["Sorry, I can only read text messages."])
    try:
        replies = await converse(merchant, CHANNEL_WHATSAPP, sender, text, caller_number=sender)
    except Exception as exc:  # noqa: BLE001 — a customer must get an answer
        await logger.awarning("whatsapp_turn_failed", merchant=merchant.id, error=str(exc))
        replies = ["Sorry, something went wrong on our side. Please try again in a moment."]
    return twiml_messages(replies)


# --------------------------------------------------------------------------- Messenger (Meta)
def verify_signature(body: bytes, header: str) -> bool:
    secret = str(get_settings().meta_app_secret or "")
    if not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(header or ""))


async def messenger_merchant(page_id: str) -> Merchant | None:
    if not page_id:
        return None
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(Merchant).where(Merchant.channel_settings["messenger"]["page_id"].astext == str(page_id), Merchant.active.is_(True))
        )


def _graph_version() -> str:
    return str(get_settings().meta_graph_version or "v21.0")


async def send_messenger(merchant: Any, recipient: str, messages: list[str]) -> None:
    token = decrypt(str((settings_of(merchant).get("messenger") or {}).get("token_enc") or ""))
    if not token:
        return
    for message in _clip(messages, CHANNEL_MESSENGER):
        response = await http().post(
            f"{GRAPH_URL}/{_graph_version()}/me/messages",
            params={"access_token": token},
            json={"recipient": {"id": recipient}, "messaging_type": "RESPONSE", "message": {"text": message}},
        )
        if response.status_code >= 400:
            await logger.awarning("messenger_send_failed", status=response.status_code, body=response.text[:300])
            return


async def _messenger_turn(merchant: Merchant, sender: str, text: str) -> None:
    try:
        replies = await converse(merchant, CHANNEL_MESSENGER, sender, text) if text else ["Sorry, I can only read text messages."]
        await send_messenger(merchant, sender, replies)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("messenger_turn_failed", merchant=merchant.id, error=str(exc))


async def handle_messenger(payload: dict[str, Any]) -> int:
    """Meta's webhook body → background turns (Meta wants a fast 200). Returns events accepted."""
    if payload.get("object") != "page":
        return 0
    accepted = 0
    for entry in payload.get("entry") or []:
        merchant = await messenger_merchant(str(entry.get("id") or ""))
        if merchant is None or not entitlements(merchant).has_channel(CHANNEL_MESSENGER):
            continue
        for event in entry.get("messaging") or []:
            message = event.get("message") or {}
            sender = str((event.get("sender") or {}).get("id") or "")
            if not sender or not message or message.get("is_echo"):
                continue
            asyncio.create_task(_messenger_turn(merchant, sender, str(message.get("text") or "").strip()))
            accepted += 1
    return accepted


async def connect_messenger(page_id: str, page_token: str) -> dict[str, Any]:
    """Check the Page token, subscribe the app to the Page's messages, return what to store."""
    version = _graph_version()
    page = await http().get(f"{GRAPH_URL}/{version}/{page_id}", params={"fields": "name", "access_token": page_token})
    if page.status_code >= 400:
        raise ValueError("Facebook did not accept that Page ID and token")
    subscribed = await http().post(
        f"{GRAPH_URL}/{version}/{page_id}/subscribed_apps",
        params={"subscribed_fields": "messages,messaging_postbacks", "access_token": page_token},
    )
    if subscribed.status_code >= 400:
        raise ValueError("The token works, but the app could not subscribe to the Page's messages")
    return {"page_id": str(page_id), "page_name": str(page.json().get("name") or ""), "token_enc": encrypt(page_token)}


__all__ = [
    "channel_view",
    "connect_messenger",
    "converse",
    "handle_messenger",
    "handle_whatsapp",
    "platform_status",
    "send_messenger",
    "settings_of",
    "twiml_messages",
    "verify_signature",
]
