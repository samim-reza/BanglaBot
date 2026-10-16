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
from app.verticals.pipelines import pipeline_vertical
from app.verticals.reception import ReceptionFlow
from app.verticals.reception.blueprint import reception_blueprint
from app.voice.languages import normalize_language, phrase, spoken_amount

_DECISION_SLOT = "decision"


def _verify_address(ctx: CallContext) -> bool:
    return bool(ctx.merchant_value("verify_address", False)) and bool(str(ctx.record_value("address", "") or "").strip())


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
            "items": items or "(no item details given)",
            "amount": amount,
            "cod": phrase("cash_on_delivery", lang),
            "address": " ".join(str(ctx.record_value("address", "") or "").split()),
        }

    def decision_guidance(self, ctx: CallContext, language: str) -> str:
        lang = normalize_language(language)
        facts = self.order_facts(ctx, lang)
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
        return Instruction(STAGE_DONE, "Nothing more to ask. Call the end_call tool without saying anything.", end_call=True)

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
        """A pure "yes" / "no" to the order question goes straight to the terminal tool
        (the tool still applies the same hearing gate the model's call would)."""
        said_cancel = bool({"cancel", "cancelled", "canceled"} & set(hearing.tokens(text)))
        if stage == STAGE_DECISION and said_cancel and hearing.affirms_cancel(text) and not hearing.declines_cancel(text) and not hearing.looks_like_question(text):
            return "cancel_order"  # "No — please cancel the order" is unmistakable, even with extra words
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
        return f"[STEP CHANGE] {body.get(node, body[NODE_WRAP_UP])}"

    # ---- terminals ---------------------------------------------------------
    def terminals(self) -> list[Terminal]:
        return [
            Terminal(
                name="confirm_order",
                outcome=OUTCOME_CONFIRMED,
                description=(
                    "The named customer clearly said YES to keeping the order (e.g. 'yes', 'sure', "
                    "'confirm'). Call only after such a clear answer."
                ),
                gate="confirm",
            ),
            Terminal(
                name="cancel_order",
                outcome=OUTCOME_CANCELLED,
                description=(
                    "The named customer clearly said NO — they do not want the order (e.g. 'no', "
                    "'don't need it', 'cancel'). Call only after such a clear answer."
                ),
                properties={
                    "reason": {
                        "type": "string",
                        "description": "Why the customer cancelled, in a few words (their language).",
                    }
                },
                note_template={"en": "Customer cancelled: {reason}"},
                gate="cancel",
            ),
        ]

    # ---- prompt parts -------------------------------------------------------
    def rules(self, language: str) -> str:
        return _RULES_EN

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        facts = self.order_facts(ctx, lang)
        notes = " ".join(str(ctx.record_value("notes", "") or "").split())
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


_SYMBOLS = {"USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$", "SGD": "S$", "GBP": "£", "EUR": "€", "INR": "₹", "PKR": "Rs ", "AED": "AED ", "ZAR": "R", "NGN": "₦"}


def _summary(record: Any, names: dict[str, str]) -> str:
    items = " ".join(str(getattr(record, "items_summary", "") or "").split())
    amount = getattr(record, "total_amount", None)
    if not (items and amount):
        return items
    currency = str(getattr(record, "currency", "") or "").upper()
    symbol = _SYMBOLS.get(currency, f"{currency} " if currency else "")
    return f"{items} · {symbol}{amount}"


#: Keyword arguments of the e-commerce :class:`Vertical` (everything but its flows).
ECOMMERCE_SPEC: dict[str, Any] = dict(
    key="ecommerce",
    label=L("E-commerce order confirmation"),
    description=L(
        "Calls customers to confirm or cancel cash-on-delivery orders before dispatch.",
    ),
    record_kind="order",
    record_label=L("Order"),
    record_label_plural=L("Orders"),
    record_fields=(
        FieldSpec("customer_name", L("Customer name"), required=True, list_column=True),
        FieldSpec("customer_phone", L("Phone"), "phone", required=True, list_column=True, placeholder="+1 415 555 0100"),
        FieldSpec("order_ref", L("Order ref"), placeholder="#1001"),
        FieldSpec("items_summary", L("Items"), "textarea", placeholder="Blue hoodie (L) x1, Sneakers x1"),
        FieldSpec("total_amount", L("Total"), "money"),
        FieldSpec("address", L("Delivery address"), "textarea"),
        FieldSpec("notes", L("Notes"), "textarea"),
    ),
    outbound_label=L("Confirmation call"),
    summarize=_summary,
)

# Outbound stays on the tuned COD-confirmation flow; inbound reception runs on the skill pipeline.
ECOMMERCE: Vertical = pipeline_vertical(
    ECOMMERCE_SPEC,
    {"inbound": reception_blueprint("ecommerce")},
    legacy_flows={"inbound": ReceptionFlow(vertical="ecommerce")},
    fixed_flows={"outbound": DEFAULT_FLOW},
)


__all__ = ["DEFAULT_FLOW", "ECOMMERCE", "EcommerceFlow"]
