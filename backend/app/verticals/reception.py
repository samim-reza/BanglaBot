"""Inbound reception: answer from the business facts, or take a message for a callback.

Used for inbound calls of a vertical that has no inbound engine of its own
(e-commerce). The model answers questions in plain text; when the caller needs
a person (order status, complaint, anything not in the facts) it saves the
request, the backend reads it back and writes a ``message`` record the
business sees under its records with status *needs review*.

help → [name] → [phone] → confirm → commit → done
"""

from __future__ import annotations

from typing import Any

from app.flows.base import OUTCOME_LEAD, CommitAction, Instruction
from app.flows.context import DIRECTION_INBOUND, CallContext
from app.flows.steps import STAGE_CONFIRM, SlotSpec, StepFlow, lang_text
from app.voice.languages import normalize_language, phrase

STAGE_HELP = "help"
STAGE_NAME = "name"
STAGE_PHONE = "phone"

PHONE_HINT = "Digits only, as the caller said them; keep a leading + and the country code if they gave one."


def clean_phone(value: Any) -> str:
    """A spoken / typed phone number as digits (with a leading + kept); '' when it cannot be one."""
    from app.flows.timefmt import ascii_digits

    text = ascii_digits(value).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not 7 <= len(digits) <= 15:
        return ""
    return f"+{digits}" if text.startswith("+") else digits


def caller_phone(slots: dict[str, Any], ctx: CallContext) -> str:
    return str(slots.get("phone") or clean_phone(ctx.caller_number) or "")


_LINES = {
    "readback": {
        "bn": "তাহলে আপনার নাম {name}, আর আপনার বার্তা: {message}। আমাদের প্রতিনিধি {phone} নম্বরে ফোন করবেন — ঠিক আছে?",
        "en": "So your name is {name}, and your message is: {message}. A team member will call you on {phone} — is that right?",
    },
    "readback_own_number": {
        "bn": "তাহলে আপনার নাম {name}, আর আপনার বার্তা: {message}। আমাদের প্রতিনিধি এই নম্বরেই আপনাকে ফোন করবেন — ঠিক আছে?",
        "en": "So your name is {name}, and your message is: {message}. A team member will call you back on this number — is that right?",
    },
    "help_guidance": {
        "bn": "কলারের প্রশ্নের উত্তর দিন শুধু ব্যবসার তথ্য থেকে। যা জানা নেই বা কর্মীর দরকার (অর্ডারের অবস্থা, অভিযোগ), সেটা message-এ সেভ করুন।",
        "en": "Answer the caller from the business facts only. Anything you cannot answer or that needs staff (order status, complaints) — save it as message.",
    },
}


class ReceptionFlow(StepFlow):
    direction = DIRECTION_INBOUND
    identity_gate = False
    slot_specs = (
        SlotSpec("caller_name", "The caller's name as they said it."),
        SlotSpec(
            "message",
            "What the caller needs a team member to follow up on, in a short sentence in their words "
            "(order status, complaint, request). Only when you cannot fully answer it yourself.",
        ),
        SlotSpec("phone", f"Phone number to call back. {PHONE_HINT}"),
    )
    stage_goals = {
        STAGE_HELP: "Help the caller. Answer questions only from the business facts. When they need staff to follow up, save message.",
        STAGE_NAME: "Get the caller's name.",
        STAGE_PHONE: "Get a mobile number to call back.",
    }
    stage_slots = {STAGE_HELP: ("message",), STAGE_NAME: ("caller_name",), STAGE_PHONE: ("phone",)}
    long_answer_stages = frozenset({STAGE_HELP, STAGE_PHONE})

    def __init__(self, vertical: str = "") -> None:
        self.vertical = vertical
        self.key = f"{vertical}.inbound" if vertical else "reception.inbound"

    def opening_question(self, ctx: CallContext, language: str) -> str:
        return phrase("how_can_i_help", language)

    def greeting(self, ctx: CallContext, language: str) -> str:
        return self.inbound_greeting(ctx, language)

    def normalize(self, fields, slots, ctx, language):
        if "phone" in fields:
            phone = clean_phone(fields["phone"])
            if not phone:
                fields = {key: value for key, value in fields.items() if key != "phone"}
                return fields, Instruction(STAGE_PHONE, phrase("phone_invalid", language), verbatim=True)
            fields = {**fields, "phone": phone}
        return fields, None

    def next_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        if not slots.get("message"):
            return STAGE_HELP
        if not slots.get("caller_name"):
            return STAGE_NAME
        if not caller_phone(slots, ctx):
            return STAGE_PHONE
        return self.tail(slots)

    def stage_line(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        if stage == STAGE_HELP:
            return Instruction(stage, lang_text(_LINES["help_guidance"], language))
        if stage == STAGE_NAME:
            return phrase("ask_caller_name", language)
        if stage == STAGE_PHONE:
            return phrase("ask_phone", language)
        if stage == STAGE_CONFIRM:
            lang = normalize_language(language)
            message = str(slots.get("message", "")).strip().rstrip(".!?।")
            # The caller's own line needs no read-back; a number they gave does.
            key = "readback" if slots.get("phone") or not ctx.caller_number else "readback_own_number"
            return lang_text(_LINES[key], lang).format(
                name=slots.get("caller_name", ""),
                message=message,
                phone=ctx.say_number(caller_phone(slots, ctx), lang),
            )
        return ""

    def commit_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        return CommitAction(
            outcome=OUTCOME_LEAD,
            status="needs_review",
            fields={
                "kind": "message",
                "customer_name": slots.get("caller_name", ""),
                "customer_phone": caller_phone(slots, ctx),
                "items_summary": slots.get("message", ""),
                "details": {"message": slots.get("message", "")},
            },
        )

    def closing_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        if outcome == OUTCOME_LEAD:
            return phrase("closing_lead", language)
        return super().closing_line(outcome, slots, ctx, language)

    def prefetch_lines(self, ctx: CallContext, language: str) -> list[str]:
        return super().prefetch_lines(ctx, language) + [
            phrase("ask_caller_name", language),
            phrase("ask_phone", language),
            phrase("phone_invalid", language),
            phrase("amend_question", language),
            phrase("closing_lead", language),
            phrase("closing_inquiry", language),
        ]

    def preview_steps(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        if lang == "bn":
            return [
                f"শুভেচ্ছা: \"{self.opening(ctx, lang)}\"",
                "প্রশ্নের উত্তর: ব্যবসার তথ্য (সেটিংসের নলেজ) থেকে উত্তর দেয়।",
                "বার্তা: যা উত্তর দেওয়া যায় না, তা নাম ও নম্বরসহ নোট করে — আপনার রেকর্ডে 'রিভিউ দরকার' হিসেবে আসে।",
            ]
        return [
            f"Greeting: \"{self.opening(ctx, lang)}\"",
            "Questions: answered from the business facts (Settings → knowledge).",
            "Message: anything it cannot answer is taken down with name and number and lands in your records as needs review.",
        ]


__all__ = ["ReceptionFlow", "caller_phone", "clean_phone"]
