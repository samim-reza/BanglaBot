"""The call brain: ``gpt-5.4-mini`` over Chat Completions with the flow tools.

Plain text in, plain text or tool calls out. The bridge owns the conversation
history (system prompt + node directives + caller/agent turns + tool results),
calls :meth:`ChatLLM.complete`, runs any tool calls through the call tools,
appends their results, and loops until the model answers in words — which
Azure TTS then speaks.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


def chat_tools_from_realtime(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Realtime tool schemas (flat ``name``/``parameters``) → Chat Completions shape."""
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            converted.append(tool)
            continue
        name = tool.get("name")
        if not name:
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description") or "",
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return converted


@dataclass(slots=True)
class LLMToolCall:
    id: str
    name: str
    arguments: str


@dataclass(slots=True)
class LLMReply:
    content: str
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    assistant_message: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMError(RuntimeError):
    pass


class ChatLLM:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str | None = None,
        max_output_tokens: int = 400,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        self.request_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_prompt_tokens = 0

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float | None = None,
    ) -> LLMReply:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": self.max_output_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
            body["parallel_tool_calls"] = False
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        if temperature is not None:
            body["temperature"] = temperature
        data = await self._post(body)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        self.request_count += 1
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.cached_prompt_tokens += int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
        tool_calls = [
            LLMToolCall(
                id=str(call.get("id") or ""),
                name=str((call.get("function") or {}).get("name") or ""),
                arguments=str((call.get("function") or {}).get("arguments") or "{}"),
            )
            for call in (message.get("tool_calls") or [])
            if isinstance(call, dict)
        ]
        return LLMReply(
            content=str(message.get("content") or "").strip(),
            tool_calls=tool_calls,
            usage=usage,
            assistant_message=message,
            finish_reason=str(choice.get("finish_reason") or ""),
        )

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in (1, 2, 3):
            try:
                response = await self._client.post(CHAT_COMPLETIONS_URL, content=json.dumps(body))
                if response.status_code == 200:
                    return response.json()
                detail = response.text[:300]
                last_error = LLMError(f"openai_chat_http_{response.status_code}: {detail}")
                if response.status_code not in {429, 500, 502, 503, 504}:
                    break
            except httpx.HTTPError as exc:
                last_error = exc
            await asyncio.sleep(0.4 * attempt)
        raise LLMError(str(last_error or "openai_chat_failed"))

    def stats(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "requests": self.request_count,
            "prompt_tokens": self.prompt_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }

    async def aclose(self) -> None:
        await self._client.aclose()
