"""One caller turn through the model: the instant ack, the model <-> tool loop (bounded
hops), tool results spoken straight from the backend, and the recovery line."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import structlog

from app.flows import hearing
from app.pipeline import faq_cache
from app.voice.audio import clean_spoken_text
from app.voice.languages import phrase
from app.voice.llm import LLMReply
from app.voice.tools import SAVE_DETAILS, ToolResult, answer_only

logger = structlog.get_logger(__name__)

#: A reply that announces a result ("you're booked", "your order is confirmed") — only a tool may say that.
_CLAIMS_DONE = re.compile(
    r"\b(?:you'?re|you are|it'?s|it is|that'?s|has been|is now|have been)\s+(?:all\s+)?(?:booked|confirmed|cancell?ed|scheduled|reserved|set)\b"
    r"|\b(?:booking|appointment|order|reservation|visit|viewing)\s+(?:is|has been)\s+(?:confirmed|booked|cancell?ed|placed)\b",
    re.IGNORECASE,
)

# Max model ↔ tool hops per caller turn.
MAX_TOOL_HOPS = 6


class TurnMixin:
    """Mixed into :class:`~app.voice.agent.core.CallAgent`."""

    async def handle_turn(self, text: str) -> None:
        """One caller turn. Until a tool runs or a reply is queued it has changed nothing, so a
        cancel (the caller kept talking) rolls it back without a trace; a turn cut off later
        (the transport's deadline) never leaves a tool call without its tool reply."""
        mark, turns = len(self.messages), self.turns
        self.interruptible = True
        try:
            await self._handle_turn(text)
        except asyncio.CancelledError:
            if self.interruptible:
                removed = self.messages[mark:]
                del self.messages[mark:]
                # Step directives flushed at the start of this turn still apply to the next one.
                self._pending_directives[:0] = [m["content"] for m in removed if m.get("role") == "system"]
                self.turns = turns
            else:
                self._drop_dangling_tool_calls()
            raise
        finally:
            self.interruptible = False
            self.skip_ack = False

    def _drop_dangling_tool_calls(self) -> None:
        """Chat Completions rejects an assistant tool call without its tool reply: cut from there."""
        for index in range(len(self.messages) - 1, -1, -1):
            message = self.messages[index]
            calls = message.get("tool_calls") if message.get("role") == "assistant" else None
            if not calls:
                continue
            answered = {m.get("tool_call_id") for m in self.messages[index + 1 :] if m.get("role") == "tool"}
            if not all(call.get("id") in answered for call in calls):
                del self.messages[index:]
            return

    async def _handle_turn(self, text: str) -> None:
        llm = self.llm
        if llm is None or self.speaker.closed:
            return
        self.turns += 1
        self.last_user_text = text
        if await self._fast_path(text):
            self.fast_turns += 1
            return
        if await self._cached_answer(text):
            self.fast_turns += 1
            return
        self._flush_directives()
        self.messages.append({"role": "user", "content": text})
        if self.settings.voice_instant_ack and not self.skip_ack and not self.speaker.assistant_speaking and not self.speaker.closing:
            # One cached word right away; the real reply queues behind it — but not
            # a "yes" on top of a caller who just said no.
            labels = hearing.classify(text)
            if not labels & {"no", "not_me", "wrong_number", "later", "repeat"}:
                self.speaker.speak(self.next_ack())
        for hop in range(MAX_TOOL_HOPS):
            if self.speaker.closed or self.speaker.closing:
                return
            started = time.monotonic()
            messages, tools = self._request(text)
            reply = await llm.complete(messages, tools=tools, temperature=self.settings.openai_llm_temperature)
            logger.info(
                "turn_llm_reply",
                call_log_id=self.call_log_id,
                hop=hop,
                ms=int((time.monotonic() - started) * 1000),
                tool_calls=[c.name for c in reply.tool_calls],
                cached=int(((reply.usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
            )
            # The model has answered: from here the turn acts (tools, speech) and is no longer cancellable.
            self.interruptible = False
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
                # Nothing from the model: ask the current question again rather than "something went wrong".
                instruction = self.runtime.current_instruction()
                line = instruction.text if instruction.verbatim and not instruction.end_call else phrase("unclear_2", self.language)
                self.messages.append({"role": "assistant", "content": line})
                self.speaker.speak(line)
                return
            if _CLAIMS_DONE.search(content) and not self.tools.outcome:
                # The model says "you're booked" but nothing was saved this turn — never let that reach the caller.
                await logger.awarning("agent_claimed_unsaved_outcome", call_log_id=self.call_log_id, stage=self.runtime.stage)
                if self.runtime.stage == "confirm" and hearing.supports(text, "confirm", identity=bool(self.flow.identity_gate)):
                    result = await self.tools.execute(SAVE_DETAILS, {"confirmed": True}, caller_text=text)
                    if result.say:
                        message = {"role": "assistant", "content": result.say}
                        self.messages.append(message)
                        self._speak_result(result, message_ref=message)
                        return
                instruction = self.runtime.current_instruction()
                if instruction.verbatim and not instruction.end_call:
                    content = instruction.text
            message = reply.assistant_message or {"role": "assistant", "content": content}
            message = {**message, "content": content}
            self.messages.append(message)
            self.speaker.speak(content, message_ref=message)
            await faq_cache.store(self.ctx, self.runtime.stage, self.language, text, answer_only(content))
            return
        await logger.awarning("agent_tool_hop_limit", call_log_id=self.call_log_id, hops=MAX_TOOL_HOPS)
        self.speaker.speak(phrase("recovery", self.language))

    def _record_turn(self, text: str, result: ToolResult) -> None:
        self.interruptible = False
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
        self.interruptible = False
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
