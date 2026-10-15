"""The data-driven catalog: tiers + add-ons, offered verticals and signup settings.

Stored in ``platform_settings`` (via ``settings_port``) and installed into the
in-process catalog that ``app.core.plans`` / ``app.core.addons`` read, so the
synchronous gate (``entitlements``) never waits on the database. Unset keys
mean the code defaults. Every process refreshes on its own every
``REFRESH_SECONDS`` (``billing_jobs``) and right after an admin edit.

Keys: ``plans.catalog`` → ``{"tiers": [...]}``, ``addons.catalog`` →
``{"addons": [...]}``, ``verticals.offered`` → ``{"keys": [...]}``,
``signup.auto_activate`` → ``{"enabled": bool}``,
``signup.require_verified_email`` → ``{"enabled": bool}``.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import addons as addon_catalog
from app.core import plans as plan_catalog
from app.core.addons import Addon
from app.core.plans import Plan
from app.schemas.plans import CatalogIn, SignupSettingsIn
from app.services import settings_port

logger = structlog.get_logger(__name__)

PLANS_KEY = "plans.catalog"
ADDONS_KEY = "addons.catalog"
VERTICALS_KEY = "verticals.offered"
AUTO_ACTIVATE_KEY = "signup.auto_activate"
VERIFIED_EMAIL_KEY = "signup.require_verified_email"
ALL_KEYS = [PLANS_KEY, ADDONS_KEY, VERTICALS_KEY, AUTO_ACTIVATE_KEY, VERIFIED_EMAIL_KEY]
REFRESH_SECONDS = 60.0

_state: dict[str, Any] = {"loaded_at": 0.0, "verticals": None, "auto_activate": False, "require_verified_email": False}


# --------------------------------------------------------------------------- parsing stored values
def _items(value: Any, field: str) -> list[dict[str, Any]]:
    raw = value.get(field) if isinstance(value, dict) else value
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _flag(value: Any) -> bool:
    return bool(value.get("enabled")) if isinstance(value, dict) else bool(value)


def parse_tiers(value: Any) -> list[Plan] | None:
    """Stored tiers over the defaults (a stored tier may omit newer fields); None = unset / unusable."""
    tiers: list[Plan] = []
    for item in _items(value, "tiers"):
        key = str(item.get("key") or "")
        try:
            tiers.append(Plan.from_json(item, plan_catalog.DEFAULT_PLANS.get(key)))
        except (TypeError, ValueError) as exc:
            logger.warning("catalog_tier_skipped", key=key, error=str(exc)[:200])
    return tiers or None


def parse_addons(value: Any) -> list[Addon] | None:
    if value is None:
        return None
    out: list[Addon] = []
    for item in _items(value, "addons"):
        key = str(item.get("key") or "")
        try:
            out.append(Addon.from_json(item, addon_catalog.DEFAULT_CATALOG.get(key)))
        except (TypeError, ValueError) as exc:
            logger.warning("catalog_addon_skipped", key=key, error=str(exc)[:200])
    return out


def install(values: dict[str, Any]) -> None:
    """Install what ``platform_settings`` holds (missing keys → code defaults)."""
    tiers = parse_tiers(values.get(PLANS_KEY))
    plan_catalog.install_plans(tiers if tiers is not None else plan_catalog.DEFAULT_PLANS.values())
    extras = parse_addons(values.get(ADDONS_KEY))
    addon_catalog.install_addons(extras if extras is not None else addon_catalog.DEFAULT_CATALOG.values())
    offered = values.get(VERTICALS_KEY)
    keys = offered.get("keys") if isinstance(offered, dict) else offered
    _state["verticals"] = [str(key) for key in keys] if isinstance(keys, list) and keys else None
    _state["auto_activate"] = _flag(values.get(AUTO_ACTIVATE_KEY, False))
    _state["require_verified_email"] = _flag(values.get(VERIFIED_EMAIL_KEY, False))
    _state["loaded_at"] = time.monotonic()


async def load(db: AsyncSession | None = None) -> None:
    install(await settings_port.get_many(ALL_KEYS, db=db))


async def ensure_fresh(max_age: float = REFRESH_SECONDS) -> None:
    """Reload when the installed catalog is older than ``max_age``; never raises."""
    if time.monotonic() - float(_state["loaded_at"] or 0.0) < max_age and _state["loaded_at"]:
        return
    try:
        await load()
    except Exception as exc:  # noqa: BLE001 — keep serving the catalog we have
        _state["loaded_at"] = time.monotonic()
        await logger.awarning("catalog_refresh_failed", error=str(exc)[:200])


# --------------------------------------------------------------------------- reads
def tiers_json(*, include_hidden: bool = True, vertical: str | None = None) -> list[dict[str, Any]]:
    return [
        plan.as_json()
        for plan in plan_catalog.PLANS.values()
        if (include_hidden or plan.public) and plan.offered_for(vertical)
    ]


def snapshot() -> dict[str, Any]:
    """The installed catalog in the admin editor's shape."""
    return {"tiers": tiers_json(), "addons": addon_catalog.public_catalog(include_hidden=True)}


