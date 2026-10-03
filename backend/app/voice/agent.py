"""The conversation brain of one call — independent of how audio gets in and out.

``CallAgent`` owns the prompt, the flow runtime, the tools and the model loop.
A *speaker* (the phone/browser audio bridge, or the text chat session) gives
it caller turns and speaks what it decides:

    caller text ─▶ fast path? (clean yes/no on a scripted step → no model at all)
                 └▶ model (gpt-5.4-mini + flow tools) ─▶ tools ─▶ line to speak

Turn economics: a backend-owned next line (verbatim instruction) is spoken
straight from the tool result, so a normal turn is ONE model round-trip —
and a clean yes/no on a scripted step is zero.
"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

import structlog

from app.flows import hearing
from app.flows.base import STAGE_COMMIT, STAGE_DONE, STAGE_RELAY, STAGE_WRONG_NUMBER, Flow
from app.flows.context import CallContext
from app.flows.runtime import FlowRuntime
from app.voice import jev
from app.voice.audio import clean_spoken_text
from app.voice.languages import ack_lines, phrase
from app.voice.llm import ChatLLM, LLMReply
from app.voice.prompts import build_messages
from app.voice.tools import SAVE_DETAILS, CallStore, CallTools, ToolResult

logger = structlog.get_logger(__name__)

# Max model ↔ tool hops per caller turn.
MAX_TOOL_HOPS = 6


class Speaker(Protocol):
    """What the agent needs from a transport."""

    closed: bool
    closing: bool
    assistant_speaking: bool

    def speak(
        self,
        text: str,
        *,
        allow_barge_in: bool = True,
        message_ref: dict[str, Any] | None = None,
        close_after: bool = False,
        transfer_to: str = "",
    ) -> Any: ...

    def schedule_hangup(self) -> None: ...


class CallAgent:
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
        self.llm: ChatLLM | None = None
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

    # ------------------------------------------------------------------ one caller turn
    async def handle_turn(self, text: str) -> None:
        llm = self.llm
        if llm is None or self.speaker.closed:
            return
        self.turns += 1
        self.last_user_text = text
        if await self._fast_path(text):
            self.fast_turns += 1
            return
        self._flush_directives()
        self.messages.append({"role": "user", "content": text})
        if self.settings.voice_instant_ack and not self.speaker.assistant_speaking and not self.speaker.closing:
            # One cached word right away; the real reply queues behind it — but not
            # a "yes" on top of a caller who just said no.
            labels = hearing.classify(text)
            if not labels & {"no", "not_me", "wrong_number", "later", "repeat"}:
                self.speaker.speak(self.next_ack())
        for hop in range(MAX_TOOL_HOPS):
            if self.speaker.closed or self.speaker.closing:
                return
            started = time.monotonic()
            reply = await llm.complete(self.messages, tools=self.current_tools, temperature=self.settings.openai_llm_temperature)
            logger.info(
                "turn_llm_reply",
                call_log_id=self.call_log_id,
                hop=hop,
                ms=int((time.monotonic() - started) * 1000),
                tool_calls=[c.name for c in reply.tool_calls],
                cached=int(((reply.usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
            )
            if reply.tool_calls:
                self.messages.append(self._assistant_tool_message(reply))
                stop = False
                for call in reply.tool_calls:
                    result = await self._run_tool_call(call.id, call.name, call.arguments)
                    stop = stop or result.stop
                if stop or self.speaker.closed or self.speaker.closing:
                    return
                continue
            content = clean_spoken_text(reply.content)
            if not content:
                await logger.ainfo("agent_empty_reply", call_log_id=self.call_log_id, finish_reason=reply.finish_reason)
                line = phrase("recovery", self.language)
                self.messages.append({"role": "assistant", "content": line})
                self.speaker.speak(line)
                return
            message = reply.assistant_message or {"role": "assistant", "content": content}
            message = {**message, "content": content}
            self.messages.append(message)
            self.speaker.speak(content, message_ref=message)
            return
        await logger.awarning("agent_tool_hop_limit", call_log_id=self.call_log_id, hops=MAX_TOOL_HOPS)
        self.speaker.speak(phrase("recovery", self.language))

    async def _fast_path(self, text: str) -> bool:
        """Answer scripted yes/no steps without the model.

        Steps with a backend-owned next line (identity, address check, a booking
        read-back, "will you come?") are answered from the hearing module when the
        caller's words are unambiguous: the slot is saved and the next line is
        spoken straight away — from the TTS cache when it is a fixed line. Anything
        less than a clean answer goes the normal way.
        """
        if self.speaker.closing:
            return False
        stage = self.runtime.stage
        labels = hearing.classify(text)
        if not labels:
            # Nothing the keyword matcher recognises: maybe a natural yes/no Jev can settle.
            fields = await self._jev_fields(stage, text)
            return bool(fields) and await self._speak_fast_fields(stage, text, fields, heard=self._jev_heard(fields))
        if "repeat" in labels:
            return False
        terminal = getattr(self.flow, "fast_terminal", None)
        if terminal is not None:
            name = terminal(stage, text, labels, self.runtime.slots, self.ctx)
            if name:
                result = await self.tools.execute(name, {}, caller_text=text)
                if result.say:
                    self._record_turn(text, result)
                    logger.info("turn_fast_path", call_log_id=self.call_log_id, stage=stage, terminal=name)
                    return True
                return False
        if "later" in labels or hearing.looks_like_question(text):
            return False
        fields = self.flow.fast_fields(stage, text, labels, self.runtime.slots, self.ctx)
        heard = text
        if not fields:
            fields = await self._jev_fields(stage, text, labels)
            heard = self._jev_heard(fields)
        if not fields:
            return False
        return await self._speak_fast_fields(stage, text, fields, heard=heard)

    async def _jev_fields(self, stage: str, text: str, labels: set[str] | None = None) -> dict[str, Any] | None:
        """A yes/no step the keyword matcher couldn't settle: ask Jev (off without an API key)."""
        slot = (getattr(self.flow, "yes_no_stages", None) or {}).get(stage)
        if not slot or not jev.enabled(self.language) or hearing.looks_like_question(text):
            return None
        if labels and labels & {"repeat", "later", "not_me", "wrong_number"}:
            return None
        confirms_cancel = getattr(self.flow, "confirms_cancellation", None)
        if confirms_cancel is not None and confirms_cancel(self.runtime.slots, self.ctx):
            # A cancellation needs the caller's own unmistakable words — never a model's guess.
            return None
        question = next((m.get("content") or "" for m in reversed(self.messages) if m.get("role") == "assistant"), "")
        decision = await jev.decide_yes_no(str(question), text, language=self.language)
        if decision is None:
            return None
        return {slot: decision == "yes"}

    @staticmethod
    def _jev_heard(fields: dict[str, Any] | None) -> str:
        """What the hearing gate checks when Jev decided: its confident verdict, as a plain answer."""
        if not fields:
            return ""
        return "yes" if next(iter(fields.values())) is True else "no"

    async def _speak_fast_fields(self, stage: str, text: str, fields: dict[str, Any], *, heard: str = "") -> bool:
        # Decide whether a line would be spoken BEFORE touching the runtime, so a
        # step the model must phrase itself leaves the flow untouched.
        preview = self.runtime.preview(fields)
        speakable = (
            (preview.instruction.verbatim and not preview.instruction.end_call)
            or preview.stage in (STAGE_COMMIT, STAGE_RELAY, STAGE_WRONG_NUMBER)
            or (preview.stage == STAGE_DONE and bool(self.tools.outcome) and not self.tools.closing_spoken)
        )
        if not speakable:
            return False
        result = await self.tools.execute(SAVE_DETAILS, fields, caller_text=heard or text)
        if not result.say:
            return False
        self._record_turn(text, result)
        logger.info("turn_fast_path", call_log_id=self.call_log_id, stage=stage, next_stage=self.runtime.stage, saved=sorted(fields))
        return True

    def _record_turn(self, text: str, result: ToolResult) -> None:
        self.messages.append({"role": "user", "content": text})
        self._flush_directives()
        message = {"role": "assistant", "content": result.say}
        self.messages.append(message)
        self._speak_result(result, message_ref=message)

    @staticmethod
    def _assistant_tool_message(reply: LLMReply) -> dict[str, Any]:
        if reply.assistant_message:
            return reply.assistant_message
        return {
            "role": "assistant",
            "content": reply.content or None,
            "tool_calls": [
                {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
                for call in reply.tool_calls
            ],
        }

    async def _run_tool_call(self, call_id: str, name: str, raw_args: str) -> ToolResult:
        try:
            result = await self.tools.execute(name, raw_args, caller_text=self.last_user_text)
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("tool_execution_failed", call_log_id=self.call_log_id, tool_name=name, error=str(exc))
            result = ToolResult(
                payload={"ok": False, "error": "tool_failed", "instruction": "Briefly apologise and ask the caller to repeat their last answer."}
            )
        self.messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result.payload, ensure_ascii=False, default=str)})
        self._flush_directives()
        if result.say:
            message = {"role": "assistant", "content": result.say}
            self.messages.append(message)
            self._speak_result(result, message_ref=message)
        elif result.hang_up:
            self.speaker.closing = True
            self.speaker.schedule_hangup()
        return result

    def _speak_result(self, result: ToolResult, *, message_ref: dict[str, Any] | None = None) -> None:
        ending = bool(result.hang_up or result.transfer_to)
        if ending:
            self.speaker.closing = True
        self.speaker.speak(
            result.say,
            allow_barge_in=not ending,
            message_ref=message_ref,
            close_after=bool(result.hang_up),
            transfer_to=result.transfer_to,
        )

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


__all__ = ["MAX_TOOL_HOPS", "CallAgent", "Speaker"]
