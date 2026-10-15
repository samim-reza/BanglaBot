"""Spoken lines + small helpers shared by the library skills."""

from __future__ import annotations

from typing import Any

from app.skills.base import LineSpec


def L2(en: str, bn: str = "") -> dict[str, str]:
    return {"en": en, "bn": bn or en}


def line(key: str, en: str, bn: str = "", *, label: str = "", variables: tuple[str, ...] = (), required: tuple[str, ...] = (), static: bool = False) -> LineSpec:
    return LineSpec(key, L2(en, bn), label=label, variables=variables, required_vars=required, account_static=static)


def filled(slots: dict[str, Any], key: str) -> bool:
    return slots.get(key) not in (None, "")


__all__ = ["L2", "filled", "line"]
