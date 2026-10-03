"""The call brain: ``gpt-5.4-mini`` over Chat Completions with the flow tools.

Plain text in, plain text or tool calls out. The agent owns the conversation
history (system prompt + node directives + caller/agent turns + tool results),
calls :meth:`ChatLLM.complete`, runs any tool calls, and loops until the model
answers in words or a tool result carries the line to speak.

Cost / latency:

- one process-wide keep-alive connection pool, so a call's first request does
  not pay a fresh TLS handshake (warmed at startup);
- ``prompt_cache_key`` (flow + account) routes calls that share a prompt prefix
  to the same cache; cached input tokens are ~10x cheaper and faster;
- the prompt is built most-stable-first (see ``voice/prompts.py``).
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
MODELS_URL = "https://api.openai.com/v1/models"

_shared_client: httpx.AsyncClient | None = None


def shared_client() -> httpx.AsyncClient:
    """One keep-alive pool for every call in this process."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=120.0),
        )
    return _shared_client


async def warm_connection(api_key: str | None) -> None:
    """Open (and keep) a TLS connection to OpenAI before the first call needs it."""
    if not api_key:
        return
    try:
        await shared_client().get(MODELS_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=5.0)
    except Exception as exc:  # noqa: BLE001 — an optimization only
        await logger.ainfo("openai_warm_failed", error=str(exc))


async def close_shared_client() -> None:
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


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
        prompt_cache_key: str | None = None,
        prompt_cache_retention: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.prompt_cache_key = prompt_cache_key
        self.prompt_cache_retention = prompt_cache_retention
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
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
        if self.prompt_cache_key:
            body["prompt_cache_key"] = self.prompt_cache_key
        if self.prompt_cache_retention:
            body["prompt_cache_retention"] = self.prompt_cache_retention
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
        client = shared_client()
        for attempt in (1, 2, 3):
            try:
                response = await client.post(
                    CHAT_COMPLETIONS_URL, content=json.dumps(body), headers=self._headers, timeout=self.timeout_seconds
                )
                if response.status_code == 200:
                    return response.json()
                detail = response.text[:300]
                last_error = LLMError(f"openai_chat_http_{response.status_code}: {detail}")
                if response.status_code == 400 and "prompt_cache_retention" in body and "prompt_cache_retention" in detail:
                    # The model does not support extended retention: retry without it.
                    body = {key: value for key, value in body.items() if key != "prompt_cache_retention"}
                    self.prompt_cache_retention = None
                    continue
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
        """Nothing to close per call: the connection pool is shared by the process."""
        return None
