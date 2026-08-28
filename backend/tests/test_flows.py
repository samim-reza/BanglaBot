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
from app.flows.ecommerce import DEFAULT_FLOW, flow_preview_steps
from app.flows.runtime import FlowRuntime
from app.voice.languages import phrase
from app.voice.prompts import build_system_prompt, transcription_prompt


def _runtime(order, merchant, language="bn"):
    directives = []
    rt = FlowRuntime(DEFAULT_FLOW, order, merchant, language=language, on_directive=directives.append)
    return rt, directives


def test_identity_gate_named_person_goes_to_decision(order, merchant):
    rt, directives = _runtime(order, merchant)
    assert rt.stage == STAGE_IDENTITY and rt.current_node == NODE_IDENTITY
    result = rt.save({"identity_confirmed": True})
    assert result["ok"] and result["saved"] == ["identity_confirmed"]
    assert rt.stage == STAGE_DECISION and rt.current_node == NODE_DECISION
    assert len(directives) == 1 and "ধাপ পরিবর্তন" in directives[0]
    # The decision instruction carries the facts, spoken naturally, in Bangla.
    assert "এক হাজার আটশো পঞ্চাশ টাকা" in result["instruction"]
    assert "ক্যাশ অন ডেলিভারি" in result["instruction"]
    assert "পাঞ্জাবি" in result["instruction"]


def test_identity_gate_someone_else_who_knows_customer_relays(order, merchant):
    rt, _ = _runtime(order, merchant)
    result = rt.save({"identity_confirmed": False})
    assert rt.stage == STAGE_KNOWS_PERSON and rt.current_node == NODE_KNOWS_PERSON
    assert result["instruction"].startswith("হুবহু বলুন:")
    assert phrase("knows_person_question", "bn", customer_name=order.customer_name) in result["instruction"]
    result = rt.save({"knows_customer": True})
    assert rt.stage == STAGE_RELAY and rt.current_node == NODE_WRAP_UP
    assert phrase("relay_line", "bn", customer_name=order.customer_name, business_name=merchant.business_name) in result["instruction"]
    assert "end_call" in result["instruction"]


def test_identity_gate_unknown_person_is_wrong_number(order, merchant):
    rt, _ = _runtime(order, merchant, language="en")
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
    assert [d.split("]")[0] for d in directives] == ["[ধাপ পরিবর্তন"]


def test_address_verification_path(order, merchant):
    """The order question comes first; the address is checked only after a yes."""
    merchant.verify_address = True
    rt, _ = _runtime(order, merchant, language="en")
    result = rt.save({"identity_confirmed": True})
    assert rt.stage == STAGE_DECISION
    assert "1850 taka" in result["instruction"] and "cash on delivery" in result["instruction"]
    rt.mark_decided(OUTCOME_CONFIRMED)
    assert not rt.done
    assert rt.stage == STAGE_ADDRESS and rt.current_node == NODE_ADDRESS
    instruction = rt.current_instruction()
    assert instruction.verbatim and order.address in instruction.text
    result = rt.save({"address_correct": False})
    assert rt.stage == STAGE_NEW_ADDRESS
    assert phrase("new_address_question", "en") in result["instruction"]
    rt.save({"new_address": "House 9, Road 2, Banani"})
    assert rt.done and rt.stage == STAGE_DONE
    assert rt.flow_data()["new_address"] == "House 9, Road 2, Banani"


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
    rt.save({"identity_confirmed": True, "note": "সন্ধ্যায় ডেলিভারি"})
    rt.mark_decided(OUTCOME_CONFIRMED)
    assert rt.done and rt.stage == STAGE_DONE and rt.current_node == NODE_WRAP_UP
    assert rt.flow_data() == {"identity_confirmed": True, "note": "সন্ধ্যায় ডেলিভারি"}
    assert rt.outcome == OUTCOME_CONFIRMED
    assert len(directives) == 2


def test_unknown_slots_are_ignored(order, merchant):
    rt, _ = _runtime(order, merchant)
    result = rt.save({"identity_confirmed": True, "hacker": "x", "note": ""})
    assert result["saved"] == ["identity_confirmed"]
    assert "hacker" not in rt.slots and "note" not in rt.slots


def test_language_switch_changes_instruction_language(order, merchant):
    rt, _ = _runtime(order, merchant)
    rt.set_language("en")
    result = rt.save({"identity_confirmed": False})
    assert result["instruction"].startswith("Say exactly:")
    assert "Do you know them?" in result["instruction"]


def test_closing_lines_and_greeting(order, merchant):
    assert DEFAULT_FLOW.closing_line("confirmed", order, merchant, "bn") == phrase("closing_confirmed", "bn")
    assert DEFAULT_FLOW.closing_line("relay", order, merchant, "en").startswith("Alright. Please let")
    assert DEFAULT_FLOW.greeting(merchant, "en") == "Hello, this is Demo Shop calling."
    merchant.custom_greeting = "আসসালামু আলাইকুম, আমি ডেমো শপ থেকে বলছি।"
    assert DEFAULT_FLOW.greeting(merchant, "bn") == merchant.custom_greeting
    lines = DEFAULT_FLOW.prefetch_lines(order, merchant, "bn")
    assert merchant.custom_greeting in lines and phrase("closing_dropped", "bn") in lines


def test_flow_preview_steps_follow_settings(merchant):
    steps = flow_preview_steps(merchant)
    assert len(steps) == 4 and steps[0].startswith("শুভেচ্ছা")
    merchant.verify_address = True
    merchant.language = "en"
    steps = flow_preview_steps(merchant)
    assert len(steps) == 5 and steps[3].startswith("Address check")  # after the confirmation


def test_system_prompt_in_both_languages(order, merchant):
    bn = build_system_prompt(order, merchant, DEFAULT_FLOW, language="bn", initial_directive="[ধাপ পরিবর্তন] x")
    assert "Demo Shop" in bn and "এক হাজার আটশো পঞ্চাশ টাকা" in bn and bn.endswith("[ধাপ পরিবর্তন] x")
    assert "আসসালামু আলাইকুম" in bn  # greeting already spoken
    en = build_system_prompt(order, merchant, DEFAULT_FLOW, language="en")
    assert "1850 taka" in en and "Am I speaking with" in en and "Supported languages" in en
    assert transcription_prompt(["bn", "en"]).startswith("অর্ডার কনফার্মেশনের")
