"""Validation of owner settings and admin locks for a call flow (see :mod:`.config`)."""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from app.pipeline.blueprint import Blueprint
from app.pipeline.config import CONFIG_VERSION, FlowConfigError, canon, effective, get_path, lock_map, set_path
from app.skills.base import template_vars
from app.verticals.forms import FieldError, clean

MAX_CONFIG_BYTES = 32 * 1024
_BRACES = re.compile(r"\{[^{}]*\}")


def _check_line(path: str, text: Any, spec, errors: list[dict[str, str]]) -> str | None:  # noqa: ANN001
    if text in (None, ""):
        return None
    if not isinstance(text, str):
        errors.append({"path": path, "message": "must be text"})
        return None
    text = " ".join(text.split())
    if len(text) > spec.max_chars:
        errors.append({"path": path, "message": f"at most {spec.max_chars} characters"})
    allowed = set(spec.variables)
    for raw in _BRACES.findall(text):
        name = raw[1:-1]
        if name not in allowed:
            hint = f"use one of {', '.join('{' + v + '}' for v in spec.variables)}" if spec.variables else "no placeholders allowed"
            errors.append({"path": path, "message": f"unknown placeholder {raw} ({hint})"})
    missing = [v for v in spec.required_vars if v not in template_vars(text)]
    if missing:
        errors.append({"path": path, "message": f"must keep {', '.join('{' + v + '}' for v in missing)}"})
    return text


def _check_order(blueprint: Blueprint, branch_key: str, order: Any, errors: list[dict[str, str]]) -> list[str] | None:
    path = f"order.{branch_key}"
    branch = blueprint.branches.get(branch_key)
    if branch is None:
        errors.append({"path": path, "message": "unknown branch"})
        return None
    if not isinstance(order, list) or sorted(order) != sorted(branch.skills):
        errors.append({"path": path, "message": "must list exactly the branch's steps"})
        return None
    default = list(branch.skills)
    for index, key in enumerate(order):
        if key != default[index] and not any(key in group and default[index] in group for group in branch.movable):
            errors.append({"path": path, "message": f"'{key}' can't move there"})
            return None
    for key, earlier in branch.before.items():
        if key in order and any(dep in order and order.index(dep) > order.index(key) for dep in earlier):
            errors.append({"path": path, "message": f"'{key}' must come after {', '.join(sorted(earlier))}"})
            return None
    return list(order)


