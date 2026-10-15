"""The LLM a call talks to: an ordered chain with quota-aware fallback.

Free tiers (Groq, Gemini) have tight per-minute and per-day limits. The router
skips a model the quota book says is exhausted, falls through on 429 / 5xx /
timeouts, and keeps per-model usage so the finance engine can price every
request on the model that actually served it.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.voice.llm import LLMError, LLMReply, usage_counts
from app.voice.providers.llm.client import LLMHTTPError, OpenAICompatLLM
from app.voice.providers.llm.endpoints import Link
from app.voice.providers.llm.quota import QUOTAS, QuotaBook
from app.voice.providers.spend import over_cap

logger = structlog.get_logger(__name__)


def estimate_tokens(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> int:
    """Rough prompt size (≈ 4 characters per token) for quota checks and budgets."""
    chars = sum(len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls") or "")) for m in messages)
    chars += len(json.dumps(tools)) if tools else 0
    return chars // 4 + 4 * len(messages)


class RoutedLLM:
    def __init__(
        self,
        links: list[Link],
        *,
        max_output_tokens: int = 300,
        timeout_seconds: float = 20.0,
        prompt_cache_key: str | None = None,
        prompt_cache_retention: str | None = None,
        quotas: QuotaBook | None = None,
    ) -> None:
        if not links:
            raise LLMError("no LLM provider configured (set GROQ_API_KEY / GEMINI_API_KEY, or OPENAI_API_KEY + LLM_ALLOW_PAID)")
        self.links = links
        self.quotas = quotas or QUOTAS
        self.max_output_tokens = max_output_tokens
        self._clients = [
            OpenAICompatLLM(
                link,
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout_seconds,
                prompt_cache_key=prompt_cache_key,
                prompt_cache_retention=prompt_cache_retention,
            )
            for link in links
        ]
        self.request_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_prompt_tokens = 0
        self.fallbacks = 0
        self.last_link: Link | None = None
        self.last_ms = 0
        self.by_model: dict[str, dict[str, int]] = {}

    # ---- identity ------------------------------------------------------------------
    @property
    def model(self) -> str:
        return (self.last_link or self.links[0]).model

    @property
    def provider(self) -> str:
        return (self.last_link or self.links[0]).provider

    def preferred_profile(self) -> str:
        """``cached`` when the chain starts on a provider with prompt caching (OpenAI), else ``compact``."""
        return "cached" if self.links[0].endpoint.cache_params else "compact"

    # ---- completion ----------------------------------------------------------------
    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float | None = None,
    ) -> LLMReply:
        need = estimate_tokens(messages, tools) + self.max_output_tokens
        errors: list[str] = []
        skipped: list[OpenAICompatLLM] = []
        capped: list[OpenAICompatLLM] = []
        for index, client in enumerate(self._clients):
            if over_cap(client.link.provider):
                capped.append(client)  # today's spend cap reached (admin → Finance → caps)
                continue
            if not self.quotas.available(client.link.key, need):
                skipped.append(client)
                continue
            reply = await self._try(client, messages, tools, tool_choice, temperature, errors)
            if reply is not None:
                if index:
                    self.fallbacks += 1
                return reply
        # Every model looked exhausted: try the skipped ones anyway, a stale
        # quota estimate is better than a silent call — and a capped one last of all.
        for client in (*skipped, *capped):
            reply = await self._try(client, messages, tools, tool_choice, temperature, errors)
            if reply is not None:
                self.fallbacks += 1
                return reply
        raise LLMError("all LLM providers failed: " + " | ".join(errors[-4:]))

    async def _try(self, client, messages, tools, tool_choice, temperature, errors) -> LLMReply | None:  # noqa: ANN001
        key = client.link.key
        try:
            reply = await client.complete(messages, tools=tools, tool_choice=tool_choice, temperature=temperature)
        except LLMHTTPError as exc:
            self.quotas.note_failure(key, exc.status, exc.headers, str(exc))
            errors.append(str(exc))
            await logger.awarning("llm_link_failed", link=key, status=exc.status, ms=client.last_ms, error=str(exc)[:160])
            return None
        self.quotas.note_response(key, client.last_headers)
        self._record(client, reply)
        return reply

    def _record(self, client: OpenAICompatLLM, reply: LLMReply) -> None:
        prompt, completion, cached = usage_counts(reply.usage)
        self.request_count += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_prompt_tokens += cached
        self.last_link = client.link
        self.last_ms = client.last_ms
        row = self.by_model.setdefault(client.link.key, {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0})
        row["requests"] += 1
        row["prompt_tokens"] += prompt
        row["completion_tokens"] += completion
        row["cached_tokens"] += cached

    # ---- reporting -----------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "requests": self.request_count,
            "prompt_tokens": self.prompt_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "fallbacks": self.fallbacks,
            "by_model": {key: dict(row) for key, row in self.by_model.items()},
        }

    async def aclose(self) -> None:
        """Nothing per call: the connection pool is shared by the process."""
        return None


__all__ = ["RoutedLLM", "estimate_tokens"]
