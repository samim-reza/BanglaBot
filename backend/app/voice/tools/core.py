"""``CallTools``: the tools the model may call during a call, assembled from small mixins."""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.flows.base import Terminal
from app.flows.runtime import FlowRuntime
from app.voice.tools.store import CallStore, ToolResult
from app.voice.tools.text import END_CALL, SAVE_DETAILS, TRANSFER_TO_HUMAN
from app.voice.tools.commit import CommitMixin
from app.voice.tools.endings import EndingsMixin
from app.voice.tools.saving import SavingMixin
from app.voice.tools.schemas import SchemasMixin
from app.voice.tools.skill_tools import SkillToolsMixin

logger = structlog.get_logger(__name__)


class CallTools(SchemasMixin, SavingMixin, SkillToolsMixin, CommitMixin, EndingsMixin):
    def __init__(self, runtime: FlowRuntime, store: CallStore, *, support_phone: str = "") -> None:
        self.runtime = runtime
        self.store = store
        self.support_phone = str(support_phone or "").strip()
        self.flow = runtime.flow
        self._terminals: dict[str, Terminal] = {t.name: t for t in self.flow.terminals()}
        self.outcome: str = ""
        self.record_id: str = str(getattr(runtime.ctx.record, "id", "") or "")
        self.note_lines: list[str] = []
        self.closing_spoken: bool = False
        #: Stage whose backend line was spoken last (a repeated read-back is shortened).
        self._spoken_stage: str = ""

    async def execute(self, name: str, arguments: Any, *, caller_text: str = "") -> ToolResult:
        args = self._parse_args(arguments)
        caller_text = str(caller_text or "")
        if name == SAVE_DETAILS:
            return await self._save_details(args, caller_text)
        if name in self._terminals:
            return await self._terminal(self._terminals[name], args, caller_text)
        if name == TRANSFER_TO_HUMAN:
            return await self._transfer(args)
        if name == END_CALL:
            return await self._end_call(args, caller_text)
        if name in self._skill_tool_names():
            return await self._skill_tool(name, args, caller_text)
        return ToolResult(payload={"ok": False, "error": f"unknown tool {name}"})

    @staticmethod
    def _parse_args(arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return dict(arguments)
        try:
            parsed = json.loads(arguments) if str(arguments or "").strip() else {}
        except json.JSONDecodeError:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def language(self) -> str:
        return self.runtime.language

