"""One OpenAI-compatible chat endpoint (a single :class:`~.endpoints.Link`).

Makes exactly one attempt: retrying, falling back and quota handling belong to
the router, so a slow provider never costs a live call more than one timeout.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.voice.llm import LLMError, LLMReply, parse_reply, shared_client
from app.voice.providers.llm.endpoints import Link, model_extras


class LLMHTTPError(LLMError):
    def __init__(self, link: Link, status: int, detail: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(f"{link.key} http {status}: {detail[:200]}")
        self.status = status
        self.headers = headers or {}


class OpenAICompatLLM:
    def __init__(
        self,
        link: Link,
        *,
        max_output_tokens: int = 300,
        timeout_seconds: float = 20.0,
        prompt_cache_key: str | None = None,
        prompt_cache_retention: str | None = None,
    ) -> None:
        self.link = link
        self.model = link.model
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.prompt_cache_key = prompt_cache_key
        self.prompt_cache_retention = prompt_cache_retention
        self._headers = {"Authorization": f"Bearer {link.api_key}", "Content-Type": "application/json"}
        #: Response headers of the last call (rate-limit bookkeeping).
        self.last_headers: dict[str, str] = {}
        self.last_ms = 0

    def body(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any],
        temperature: float | None,
    ) -> dict[str, Any]:
        endpoint = self.link.endpoint
        body: dict[str, Any] = {"model": self.model, "messages": messages, endpoint.max_tokens_field: self.max_output_tokens}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
            if endpoint.parallel_tool_calls:
                body["parallel_tool_calls"] = False
        if temperature is not None:
            body["temperature"] = temperature
        if endpoint.cache_params:
            if self.prompt_cache_key:
                body["prompt_cache_key"] = self.prompt_cache_key
            if self.prompt_cache_retention:
                body["prompt_cache_retention"] = self.prompt_cache_retention
        body.update(model_extras(self.link.provider, self.model))
        return body

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float | None = None,
    ) -> LLMReply:
        body = self.body(messages, tools=tools, tool_choice=tool_choice, temperature=temperature)
        started = time.monotonic()
        try:
            response = await shared_client().post(
                self.link.endpoint.url, content=json.dumps(body), headers=self._headers, timeout=self.timeout_seconds
            )
        except httpx.HTTPError as exc:
            raise LLMHTTPError(self.link, 0, f"{type(exc).__name__}: {exc}") from exc
        finally:
            self.last_ms = int((time.monotonic() - started) * 1000)
        self.last_headers = {k.lower(): v for k, v in response.headers.items()}
        if response.status_code != 200:
            raise LLMHTTPError(self.link, response.status_code, response.text, self.last_headers)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMHTTPError(self.link, 502, "invalid JSON body") from exc
        if not data.get("choices"):
            raise LLMHTTPError(self.link, 502, f"no choices: {str(data)[:160]}")
        return parse_reply(data)


__all__ = ["LLMHTTPError", "OpenAICompatLLM"]
