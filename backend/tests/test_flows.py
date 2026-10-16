from app.flows.base import (
    NODE_ADDRESS,
    NODE_DECISION,
    NODE_IDENTITY,
    NODE_KNOWS_PERSON,
    NODE_WRAP_UP,
    OUTCOME_CONFIRMED,
    STAGE_ADDRESS,
    STAGE_DECISION,
    STAGE_DONE,
    STAGE_IDENTITY,
    STAGE_KNOWS_PERSON,
    STAGE_NEW_ADDRESS,
    STAGE_RELAY,
    STAGE_WRONG_NUMBER,
)
from app.flows.context import CallContext
from app.flows.runtime import FlowRuntime
from app.verticals.ecommerce import DEFAULT_FLOW
from app.voice.languages import phrase
from app.voice.prompts import build_system_prompt, transcription_prompt


def _ctx(order, merchant):
    return CallContext(merchant=merchant, record=order)


def _runtime(order, merchant, language="en"):
    directives = []
    rt = FlowRuntime(DEFAULT_FLOW, _ctx(order, merchant), language=language, on_directive=directives.append)
    return rt, directives


def flow_preview_steps(merchant):
    return DEFAULT_FLOW.preview_steps(CallContext(merchant=merchant), merchant.language)


def test_identity_gate_named_person_goes_to_decision(order, merchant):
    rt, directives = _runtime(order, merchant)
    assert rt.stage == STAGE_IDENTITY and rt.current_node == NODE_IDENTITY
    result = rt.save({"identity_confirmed": True})
    assert result["ok"] and result["saved"] == ["identity_confirmed"]
    assert rt.stage == STAGE_DECISION and rt.current_node == NODE_DECISION
    assert len(directives) == 1 and "STEP CHANGE" in directives[0]
    # The decision instruction carries the facts, spoken naturally.
    assert "45 dollars" in result["instruction"]
    assert "cash on delivery" in result["instruction"]
    assert "Cotton kurta" in result["instruction"]


def test_identity_gate_someone_else_who_knows_customer_relays(order, merchant):
    rt, _ = _runtime(order, merchant)
    result = rt.save({"identity_confirmed": False})
    assert rt.stage == STAGE_KNOWS_PERSON and rt.current_node == NODE_KNOWS_PERSON
    assert result["instruction"].startswith("Say exactly:")
    assert phrase("knows_person_question", "en", customer_name=order.customer_name) in result["instruction"]
    result = rt.save({"knows_customer": True})
    assert rt.stage == STAGE_RELAY and rt.current_node == NODE_WRAP_UP
    assert phrase("relay_line", "en", customer_name=order.customer_name, business_name=merchant.business_name) in result["instruction"]
    assert "end_call" in result["instruction"]


def test_identity_gate_unknown_person_is_wrong_number(order, merchant):
    rt, _ = _runtime(order, merchant)
    rt.save({"identity_confirmed": False, "knows_customer": False})
    assert rt.stage == STAGE_WRONG_NUMBER and rt.current_node == NODE_WRAP_UP
    instruction = rt.current_instruction()
    assert instruction.verbatim and instruction.end_call
    assert instruction.text == phrase("wrong_number_line", "en")
    rt2, _ = _runtime(order, merchant)
    rt2.save({"wrong_person": True})
    assert rt2.stage == STAGE_WRONG_NUMBER


def test_slots_volunteered_early_skip_questions(order, merchant):
    merchant.verify_address = True
    rt, directives = _runtime(order, merchant)
    rt.save({"identity_confirmed": True, "address_correct": True})
    assert rt.stage == STAGE_DECISION
    assert [d.split("]")[0] for d in directives] == ["[STEP CHANGE"]


def test_address_verification_path(order, merchant):
    """The order question comes first; the address is checked only after a yes."""
    merchant.verify_address = True
    rt, _ = _runtime(order, merchant)
    result = rt.save({"identity_confirmed": True})
    assert rt.stage == STAGE_DECISION
    assert "45 dollars" in result["instruction"] and "cash on delivery" in result["instruction"]
    rt.mark_decided(OUTCOME_CONFIRMED)
    assert not rt.done
    assert rt.stage == STAGE_ADDRESS and rt.current_node == NODE_ADDRESS
    instruction = rt.current_instruction()
    assert instruction.verbatim and order.address in instruction.text
    result = rt.save({"address_correct": False})
    assert rt.stage == STAGE_NEW_ADDRESS
    assert phrase("new_address_question", "en") in result["instruction"]
    rt.save({"new_address": "9 Elm Road, Riverside"})
    assert rt.done and rt.stage == STAGE_DONE
    assert rt.flow_data()["new_address"] == "9 Elm Road, Riverside"


