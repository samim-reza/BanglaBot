"""E-commerce engine: outbound order-confirmation calls (+ an inbound reception line).

identity → (knows_person → relay / wrong number) → decision → [address] → wrap-up
"""

from __future__ import annotations

from typing import Any

from app.flows import hearing
from app.flows.base import (
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
)
from app.flows.context import CallContext
from app.verticals.base import FieldSpec, L, Vertical
from app.verticals.reception import ReceptionFlow
from app.voice.languages import normalize_language, phrase, spoken_amount

_DECISION_SLOT = "decision"


def _verify_address(ctx: CallContext) -> bool:
    return bool(ctx.merchant_value("verify_address", False)) and bool(str(ctx.record_value("address", "") or "").strip())


_RULES_BN = """এই কলের উদ্দেশ্য: কাস্টমারের দেওয়া একটি অর্ডার কনফার্ম করা।
- পরিচয়: ফোন ধরা ব্যক্তি নিজেই নামের কাস্টমার হলে identity_confirmed=true; অন্য কেউ হলে identity_confirmed=false এবং জিজ্ঞেস করো তিনি কাস্টমারকে চেনেন কি না (knows_customer)। কাস্টমার ছাড়া অন্য কেউ অর্ডার কনফার্ম বা বাতিল করতে পারবেন না, এবং অন্য কাউকে অর্ডারের পণ্য বা দাম বলো না।
- confirm_order বা cancel_order শুধু তখনই কল করো যখন কাস্টমার নিজের মুখে স্পষ্ট "হ্যাঁ" বা "না" বলেছেন। অস্পষ্ট বা এক-শব্দের ধোঁয়াশা উত্তর হলে অনুমান করো না — ছোট করে আবার জিজ্ঞেস করো। কাস্টমার পরে কথা বলতে চাইলে end_call কল করো।
- ডেলিভারির তারিখ, ডিসকাউন্ট বা রিটার্ন নীতি নিয়ে প্রতিশ্রুতি দিও না; দাম বা ডেলিভারি চার্জ নিয়ে দর কষাকষি করো না — বলো প্রতিনিধি জানাবেন, প্রয়োজনে transfer_to_human।
- পণ্যের কাঁচা লেখা হুবহু পড়ো না; মানুষ যেভাবে বলে সেভাবে বলো। টাকার অংক কথায় বলো।"""

_RULES_EN = """Purpose of this call: confirm one order the customer placed.
- Identity: if the person on the line is the named customer, identity_confirmed=true; if it is someone else, identity_confirmed=false and ask whether they know the customer (knows_customer). Nobody but the customer may confirm or cancel, and never tell anyone else what was ordered or for how much.
- Call confirm_order or cancel_order only after a clear "yes" or "no" in the customer's own words. If the answer is vague or a one-word mumble, do not guess — ask again briefly. If they want to talk later, call end_call.
- Never promise delivery dates, discounts or return policies, and do not negotiate price or delivery charges — say a team member will follow up, or call transfer_to_human.
- Never read raw item text; describe the items the way a person would. Say amounts in words."""


