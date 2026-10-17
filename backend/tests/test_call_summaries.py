"""AI call summaries: which conversations get one, the request, the cleanup, the detached
run (stored, metered, never raising) and the waiters (owner alerts). No LLM, no database."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core import memo
from app.finance import pricebook, recorder
from app.models import CallLog, Order, OrderStatus
from app.services import order_service, summaries
from app.services.summaries import prompt, runner
from tests.finance_fakes import Factory, FakeSession
from tests.security_fakes import make_merchant

#: The real writer (the autouse fixture swaps in a recorder of calls).
ORIGINAL_RECORD = recorder.record_llm_extra
TRANSCRIPT = "Agent: Thanks for calling Bright Smile, how can I help?\nCustomer: Hi, I'd like a cleaning on Tuesday.\nAgent: You're booked."


class FakeLLM:
    def __init__(self, content: str = "Summary: **Emily Johnson** booked a cleaning.", *, fail: bool = False, gate: asyncio.Event | None = None) -> None:
        self.content, self.fail, self.gate = content, fail, gate
        self.requests: list[list[dict]] = []

    async def complete(self, messages, **_):  # noqa: ANN001, ANN003
        self.requests.append(messages)
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("every provider is down")
        return SimpleNamespace(content=self.content)

    def stats(self) -> dict:
        tokens = 300 * len(self.requests)
        return {"provider": "openai", "model": "gpt-5.4-mini", "prompt_tokens": tokens, "completion_tokens": 30, "by_model": {}}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    runner._done.clear()
    runner._events.clear()
    metered: list[tuple] = []

    async def record_llm_extra(merchant_id, call_log_id, usage, *, purpose):  # noqa: ANN001, ANN202
        metered.append((merchant_id, call_log_id, usage["prompt_tokens"], purpose))
        return 1

    monkeypatch.setattr(recorder, "record_llm_extra", record_llm_extra)
    yield metered
    monkeypatch.setattr(runner, "session_factory", None)
    monkeypatch.setattr(runner, "llm_factory", None)


def conversation(transcript: str = TRANSCRIPT, **log_fields) -> tuple[FakeSession, CallLog]:
    merchant = make_merchant(id="m1", business_name="Bright Smile Dental", timezone="America/New_York")
    record = Order(
        id="o1", merchant_id="m1", kind="appointment", customer_name="Emily Johnson", customer_phone="+16175550142",
        items_summary="Cleaning", total_amount=Decimal("120"), currency="USD", order_ref="BS-1001", status=OrderStatus.confirmed,
        scheduled_at=datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc),
    )
    log = CallLog(id="c1", merchant_id="m1", order_id="o1", direction="inbound", caller_number="+16175550142",
                  outcome="booked", transcript=transcript, **log_fields)
    return FakeSession(merchant, record, log), log


def use(monkeypatch, session: FakeSession, llm: FakeLLM | None) -> None:
    monkeypatch.setattr(runner, "session_factory", Factory(session))
    monkeypatch.setattr(runner, "llm_factory", lambda merchant: llm)


# ------------------------------------------------------------------ prompt (pure)
def test_only_conversations_where_the_customer_spoke_get_a_summary():
    assert prompt.has_caller_turn(TRANSCRIPT)
    assert prompt.has_caller_turn("Agent: hi\ncaller: yes")
    assert not prompt.has_caller_turn("Agent: Hello? Are you there?\nAgent: Goodbye.")
    assert not prompt.has_caller_turn("") and not prompt.has_caller_turn(None)
    assert not prompt.has_caller_turn("Customer:   ")


def test_long_transcripts_keep_the_start_and_the_end():
    lines = [f"Customer: line {i} " + "x" * 80 for i in range(200)]
    text = prompt.excerpt("\n".join(lines))
    assert len(text) <= prompt.MAX_TRANSCRIPT_CHARS + 10 and "[...]" in text
    assert text.startswith("Customer: line 0 ") and lines[-1] in text
    assert prompt.excerpt("Agent: short") == "Agent: short"


def test_the_answer_is_cleaned_to_one_plain_capped_line():
    assert prompt.clean('Summary: **Emily** asked\nabout `UT-1001`. ') == "Emily asked about UT-1001."
    assert prompt.clean('"Call summary - Tom booked."') == "Tom booked."
    assert prompt.clean(None) == "" and prompt.clean("  ") == ""
    long = "Emily asked about her order and many other things. " * 20
    cut = prompt.clean(long)
    assert len(cut) <= prompt.MAX_SUMMARY_CHARS and cut.endswith(".")


def test_facts_name_the_customer_booking_and_reference():
    record = SimpleNamespace(customer_name="Emily Johnson", items_summary="Cleaning", kind="appointment", order_ref="BS-1")
    lines = prompt.facts(business="Bright Smile", direction="inbound", caller_number="+1617", outcome="not_interested",
                         record=record, when="Tue, Oct 20 at 3 PM", amount="$120")
    assert "Channel: Phone call (customer called in)" in lines and "Customer name: Emily Johnson" in lines
    assert "Appointment: Cleaning" in lines and "When: Tue, Oct 20 at 3 PM" in lines and "Total: $120" in lines
    assert "Reference: BS-1" in lines and "Result recorded by the receptionist: not interested" in lines
    anonymous = prompt.facts(record=SimpleNamespace(customer_name="Caller", kind="lead"))
    assert not any(line.startswith("Customer name") for line in anonymous)
    messages = prompt.build_messages(lines, TRANSCRIPT)
    assert messages[0]["role"] == "system" and "at most 45 words" in messages[0]["content"]
    assert messages[1]["content"].endswith(TRANSCRIPT) and "Conversation:" in messages[1]["content"]


# ------------------------------------------------------------------ the run
async def test_summary_is_generated_stored_metered_and_wakes_waiters(monkeypatch, _isolated):
    session, log = conversation()
    llm = FakeLLM()
    use(monkeypatch, session, llm)
    waiter = asyncio.create_task(summaries.wait_for("c1", 5))
    await asyncio.sleep(0)
    text = await summaries.summarize("c1")
    assert text == "Emily Johnson booked a cleaning." and log.summary == text and session.commits == 1
    assert await waiter == text and await summaries.wait_for("c1", 0) == text  # late waiters too
    facts = llm.requests[0][1]["content"]
    assert "Customer name: Emily Johnson" in facts and "Tue, Oct 20 at 3 PM" in facts and "Total: $120" in facts
    assert _isolated == [("m1", "c1", 300, "summary")]


async def test_no_caller_turn_existing_summary_or_no_llm_means_no_request(monkeypatch, _isolated):
    session, _ = conversation("Agent: Hello?\nAgent: Goodbye.")
    llm = FakeLLM()
    use(monkeypatch, session, llm)
    assert await summaries.summarize("c1") == "" and not llm.requests
    session, _ = conversation(summary="Already written.")
    use(monkeypatch, session, llm)
    assert await summaries.summarize("c1") == "" and not llm.requests
    session, log = conversation()
    use(monkeypatch, session, None)  # no LLM configured
    assert await summaries.summarize("c1") == "" and log.summary is None
    assert await summaries.summarize("missing") == "" and not _isolated


async def test_a_failed_llm_never_raises_and_still_meters_and_wakes(monkeypatch, _isolated):
    session, log = conversation()
    use(monkeypatch, session, FakeLLM(fail=True))
    waiter = asyncio.create_task(summaries.wait_for("c1", 5))
    await asyncio.sleep(0)
    assert await summaries.summarize("c1") == ""
    assert log.summary is None and await waiter == "" and _isolated and _isolated[0][3] == "summary"
    broken = FakeSession(fail_execute=True)

    async def fail_get(*_):  # noqa: ANN002, ANN202
        raise ConnectionError("database unreachable")

    broken.get = fail_get
    use(monkeypatch, broken, FakeLLM())
    assert await summaries.summarize("c2") == ""


async def test_schedule_is_detached_so_the_teardown_never_waits(monkeypatch):
    session, log = conversation()
    gate = asyncio.Event()
    use(monkeypatch, session, FakeLLM("Emily booked.", gate=gate))
    summaries.schedule("c1")  # returns at once although the model hasn't answered
    assert runner._pending and log.summary is None
    assert await summaries.wait_for("c1", 0.01) is None  # timed out: alerts send without it
    gate.set()
    await asyncio.gather(*list(runner._pending))
    assert log.summary == "Emily booked."
    summaries.schedule("")  # nothing to do


async def test_the_call_store_schedules_it(monkeypatch):
    from app.services.calls.store import DbCallStore

    seen: list[str] = []
    monkeypatch.setattr(summaries, "schedule", seen.append)
    await DbCallStore(order_id="", call_log_id="c9").summarize()
    assert seen == ["c9"]


def test_the_account_chain_is_sized_for_a_summary(monkeypatch):
    from app.voice.providers.llm import factory

    built: list[dict] = []
    monkeypatch.setattr(factory, "llm_configured", lambda merchant: True)
    monkeypatch.setattr(factory, "llm_for_call", lambda **kwargs: built.append(kwargs) or "chain")
    assert runner.make_llm(make_merchant()) == "chain"
    assert built[0]["max_output_tokens"] == summaries.MAX_OUTPUT_TOKENS == 120 and built[0]["flow_key"] == "summary"
    monkeypatch.setattr(factory, "llm_configured", lambda merchant: False)
    assert runner.make_llm(make_merchant()) is None


def test_the_api_serializes_the_summary():
    log = CallLog(id="c1", merchant_id="m1", direction="widget", summary="Lee booked a haircut.")
    assert order_service.serialize_call_log(log)["summary"] == "Lee booked a haircut."
    assert order_service.serialize_call_log(CallLog(id="c2", merchant_id="m1"))["summary"] == ""


# ------------------------------------------------------------------ metering (category llm)
async def test_summary_tokens_enter_the_ledger_tagged_and_linked_safely(monkeypatch):
    from app.core.datetime_utils import utcnow

    monkeypatch.setattr(recorder, "record_llm_extra", ORIGINAL_RECORD)
    memo.put(f"finance:pricebook:{utcnow().date().isoformat()}", pricebook.defaults_book(), ttl=60)
    usage = {"by_model": {"openai:gpt-5.4-mini": {"prompt_tokens": 400, "completion_tokens": 30}}}
    fresh = FakeSession()  # the call's own lines aren't in yet: keep the link in meta only
    monkeypatch.setattr(recorder, "session_factory", Factory(fresh))
    assert await recorder.record_llm_extra("m1", "c1", usage, purpose="summary") >= 1
    rows = fresh.executed[0][1]
    assert {row["category"] for row in rows} == {"llm"} and {row["call_log_id"] for row in rows} == {None}
    assert all(row["meta"]["purpose"] == "summary" and row["meta"]["call_log_id"] == "c1" for row in rows)
    metered = FakeSession(scalar=["e1"])  # already metered: attach to the call
    monkeypatch.setattr(recorder, "session_factory", Factory(metered))
    await recorder.record_llm_extra("m1", "c1", usage, purpose="summary")
    assert {row["call_log_id"] for row in metered.executed[0][1]} == {"c1"}
    monkeypatch.setattr(recorder, "session_factory", Factory(FakeSession(fail_execute=True)))
    assert await recorder.record_llm_extra("m1", "c1", usage, purpose="summary") == 0
    monkeypatch.setattr(recorder, "session_factory", None)
    memo.clear()


async def test_a_finished_chat_asks_its_store_for_the_summary():
    from app.flows.context import DIRECTION_INBOUND, CallContext
    from app.verticals import flow_for
    from app.voice.llm import LLMReply, LLMToolCall
    from app.voice.text_session import TextSession
    from app.voice.tools import NullCallStore
    from tests.test_platform import ScriptedLLM

    class Store(NullCallStore):
        summarized = 0

        async def summarize(self) -> None:
            self.summarized += 1

    merchant = SimpleNamespace(
        id="m1", vertical="ecommerce", business_name="Urban Threads", language="en", region="US", timezone="America/New_York",
        currency="USD", emergency_number="911", knowledge="", support_phone="+1999", custom_greeting="", vertical_config={},
    )
    store = Store()
    llm = ScriptedLLM([LLMReply(content="", tool_calls=[LLMToolCall("c1", "save_details", '{"message": "Where is my order", "caller_name": "Emily"}')])])
    ctx = CallContext(merchant=merchant, direction=DIRECTION_INBOUND, caller_number="+14155550123", channel="chat")
    session = TextSession(merchant=merchant, ctx=ctx, flow=flow_for(merchant, DIRECTION_INBOUND), store=store, call_log_id="log", llm=llm)
    await session.start()
    await session.say("where is my order? I'm Emily")
    await session.say("yes")
    assert session.ended and store.summarized == 1 and store.usage
    await session.finish()  # finishing twice never asks twice
    assert store.summarized == 1


async def test_a_finished_phone_call_asks_its_store_for_the_summary():
    import time

    from app.voice.bridge.lifecycle import LifecycleMixin
    from app.voice.tools import NullCallStore

    class Store(NullCallStore):
        summarized = 0

        async def summarize(self) -> None:
            self.summarized += 1

    async def persist(*, force=False):  # noqa: ANN001, ANN202
        return None

    store = Store()
    call = SimpleNamespace(
        _finalized=False, call_log_id="c1", outcome="booked", ctx=SimpleNamespace(direction="inbound"), _persist_transcript=persist,
        tts_chars=10, tts_cache_hits=0, started_at=time.monotonic(), _llm=None, store=store, _stt_usage=[], _tts_usage=[],
        flow=SimpleNamespace(key="clinic.inbound"), runtime=SimpleNamespace(current_node="wrap_up"),
        agent=SimpleNamespace(turns=3, fast_turns=1),
    )
    await LifecycleMixin._finalize(call)
    await LifecycleMixin._finalize(call)  # once per call
    assert store.summarized == 1 and store.usage
