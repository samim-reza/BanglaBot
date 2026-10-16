"""An account's call flow: describe it for the editor, validate + save the owner's settings,
admin locks, a deterministic preview, and pre-warming the fixed lines into the TTS cache.

A vertical may have an inbound and an outbound pipeline that share skills (the
goodbye, emergency, schedule …). The stored settings are one document; each
part is validated against the pipeline(s) that have that step.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

import structlog
from fastapi import HTTPException

from app.core.addons import entitlements
from app.flows.context import CallContext
from app.pipeline.blueprint import Blueprint
from app.pipeline.compiled import PIPELINES
from app.pipeline.config import CONFIG_VERSION, FlowConfigError, config_hash, lock_map
from app.pipeline.validate import clean_agent_flow, clean_locks
from app.services import audit_service
from app.verticals import vertical_for
from app.verticals.base import Vertical
from app.voice.languages import normalize_language

logger = structlog.get_logger(__name__)

LANGUAGES = ("en",)
#: What an owner on a "lines only" plan may change.
LINES_ONLY_KEYS = frozenset({"lines"})


def _blueprints(vertical: Vertical) -> dict[str, Blueprint]:
    if not vertical.blueprints:
        raise HTTPException(status_code=404, detail="This business type has a fixed call flow")
    return dict(vertical.blueprints)


def _subset(bp: Blueprint, data: Mapping[str, Any]) -> dict[str, Any]:
    keys = set(bp.all_keys())
    return {
        "steps": {k: v for k, v in (data.get("steps") or {}).items() if k in keys},
        "branches": {k: v for k, v in (data.get("branches") or {}).items() if k in bp.branches},
        "order": {k: v for k, v in (data.get("order") or {}).items() if k in bp.branches},
    }


def locks_for(bp: Blueprint, locks: Mapping[str, Any] | None) -> dict[str, Any]:
    """Only the lock paths that name this pipeline's steps / branches."""
    keys, branches = set(bp.all_keys()), set(bp.branches)
    kept = {}
    for path, value in lock_map(locks).items():
        parts = path.split(".")
        if (parts[0] == "steps" and len(parts) > 1 and parts[1] in keys) or (parts[0] in ("branches", "order") and len(parts) > 1 and parts[1] in branches):
            kept[path] = value
    return {"locks": kept} if kept else {}


def state_hash(merchant: Any) -> str:
    """ETag of what is stored (owner settings + locks): two editors can't overwrite each other."""
    vertical = vertical_for(merchant)
    bp = next(iter(_blueprints(vertical).values()))
    return config_hash(bp, getattr(merchant, "agent_flow", None) or {}, getattr(merchant, "agent_flow_locks", None) or {}, vertical.preset or None)


def clean_for_vertical(vertical: Vertical, data: Mapping[str, Any], *, locks: Mapping[str, Any] | None, lines_only: bool = False) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise FlowConfigError([{"path": "", "message": "must be an object"}])
    blueprints = _blueprints(vertical)
    known_steps = {key for bp in blueprints.values() for key in bp.all_keys()}
    known_branches = {key for bp in blueprints.values() for key in bp.branches}
    errors: list[dict[str, str]] = [{"path": f"steps.{k}", "message": "unknown step"} for k in (data.get("steps") or {}) if k not in known_steps]
    errors += [{"path": f"branches.{k}", "message": "unknown branch"} for k in (data.get("branches") or {}) if k not in known_branches]
    errors += [{"path": f"order.{k}", "message": "unknown branch"} for k in (data.get("order") or {}) if k not in known_branches]
    if lines_only:
        for key, step in (data.get("steps") or {}).items():
            if isinstance(step, Mapping) and set(step) - LINES_ONLY_KEYS:
                errors.append({"path": f"steps.{key}", "message": "your plan lets you reword lines; upgrade to change steps"})
        if data.get("branches") or data.get("order"):
            errors.append({"path": "order", "message": "your plan lets you reword lines; upgrade to change steps"})
    out: dict[str, Any] = {"_v": CONFIG_VERSION}
    locked: list[str] = []
    for bp in blueprints.values():
        try:
            cleaned = clean_agent_flow(bp, _subset(bp, data), locks=locks_for(bp, locks), languages=LANGUAGES, preset=vertical.preset or None)
        except FlowConfigError as exc:
            errors += exc.errors
            locked += exc.locked
            continue
        for part in ("steps", "branches", "order"):
            if cleaned.get(part):
                out.setdefault(part, {}).update(cleaned[part])
    if errors:
        unique = list({(e["path"], e["message"]): e for e in errors}.values())
        raise FlowConfigError(unique, locked=sorted(set(locked)))
    return out


