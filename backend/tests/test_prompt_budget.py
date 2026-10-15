"""The compact prompt profile stays small (free LLM tiers count every token) and still carries what a step needs."""

from __future__ import annotations

import pytest

from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.runtime import FlowRuntime
from app.pipeline.prompt import compact_messages, compact_tools, estimate_tokens, window
from app.verticals import flow_for
from app.voice.tools import CallTools, NullCallStore
from tests.test_pipeline import DOCTORS, NOW, Account

BUDGET_TOKENS = 1500
KNOWLEDGE = (
    "We are open Monday to Friday 9 AM to 6 PM. Closed on weekends.\n\n"
    "Parking is free behind the building.\n\n"
    "We accept Aetna and Cigna insurance. Self-pay patients get a 10% discount.\n\n" + "Filler policy text. " * 300
)


def _setup(caller_text: str):
    merchant = Account(knowledge=KNOWLEDGE)
    ctx = CallContext(merchant=merchant, catalog=list(DOCTORS), direction=DIRECTION_INBOUND, now=NOW)
    runtime = FlowRuntime(flow_for(merchant, DIRECTION_INBOUND), ctx, language="en")
    return runtime, CallTools(runtime, NullCallStore()), ctx


@pytest.mark.asyncio
async def test_each_step_fits_the_budget():
    runtime, tools, ctx = _setup("")
    history = [{"role": "assistant", "content": "Hello, how can I help?"}]
    for fields, said in (
        ({}, "I need an appointment"),
        ({"intent": "book", "doctor": "D1"}, "Dr Mitchell please"),
        ({"date": "2026-10-05"}, "Monday"),
        ({"patient_name": "Jo"}, "Jo"),
    ):
        if fields:
            await tools.execute("save_details", fields, caller_text=said)
        history += [{"role": "user", "content": said}, {"role": "assistant", "content": "Okay."}]
        messages = compact_messages(runtime.flow, runtime, ctx, history, "en", said)
        request = estimate_tokens(messages, compact_tools(tools.schemas(), runtime.flow, runtime))
        assert request <= BUDGET_TOKENS, (runtime.stage, request)


def test_knowledge_is_sent_only_when_the_caller_asks_about_it():
    runtime, tools, ctx = _setup("")
    asked = compact_messages(runtime.flow, runtime, ctx, [], "en", "do you take aetna insurance?")[1]["content"]
    assert "Aetna and Cigna" in asked and "Filler policy" not in asked
    other = compact_messages(runtime.flow, runtime, ctx, [], "en", "I'd like to book")[1]["content"]
    assert "Aetna" not in other


def test_window_keeps_tool_pairs_and_drops_old_turns_and_system_notes():
    messages = [{"role": "system", "content": "rules"}, {"role": "assistant", "content": "Hi"}]
    for n in range(5):
        messages += [
            {"role": "user", "content": f"turn {n}"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": f"c{n}", "type": "function", "function": {"name": "save_details", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"c{n}", "content": "{}"},
            {"role": "system", "content": "[STEP: x]"},
        ]
    kept = window(messages, turns=3)
    assert kept[0] == {"role": "user", "content": "turn 2"}
    assert all(m["role"] != "system" for m in kept)
    assert [m["role"] for m in kept[:3]] == ["user", "assistant", "tool"]


def test_compact_tools_trim_save_details_to_the_active_path():
    runtime, tools, ctx = _setup("")
    props = compact_tools(tools.schemas(), runtime.flow, runtime)[0]["function"]["parameters"]["properties"]
    assert "appointment" not in props  # the reschedule/cancel lookup isn't on the path yet
    assert {"intent", "doctor", "date", "reply"} <= set(props)