def test_address_is_not_checked_for_a_cancelled_order(order, merchant):
    merchant.verify_address = True
    rt, _ = _runtime(order, merchant)
    rt.save({"identity_confirmed": True})
    rt.mark_decided("cancelled")
    assert rt.done


def test_address_skipped_when_merchant_does_not_verify(order, merchant):
    merchant.verify_address = False
    rt, _ = _runtime(order, merchant)
    rt.save({"identity_confirmed": True})
    assert rt.stage == STAGE_DECISION


def test_decision_marks_done_and_flow_data_excludes_decision(order, merchant):
    rt, directives = _runtime(order, merchant)
    rt.save({"identity_confirmed": True, "note": "deliver in the evening"})
    rt.mark_decided(OUTCOME_CONFIRMED)
    assert rt.done and rt.stage == STAGE_DONE and rt.current_node == NODE_WRAP_UP
    assert rt.flow_data() == {"identity_confirmed": True, "note": "deliver in the evening"}
    assert rt.outcome == OUTCOME_CONFIRMED
    assert len(directives) == 2


def test_unknown_slots_are_ignored(order, merchant):
    rt, _ = _runtime(order, merchant)
    result = rt.save({"identity_confirmed": True, "hacker": "x", "note": ""})
    assert result["saved"] == ["identity_confirmed"]
    assert "hacker" not in rt.slots and "note" not in rt.slots


def test_retired_language_code_runs_in_english(order, merchant):
    # An account saved with a language that is no longer offered still gets English lines.
    rt, _ = _runtime(order, merchant)
    rt.set_language("bn")
    assert rt.language == "en"
    result = rt.save({"identity_confirmed": False})
    assert result["instruction"].startswith("Say exactly:")
    assert "Do you know them?" in result["instruction"]


def test_closing_lines_and_greeting(order, merchant):
    ctx = _ctx(order, merchant)
    assert DEFAULT_FLOW.closing_line("confirmed", {}, ctx, "en") == phrase("closing_confirmed", "en")
    assert DEFAULT_FLOW.closing_line("relay", {}, ctx, "en").startswith("Alright. Please let")
    assert DEFAULT_FLOW.greeting(ctx, "en") == "Hello, this is Demo Shop calling."
    merchant.custom_greeting = "Hi, this is Demo Shop calling about your order."
    assert DEFAULT_FLOW.greeting(ctx, "en") == merchant.custom_greeting
    lines = DEFAULT_FLOW.prefetch_lines(ctx, "en")
    assert merchant.custom_greeting in lines and phrase("closing_dropped", "en") in lines


def test_flow_preview_steps_follow_settings(merchant):
    steps = flow_preview_steps(merchant)
    assert len(steps) == 4 and steps[0].startswith("Greeting")
    merchant.verify_address = True
    steps = flow_preview_steps(merchant)
    assert len(steps) == 5 and steps[3].startswith("Address check")  # after the confirmation


def test_system_prompt(order, merchant):
    ctx = _ctx(order, merchant)
    opening = DEFAULT_FLOW.opening(ctx, "en")
    en = build_system_prompt(DEFAULT_FLOW, ctx, language="en", opening=opening, initial_directive="[STEP CHANGE] x")
    assert "Demo Shop" in en and "45 dollars" in en and en.endswith("[STEP CHANGE] x")
    assert "Hello, this is Demo Shop calling." in en  # greeting already spoken
    assert "Am I speaking with" in en and "Speak only English" in en
    assert transcription_prompt(["en"]).startswith("Phone call.")


def test_system_prompt_keeps_the_stable_part_first(order, merchant):
    """Prompt caching needs an identical prefix: the rules must not depend on the call."""
    from app.voice.prompts import build_messages

    first = build_messages(DEFAULT_FLOW, _ctx(order, merchant), language="en", opening="Hi")
    order.customer_name = "Someone Else"
    second = build_messages(DEFAULT_FLOW, _ctx(order, merchant), language="en", opening="Hello")
    assert first[0] == second[0] and first[1] == second[1]
    assert first[2] != second[2]
