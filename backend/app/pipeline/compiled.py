"""Compile a blueprint + an account's settings into a frozen pipeline, cached by hash.

Every call with the same settings shares one :class:`CompiledPipeline` (and
its :class:`~app.pipeline.flow.PipelineFlow`): nothing is rebuilt per call,
and accounts on the defaults all share the same object.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.flows.steps import SlotSpec
from app.pipeline.blueprint import Blueprint, Branch
from app.pipeline.config import config_hash, effective
from app.skills.base import BoundSkill

#: Compiled pipelines kept in memory (default configurations are never evicted).
CACHE_SIZE = 256


@dataclass
class CompiledPipeline:
    hash: str
    blueprint: Blueprint
    view: dict[str, Any]
    bound: dict[str, BoundSkill]
    prelude: tuple[BoundSkill, ...]
    #: Enabled branches only, each with its enabled skills in the account's order.
    branches: dict[str, tuple[BoundSkill, ...]]
    globals: tuple[BoundSkill, ...]
    effects: tuple[BoundSkill, ...]
    slot_specs: tuple[SlotSpec, ...]
    yes_no_stages: dict[str, str]
    gated: tuple[str, ...]
    long_answer_stages: frozenset[str]
    passive: frozenset[str]
    date_slots: tuple[str, ...]
    stage_slots: dict[str, tuple[str, ...]]
    volunteerable: frozenset[str]
    flow: Any = field(default=None, repr=False)

    def branch(self, key: str) -> Branch | None:
        return self.blueprint.branches.get(key) if key in self.branches else None

    def enabled(self, key: str) -> bool:
        bound = self.bound.get(key)
        return bool(bound and bound.enabled)

    def sequence(self) -> list[BoundSkill]:
        """Every enabled skill once: prelude, then branches in order, then globals and effects."""
        seen: dict[str, BoundSkill] = {}
        for bound in (*self.prelude, *(b for skills in self.branches.values() for b in skills), *self.globals, *self.effects):
            seen.setdefault(bound.key, bound)
        return list(seen.values())


def _bind(blueprint: Blueprint, view: Mapping[str, Any], branch_keys: tuple[str, ...]) -> dict[str, BoundSkill]:
    bound: dict[str, BoundSkill] = {}
    for key in blueprint.all_keys():
        step = view["steps"][key]
        skill = blueprint.skills[key]
        opts = dict(step["options"])
        if skill.kind == "router":
            # The router only offers branches the account has switched on.
            opts["_branches"] = branch_keys
        bound[key] = BoundSkill(
            skill=skill,
            enabled=bool(step["enabled"]),
            opts=opts,
            lines={lang: dict(lines) for lang, lines in step["lines"].items()},
        )
    return bound


def build(blueprint: Blueprint, owner: Mapping[str, Any] | None = None, locks: Mapping[str, Any] | None = None, preset: Mapping[str, Any] | None = None) -> CompiledPipeline:
    view = effective(blueprint, owner, locks, preset)
    branch_keys = tuple(key for key in blueprint.branches if view["branches"][key]["enabled"])
    bound = _bind(blueprint, view, branch_keys)

    def enabled(keys) -> tuple[BoundSkill, ...]:  # noqa: ANN001
        return tuple(bound[key] for key in keys if bound[key].enabled)

    branches = {key: enabled(view["order"][key]) for key in branch_keys}
    prelude = enabled(blueprint.prelude)
    globals_ = enabled(blueprint.globals)
    effects = enabled(blueprint.effects)
    specs: dict[str, SlotSpec] = {}
    yes_no: dict[str, str] = {}
    gated: list[str] = []
    long_answer: set[str] = set()
    passive: set[str] = set()
    dates: list[str] = []
    stage_slots: dict[str, tuple[str, ...]] = {}
    volunteerable: set[str] = set()
    active = [*prelude, *(b for skills in branches.values() for b in skills), *globals_, *effects]
    for b in active:
        skill = b.skill
        for spec in skill.slot_specs(b):
            specs.setdefault(spec.key, spec)
        yes_no.update(skill.yes_no)
        gated += [key for key in skill.gated if key not in gated]
        long_answer |= set(skill.long_answer)
        passive |= set(skill.passive)
        dates += [key for key in skill.date_slots if key not in dates]
        volunteerable |= set(skill.volunteerable)
        for stage in skill.stages(b):
            stage_slots.setdefault(stage, tuple(getattr(skill, "stage_slots", {}).get(stage, (stage,))))
    compiled = CompiledPipeline(
        hash=config_hash(blueprint, owner, locks, preset),
        blueprint=blueprint,
        view=view,
        bound=bound,
        prelude=prelude,
        branches=branches,
        globals=globals_,
        effects=effects,
        slot_specs=tuple(specs.values()),
        yes_no_stages=yes_no,
        gated=tuple(gated),
        long_answer_stages=frozenset(long_answer),
        passive=frozenset(passive),
        date_slots=tuple(dates),
        stage_slots=stage_slots,
        volunteerable=frozenset(volunteerable),
    )
    from app.pipeline.flow import PipelineFlow

    flow_cls = blueprint.flow_cls or PipelineFlow
    compiled.flow = flow_cls(compiled)
    return compiled


class PipelineCache:
    """LRU of compiled pipelines keyed by config hash; default configs are pinned."""

    def __init__(self, size: int = CACHE_SIZE) -> None:
        self.size = size
        self._items: OrderedDict[str, CompiledPipeline] = OrderedDict()
        self._pinned: dict[str, CompiledPipeline] = {}
        self.hits = 0
        self.misses = 0

    def get(self, blueprint: Blueprint, owner: Mapping[str, Any] | None, locks: Mapping[str, Any] | None, preset: Mapping[str, Any] | None = None) -> CompiledPipeline:
        owner = owner if isinstance(owner, Mapping) and (owner.get("steps") or owner.get("order") or owner.get("branches")) else None
        locks = locks if isinstance(locks, Mapping) and (locks.get("locks") or {}) else None
        key = config_hash(blueprint, owner, locks, preset)
        pinned = self._pinned.get(key)
        if pinned is not None:
            self.hits += 1
            return pinned
        found = self._items.get(key)
        if found is not None:
            self._items.move_to_end(key)
            self.hits += 1
            return found
        self.misses += 1
        compiled = build(blueprint, owner, locks, preset)
        if owner is None and locks is None:
            self._pinned[key] = compiled
        else:
            self._items[key] = compiled
            while len(self._items) > self.size:
                self._items.popitem(last=False)
        return compiled

    def stats(self) -> dict[str, int]:
        return {"entries": len(self._items), "pinned": len(self._pinned), "hits": self.hits, "misses": self.misses}


PIPELINES = PipelineCache()

__all__ = ["PIPELINES", "CompiledPipeline", "PipelineCache", "build"]
