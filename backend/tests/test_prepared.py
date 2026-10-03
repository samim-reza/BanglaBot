"""The pre-composed confirmation question: compose, validate, store, warm."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.verticals.ecommerce import DEFAULT_FLOW
from app.voice import prepared


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[dict]] = []
        self.closed = False

    async def complete(self, messages, **kwargs):
        self.calls.append(messages)
        return SimpleNamespace(content=self.content)

    async def aclose(self) -> None:
        self.closed = True


class FakeTTS:
    def __init__(self) -> None:
        self.warmed: list[tuple[str, str]] = []

    async def warm(self, lines, *, language, persona, voice=None) -> int:
        self.warmed.extend((line, language) for line in lines)
        return len(self.warmed)


@pytest.fixture
def order():
    return SimpleNamespace(id="o-1", customer_name="Samim", items_summary="Shirt x2", total_amount=1250, currency="BDT", address="")


@pytest.fixture
def merchant():
    return SimpleNamespace(business_name="Demo Shop", language="bn", supported_languages=["bn", "en"], voice_persona="female", verify_address=False)


@pytest.fixture(autouse=True)
def _clean_store():
    prepared.clear()
    yield
    prepared.clear()


@pytest.mark.asyncio
async def test_compose_uses_model_line_when_it_is_a_question(order, merchant):
    llm = FakeLLM("আপনি দুইটা শার্ট অর্ডার করেছেন, মোট এক হাজার দুইশো পঞ্চাশ টাকা ক্যাশ অন ডেলিভারিতে। অর্ডারটি কি কনফার্ম করবেন?")
    line = await prepared.compose_decision_line(llm, DEFAULT_FLOW, order, merchant, "bn")
    assert line.endswith("?")
    assert "এক হাজার দুইশো পঞ্চাশ" in llm.calls[0][1]["content"]  # amount handed over in words


@pytest.mark.asyncio
async def test_compose_falls_back_when_the_model_line_is_unusable(order, merchant):
    line = await prepared.compose_decision_line(FakeLLM("- item list\n- total"), DEFAULT_FLOW, order, merchant, "en")
    assert line == prepared.fallback_decision_line(DEFAULT_FLOW, order, "en")
    assert "1250" in line or "one thousand" in line.lower() or "taka" in line.lower()


@pytest.mark.asyncio
async def test_prepare_call_lines_stores_and_warms_every_language(order, merchant):
    llm = FakeLLM("You ordered two shirts for 1,250 taka, cash on delivery. Shall I confirm the order?")
    tts = FakeTTS()
    result = await prepared.prepare_call_lines(order, merchant, llm=llm, tts=tts)
    assert set(result) == {"bn"}  # only the merchant's call language is prepared
    assert prepared.get_decision_line("o-1", "bn") == result["bn"]
    assert prepared.get_decision_line("o-1", "en") is None
    assert {lang for _, lang in tts.warmed} == {"bn"}
    assert not llm.closed  # a caller-supplied LLM is not closed by the helper


def test_store_expires_and_is_keyed_per_language():
    prepared.put_decision_line("o-2", "bn", "প্রশ্ন?")
    assert prepared.get_decision_line("o-2", "bn") == "প্রশ্ন?"
    assert prepared.get_decision_line("o-2", "en") is None
    prepared._decision_lines[("o-2", "bn")] = ("প্রশ্ন?", -10**9)
    assert prepared.get_decision_line("o-2", "bn") is None


def test_call_snapshot_round_trip(order, merchant):
    prepared.put_call_snapshot("log-9", prepared.CallSnapshot(merchant=merchant, order=order, call_sid="CA9"))
    snapshot = prepared.get_call_snapshot("log-9")
    assert snapshot is not None and snapshot.order is order and snapshot.merchant is merchant and snapshot.call_sid == "CA9"
    assert snapshot.direction == "outbound" and not snapshot.web
    assert prepared.get_call_snapshot("other") is None
    assert prepared.pop_call_snapshot("log-9") is snapshot and prepared.get_call_snapshot("log-9") is None
