"""Skill tools on a pipeline flow: collected from enabled skills, usable only while their skill is active."""

from __future__ import annotations

from typing import Any

from app.flows.context import CallContext
from app.skills.base import BoundSkill


class PipelineToolsMixin:
    def _tool_owners(self) -> dict[str, BoundSkill]:
        owners: dict[str, BoundSkill] = {}
        for bound in self.cp.sequence():
            for schema in bound.skill.tools(bound):
                owners.setdefault(str(schema["function"]["name"]), bound)
        return owners

    def extra_tool_schemas(self) -> list[dict[str, Any]]:
        """Stable per compiled pipeline (part of the cached prompt prefix)."""
        seen: set[str] = set()
        schemas: list[dict[str, Any]] = []
        for bound in self.cp.sequence():
            for schema in bound.skill.tools(bound):
                name = str(schema["function"]["name"])
                if name not in seen:
                    seen.add(name)
                    schemas.append(schema)
        return schemas

    def extra_tool_names(self) -> set[str]:
        return set(self._tool_owners())

    def run_extra_tool(self, name: str, args: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str, *, caller_text: str = "") -> dict[str, Any]:
        owner = self._tool_owners().get(name)
        if owner is None:
            return {"ok": False, "reason": "unknown_tool"}
        if owner.key not in {b.key for b in self.active(slots)} or not owner.skill.applies(owner, slots, ctx):
            return {"ok": False, "reason": "not_now"}  # the tool guard: only while its skill is active
        return owner.skill.run_tool(owner, name, args, slots, ctx, language, caller_text=caller_text)


__all__ = ["PipelineToolsMixin"]
