"""Small HTTP helpers for the e2e tests: sign-ins, account setup, direct SQL reads."""

from __future__ import annotations

import itertools
import secrets
from typing import Any

import httpx
from sqlalchemy import select

from tests.e2e.env import ADMIN_PASSWORD, ADMIN_USERNAME

OWNER_PASSWORD = "Owner-Pass-e2e-4826!"
_numbers = itertools.count(100)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def client_ip() -> dict[str, str]:
    """A fresh client address (one trusted proxy hop): sign-in limits are per IP."""
    return {"X-Forwarded-For": f"203.0.113.{secrets.randbelow(250) + 1}, 10.0.0.{secrets.randbelow(250) + 1}"}


def unique(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(3)}"


def next_number() -> str:
    """A fresh US number per account (inbound routing is by the dialed number)."""
    return f"+1415555{next(_numbers):04d}"


async def ok(response: httpx.Response, status: int = 200) -> Any:
    assert response.status_code == status, f"{response.request.method} {response.request.url.path} → {response.status_code}: {response.text[:500]}"
    return response.json() if response.content and "json" in response.headers.get("content-type", "") else response


async def admin_token(client: httpx.AsyncClient, username: str = ADMIN_USERNAME, password: str = ADMIN_PASSWORD, code: str = "") -> str:
    data = await ok(await client.post("/api/admin/login", json={"username": username, "password": password, "code": code}, headers=client_ip()))
    return data["token"]


async def owner_token(client: httpx.AsyncClient, username: str, password: str = OWNER_PASSWORD) -> str:
    data = await ok(await client.post("/api/auth/login", json={"username": username, "password": password}, headers=client_ip()))
    return data["token"]


async def create_account(client: httpx.AsyncClient, admin: str, *, vertical: str, plan: str = "growth", inbound: bool = True, **extra: Any) -> dict[str, Any]:
    """An account made in the admin console (US region), signed in as its owner."""
    username = extra.pop("username", None) or unique(f"{vertical[:6]}-")
    body = {
        "business_name": extra.pop("business_name", f"E2E {vertical.replace('_', ' ').title()} {username[-6:]}"), "username": username,
        "password": OWNER_PASSWORD, "vertical": vertical, "region": "US", "plan": plan, "owner_name": "Pat Owner",
        "email": f"{username}@example.test", "inbound_number": next_number() if inbound else "", "timezone": "America/New_York", **extra,
    }
    merchant = await ok(await client.post("/api/admin/merchants", json=body, headers=bearer(admin)), 201)
    token = await owner_token(client, username)
    return {"merchant": merchant, "token": token, "headers": bearer(token), "username": username}


async def salon_catalog(client: httpx.AsyncClient, headers: dict[str, str], *, staff: tuple[str, ...] = ("Maya",)) -> dict[str, dict]:
    """One service done by ``staff``, each working every day 08:00–20:00."""
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    people = {}
    for name in staff:
        people[name] = await ok(
            await client.post("/api/catalog?kind=staff", headers=headers, json={"name": name, "days": days, "start_time": "08:00", "end_time": "20:00"}), 201
        )
    service = await ok(
        await client.post("/api/catalog?kind=service", headers=headers, json={"name": "Haircut", "duration_minutes": 45, "price": 45, "staff": list(staff)}), 201
    )
    return {"service": service, **people}


async def salon_with_widget(client: httpx.AsyncClient) -> dict[str, Any]:
    """A Growth salon whose web-chat add-on was requested and approved, widget switched on."""
    admin = await admin_token(client)
    account = await create_account(client, admin, vertical="salon", plan="growth", inbound=False)
    headers = account["headers"]
    await salon_catalog(client, headers)
    # The website chatbot is an add-on on a voice tier: refused until the admin approves the request.
    refused = await client.patch("/api/auth/me", json={"widget_enabled": True}, headers=headers)
    assert refused.status_code == 403
    shop = await ok(await client.post("/api/addons/requests", json={"addon": "web_chat", "note": "for our site"}, headers=headers), 201)
    [pending] = [row for row in shop["requests"] if row["addon"] == "web_chat"]
    await ok(await client.post(f"/api/admin/addon-requests/{pending['id']}/approve", json={"admin_note": "ok"}, headers=bearer(admin)))
    me = await ok(await client.patch("/api/auth/me", json={"widget_enabled": True, "widget_settings": {"title": "Chat with Glow", "color": "#112233"}}, headers=headers))
    assert me["widget_enabled"] is True and len(me["widget_key"]) >= 16 and me["addons"].get("web_chat") == 1
    account["merchant"] = me
    return account


async def fetch(model: Any, **where: Any) -> list[Any]:
    """Rows of ``model`` matching ``column == value`` filters, read on a fresh session."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = select(model)
        for key, value in where.items():
            stmt = stmt.where(getattr(model, key) == value)
        return list(await session.scalars(stmt))


__all__ = ["OWNER_PASSWORD", "admin_token", "bearer", "client_ip", "create_account", "fetch", "next_number", "ok", "owner_token", "salon_catalog", "salon_with_widget", "unique"]
