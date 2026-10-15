"""Google Calendar OAuth: availability, the consent URL and signed state, the code
exchange, cached access tokens from the stored (encrypted) refresh token, and revoke."""

from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import structlog

from app.core import memo
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.security import sign_token, verify_token
from app.models import Merchant
from app.services.calendar import common
from app.services.calendar.common import FETCH_TIMEOUT, settings_of

logger = structlog.get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/calendar"


def google_available() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    settings = get_settings()
    if settings.google_redirect_uri:
        return settings.google_redirect_uri
    base = str(settings.public_base_url or "http://localhost:8000").rstrip("/")
    return f"{base}/api/integrations/google/callback"


def auth_url(merchant_id: str) -> str:
    settings = get_settings()
    state = sign_token({"typ": "google_oauth", "mid": merchant_id, "n": secrets.token_hex(6)}, ttl_seconds=900)
    query = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(query)}"


def merchant_from_state(state: str) -> str:
    payload = verify_token(state)
    if payload.get("typ") != "google_oauth" or not payload.get("mid"):
        raise ValueError("bad state")
    return str(payload["mid"])


def _email_from_id_token(id_token: str) -> str:
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("email") or "")
    except (IndexError, ValueError):
        return ""


async def exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    response = await common.http().post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=FETCH_TIMEOUT,
    )
    if response.status_code != 200:
        raise ValueError(f"google_token_exchange_{response.status_code}: {response.text[:200]}")
    data = response.json()
    if not data.get("refresh_token"):
        raise ValueError("Google did not return a refresh token — remove the app's access in your Google account and connect again.")
    return {
        "refresh_token_enc": encrypt(str(data["refresh_token"])),
        "email": _email_from_id_token(str(data.get("id_token") or "")),
        "calendar_id": "primary",
        "check_busy": True,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "_access_token": str(data.get("access_token") or ""),
        "_expires_in": int(data.get("expires_in") or 3600),
    }


async def access_token(merchant: Merchant) -> str:
    google = settings_of(merchant).get("google") or {}
    refresh = decrypt(str(google.get("refresh_token_enc") or ""))
    if not refresh:
        raise PermissionError("Google Calendar is not connected")
    key = f"gtoken:{merchant.id}"
    cached = memo.get(key)
    if cached:
        return str(cached)
    settings = get_settings()
    response = await common.http().post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
        timeout=FETCH_TIMEOUT,
    )
    if response.status_code != 200:
        raise PermissionError(f"google_token_refresh_{response.status_code}: {response.text[:160]}")
    data = response.json()
    token = str(data["access_token"])
    memo.put(key, token, ttl=max(60, int(data.get("expires_in") or 3600) - 120))
    return token


async def revoke(merchant: Merchant) -> None:
    google = settings_of(merchant).get("google") or {}
    refresh = decrypt(str(google.get("refresh_token_enc") or ""))
    memo.drop(f"gtoken:{merchant.id}")
    if refresh:
        try:
            await common.http().post(GOOGLE_REVOKE_URL, data={"token": refresh}, timeout=FETCH_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 — disconnect locally regardless
            await logger.ainfo("google_revoke_failed", error=str(exc)[:160])
