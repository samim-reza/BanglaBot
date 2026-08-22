"""Flow-engine tests: derived nodes, skip-if-answered, per-service scripts.

Run directly (no pytest needed):  venv/bin/python tests/test_flows.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import flows  # noqa: E402
from app.flows.base import (  # noqa: E402
    NODE_DECISION,
    NODE_IDENTITY,
    NODE_KNOWS_PERSON,
    NODE_SCHEDULE,
    NODE_WRAP_UP,
    STAGE_ADDRESS,
    STAGE_DECISION,
    STAGE_IDENTITY,
    STAGE_KNOWS_PERSON,
    STAGE_RELAY,
    STAGE_SCHEDULE,
    STAGE_WRONG_NUMBER,
)
from app.flows.courier import NODE_PARCEL  # noqa: E402
from app.flows.runtime import FlowRuntime  # noqa: E402


def order(**kw):
    base = dict(
        id="ord12345678",
        order_ref="ORD-1",
        customer_name="রহিম",
        customer_phone="01712345678",
        address="ধানমন্ডি ২৭, ঢাকা",
        items_summary="পাঞ্জাবি x১",
        total_amount=1200,
        notes="",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def merchant(**kw):
    base = dict(
        business_name="টেস্ট শপ",
        service_type="ecommerce",
        flow_settings={},
        custom_greeting="",
        support_phone="01700000000",
    )
    base.update(kw)
    return SimpleNamespace(**base)


class FakeContext:
    def __init__(self):
        self.messages = []

    def add_message(self, message):
        self.messages.append(message)


PASSED = 0


def check(name, condition, detail=""):
    global PASSED
    assert condition, f"FAIL: {name} {detail}"
    PASSED += 1
    print(f"  ok - {name}")


def test_registry():
    print("registry:")
    check("two services registered", set(flows.SERVICE_KEYS) == {"ecommerce", "courier"})
    check("unknown service falls back", flows.get_flow("nonsense").key == "ecommerce")
    check("valid check", flows.is_valid_service("courier") and not flows.is_valid_service("x"))
    catalog = flows.public_catalog()
    check("catalog has bn names", all(entry["name_bn"] for entry in catalog))
    kept = flows.validate_flow_settings("courier", {"verify_address": False, "junk": True})
    check("settings validation drops unknown keys", kept == {"verify_address": False})


def test_ecommerce_default_flow():
    print("ecommerce (default settings — no address step):")
    flow = flows.get_flow("ecommerce")
    m = merchant()
    o = order()
    ctx = FakeContext()
    rt = FlowRuntime(flow, o, m, ctx)
    check("starts at identity", rt.current_node == NODE_IDENTITY and rt.stage == STAGE_IDENTITY)
    check("identity question names customer", "রহিম" in rt.current_instruction_bn())

    result = rt.save({"identity_confirmed": True})
    check("identity -> decision (address off by default)", rt.stage == STAGE_DECISION)
    check("node changed to decision", rt.current_node == NODE_DECISION)
    check("directive appended on node change", len(ctx.messages) == 1)
    check("directive marked as step change", "ধাপ পরিবর্তন" in ctx.messages[0]["content"])
    check("instruction includes amount", "1200" in result["instruction"])
    check("confirm line is scripted", "আপনি কি কনফার্ম করতে চান?" in result["instruction"])
    check("tool result lists saved keys", result["saved"] == ["identity_confirmed"])


def test_ecommerce_address_step_and_skip():
    print("ecommerce (verify_address on, volunteered answers skip questions):")
    flow = flows.get_flow("ecommerce")
    m = merchant(flow_settings={"verify_address": True})
    o = order()
    ctx = FakeContext()
    rt = FlowRuntime(flow, o, m, ctx)

    # Caller volunteers identity AND address correctness in one breath:
    rt.save({"identity_confirmed": True, "address_correct": True})
    check("both slots skip straight to decision", rt.stage == STAGE_DECISION)

    # Fresh call where the caller only confirms identity:
    rt2 = FlowRuntime(flow, o, m, FakeContext())
    rt2.save({"identity_confirmed": True})
    check("address asked when not volunteered", rt2.stage == STAGE_ADDRESS)
    check("address question reads the address", "ধানমন্ডি" in rt2.current_instruction_bn())
    # Wrong address without a replacement keeps the stage until captured:
    rt2.save({"address_correct": False})
    check("wrong address re-asks for the new one", rt2.stage == STAGE_ADDRESS)
    check("re-ask asks for correct address", "সঠিক ঠিকানা" in rt2.current_instruction_bn())
    rt2.save({"new_address": "মিরপুর ১০, ঢাকা"})
    check("new address advances to decision", rt2.stage == STAGE_DECISION)

    # No address on the order → the address step can never trigger:
    rt3 = FlowRuntime(flow, order(address=""), m, FakeContext())
    rt3.save({"identity_confirmed": True})
    check("empty address skips the address step", rt3.stage == STAGE_DECISION)


def test_wrong_person():
    print("wrong number:")
    flow = flows.get_flow("ecommerce")
    rt = FlowRuntime(flow, order(), merchant(), FakeContext())
    rt.save({"wrong_person": True})
    check("wrong person -> wrap up node", rt.current_node == NODE_WRAP_UP)
    check("stage is wrong_number", rt.stage == STAGE_WRONG_NUMBER)
    check("instruction says end call", "end_call" in rt.current_instruction_bn())


def test_identity_not_named_person():
    print("not the named person → know them? → relay or reject:")
    flow = flows.get_flow("ecommerce")
    o = order()
    rt = FlowRuntime(flow, o, merchant(), FakeContext())
    rt.save({"identity_confirmed": False})
    check("not named person -> knows-person stage", rt.stage == STAGE_KNOWS_PERSON)
    check("node is knows_person", rt.current_node == NODE_KNOWS_PERSON)
    check("asks if they know the customer", "রহিম-কে চিনেন" in rt.current_instruction_bn())
    check("order details in the know-them question", "পাঞ্জাবি" in rt.current_instruction_bn())

    rt.save({"knows_customer": True})
    check("knows them -> relay wrap-up", rt.stage == STAGE_RELAY and rt.current_node == NODE_WRAP_UP)
    check("relay instruction is silent end_call", "end_call" in rt.current_instruction_bn())
    line = flow.closing_line_bn(merchant(), o, "relay", {"knows_customer": True})
    check("relay hang-up asks them to confirm", "কনফার্ম করতে বলবেন" in line)

    rt2 = FlowRuntime(flow, o, merchant(), FakeContext())
    rt2.save({"identity_confirmed": False, "knows_customer": False})
    check("don't know them -> wrong number in one turn", rt2.stage == STAGE_WRONG_NUMBER)
    sorry = flow.closing_line_bn(merchant(), o, "wrong_number", {"knows_customer": False})
    check("reject hang-up apologizes", "দুঃখিত" in sorry)

    thanks = flow.closing_line_bn(merchant(), o, "confirmed", {})
    check("confirm hang-up thanks the shop", "টেস্ট শপ-এর সাথে থাকার জন্য ধন্যবাদ" in thanks)


def test_courier_full_flow():
    print("courier (defaults: address + time both on):")
    flow = flows.get_flow("courier")
    m = merchant(service_type="courier")
    o = order(order_ref="TRK-9", items_summary="জুতা x১", total_amount=850)
    ctx = FakeContext()
    rt = FlowRuntime(flow, o, m, ctx)
    check("starts at identity", rt.current_node == NODE_IDENTITY)

    rt.save({"identity_confirmed": True})
    check("then parcel/address", rt.stage == STAGE_ADDRESS and rt.current_node == NODE_PARCEL)
    check("parcel announce in instruction", "পার্সেল" in rt.current_instruction_bn())

    rt.save({"address_correct": True})
    check("then delivery time", rt.stage == STAGE_SCHEDULE and rt.current_node == NODE_SCHEDULE)

    result = rt.save({"delivery_time": "বিকেল পাঁচটার পরে"})
    check("then decision", rt.stage == STAGE_DECISION and rt.current_node == NODE_DECISION)
    check("decision recap includes the time", "বিকেল পাঁচটার পরে" in result["instruction"])
    check("decision recap includes COD amount", "850" in result["instruction"])
    check("three directives appended", len(ctx.messages) == 3)


def test_courier_volunteered_skips():
    print("courier (caller volunteers everything at once):")
    flow = flows.get_flow("courier")
    m = merchant(service_type="courier")
    rt = FlowRuntime(flow, order(), m, FakeContext())
    result = rt.save(
        {
            "identity_confirmed": True,
            "address_correct": True,
            "delivery_time": "দুপুরে",
        }
    )
    check("single turn jumps to decision", rt.stage == STAGE_DECISION)
    check("saved keys reported sorted", result["saved"] == [
        "address_correct", "delivery_time", "identity_confirmed",
    ])


def test_courier_settings_off():
    print("courier (both toggles off — parcel announce moves to decision):")
    flow = flows.get_flow("courier")
    m = merchant(
        service_type="courier",
        flow_settings={"verify_address": False, "ask_delivery_time": False},
    )
    rt = FlowRuntime(flow, order(), m, FakeContext())
    rt.save({"identity_confirmed": True})
    check("identity jumps straight to decision", rt.stage == STAGE_DECISION)
    check("decision announces the parcel", "এসেছে" in rt.current_instruction_bn())

    # Time on / address off: the schedule question must announce the parcel.
    m2 = merchant(service_type="courier", flow_settings={"verify_address": False})
    rt2 = FlowRuntime(flow, order(), m2, FakeContext())
    rt2.save({"identity_confirmed": True})
    check("schedule step announces parcel when address off", "এসেছে" in rt2.current_instruction_bn())


def test_terminals_and_static():
    print("terminals + static digit maps:")
    from app.models import OrderStatus

    eflow, cflow = flows.get_flow("ecommerce"), flows.get_flow("courier")
    e_names = {t.name for t in eflow.terminals()}
    c_names = {t.name for t in cflow.terminals()}
    check("ecommerce terminals", e_names == {"confirm_order", "cancel_order"})
    check(
        "courier terminals",
        c_names == {"confirm_delivery", "reschedule_delivery", "refuse_parcel"},
    )
    resched = next(t for t in cflow.terminals() if t.name == "reschedule_delivery")
    check("reschedule keeps order callable", resched.status == OrderStatus.rescheduled)

    m = merchant(service_type="courier")
    digits = cflow.static_digits(m)
    check("courier static digits 1/2/3/4", set(digits) == {"1", "2", "3", "4"})
    check("courier digit 2 reschedules", digits["2"][1] == "rescheduled")
    m_nosupport = merchant(service_type="courier", support_phone="")
    check("no support phone drops the transfer digit", "4" not in cflow.static_digits(m_nosupport))
    e_digits = eflow.static_digits(merchant())
    check("ecommerce digit map unchanged", set(e_digits) == {"1", "2", "3"})


def test_previews_and_prompt():
    print("previews + system prompt assembly:")
    from app.voice.prompts import build_system_prompt

    cflow = flows.get_flow("courier")
    all_on = cflow.preview_steps_bn({"verify_address": True, "ask_delivery_time": True})
    trimmed = cflow.preview_steps_bn({"verify_address": False, "ask_delivery_time": False})
    check("toggles shorten the preview", len(trimmed) == len(all_on) - 1)

    m = merchant(service_type="courier")
    o = order()
    rt = FlowRuntime(cflow, o, m, FakeContext())
    prompt = build_system_prompt(o, m, rt)
    check("prompt leads with the shared rulebook", prompt.startswith("কথা বলার মূল নিয়ম"))
    check("prompt names the courier service", "কুরিয়ার" in prompt)
    check("prompt says greeting already spoken", "গ্রিটিং" in prompt)
    check(
        "opening question is speakable and names the customer",
        rt.opening_question_bn() == "আমি কি রহিম-এর সাথে কথা বলছি?",
    )
    check("prompt embeds the opening question", rt.opening_question_bn() in prompt)
    check(
        "core rules demand ending every turn with a question",
        "প্রশ্ন ছাড়া শেষ করবে না" in prompt,
    )


if __name__ == "__main__":
    for test in (
        test_registry,
        test_ecommerce_default_flow,
        test_ecommerce_address_step_and_skip,
        test_wrong_person,
        test_identity_not_named_person,
        test_courier_full_flow,
        test_courier_volunteered_skips,
        test_courier_settings_off,
        test_terminals_and_static,
        test_previews_and_prompt,
    ):
        test()
    print(f"\nAll {PASSED} checks passed.")