def defaults() -> dict[str, Any]:
    return {
        "tiers": [plan.as_json() for plan in plan_catalog.DEFAULT_PLANS.values()],
        "addons": [addon.as_json() for addon in addon_catalog.DEFAULT_CATALOG.values()],
    }


def all_vertical_keys() -> list[str]:
    from app.verticals import VERTICALS

    return list(VERTICALS)


def offered_verticals() -> list[str]:
    """Verticals new accounts may pick (unknown keys dropped; unset = all)."""
    known = all_vertical_keys()
    chosen = _state["verticals"]
    if not chosen:
        return known
    picked = [key for key in chosen if key in known]
    return picked or known


def signup_settings() -> dict[str, bool]:
    return {"auto_activate": bool(_state["auto_activate"]), "require_verified_email": bool(_state["require_verified_email"])}


# --------------------------------------------------------------------------- writes (admin)
def to_storage(data: CatalogIn) -> tuple[dict[str, Any], dict[str, Any]]:
    tiers = []
    for tier in data.tiers:
        item = tier.model_dump()
        item["public"] = item.pop("visible")
        tiers.append(item)
    return {"tiers": tiers}, {"addons": [addon.model_dump() for addon in data.addons]}


async def keys_in_use(db: AsyncSession, tiers: list[str], addons: list[str]) -> list[str]:
    """Removed keys some account still uses (they must be hidden instead)."""
    from app.models import Merchant

    used: list[str] = []
    for key in tiers:
        if await db.scalar(select(Merchant.id).where(Merchant.plan == key).limit(1)):
            used.append(f"tier {key}")
    for key in addons:
        if await db.scalar(select(Merchant.id).where(Merchant.addons.has_key(key)).limit(1)):
            used.append(f"add-on {key}")
    return used


async def save_catalog(db: AsyncSession, data: CatalogIn, *, by: str) -> dict[str, Any]:
    """Validate against the live catalog, store, install. The caller commits."""
    removed_tiers = sorted(set(plan_catalog.PLANS) - {tier.key for tier in data.tiers})
    removed_addons = sorted(set(addon_catalog.CATALOG) - {addon.key for addon in data.addons})
    used = await keys_in_use(db, removed_tiers, removed_addons)
    if used:
        raise HTTPException(status_code=422, detail=f"Still in use — hide instead of deleting: {', '.join(used)}")
    tiers, extras = to_storage(data)
    await settings_port.put(db, PLANS_KEY, tiers, by=by)
    await settings_port.put(db, ADDONS_KEY, extras, by=by)
    install({PLANS_KEY: tiers, ADDONS_KEY: extras, VERTICALS_KEY: {"keys": _state["verticals"] or []},
             AUTO_ACTIVATE_KEY: _state["auto_activate"], VERIFIED_EMAIL_KEY: _state["require_verified_email"]})
    return {"removed": {"tiers": removed_tiers, "addons": removed_addons}}


async def save_offered_verticals(db: AsyncSession, keys: list[str], *, by: str) -> list[str]:
    await settings_port.put(db, VERTICALS_KEY, {"keys": list(keys)}, by=by)
    _state["verticals"] = list(keys)
    return offered_verticals()


async def save_signup_settings(db: AsyncSession, data: SignupSettingsIn, *, by: str) -> dict[str, bool]:
    await settings_port.put(db, AUTO_ACTIVATE_KEY, {"enabled": data.auto_activate}, by=by)
    await settings_port.put(db, VERIFIED_EMAIL_KEY, {"enabled": data.require_verified_email}, by=by)
    _state["auto_activate"] = data.auto_activate
    _state["require_verified_email"] = data.require_verified_email
    return signup_settings()


__all__ = [
    "defaults",
    "ensure_fresh",
    "install",
    "load",
    "offered_verticals",
    "save_catalog",
    "save_offered_verticals",
    "save_signup_settings",
    "signup_settings",
    "snapshot",
    "tiers_json",
]
