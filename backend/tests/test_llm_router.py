"""LLM provider chain: request shapes per provider, quota-aware fallback, reply parsing."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.voice.llm import LLMError, clean_assistant_message, parse_reply
from app.voice.providers.llm import client as client_module
from app.voice.providers.llm.client import OpenAICompatLLM
from app.voice.providers.llm.endpoints import ENDPOINTS, Link, model_extras, resolve_links
from app.voice.providers.llm.quota import QuotaBook, parse_duration
from app.voice.providers.llm.router import RoutedLLM, estimate_tokens
from app.voice.providers.settings import get_provider_settings

MESSAGES = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]
TOOLS = [{"type": "function", "function": {"name": "save_details", "parameters": {"type": "object", "properties": {}}}}]


def link(provider: str, model: str) -> Link:
    return Link(provider, model, ENDPOINTS[provider], "test-key")


def ok_body(text: str = "Hello", **message: Any) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": text, **message}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 10}},
    }


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def transport(monkeypatch):
    """Route every provider request through a handler the test controls."""
    state: dict[str, Any] = {"requests": [], "handler": None}

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        state["requests"].append((str(request.url), body))
        return state["handler"](request, body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(client_module, "shared_client", lambda: client)
    return state


# ---- parsing ----------------------------------------------------------------------------
def test_parse_reply_strips_provider_extras():
    data = ok_body(
        "",
        reasoning="secret chain of thought",
        tool_calls=[{"id": "c1", "type": "function", "function": {"name": "save_details", "arguments": '{"a":1}'}, "index": 0}],
    )
    reply = parse_reply(data)
    assert reply.tool_calls[0].name == "save_details"
    assert "reasoning" not in reply.assistant_message
    assert reply.assistant_message["tool_calls"][0] == {
        "id": "c1",
        "type": "function",
        "function": {"name": "save_details", "arguments": '{"a":1}'},
    }
    assert reply.assistant_message["content"] is None


def test_clean_assistant_message_plain_text():
    assert clean_assistant_message({"content": "Hi", "extra_content": {"x": 1}}) == {"role": "assistant", "content": "Hi"}


def test_parse_duration():
    assert parse_duration("2m59.56s") == pytest.approx(179.56)
    assert parse_duration("7.66s") == pytest.approx(7.66)
    assert parse_duration("120ms") == pytest.approx(0.12)
    assert parse_duration("30") == 30
    assert parse_duration("1h2m") == pytest.approx(3720)
    assert parse_duration("") is None and parse_duration("soon") is None


# ---- links + request shapes ------------------------------------------------------------
def test_resolve_links_skips_unknown_missing_and_paid(monkeypatch):
    pset = get_provider_settings()
    monkeypatch.setattr(pset, "groq_api_key", "g")
    monkeypatch.setattr(pset, "gemini_api_key", None)
    links = resolve_links("groq:openai/gpt-oss-20b,gemini:gemini-3.1-flash-lite,nope:x,openai:gpt-5.4-mini", allow_paid=False)
    assert [l.key for l in links] == ["groq:openai/gpt-oss-20b"]


def test_model_extras_keep_calls_fast():
    assert model_extras("groq", "openai/gpt-oss-120b") == {"reasoning_effort": "low", "include_reasoning": False}
    assert model_extras("groq", "qwen/qwen3.8-27b")["reasoning_effort"] == "none"
    assert model_extras("gemini", "gemini-3.1-flash-lite") == {"reasoning_effort": "none"}
    assert model_extras("gemini", "gemini-flash-lite-latest") == {"reasoning_effort": "low"}


def test_body_per_provider():
    gemini = OpenAICompatLLM(link("gemini", "gemini-3.1-flash-lite"), max_output_tokens=120, prompt_cache_key="k")
    body = gemini.body(MESSAGES, tools=TOOLS, tool_choice="auto", temperature=None)
    assert body["max_tokens"] == 120 and "max_completion_tokens" not in body
    assert "parallel_tool_calls" not in body and "prompt_cache_key" not in body

    openai = OpenAICompatLLM(link("openai", "gpt-5.4-mini"), prompt_cache_key="clinic.inbound:m1")
    body = openai.body(MESSAGES, tools=TOOLS, tool_choice="auto", temperature=None)
    assert body["prompt_cache_key"] == "clinic.inbound:m1"
    assert body["parallel_tool_calls"] is False and body["max_completion_tokens"] == 300


# ---- routing ----------------------------------------------------------------------------
async def test_falls_back_on_429_and_then_skips_blocked_link(transport):
    clock = Clock()
    quotas = QuotaBook(clock=clock)

    def handler(request, body):
        if body["model"] == "openai/gpt-oss-120b":
            return httpx.Response(429, headers={"retry-after": "30"}, json={"error": "rate"})
        return httpx.Response(200, json=ok_body("from 20b"))

    transport["handler"] = handler
    llm = RoutedLLM([link("groq", "openai/gpt-oss-120b"), link("groq", "openai/gpt-oss-20b")], quotas=quotas)
    reply = await llm.complete(MESSAGES, tools=TOOLS)
    assert reply.content == "from 20b" and llm.fallbacks == 1
    assert llm.last_link.model == "openai/gpt-oss-20b"

    transport["requests"].clear()
    await llm.complete(MESSAGES, tools=TOOLS)
    assert [b["model"] for _, b in transport["requests"]] == ["openai/gpt-oss-20b"]  # blocked link skipped

    clock.now += 31
    transport["requests"].clear()
    await llm.complete(MESSAGES, tools=TOOLS)
    assert transport["requests"][0][1]["model"] == "openai/gpt-oss-120b"  # retried after the cool-off


async def test_low_remaining_tokens_skips_link_until_reset(transport):
    clock = Clock()
    quotas = QuotaBook(clock=clock)
    transport["handler"] = lambda request, body: httpx.Response(
        200, json=ok_body(body["model"]), headers={"x-ratelimit-remaining-tokens": "5", "x-ratelimit-reset-tokens": "10s"}
    )
    llm = RoutedLLM([link("groq", "a"), link("gemini", "b")], quotas=quotas, max_output_tokens=100)
    assert (await llm.complete(MESSAGES)).content == "a"
    assert (await llm.complete(MESSAGES)).content == "b"  # "a" has 5 tokens left < need
    clock.now += 11
    assert (await llm.complete(MESSAGES)).content == "a"


async def test_all_links_failing_raises(transport):
    transport["handler"] = lambda request, body: httpx.Response(503, text="down")
    llm = RoutedLLM([link("groq", "a"), link("gemini", "b")], quotas=QuotaBook(clock=Clock()))
    with pytest.raises(LLMError):
        await llm.complete(MESSAGES)


async def test_exhausted_links_are_still_tried_as_a_last_resort(transport):
    clock = Clock()
    quotas = QuotaBook(clock=clock)
    quotas.note_failure("groq:a", 429, {"retry-after": "60"})
    transport["handler"] = lambda request, body: httpx.Response(200, json=ok_body("stale quota was wrong"))
    llm = RoutedLLM([link("groq", "a")], quotas=quotas)
    assert (await llm.complete(MESSAGES)).content == "stale quota was wrong"


async def test_stats_per_model(transport):
    transport["handler"] = lambda request, body: httpx.Response(200, json=ok_body())
    llm = RoutedLLM([link("groq", "a")], quotas=QuotaBook(clock=Clock()))
    await llm.complete(MESSAGES)
    await llm.complete(MESSAGES)
    stats = llm.stats()
    assert stats["requests"] == 2 and stats["prompt_tokens"] == 100 and stats["cached_prompt_tokens"] == 20
    assert stats["by_model"]["groq:a"]["requests"] == 2
    assert llm.prompt_tokens == 100  # the bridge/text session read these attributes


def test_no_links_is_a_clear_error():
    with pytest.raises(LLMError):
        RoutedLLM([])


def test_preferred_profile():
    assert RoutedLLM([link("openai", "gpt-5.4-mini")]).preferred_profile() == "cached"
    assert RoutedLLM([link("groq", "a")]).preferred_profile() == "compact"


def test_estimate_tokens_counts_tools():
    assert estimate_tokens(MESSAGES, TOOLS) > estimate_tokens(MESSAGES)
