"""The LLM chain on a live call: transport errors and timeouts fall through to the next
link like an HTTP failure, and one quick retry pass runs when every link failed with
something transient (429 / 5xx / timeout / connection) — never for a hard failure."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest

from app.voice.llm import LLMError
from app.voice.providers.llm import client as client_module
from app.voice.providers.llm import router as router_module
from app.voice.providers.llm.endpoints import ENDPOINTS, Link
from app.voice.providers.llm.quota import QuotaBook
from app.voice.providers.llm.router import RoutedLLM, retry_wait

MESSAGES = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]


def link(provider: str, model: str) -> Link:
    return Link(provider, model, ENDPOINTS[provider], "test-key")


def ok(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}], "usage": {}})


@pytest.fixture
def transport(monkeypatch):
    """Every provider request goes to a scripted handler: one step per request."""
    state: dict[str, Any] = {"models": [], "steps": []}

    def handle(request: httpx.Request) -> httpx.Response:
        state["models"].append(json.loads(request.content)["model"])
        step = state["steps"].pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(client_module, "shared_client", lambda: client)
    monkeypatch.setattr(router_module, "RETRY_BACKOFF_SECONDS", 0.05)
    return state


async def test_a_non_http_error_falls_through_to_the_next_link(transport):
    # Not an httpx error, so the client can't wrap it: before, this escaped the router.
    transport["steps"] = [asyncio.TimeoutError(), ok("from b")]
    quotas = QuotaBook()
    llm = RoutedLLM([link("groq", "a"), link("gemini", "b")], quotas=quotas)
    reply = await llm.complete(MESSAGES)
    assert reply.content == "from b" and llm.fallbacks == 1
    assert transport["models"] == ["a", "b"]
    assert not quotas.available("groq:a")  # cooled off like any other failure


async def test_single_link_blip_is_retried_once(transport):
    transport["steps"] = [httpx.ReadTimeout("slow"), ok("second time lucky")]
    llm = RoutedLLM([link("groq", "a")], quotas=QuotaBook())
    started = time.monotonic()
    reply = await llm.complete(MESSAGES)
    assert reply.content == "second time lucky" and llm.retries == 1 and llm.stats()["retries"] == 1
    assert transport["models"] == ["a", "a"] and time.monotonic() - started >= 0.05


async def test_every_link_overloaded_gets_one_retry_pass_then_gives_up(transport):
    transport["steps"] = [httpx.Response(503, text="busy"), httpx.ConnectError("refused"), httpx.Response(502), httpx.Response(500)]
    llm = RoutedLLM([link("groq", "a"), link("gemini", "b")], quotas=QuotaBook())
    with pytest.raises(LLMError):
        await llm.complete(MESSAGES)
    assert transport["models"] == ["a", "b", "a", "b"]  # one pass, then one retry pass — no more


async def test_small_retry_after_is_honoured(monkeypatch, transport):
    monkeypatch.setattr(router_module, "RETRY_AFTER_CAP_SECONDS", 0.5)
    transport["steps"] = [httpx.Response(429, headers={"retry-after": "0.3"}), ok("after the burst")]
    llm = RoutedLLM([link("groq", "a")], quotas=QuotaBook())
    started = time.monotonic()
    assert (await llm.complete(MESSAGES)).content == "after the burst"
    assert time.monotonic() - started >= 0.3


async def test_no_retry_for_a_long_rate_limit_or_a_hard_failure(transport):
    transport["steps"] = [httpx.Response(429, headers={"retry-after": "30"})]
    with pytest.raises(LLMError):
        await RoutedLLM([link("groq", "a")], quotas=QuotaBook()).complete(MESSAGES)
    assert transport["models"] == ["a"]

    transport["models"].clear()
    transport["steps"] = [httpx.Response(503), httpx.Response(401, text="bad key")]
    with pytest.raises(LLMError):
        await RoutedLLM([link("groq", "a"), link("gemini", "b")], quotas=QuotaBook()).complete(MESSAGES)
    assert transport["models"] == ["a", "b"]  # a bad key won't heal in half a second


def test_retry_wait_rules():
    assert retry_wait([]) is None
    assert retry_wait([(0, None), (503, None)]) == router_module.RETRY_BACKOFF_SECONDS
    assert retry_wait([(429, 1.0), (500, None)]) == 1.0
    assert retry_wait([(429, 30.0)]) is None
    assert retry_wait([(429, 30.0), (0, None)]) == router_module.RETRY_BACKOFF_SECONDS
    assert retry_wait([(400, None), (503, None)]) is None
