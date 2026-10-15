"""One caller turn through the model: the instant ack, the model <-> tool loop (bounded
hops), tool results spoken straight from the backend, and the recovery line."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from app.flows import hearing
from app.pipeline import faq_cache
from app.voice.audio import clean_spoken_text
from app.voice.languages import phrase
from app.voice.llm import LLMReply
from app.voice.tools import ToolResult, answer_only

logger = structlog.get_logger(__name__)

# Max model ↔ tool hops per caller turn.
MAX_TOOL_HOPS = 6


class TurnMixin:
    """Mixed into :class:`~app.voice.agent.core.CallAgent`."""

    async def handle_turn(self, text: str) -> None:
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
            await faq_cache.store(self.ctx, self.runtime.stage, self.language, text, answer_only(content))
            return
        await logger.awarning("agent_tool_hop_limit", call_log_id=self.call_log_id, hops=MAX_TOOL_HOPS)
        self.speaker.speak(phrase("recovery", self.language))

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
