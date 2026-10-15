"""Instagram DM and WhatsApp via Meta's Cloud API — both through the platform's Meta app.

Same pattern as Messenger (``channel_service``): Meta posts to ``/api/meta/webhook``
(``X-Hub-Signature-256`` with the app secret, ``hub.verify_token`` on setup), each
message runs a turn of the shared text-session agent in the background, and the
reply goes out through the Graph API. Both stay off until the owner connects them
and the account has the channel (Instagram add-on / WhatsApp add-on).

* Instagram: ``object="instagram"``; the owner connects the Instagram professional
  account id + the linked Page's access token; replies via ``/me/messages``.
* WhatsApp Cloud: ``object="whatsapp_business_account"``; the owner connects the
  WhatsApp phone number id + a (system-user) access token; replies via
  ``/{phone_number_id}/messages``. The Twilio WhatsApp sender keeps working too.

Tokens are stored with ``encrypt_secret`` under ``channel_settings["instagram"]`` /
``channel_settings["whatsapp_cloud"]``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.entitlements import entitlements
from app.core.plans import CHANNEL_INSTAGRAM, CHANNEL_WHATSAPP
from app.db.session import AsyncSessionLocal
from app.models import Merchant
from app.services import channel_service

logger = structlog.get_logger(__name__)

INSTAGRAM = "instagram"
WHATSAPP_CLOUD = "whatsapp_cloud"
#: settings key → the field a merchant is found by.
LOOKUP_FIELD = {INSTAGRAM: "account_id", WHATSAPP_CLOUD: "phone_number_id"}
MAX_CHARS = {INSTAGRAM: 1000, WHATSAPP_CLOUD: 4096}
TEXT_ONLY = "Sorry, I can only read text messages."
_tasks: set[asyncio.Task] = set()


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def config(merchant: Any, kind: str) -> dict[str, Any]:
    return channel_service.settings_of(merchant).get(kind) or {}


def view(merchant: Any) -> dict[str, Any]:
    """What the portal may show (never the tokens)."""
    instagram, cloud = config(merchant, INSTAGRAM), config(merchant, WHATSAPP_CLOUD)
    return {
        "instagram": {
            "account_id": str(instagram.get("account_id") or ""),
            "username": str(instagram.get("username") or ""),
            "connected": bool(instagram.get("token_enc")),
        },
        "whatsapp_cloud": {
            "phone_number_id": str(cloud.get("phone_number_id") or ""),
            "display_number": str(cloud.get("display_number") or ""),
            "name": str(cloud.get("name") or ""),
            "connected": bool(cloud.get("token_enc")),
        },
    }


def platform_status() -> dict[str, Any]:
    settings = get_settings()
    base = str(settings.public_base_url or "").rstrip("/")
    ready = bool(settings.meta_app_secret and settings.meta_verify_token)
    webhook = f"{base}/api/meta/webhook" if base else ""
    return {"instagram_ready": ready, "instagram_webhook": webhook, "whatsapp_cloud_ready": ready, "whatsapp_cloud_webhook": webhook}


def _graph() -> str:
    return f"{channel_service.GRAPH_URL}/{get_settings().meta_graph_version or 'v21.0'}"


def _clip(messages: list[str], kind: str) -> list[str]:
    return [message[: MAX_CHARS[kind]] for message in messages if message.strip()]


# --------------------------------------------------------------------------- accounts
async def find_merchant(kind: str, value: str) -> Merchant | None:
    if not value:
        return None
    column = Merchant.channel_settings[kind][LOOKUP_FIELD[kind]].astext
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(Merchant).where(column == str(value), Merchant.active.is_(True)))


async def taken(db: AsyncSession, kind: str, value: str, merchant_id: str) -> bool:
    """Another account already connected this Instagram account / WhatsApp number."""
    column = Merchant.channel_settings[kind][LOOKUP_FIELD[kind]].astext
    return await db.scalar(select(Merchant.id).where(column == str(value), Merchant.id != merchant_id).limit(1)) is not None


async def connect_instagram(account_id: str, page_token: str) -> dict[str, Any]:
    """Check the token against the Instagram account; return what to store."""
    response = await channel_service.http().get(f"{_graph()}/{account_id}", params={"fields": "username", "access_token": page_token})
    if response.status_code >= 400:
        raise ValueError("Meta did not accept that Instagram account ID and token")
    return {"account_id": str(account_id), "username": str(response.json().get("username") or ""), "token_enc": encrypt_secret(page_token)}


async def connect_whatsapp_cloud(phone_number_id: str, access_token: str) -> dict[str, Any]:
    response = await channel_service.http().get(
        f"{_graph()}/{phone_number_id}",
        params={"fields": "display_phone_number,verified_name"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code >= 400:
        raise ValueError("Meta did not accept that phone number ID and token")
    data = response.json()
    return {
        "phone_number_id": str(phone_number_id),
        "display_number": str(data.get("display_phone_number") or ""),
        "name": str(data.get("verified_name") or ""),
        "token_enc": encrypt_secret(access_token),
    }


# --------------------------------------------------------------------------- sending
async def send_instagram(merchant: Any, recipient: str, messages: list[str]) -> None:
    token = decrypt_secret(str(config(merchant, INSTAGRAM).get("token_enc") or ""))
    if not token:
        return
    for message in _clip(messages, INSTAGRAM):
        response = await channel_service.http().post(
            f"{_graph()}/me/messages",
            params={"access_token": token},
            json={"recipient": {"id": recipient}, "messaging_type": "RESPONSE", "message": {"text": message}},
        )
        if response.status_code >= 400:
            await logger.awarning("instagram_send_failed", status=response.status_code, body=response.text[:300])
            return


async def send_whatsapp_cloud(merchant: Any, to: str, messages: list[str]) -> None:
    cloud = config(merchant, WHATSAPP_CLOUD)
    token = decrypt_secret(str(cloud.get("token_enc") or ""))
    number_id = str(cloud.get("phone_number_id") or "")
    if not token or not number_id:
        return
    for message in _clip(messages, WHATSAPP_CLOUD):
        response = await channel_service.http().post(
            f"{_graph()}/{number_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "text",
                  "text": {"preview_url": False, "body": message}},
        )
        if response.status_code >= 400:
            await logger.awarning("whatsapp_cloud_send_failed", status=response.status_code, body=response.text[:300])
            return


# --------------------------------------------------------------------------- inbound
async def _instagram_turn(merchant: Merchant, sender: str, text: str) -> None:
    try:
        replies = await channel_service.converse(merchant, CHANNEL_INSTAGRAM, sender, text) if text else [TEXT_ONLY]
        await send_instagram(merchant, sender, replies)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("instagram_turn_failed", merchant=merchant.id, error=str(exc))


async def _whatsapp_turn(merchant: Merchant, sender: str, text: str) -> None:
    caller = f"+{sender.lstrip('+')}"
    try:
        replies = await channel_service.converse(merchant, CHANNEL_WHATSAPP, caller, text, caller_number=caller) if text else [TEXT_ONLY]
        await send_whatsapp_cloud(merchant, sender, replies)
    except Exception as exc:  # noqa: BLE001
        await logger.awarning("whatsapp_cloud_turn_failed", merchant=merchant.id, error=str(exc))


async def handle_instagram(payload: dict[str, Any]) -> int:
    accepted = 0
    for entry in payload.get("entry") or []:
        account_id = str(entry.get("id") or "")
        merchant = await find_merchant(INSTAGRAM, account_id)
        if merchant is None or not entitlements(merchant).has_channel(CHANNEL_INSTAGRAM):
            continue
        for event in entry.get("messaging") or []:
            message = event.get("message") or {}
            sender = str((event.get("sender") or {}).get("id") or "")
            if not sender or sender == account_id or not message or message.get("is_echo"):
                continue
            _spawn(_instagram_turn(merchant, sender, str(message.get("text") or "").strip()))
            accepted += 1
    return accepted


async def handle_whatsapp_cloud(payload: dict[str, Any]) -> int:
    accepted = 0
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            if change.get("field") != "messages" or not value.get("messages"):
                continue  # delivery / read statuses
            merchant = await find_merchant(WHATSAPP_CLOUD, str((value.get("metadata") or {}).get("phone_number_id") or ""))
            if merchant is None or not entitlements(merchant).has_channel(CHANNEL_WHATSAPP):
                continue
            for message in value.get("messages") or []:
                sender = str(message.get("from") or "")
                if not sender:
                    continue
                text = str((message.get("text") or {}).get("body") or "").strip() if message.get("type") == "text" else ""
                _spawn(_whatsapp_turn(merchant, sender, text))
                accepted += 1
    return accepted


async def handle(payload: dict[str, Any]) -> int:
    """Meta webhook body (already signature-checked) → background turns; returns events accepted."""
    kind = payload.get("object")
    if kind == "instagram":
        return await handle_instagram(payload)
    if kind == "whatsapp_business_account":
        return await handle_whatsapp_cloud(payload)
    return 0


__all__ = [
    "INSTAGRAM",
    "WHATSAPP_CLOUD",
    "connect_instagram",
    "connect_whatsapp_cloud",
    "find_merchant",
    "handle",
    "platform_status",
    "send_instagram",
    "send_whatsapp_cloud",
    "taken",
    "view",
]
