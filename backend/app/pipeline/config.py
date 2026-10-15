"""An account's call-flow settings: validation, admin locks, the effective view and its hash.

Stored sparse in ``merchants.agent_flow`` (only what the owner changed), so
improvements to platform defaults still reach accounts that never touched a
setting::

    {"_v": 1,
     "steps": {"payment": {"enabled": true, "options": {"mode": "online_required"},
                           "lines": {"en": {"ask_method": "…"}}}},
     "branches": {"cancel": {"enabled": false}},
     "order": {"book": ["doctor", "schedule", "patient_type", "intake"]}}

Admin locks live in ``merchants.agent_flow_locks`` as ``{"locks": {path: value}}``
with paths ``steps.<skill>.enabled``, ``steps.<skill>.options.<name>``,
``steps.<skill>.lines.<lang>.<key>``, ``branches.<branch>.enabled``,
``order.<branch>``. Precedence: blueprint defaults < vertical preset < owner < lock.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from app.pipeline.blueprint import Blueprint
from app.skills.base import SKILL_LIB_VERSION

CONFIG_VERSION = 1


class FlowConfigError(ValueError):
    def __init__(self, errors: list[dict[str, str]], *, locked: list[str] | None = None) -> None:
        self.errors = errors
        self.locked = locked or []
        super().__init__("; ".join(f"{e['path']}: {e['message']}" for e in errors) or "locked settings")


def canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def config_hash(blueprint: Blueprint, owner: Mapping[str, Any] | None, locks: Mapping[str, Any] | None, preset: Mapping[str, Any] | None = None) -> str:
    raw = f"{blueprint.key}|{blueprint.version}|{SKILL_LIB_VERSION}|{canon(preset or {})}|{canon(owner or {})}|{canon(locks or {})}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def lock_map(locks: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(locks, Mapping):
        return {}
    inner = locks.get("locks", locks)
    return dict(inner) if isinstance(inner, Mapping) else {}


# ---- effective view ------------------------------------------------------------------------
def _merge_step(target: dict[str, Any], source: Mapping[str, Any] | None) -> None:
    if not isinstance(source, Mapping):
        return
    if isinstance(source.get("enabled"), bool):
        target["enabled"] = source["enabled"]
    if isinstance(source.get("options"), Mapping):
        target["options"].update({k: v for k, v in source["options"].items() if v is not None})
    if isinstance(source.get("lines"), Mapping):
        for lang, lines in source["lines"].items():
            if isinstance(lines, Mapping):
                target["lines"].setdefault(lang, {}).update({k: v for k, v in lines.items() if v})


def set_path(view: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if parts[0] == "steps" and len(parts) >= 3 and parts[1] in view["steps"]:
        step = view["steps"][parts[1]]
        if parts[2] == "enabled" and isinstance(value, bool):
            step["enabled"] = value
        elif parts[2] == "options" and len(parts) == 4:
            step["options"][parts[3]] = value
        elif parts[2] == "lines" and len(parts) == 5 and isinstance(value, str):
            step["lines"].setdefault(parts[3], {})[parts[4]] = value
    elif parts[0] == "branches" and len(parts) == 3 and parts[1] in view["branches"] and isinstance(value, bool):
        view["branches"][parts[1]]["enabled"] = value
    elif parts[0] == "order" and len(parts) == 2 and parts[1] in view["order"] and isinstance(value, list):
        view["order"][parts[1]] = list(value)


def get_path(view: Mapping[str, Any], path: str) -> Any:
    parts = path.split(".")
    try:
        if parts[0] == "steps":
            step = view["steps"][parts[1]]
            if parts[2] == "enabled":
                return step["enabled"]
            if parts[2] == "options":
                return step["options"].get(parts[3])
            if parts[2] == "lines":
                return (step["lines"].get(parts[3]) or {}).get(parts[4])
        if parts[0] == "branches":
            return view["branches"][parts[1]]["enabled"]
        if parts[0] == "order":
            return view["order"][parts[1]]
    except (KeyError, IndexError):
        return None
    return None


def effective(blueprint: Blueprint, owner: Mapping[str, Any] | None, locks: Mapping[str, Any] | None = None, preset: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Every skill's enabled / options / line overrides and every branch's order, all layers applied."""
    view: dict[str, Any] = {"steps": {}, "branches": {}, "order": {}}
    for key in blueprint.all_keys():
        skill = blueprint.skills[key]
        view["steps"][key] = {"enabled": skill.default_enabled, "options": dict(skill.defaults), "lines": {}}
    for key, branch in blueprint.branches.items():
        view["branches"][key] = {"enabled": True}
        view["order"][key] = list(branch.skills)
    for layer in (preset or {}, owner or {}):
        for key, step in (layer.get("steps") or {}).items():
            if key in view["steps"]:
                _merge_step(view["steps"][key], step)
        for key, branch in (layer.get("branches") or {}).items():
            if key in view["branches"] and isinstance(branch, Mapping) and isinstance(branch.get("enabled"), bool):
                view["branches"][key]["enabled"] = branch["enabled"]
        for key, order in (layer.get("order") or {}).items():
            if key in view["order"] and isinstance(order, list):
                view["order"][key] = [k for k in order if k in blueprint.branches[key].skills]
    for path, value in lock_map(locks).items():
        set_path(view, path, value)
    for key in blueprint.all_keys():
        if not blueprint.skills[key].toggleable:
            view["steps"][key]["enabled"] = True
    for key, branch in blueprint.branches.items():
        if not branch.toggleable:
            view["branches"][key]["enabled"] = True
    return view


__all__ = [
    "CONFIG_VERSION",
    "FlowConfigError",
    "canon",
    "config_hash",
    "effective",
    "get_path",
    "lock_map",
    "set_path",
]