# ---- describe / preview ---------------------------------------------------------------------------
def describe(merchant: Any) -> dict[str, Any]:
    vertical = vertical_for(merchant)
    blueprints = _blueprints(vertical)
    owner = getattr(merchant, "agent_flow", None) or {}
    locks = getattr(merchant, "agent_flow_locks", None) or {}
    directions = {}
    for direction, bp in blueprints.items():
        compiled = PIPELINES.get(bp, owner, locks, vertical.preset or None)
        directions[direction] = {"blueprint": bp.as_json(), "effective": compiled.view}
    ent = entitlements(merchant)
    return {
        "vertical": vertical.key,
        "config": owner or {"_v": CONFIG_VERSION},
        "locked": sorted(lock_map(locks)),
        "hash": state_hash(merchant),
        "languages": list(LANGUAGES),
        "editing": getattr(ent, "flow_editing", "full"),
        "directions": directions,
    }


def preview(merchant: Any, draft: Mapping[str, Any] | None = None, *, language: str | None = None) -> dict[str, Any]:
    """What each branch will ask, in order, with the (owner-edited) wording — deterministic, no model."""
    vertical = vertical_for(merchant)
    owner = clean_for_vertical(vertical, draft, locks=getattr(merchant, "agent_flow_locks", None)) if draft is not None else (getattr(merchant, "agent_flow", None) or {})
    language = normalize_language(language or getattr(merchant, "language", None))
    business = str(getattr(merchant, "business_name", "") or "")
    out: dict[str, Any] = {}
    for direction, bp in _blueprints(vertical).items():
        compiled = PIPELINES.get(bp, owner, getattr(merchant, "agent_flow_locks", None), vertical.preset or None)
        ctx = CallContext(merchant=merchant, direction=direction)
        branches = []
        for key, skills in compiled.branches.items():
            steps = []
            for bound in (*compiled.prelude, *skills):
                spec = bound.skill.lines[0] if bound.skill.lines else None
                steps.append({
                    "skill": bound.key,
                    "label": dict(bound.skill.label),
                    "kind": bound.skill.kind,
                    "says": bound.line_text(spec.key, language) if spec else "",
                })
            branches.append({"key": key, "label": dict(bp.branches[key].label), "steps": steps})
        out[direction] = {"opening": compiled.flow.opening(ctx, language).replace("{business}", business), "branches": branches}
    return {"language": language, "directions": out}


# ---- saving ---------------------------------------------------------------------------------------
async def save(db: Any, merchant: Any, data: Mapping[str, Any], *, base_hash: str | None, actor: dict[str, str], request: Any = None, enforce_locks: bool = True) -> dict[str, Any]:
    if base_hash and base_hash != state_hash(merchant):
        raise HTTPException(status_code=409, detail="The call flow was changed somewhere else — reload and try again")
    vertical = vertical_for(merchant)
    lines_only = enforce_locks and getattr(entitlements(merchant), "flow_editing", "full") == "lines"
    locks = getattr(merchant, "agent_flow_locks", None) if enforce_locks else None
    cleaned = clean_for_vertical(vertical, data, locks=locks, lines_only=lines_only)
    if enforce_locks:
        _check_capabilities(merchant, cleaned)
    before = getattr(merchant, "agent_flow", None) or {}
    merchant.agent_flow = cleaned
    audit_service.stage(
        db,
        action="agent_flow.saved",
        actor_type=actor.get("type", "merchant"),
        actor_id=actor.get("id", ""),
        target_type="merchant",
        target_id=str(merchant.id),
        merchant_id=str(merchant.id),
        request=request,
        meta={"changed": sorted(set(_paths(cleaned)) ^ set(_paths(before)))[:40]},
    )
    await db.commit()
    schedule_warm(merchant)
    return describe(merchant)


