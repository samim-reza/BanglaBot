"""OpenAI-compatible chat endpoints and the per-model request knobs.

Groq, Gemini (its OpenAI-compatible surface), OpenRouter and OpenAI all speak
the Chat Completions wire format; they differ in which optional fields they
accept. A :class:`Link` is one ``provider:model`` entry of the LLM chain with
its key resolved, ready to call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.voice.providers.settings import get_provider_settings, parse_chain


@dataclass(frozen=True)
class Endpoint:
    name: str
    url: str
    #: Costs money per token (skipped unless LLM_ALLOW_PAID).
    paid: bool
    #: Accepts ``prompt_cache_key`` / ``prompt_cache_retention`` (OpenAI prompt caching).
    cache_params: bool
    #: Accepts ``parallel_tool_calls``.
    parallel_tool_calls: bool
    #: Name of the output-length field.
    max_tokens_field: str = "max_completion_tokens"


ENDPOINTS: dict[str, Endpoint] = {
    "openai": Endpoint("openai", "https://api.openai.com/v1/chat/completions", True, True, True),
    "groq": Endpoint("groq", "https://api.groq.com/openai/v1/chat/completions", False, False, True),
    "gemini": Endpoint(
        "gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", False, False, False, "max_tokens"
    ),
    "openrouter": Endpoint("openrouter", "https://openrouter.ai/api/v1/chat/completions", False, False, True, "max_tokens"),
}


@dataclass(frozen=True)
class Link:
    provider: str
    model: str
    endpoint: Endpoint
    api_key: str = field(repr=False)

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def paid(self) -> bool:
        return self.endpoint.paid


def model_extras(provider: str, model: str) -> dict[str, Any]:
    """Request fields that keep a model fast on a live call (no long hidden reasoning)."""
    name = model.lower()
    if provider == "openai":
        effort = get_settings().openai_llm_reasoning_effort
        return {"reasoning_effort": effort} if effort else {}
    if provider == "groq" and "gpt-oss" in name:
        return {"reasoning_effort": "low", "include_reasoning": False}
    if provider == "groq" and "qwen" in name:
        return {"reasoning_effort": "none", "reasoning_format": "hidden"}
    if provider == "gemini":
        # Measured 2026-10-16: 3.1-flash-lite with thinking off ≈ 1 s; the "-latest"
        # aliases reject "none" and take 5–18 s with default thinking.
        return {"reasoning_effort": "none"} if "lite" in name and "latest" not in name else {"reasoning_effort": "low"}
    return {}


def _api_key(provider: str) -> str | None:
    if provider == "openai":
        return get_settings().openai_api_key
    return getattr(get_provider_settings(), f"{provider}_api_key", None)


def resolve_links(chain: str | list[str] | None = None, *, allow_paid: bool | None = None) -> list[Link]:
    """Turn ``"groq:openai/gpt-oss-120b,gemini:…"`` into callable links.

    Entries whose provider is unknown or has no key are skipped; paid
    providers only when allowed. The model part may itself contain ``:``.
    """
    pset = get_provider_settings()
    allow = pset.llm_allow_paid if allow_paid is None else allow_paid
    entries = chain if isinstance(chain, list) else parse_chain(chain if chain is not None else pset.llm_chain)
    links: list[Link] = []
    for entry in entries:
        provider, _, model = entry.partition(":")
        endpoint = ENDPOINTS.get(provider.strip())
        model = model.strip()
        if endpoint is None or not model or (endpoint.paid and not allow):
            continue
        key = _api_key(endpoint.name)
        if key:
            links.append(Link(endpoint.name, model, endpoint, key))
    return links


__all__ = ["ENDPOINTS", "Endpoint", "Link", "model_extras", "resolve_links"]
