"""Spoken lines + small helpers shared by the library skills."""

from __future__ import annotations

from typing import Any

from app.skills.base import LineSpec
from app.verticals.base import L


def line(key: str, en: str, *, label: str = "", variables: tuple[str, ...] = (), required: tuple[str, ...] = (), static: bool = False) -> LineSpec:
    return LineSpec(key, L(en), label=label, variables=variables, required_vars=required, account_static=static)


def filled(slots: dict[str, Any], key: str) -> bool:
    return slots.get(key) not in (None, "")


__all__ = ["L", "filled", "line"]