async def save_locks(db: Any, merchant: Any, data: Mapping[str, Any], *, actor: dict[str, str], request: Any = None) -> dict[str, Any]:
    vertical = vertical_for(merchant)
    raw = lock_map(data)
    owner = getattr(merchant, "agent_flow", None) or {}
    merged: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    claimed: set[str] = set()
    for bp in _blueprints(vertical).values():
        mine = {path: value for path, value in raw.items() if locks_for(bp, {"locks": {path: value}})}
        claimed |= set(mine)
        if not mine:
            continue
        try:
            merged.update(clean_locks(bp, {"locks": mine}, owner, vertical.preset or None)["locks"])
        except FlowConfigError as exc:
            errors += exc.errors
    errors += [{"path": path, "message": "unknown setting"} for path in raw if path not in claimed]
    if errors:
        raise FlowConfigError(errors)
    merchant.agent_flow_locks = {"_v": CONFIG_VERSION, "locks": merged} if merged else {}
    audit_service.stage(
        db, action="agent_flow.locks", actor_type=actor.get("type", "admin"), actor_id=actor.get("id", ""),
        target_type="merchant", target_id=str(merchant.id), merchant_id=str(merchant.id), request=request, meta={"locks": sorted(merged)},
    )
    await db.commit()
    schedule_warm(merchant)
    return describe(merchant)


def _check_capabilities(merchant: Any, config: Mapping[str, Any]) -> None:
    """Paid features of the plan: online payment collection and custom intake questions."""
    ent = entitlements(merchant)
    steps = config.get("steps") or {}
    errors = []
    payment = steps.get("payment") or {}
    if payment.get("enabled") is True and not getattr(ent, "payments", True):
        errors.append({"path": "steps.payment.enabled", "message": "taking payments is part of a higher plan"})
    custom = ((steps.get("intake") or {}).get("options") or {}).get("custom") or []
    if custom and not getattr(ent, "custom_fields", True):
        errors.append({"path": "steps.intake.options.custom", "message": "custom questions are part of a higher plan"})
    if errors:
        raise FlowConfigError(errors)


def _paths(config: Mapping[str, Any]) -> list[str]:
    paths = []
    for key, step in (config.get("steps") or {}).items():
        paths += [f"steps.{key}.{part}" for part in (step or {})]
    paths += [f"branches.{key}" for key in (config.get("branches") or {})]
    paths += [f"order.{key}" for key in (config.get("order") or {})]
    return paths


# ---- TTS pre-warm ---------------------------------------------------------------------------------
def schedule_warm(merchant: Any) -> None:
    """Synthesize + pin every fixed line of the new flow in the background (never blocks the save)."""
    try:
        asyncio.get_running_loop().create_task(warm_lines(merchant.id))
    except RuntimeError:
        return


async def warm_lines(merchant_id: str) -> int:
    from app.db.session import AsyncSessionLocal
    from app.models import Merchant
    from app.services.context_service import load_catalog
    from app.voice.providers.tts import get_tts_for
    from app.voice.tts import normalize_persona

    try:
        async with AsyncSessionLocal() as db:
            merchant = await db.get(Merchant, merchant_id)
            if merchant is None:
                return 0
            catalog = await load_catalog(db, merchant)
        language = normalize_language(getattr(merchant, "language", None))
        persona = normalize_persona(getattr(merchant, "voice_persona", None))
        warmed = 0
        for direction, bp in vertical_for(merchant).blueprints.items():
            flow = PIPELINES.get(bp, merchant.agent_flow, merchant.agent_flow_locks, vertical_for(merchant).preset or None).flow
            lines = flow.prefetch_lines(CallContext(merchant=merchant, direction=direction, catalog=catalog), language)
            engine = get_tts_for(language)
            engine.pin_lines(lines, language=language, persona=persona)
            warmed += await engine.warm(lines, language=language, persona=persona)
        await logger.ainfo("agent_flow_warmed", merchant_id=merchant_id, lines=warmed)
        return warmed
    except Exception as exc:  # noqa: BLE001 — warming is an optimisation only
        await logger.awarning("agent_flow_warm_failed", merchant_id=merchant_id, error=str(exc)[:200])
        return 0


__all__ = ["clean_for_vertical", "describe", "locks_for", "preview", "save", "save_locks", "schedule_warm", "state_hash", "warm_lines"]
