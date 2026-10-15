"""Fakes for the plan / signup / subscription tests: an in-memory platform_settings store and
a clean catalog per test. Nothing here opens a database connection."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.core import addons as addon_catalog
from app.core import plans as plan_catalog
from app.services import catalog_plans, settings_port


class SettingsMemory:
    """Stands in for ``settings_port.get_many`` / ``put``: values live in ``self.values``."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.puts: list[tuple[str, Any, str]] = []

    async def get_many(self, keys: list[str], *, db: Any = None) -> dict[str, Any]:
        return {key: self.values[key] for key in keys if key in self.values}

    async def put(self, db: Any, key: str, value: Any, *, by: str = "") -> None:
        self.values[key] = value
        self.puts.append((key, value, by))


def isolate_catalog(monkeypatch) -> SettingsMemory:
    memory = SettingsMemory()
    monkeypatch.setattr(settings_port, "get_many", memory.get_many)
    monkeypatch.setattr(settings_port, "put", memory.put)
    reset_catalog()
    return memory


def reset_catalog() -> None:
    plan_catalog.reset_plans()
    addon_catalog.reset_addons()
    catalog_plans.install({})


def account(plan: str = "starter", owned: dict | None = None, **kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = dict(id="m1", plan=plan, addons={"_v": 1, **(owned or {})}, vertical="clinic", widget_enabled=False, active=True)
    base.update(kw)
    return SimpleNamespace(**base)


def editor_payload() -> dict[str, Any]:
    """The default catalog in the admin editor's PUT shape."""
    data = catalog_plans.defaults()
    for tier in data["tiers"]:
        tier.pop("public", None)
    return data


__all__ = ["SettingsMemory", "account", "editor_payload", "isolate_catalog", "reset_catalog"]
