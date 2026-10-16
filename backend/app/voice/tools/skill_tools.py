"""Tools a skill brings (e.g. the restaurant cart), guarded so they only work while that skill is active.

A skill tool returns internal slot updates (the cart is not a ``save_details``
field) which the runtime applies, then the backend speaks the next line —
the same one-round-trip turn as ``save_details``.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.flows.base import STAGE_COMMIT
from app.voice.tools.store import ToolResult
from app.voice.tools.text import _join, answer_only

logger = structlog.get_logger(__name__)


class SkillToolsMixin:
    def _skill_tool_names(self) -> set[str]:
        names = getattr(self.flow, "extra_tool_names", None)
        return set(names()) if names is not None else set()

    async def _skill_tool(self, name: str, args: dict[str, Any], caller_text: str) -> ToolResult:
        if self.outcome and self.closing_spoken:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        reply = answer_only(" ".join(str(args.pop("reply", "") or "").split()))
        outcome = self.flow.run_extra_tool(name, args, self.runtime.slots, self.runtime.ctx, self.language, caller_text=caller_text)
        if not outcome.get("ok"):
            await logger.ainfo("skill_tool_refused", tool=name, reason=outcome.get("reason"))
            instruction = self.runtime.current_instruction()
            payload = {"ok": False, "reason": outcome.get("reason", "not_now"), "instruction": instruction.for_model(self.language)}
            return ToolResult(payload=payload)
        result = self.runtime.apply_internal(outcome.get("updates") or {})
        if outcome.get("save"):
            result = self.runtime.save(dict(outcome["save"]))
        result["tool"] = {k: v for k, v in outcome.items() if k not in ("ok", "updates", "say", "save")}
        if self.runtime.stage == STAGE_COMMIT and not self.outcome:
            return await self._commit(reply)
        said = str(outcome.get("say") or "")
        if said:
            reply = ""  # the tool reports what it actually did ("the cannoli isn't available") — not the model's guess
        instruction = self.runtime.last_instruction
        if instruction is not None and instruction.verbatim and not instruction.end_call:
            return self._speak_next(result, _join(reply, said, instruction.text), stage=self.runtime.stage)
        return ToolResult(payload=result)


__all__ = ["SkillToolsMixin"]
