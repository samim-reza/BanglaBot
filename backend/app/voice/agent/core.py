"""``CallAgent``: one call's conversation state — prompt, flow runtime, tools — assembled
from the turn / fast-path / prompt-profile mixins."""

from __future__ import annotations

from typing import Any

from app.flows.base import Flow
from app.flows.context import CallContext
from app.flows.runtime import FlowRuntime
from app.voice.agent.fast_path import FastPathMixin
from app.voice.agent.prompt_profile import PromptProfileMixin
from app.voice.agent.protocol import Speaker
from app.voice.agent.turn import TurnMixin
from app.voice.languages import ack_lines
from app.voice.prompts import build_messages
from app.voice.providers.base import LLMClient
from app.voice.tools import CallStore, CallTools


class CallAgent(TurnMixin, FastPathMixin, PromptProfileMixin):
    def __init__(
        self,
        *,
        flow: Flow,
        ctx: CallContext,
        store: CallStore,
        speaker: Speaker,
        language: str,
        settings: Any,
        call_log_id: str = "",
        support_phone: str = "",
    ) -> None:
        self.flow = flow
        self.ctx = ctx
        self.store = store
        self.speaker = speaker
        self.language = language
        self.settings = settings
        self.call_log_id = call_log_id
        self.runtime = FlowRuntime(flow, ctx, language=language, on_directive=self._on_directive)
        self.tools = CallTools(self.runtime, store, support_phone=support_phone)
        self.messages: list[dict[str, Any]] = []
        # Node directives raised while a tool runs; appended only AFTER the tool
        # reply, because Chat Completions requires the tool message to directly
        # follow the assistant message that called it.
        self._pending_directives: list[str] = []
        self.current_tools: list[dict[str, Any]] = self.tools.schemas()
        self.llm: LLMClient | None = None
        self.last_user_text = ""
        self.turns = 0
        self.fast_turns = 0
        self._ack_index = 0

    # ------------------------------------------------------------------ setup
    def opening(self) -> str:
        return self.runtime.opening()

    def configure(self) -> str:
        """Build the prompt; returns the opening line the transport speaks first."""
        opening = self.opening()
        self.messages = build_messages(
            self.flow, self.ctx, language=self.language, opening=opening, initial_directive=self.runtime.initial_directive()
        )
        # The greeting + first question are spoken by the transport; the model sees them as its own words.
        self.messages.append({"role": "assistant", "content": opening})
        return opening

    def _on_directive(self, directive: str) -> None:
        if self.messages:
            self._pending_directives.append(directive)

    def _flush_directives(self) -> None:
        for directive in self._pending_directives:
            self.messages.append({"role": "system", "content": directive})
        self._pending_directives.clear()

    @property
    def outcome(self) -> str:
        return self.tools.outcome

    def next_ack(self) -> str:
        lines = ack_lines(self.language)
        line = lines[self._ack_index % len(lines)]
        self._ack_index += 1
        return line

    # ------------------------------------------------------------------ transport-driven endings
    async def settle(self, outcome: str) -> str:
        return await self.tools.settle(outcome)

    async def abandon(self, outcome: str) -> None:
        await self.tools.abandon(outcome)

    def state(self) -> dict[str, Any]:
        """A snapshot for test consoles: stage, slots, outcome."""
        return {
            "stage": self.runtime.stage,
            "node": self.runtime.current_node,
            "slots": self.runtime.flow_data(),
            "outcome": self.tools.outcome,
            "record_id": self.tools.record_id,
        }


__all__ = ["CallAgent"]
