"""The e-commerce order-confirmation flow.

identity → (knows_person → relay / wrong number) → [address] → decision → wrap-up
"""

from __future__ import annotations

from typing import Any

from app.flows.base import (
    MAX_REASKS,
    NODE_ADDRESS,
    NODE_DECISION,
    NODE_IDENTITY,
    NODE_KNOWS_PERSON,
    NODE_WRAP_UP,
    OUTCOME_CANCELLED,
    OUTCOME_CONFIRMED,
    STAGE_ADDRESS,
    STAGE_DECISION,
    STAGE_DONE,
    STAGE_NEW_ADDRESS,
    Flow,
    Instruction,
    Terminal,
    _get,
)
from app.voice.languages import normalize_language, phrase, spoken_amount

_DECISION_SLOT = "decision"


def _verify_address(merchant: Any, order: Any) -> bool:
    return bool(_get(merchant, "verify_address", False)) and bool(str(_get(order, "address", "") or "").strip())


class EcommerceFlow(Flow):
    key = "ecommerce"

    # ---- slots ---------------------------------------------------------
    def slot_properties(self) -> dict[str, Any]:
        props = super().slot_properties()
        props.update(
            {
                "address_correct": {
                    "type": "boolean",
                    "description": "Whether the customer said the delivery address we read out is correct.",
                },
                "new_address": {
                    "type": "string",
                    "description": "The corrected delivery address, exactly as the customer gave it.",
                },
            }
        )
        return props

    # ---- cascade --------------------------------------------------------
    def next_stage(self, slots: dict[str, Any], order: Any, merchant: Any) -> str:
        gate = self.identity_stage(slots)
        if gate is not None:
            return gate
        decision = slots.get(_DECISION_SLOT)
        if not decision:
            return STAGE_DECISION
        # The address is checked only for a confirmed order, after the yes.
        if decision == OUTCOME_CONFIRMED and _verify_address(merchant, order):
            correct = slots.get("address_correct")
            if correct is None and not slots.get("new_address"):
                return STAGE_ADDRESS
            if correct is False and not slots.get("new_address"):
                return STAGE_NEW_ADDRESS
        return STAGE_DONE

    # ---- facts spoken in the decision step -------------------------------
    def order_facts(self, order: Any, language: str) -> dict[str, str]:
        lang = normalize_language(language)
        items = " ".join(str(_get(order, "items_summary", "") or "").split())
        amount = spoken_amount(_get(order, "total_amount", 0), _get(order, "currency", "BDT"), lang)
        return {
            "items": items or ("(পণ্যের বিবরণ দেওয়া নেই)" if lang == "bn" else "(no item details given)"),
            "amount": amount,
            "cod": phrase("cash_on_delivery", lang),
            "address": " ".join(str(_get(order, "address", "") or "").split()),
        }

    def decision_guidance(self, order: Any, language: str) -> str:
        lang = normalize_language(language)
        facts = self.order_facts(order, lang)
        if lang == "bn":
            return (
                "এখন অর্ডারটি নিশ্চিত করার পালা। এক-দুই বাক্যে স্বাভাবিক কথ্য বাংলায় বলুন কাস্টমার কী অর্ডার করেছেন "
                f"(পণ্য: {facts['items']}), মোট দাম {facts['amount']}, পেমেন্ট {facts['cod']} — তারপর জিজ্ঞেস করুন "
                "তিনি অর্ডারটি কনফার্ম করতে চান কি না। পণ্যের কাঁচা লেখা হুবহু পড়বেন না, কথার মতো করে বলবেন।"
            )
        return (
            "Now confirm the order. In one or two natural sentences tell the customer what they ordered "
            f"(items: {facts['items']}), the total {facts['amount']}, payment {facts['cod']} — then ask whether "
            "they would like to confirm the order. Do not read the raw item text; say it the way a person would."
        )

    # ---- instructions ----------------------------------------------------
    def instruction(self, stage: str, slots: dict[str, Any], order: Any, merchant: Any, language: str) -> Instruction:
        identity = self.identity_instruction(stage, order, merchant, language)
        if identity is not None:
            return identity
        lang = normalize_language(language)
        if stage == STAGE_ADDRESS:
            address = self.order_facts(order, lang)["address"]
            return Instruction(stage, phrase("address_question", lang, address=address), verbatim=True)
        if stage == STAGE_NEW_ADDRESS:
            return Instruction(stage, phrase("new_address_question", lang), verbatim=True)
        if stage == STAGE_DECISION:
            return Instruction(stage, self.decision_guidance(order, lang))
        text = (
            "আর কিছু জিজ্ঞেস করার নেই। কিছু না বলে end_call টুল কল করুন।"
            if lang == "bn"
            else "Nothing more to ask. Call the end_call tool without saying anything."
        )
        return Instruction(STAGE_DONE, text, end_call=True)

    # ---- node directives (appended as a system message on node change) ----
    def node_directive(self, node: str, order: Any, merchant: Any, language: str) -> str:
        lang = normalize_language(language)
        name = _get(order, "customer_name", "")
        head = "ধাপ পরিবর্তন" if lang == "bn" else "STEP CHANGE"
        if lang == "bn":
            body = {
                NODE_IDENTITY: (
                    f"বর্তমান ধাপ: পরিচয়। লক্ষ্য — ফোন ধরা ব্যক্তি {name} কি না, সেটা নিশ্চিত হওয়া। "
                    "উত্তর পেলে save_details দিয়ে identity_confirmed সেভ করুন। পরিচয় নিশ্চিত না হওয়া পর্যন্ত "
                    "অর্ডারের কথা বলবেন না।"
                ),
                NODE_KNOWS_PERSON: (
                    f"বর্তমান ধাপ: অন্য কেউ ফোন ধরেছেন। জিজ্ঞেস করুন তিনি {name}-কে চেনেন কি না, উত্তর "
                    "knows_customer-এ সেভ করুন। অর্ডারের বিস্তারিত (পণ্য, দাম) এই ব্যক্তিকে বলবেন না। "
                    "চিনলে instruction-এর বার্তাটি হুবহু বলে end_call করুন; না চিনলে ক্ষমা চেয়ে end_call করুন।"
                ),
                NODE_ADDRESS: (
                    "বর্তমান ধাপ: ঠিকানা যাচাই (অর্ডার কনফার্ম হয়ে গেছে)। instruction অনুযায়ী ঠিকানা পড়ে শুনিয়ে জিজ্ঞেস করুন ঠিক আছে কি না। "
                    "ঠিক থাকলে address_correct=true; বদলাতে চাইলে address_correct=false এবং নতুন ঠিকানা "
                    "new_address-এ হুবহু সেভ করুন।"
                ),
                NODE_DECISION: (
                    "বর্তমান ধাপ: অর্ডার কনফার্মেশন। "
                    + self.decision_guidance(order, lang)
                    + " কাস্টমার স্পষ্ট হ্যাঁ বললে confirm_order, স্পষ্ট না বললে cancel_order কল করুন। "
                    "অস্পষ্ট হলে অনুমান না করে ছোট করে আবার জিজ্ঞেস করুন। প্রশ্ন করলে সংক্ষেপে উত্তর দিয়ে "
                    "আবার কনফার্মেশনের প্রশ্নে ফিরুন। দাম বা ডেলিভারি নিয়ে দর কষাকষি হলে transfer_to_human।"
                ),
                NODE_WRAP_UP: (
                    "বর্তমান ধাপ: সমাপ্তি। আর কোনো প্রশ্ন নেই। instruction-এ কোনো বাক্য থাকলে সেটি হুবহু বলুন, "
                    "তারপর end_call কল করুন। নতুন কিছু জিজ্ঞেস করবেন না।"
                ),
            }
        else:
            body = {
                NODE_IDENTITY: (
                    f"Current step: identity. Goal — find out whether the person on the line is {name}. "
                    "Save the answer with save_details (identity_confirmed). Do not discuss the order until "
                    "identity is confirmed."
                ),
                NODE_KNOWS_PERSON: (
                    f"Current step: someone else answered. Ask whether they know {name} and save it as "
                    "knows_customer. Do not share order details (items, amount) with this person. If they know "
                    "them, say the instruction's message word for word and call end_call; if not, apologise and "
                    "call end_call."
                ),
                NODE_ADDRESS: (
                    "Current step: address check (the order is already confirmed). Read the address from the instruction and ask if it is correct. "
                    "Correct → address_correct=true; needs a change → address_correct=false and save the new "
                    "address exactly as given in new_address."
                ),
                NODE_DECISION: (
                    "Current step: order confirmation. "
                    + self.decision_guidance(order, lang)
                    + " Call confirm_order on a clear yes and cancel_order on a clear no. If the answer is unclear, "
                    "do not guess — briefly ask again. Answer questions briefly, then return to the confirmation "
                    "question. Haggling over price or delivery → transfer_to_human."
                ),
                NODE_WRAP_UP: (
                    "Current step: wrap-up. There is nothing left to ask. If the instruction carries a sentence, say "
                    "it word for word, then call end_call. Do not ask anything new."
                ),
            }
        return f"[{head}] {body.get(node, body[NODE_WRAP_UP])}"

    # ---- terminals ---------------------------------------------------------
    def terminals(self) -> list[Terminal]:
        return [
            Terminal(
                name="confirm_order",
                outcome=OUTCOME_CONFIRMED,
                description=(
                    "The named customer clearly said YES to keeping the order (e.g. 'হ্যাঁ', 'জি', 'ঠিক আছে', "
                    "'yes', 'confirm'). Call only after such a clear answer."
                ),
            ),
            Terminal(
                name="cancel_order",
                outcome=OUTCOME_CANCELLED,
                description=(
                    "The named customer clearly said NO — they do not want the order (e.g. 'না', 'লাগবে না', "
                    "'বাতিল', 'no', 'cancel'). Call only after such a clear answer."
                ),
                properties={
                    "reason": {
                        "type": "string",
                        "description": "Why the customer cancelled, in a few words (their language).",
                    }
                },
                note_template={"bn": "কাস্টমার বাতিল করেছেন: {reason}", "en": "Customer cancelled: {reason}"},
            ),
        ]

    # ---- prefetch / preview ------------------------------------------------
    def prefetch_lines(self, order: Any, merchant: Any, language: str) -> list[str]:
        lang = normalize_language(language)
        name = _get(order, "customer_name", "")
        business = _get(merchant, "business_name", "")
        lines = [
            # The opening is spoken as ONE unit (greeting + question) so it keeps
            # its natural prosody; warm it exactly as the bridge will request it.
            f"{self.greeting(merchant, lang)} {self.opening_question(order, lang)}",
            self.greeting(merchant, lang),
            self.opening_question(order, lang),
            phrase("identity_reask", lang, customer_name=name),
            phrase("knows_person_question", lang, customer_name=name),
            phrase("relay_line", lang, customer_name=name, business_name=business),
            phrase("wrong_number_line", lang),
            phrase("decision_reask_1", lang),
            phrase("decision_reask_2", lang),
            phrase("closing_confirmed", lang),
            phrase("closing_cancelled", lang),
            phrase("closing_unclear", lang),
            phrase("closing_transfer", lang),
            phrase("closing_transfer_callback", lang),
            phrase("closing_dropped", lang),
            phrase("closing_timeout", lang),
            phrase("still_there", lang),
            phrase("recovery", lang),
        ]
        if _verify_address(merchant, order):
            lines.append(phrase("address_question", lang, address=self.order_facts(order, lang)["address"]))
            lines.append(phrase("new_address_question", lang))
        return [line for line in lines if line]

    def preview_steps(self, merchant: Any, language: str) -> list[str]:
        lang = normalize_language(language)
        steps = [
            phrase("preview_greeting", lang, greeting=self.greeting(merchant, lang)),
            phrase("preview_identity", lang),
        ]
        steps.append(phrase("preview_decision", lang))
        if bool(_get(merchant, "verify_address", False)):
            steps.append(phrase("preview_address", lang))
        steps.append(phrase("preview_wrap_up", lang))
        return steps


DEFAULT_FLOW = EcommerceFlow()


def flow_preview_steps(merchant: Any, language: str | None = None) -> list[str]:
    """Ordered questions the agent will ask, for the merchant settings page."""
    return DEFAULT_FLOW.preview_steps(merchant, language or _get(merchant, "language", "bn"))


__all__ = ["DEFAULT_FLOW", "EcommerceFlow", "MAX_REASKS", "flow_preview_steps"]