def clean_agent_flow(
    blueprint: Blueprint,
    data: Mapping[str, Any],
    *,
    locks: Mapping[str, Any] | None = None,
    languages: tuple[str, ...] = ("en", "bn"),
    preset: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The owner's submitted settings → the sparse stored form. Raises :class:`FlowConfigError`."""
    if not isinstance(data, Mapping):
        raise FlowConfigError([{"path": "", "message": "must be an object"}])
    if len(canon(data).encode("utf-8")) > MAX_CONFIG_BYTES:
        raise FlowConfigError([{"path": "", "message": "settings are too large"}])
    errors: list[dict[str, str]] = []
    out: dict[str, Any] = {"_v": CONFIG_VERSION}
    steps_out: dict[str, Any] = {}
    for key, step in (data.get("steps") or {}).items():
        skill = blueprint.skills.get(key)
        if skill is None or key not in blueprint.all_keys():
            errors.append({"path": f"steps.{key}", "message": "unknown step"})
            continue
        if not isinstance(step, Mapping):
            continue
        entry: dict[str, Any] = {}
        if "enabled" in step and step["enabled"] is not None:
            if not isinstance(step["enabled"], bool):
                errors.append({"path": f"steps.{key}.enabled", "message": "must be true or false"})
            elif step["enabled"] is False and not skill.toggleable:
                errors.append({"path": f"steps.{key}.enabled", "message": "this step can't be switched off"})
            else:
                entry["enabled"] = step["enabled"]
        if isinstance(step.get("options"), Mapping) and step["options"]:
            known = {spec.key for spec in skill.options}
            unknown = sorted(set(step["options"]) - known)
            for name in unknown:
                errors.append({"path": f"steps.{key}.options.{name}", "message": "unknown option"})
            try:
                options = clean(skill.options, {k: v for k, v in step["options"].items() if k in known}, partial=True)
            except FieldError as exc:
                errors.append({"path": f"steps.{key}.options.{exc.key}", "message": str(exc).split(": ", 1)[-1]})
                options = {}
            validate = getattr(skill, "validate_options", None)
            if callable(validate) and options:
                merged = {**skill.defaults, **options}
                for path, message in validate(merged):
                    errors.append({"path": f"steps.{key}.options.{path}", "message": message})
            options = {k: v for k, v in options.items() if v is not None}
            if options:
                entry["options"] = options
        if isinstance(step.get("lines"), Mapping) and step["lines"]:
            lines_out: dict[str, dict[str, str]] = {}
            for lang, lines in step["lines"].items():
                if lang not in languages:
                    errors.append({"path": f"steps.{key}.lines.{lang}", "message": "unsupported language"})
                    continue
                if not isinstance(lines, Mapping):
                    continue
                for line_key, text in lines.items():
                    spec = skill.line_spec(line_key)
                    path = f"steps.{key}.lines.{lang}.{line_key}"
                    if spec is None:
                        errors.append({"path": path, "message": "unknown line"})
                        continue
                    cleaned = _check_line(path, text, spec, errors)
                    if cleaned:
                        lines_out.setdefault(lang, {})[line_key] = cleaned
            if lines_out:
                entry["lines"] = lines_out
        if entry:
            steps_out[key] = entry
    if steps_out:
        out["steps"] = steps_out
    branches_out: dict[str, Any] = {}
    for key, branch in (data.get("branches") or {}).items():
        spec = blueprint.branches.get(key)
        if spec is None:
            errors.append({"path": f"branches.{key}", "message": "unknown branch"})
            continue
        enabled = branch.get("enabled") if isinstance(branch, Mapping) else None
        if isinstance(enabled, bool):
            if not enabled and not spec.toggleable:
                errors.append({"path": f"branches.{key}.enabled", "message": "can't be switched off"})
            else:
                branches_out[key] = {"enabled": enabled}
    if branches_out:
        if not any((branches_out.get(k) or {}).get("enabled", True) for k in blueprint.branches):
            errors.append({"path": "branches", "message": "keep at least one thing callers can do"})
        out["branches"] = branches_out
    order_out: dict[str, list[str]] = {}
    for key, order in (data.get("order") or {}).items():
        cleaned_order = _check_order(blueprint, key, order, errors)
        if cleaned_order and cleaned_order != list(blueprint.branches[key].skills):
            order_out[key] = cleaned_order
    if order_out:
        out["order"] = order_out
    if errors:
        raise FlowConfigError(errors)
    _enforce_locks(blueprint, out, locks, preset)
    return out


_ABSENT = object()


def _explicit(owner: Mapping[str, Any], path: str) -> Any:
    """The value the owner's own (sparse) settings give ``path``, or ``_ABSENT``."""
    parts = path.split(".")
    try:
        if parts[0] == "steps":
            step = (owner.get("steps") or {})[parts[1]]
            if parts[2] == "enabled":
                return step["enabled"] if "enabled" in step else _ABSENT
            if parts[2] == "options":
                return step["options"][parts[3]]
            if parts[2] == "lines":
                return step["lines"][parts[3]][parts[4]]
        if parts[0] == "branches":
            return (owner.get("branches") or {})[parts[1]]["enabled"]
        if parts[0] == "order":
            return (owner.get("order") or {})[parts[1]]
    except (KeyError, IndexError, TypeError):
        return _ABSENT
    return _ABSENT


def _enforce_locks(blueprint: Blueprint, owner: dict[str, Any], locks: Mapping[str, Any] | None, preset: Mapping[str, Any] | None) -> None:
    """An owner setting that names a locked path with a different value is refused (listing the paths).

    Settings the owner didn't touch are fine whatever the default is — the lock wins in the effective view.
    """
    changed = []
    for path, value in lock_map(locks).items():
        mine = _explicit(owner, path)
        if mine is not _ABSENT and canon(mine) != canon(value):
            changed.append(path)
    if changed:
        raise FlowConfigError(
            [{"path": path, "message": "locked by the platform"} for path in changed], locked=sorted(changed)
        )


def clean_locks(blueprint: Blueprint, data: Mapping[str, Any], owner: Mapping[str, Any] | None, preset: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Admin input ``{"locks": {path: value|null}}`` → stored locks; ``null`` freezes the current value."""
    raw = lock_map(data)
    current = effective(blueprint, owner, None, preset)
    out: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    for path, value in raw.items():
        resolved = get_path(current, path) if value is None else value
        if resolved is None and value is None:
            errors.append({"path": path, "message": "unknown setting"})
            continue
        probe = copy.deepcopy(current)
        set_path(probe, path, resolved)
        if canon(get_path(probe, path)) != canon(resolved):
            errors.append({"path": path, "message": "unknown setting or wrong type"})
            continue
        out[path] = resolved
    if errors:
        raise FlowConfigError(errors)
    return {"_v": CONFIG_VERSION, "locks": out}


__all__ = ["MAX_CONFIG_BYTES", "clean_agent_flow", "clean_locks"]