class EcommerceFlow(Flow):
    key = "ecommerce.outbound"
    vertical = "ecommerce"

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
                "note": {
                    "type": "string",
                    "description": "Anything important the customer asked us to pass on (short, in their words).",
                },
            }
        )
        return props

    # ---- cascade --------------------------------------------------------
    def next_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        gate = self.identity_stage(slots)
        if gate is not None:
            return gate
        decision = slots.get(_DECISION_SLOT)
        if not decision:
            return STAGE_DECISION
        # The address is checked only for a confirmed order, after the yes.
        if decision == OUTCOME_CONFIRMED and _verify_address(ctx):
            correct = slots.get("address_correct")
            if correct is None and not slots.get("new_address"):
                return STAGE_ADDRESS
            if correct is False and not slots.get("new_address"):
                return STAGE_NEW_ADDRESS
        return STAGE_DONE

    def node_for_stage(self, stage: str) -> str:
        return {
            STAGE_ADDRESS: NODE_ADDRESS,
            STAGE_NEW_ADDRESS: NODE_ADDRESS,
            STAGE_DECISION: NODE_DECISION,
        }.get(stage) or super().node_for_stage(stage)

    # ---- facts spoken in the decision step -------------------------------
    def order_facts(self, ctx: CallContext, language: str) -> dict[str, str]:
        lang = normalize_language(language)
        items = " ".join(str(ctx.record_value("items_summary", "") or "").split())
        amount = spoken_amount(ctx.record_value("total_amount", 0), ctx.record_value("currency", "") or ctx.currency, lang)
        return {
            "items": items or ("(পণ্যের বিবরণ দেওয়া নেই)" if lang == "bn" else "(no item details given)"),
            "amount": amount,
            "cod": phrase("cash_on_delivery", lang),
            "address": " ".join(str(ctx.record_value("address", "") or "").split()),
        }

    def decision_guidance(self, ctx: CallContext, language: str) -> str:
        lang = normalize_language(language)
        facts = self.order_facts(ctx, lang)
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
    def instruction(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction:
        identity = self.identity_instruction(stage, ctx, language)
        if identity is not None:
            return identity
        lang = normalize_language(language)
        if stage == STAGE_ADDRESS:
            address = self.order_facts(ctx, lang)["address"]
            return Instruction(stage, phrase("address_question", lang, address=address), verbatim=True)
        if stage == STAGE_NEW_ADDRESS:
            return Instruction(stage, phrase("new_address_question", lang), verbatim=True)
        if stage == STAGE_DECISION:
            # Composed by the model while the phone rang (voice/prepared.py), so the
            # caller's "yes, speaking" is answered from the TTS cache.
            prepared = str(ctx.prepared.get("decision") or "").strip()
            if prepared:
                return Instruction(stage, prepared, verbatim=True)
            return Instruction(stage, self.decision_guidance(ctx, lang))
        text = (
            "আর কিছু জিজ্ঞেস করার নেই। কিছু না বলে end_call টুল কল করুন।"
            if lang == "bn"
            else "Nothing more to ask. Call the end_call tool without saying anything."
        )
        return Instruction(STAGE_DONE, text, end_call=True)

    # ---- fast path --------------------------------------------------------
    def fast_fields(self, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> dict[str, Any] | None:
        identity_talk = bool(labels & {"not_me", "knows", "wrong_number"})
        if stage == STAGE_ADDRESS and hearing.is_pure_answer(text) and not identity_talk:
            if "yes" in labels and "no" not in labels:
                return {"address_correct": True}
            if "no" in labels and "yes" not in labels:
                return {"address_correct": False}
            return None
        return self.identity_fast_fields(stage, text, labels)

    def fast_terminal(self, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> str | None:
        """A pure "হ্যাঁ" / "না" to the order question goes straight to the terminal tool
        (the tool still applies the same hearing gate the model's call would)."""
        if stage != STAGE_DECISION or not hearing.is_pure_answer(text) or hearing.looks_like_question(text):
            return None
        if labels & {"later", "repeat", "not_me", "knows", "wrong_number"}:
            return None
        if hearing.supports(text, "confirm"):
            return "confirm_order"
        if hearing.supports(text, "cancel"):
            return "cancel_order"
        return None

    def stage_hint(self, stage: str) -> dict[str, Any]:
        return {"long_answer": stage == STAGE_NEW_ADDRESS}

    # ---- node directives (appended as a system message on node change) ----
    def node_directive(self, node: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        lang = normalize_language(language)
        name = self.person_name(ctx)
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
                    "knows_customer-এ সেভ করুন। অর্ডারের বিস্তারিত (পণ্য, দাম) এই ব্যক্তিকে বলবেন না।"
                ),
                NODE_ADDRESS: (
                    "বর্তমান ধাপ: ঠিকানা যাচাই (অর্ডার কনফার্ম হয়ে গেছে)। ঠিক থাকলে address_correct=true; "
                    "বদলাতে চাইলে address_correct=false এবং নতুন ঠিকানা new_address-এ হুবহু সেভ করুন।"
                ),
                NODE_DECISION: (
                    "বর্তমান ধাপ: অর্ডার কনফার্মেশন। "
                    + self.decision_guidance(ctx, lang)
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
                    "knows_customer. Do not share order details (items, amount) with this person."
                ),
                NODE_ADDRESS: (
                    "Current step: address check (the order is already confirmed). Correct → address_correct=true; "
                    "needs a change → address_correct=false and save the new address exactly as given in new_address."
                ),
                NODE_DECISION: (
                    "Current step: order confirmation. "
                    + self.decision_guidance(ctx, lang)
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
                gate="confirm",
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
                gate="cancel",
            ),
        ]

    # ---- prompt parts -------------------------------------------------------
    def rules(self, language: str) -> str:
        return _RULES_BN if normalize_language(language) == "bn" else _RULES_EN

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        facts = self.order_facts(ctx, lang)
        notes = " ".join(str(ctx.record_value("notes", "") or "").split())
        if lang == "bn":
            lines = [
                f"- কাস্টমারের নাম: {self.person_name(ctx)}",
                f"- অর্ডারের পণ্য: {facts['items']}",
                f"- মোট মূল্য: {facts['amount']} ({facts['cod']})",
            ]
            if facts["address"]:
                lines.append(f"- ডেলিভারি ঠিকানা: {facts['address']}")
            if notes:
                lines.append(f"- বিক্রেতার নোট: {notes}")
            return lines
        lines = [
            f"- Customer name: {self.person_name(ctx)}",
            f"- Items ordered: {facts['items']}",
            f"- Total: {facts['amount']} ({facts['cod']})",
        ]
        if facts["address"]:
            lines.append(f"- Delivery address: {facts['address']}")
        if notes:
            lines.append(f"- Merchant note: {notes}")
        return lines

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        items = " ".join(str(ctx.record_value("items_summary", "") or "").split())[:120]
        return [str(ctx.merchant_value("business_name", "")), self.person_name(ctx), items]

    # ---- prefetch / preview ------------------------------------------------
    def prefetch_lines(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        lines = super().prefetch_lines(ctx, lang)
        lines += [
            # The opening is spoken as ONE unit (greeting + question) so it keeps
            # its natural prosody; the parts are warmed too for the re-ask paths.
            self.greeting(ctx, lang),
            self.opening_question(ctx, lang),
            phrase("decision_reask_1", lang),
            phrase("decision_reask_2", lang),
            phrase("closing_confirmed", lang),
            phrase("closing_cancelled", lang),
        ]
        if _verify_address(ctx):
            lines.append(phrase("address_question", lang, address=self.order_facts(ctx, lang)["address"]))
            lines.append(phrase("new_address_question", lang))
        return [line for line in lines if line]

    def preview_steps(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        steps = [
            phrase("preview_greeting", lang, greeting=self.greeting(ctx, lang)),
            phrase("preview_identity", lang),
            phrase("preview_decision", lang),
        ]
        if bool(ctx.merchant_value("verify_address", False)):
            steps.append(phrase("preview_address", lang))
        steps.append(phrase("preview_wrap_up", lang))
        return steps


DEFAULT_FLOW = EcommerceFlow()


_SYMBOLS = {"USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$", "SGD": "S$", "GBP": "£", "EUR": "€", "INR": "₹", "BDT": "৳", "PKR": "Rs ", "AED": "AED ", "ZAR": "R", "NGN": "₦"}


def _summary(record: Any, names: dict[str, str]) -> str:
    items = " ".join(str(getattr(record, "items_summary", "") or "").split())
    amount = getattr(record, "total_amount", None)
    if not (items and amount):
        return items
    currency = str(getattr(record, "currency", "") or "").upper()
    symbol = _SYMBOLS.get(currency, f"{currency} " if currency else "")
    return f"{items} · {symbol}{amount}"


ECOMMERCE = Vertical(
    key="ecommerce",
    label=L("E-commerce order confirmation", "ই-কমার্স অর্ডার কনফার্মেশন"),
    description=L(
        "Calls customers to confirm or cancel cash-on-delivery orders before dispatch.",
        "ডেলিভারির আগে কাস্টমারকে ফোন করে ক্যাশ-অন-ডেলিভারি অর্ডার কনফার্ম বা বাতিল করে।",
    ),
    record_kind="order",
    record_label=L("Order", "অর্ডার"),
    record_label_plural=L("Orders", "অর্ডার"),
    record_fields=(
        FieldSpec("customer_name", L("Customer name", "কাস্টমারের নাম"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone", "ফোন"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("order_ref", L("Order ref", "অর্ডার নম্বর"), placeholder="#1001"),
        FieldSpec("items_summary", L("Items", "পণ্য"), "textarea", placeholder="Blue hoodie (L) x1, Sneakers x1"),
        FieldSpec("total_amount", L("Total", "মোট"), "money"),
        FieldSpec("address", L("Delivery address", "ডেলিভারি ঠিকানা"), "textarea"),
        FieldSpec("notes", L("Notes", "নোট"), "textarea"),
    ),
    flows={"outbound": DEFAULT_FLOW, "inbound": ReceptionFlow(vertical="ecommerce")},
    outbound_label=L("Confirmation call", "কনফার্মেশন কল"),
    summarize=_summary,
)


__all__ = ["DEFAULT_FLOW", "ECOMMERCE", "EcommerceFlow"]
