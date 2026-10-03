"""Slot-derived conversation flow: the contract every business engine implements.

The idea in one paragraph: the *current stage* is never stored. On every turn
the backend looks at the slots collected so far and asks "what is the next
thing the caller still owes us?" — that stage is the node. Skipping a question
the caller already answered (volunteered early, or pre-filled from the record)
is simply the absence of a return further down the cascade, and a correction
can never leave a stale pointer behind.

The backend also owns the *wording* of the next question: every save returns
an :class:`Instruction`. A verbatim instruction is spoken by the backend
directly (from the TTS cache when it is a fixed line) — the model only has to
understand the caller and extract slots, which keeps a turn to a single model
round-trip. A node change appends a short directive to the conversation tail
instead of rewriting the system prompt, which keeps the prompt head cacheable.

Everything here is plain Python over a :class:`~app.flows.context.CallContext`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.flows.context import DIRECTION_OUTBOUND, CallContext
from app.voice.languages import normalize_language, phrase

# --- Stages: the finest-grained "what is still missing" answers ------------
STAGE_IDENTITY = "identity"
STAGE_KNOWS_PERSON = "knows_person"
STAGE_RELAY = "relay"
STAGE_WRONG_NUMBER = "wrong_number"
STAGE_ADDRESS = "address"
STAGE_NEW_ADDRESS = "new_address"
STAGE_DECISION = "decision"
#: Everything needed is collected and confirmed — the backend writes the result.
STAGE_COMMIT = "commit"
STAGE_DONE = "done"

# --- Nodes: instruction bundles; several stages may share one node ---------
NODE_IDENTITY = "identity"
NODE_KNOWS_PERSON = "knows_person"
NODE_ADDRESS = "address"
NODE_DECISION = "decision"
NODE_WRAP_UP = "wrap_up"

# --- Call outcomes (CallLog.outcome) --------------------------------------
OUTCOME_CONFIRMED = "confirmed"
OUTCOME_CANCELLED = "cancelled"
OUTCOME_TRANSFER = "transfer"
OUTCOME_WRONG_NUMBER = "wrong_number"
OUTCOME_RELAY = "relay"
OUTCOME_UNCLEAR = "unclear"
OUTCOME_AUTO_DROPPED = "auto_dropped"
#: The callee rejected / was busy and the carrier forwarded the call.
OUTCOME_DIVERTED = "diverted"
#: Twilio's answering-machine detection heard a machine.
OUTCOME_VOICEMAIL = "voicemail"
#: A new appointment / booking / site visit was written.
OUTCOME_BOOKED = "booked"
#: An existing appointment / booking moved to a new time.
OUTCOME_RESCHEDULED = "rescheduled"
#: A lead (buyer, seller, out-of-area request, message) was captured for follow-up.
OUTCOME_LEAD = "lead"
#: The caller only asked questions; nothing to write.
OUTCOME_INQUIRY = "inquiry"
#: A lead said they are no longer interested.
OUTCOME_NOT_INTERESTED = "not_interested"
#: Medical / safety emergency: the caller was told to call 999.
OUTCOME_EMERGENCY = "emergency"

#: Record status each outcome settles the record to ("" = leave the record alone).
OUTCOME_STATUS: dict[str, str] = {
    OUTCOME_CONFIRMED: "confirmed",
    OUTCOME_CANCELLED: "cancelled",
    OUTCOME_TRANSFER: "needs_review",
    OUTCOME_WRONG_NUMBER: "needs_review",
    OUTCOME_RELAY: "needs_review",
    OUTCOME_UNCLEAR: "needs_review",
    OUTCOME_AUTO_DROPPED: "no_answer",
    OUTCOME_DIVERTED: "no_answer",
    OUTCOME_VOICEMAIL: "no_answer",
    OUTCOME_BOOKED: "confirmed",
    OUTCOME_RESCHEDULED: "confirmed",
    OUTCOME_LEAD: "needs_review",
    OUTCOME_INQUIRY: "",
    OUTCOME_NOT_INTERESTED: "cancelled",
    OUTCOME_EMERGENCY: "needs_review",
}

#: Set on the call log by the status callback when nobody picked up.
OUTCOME_NO_ANSWER = "no_answer"

#: Every outcome, for the API / UI.
OUTCOMES: tuple[str, ...] = (*OUTCOME_STATUS, OUTCOME_NO_ANSWER)

#: Outcomes that mean the customer never actually took the call — the record
#: goes back to ``no_answer`` and stays callable.
UNANSWERED_OUTCOMES = frozenset({OUTCOME_AUTO_DROPPED, OUTCOME_DIVERTED, OUTCOME_VOICEMAIL})

#: Phrase key of the closing line spoken for each outcome (flows may override).
OUTCOME_CLOSING_KEY: dict[str, str] = {
    OUTCOME_CONFIRMED: "closing_confirmed",
    OUTCOME_CANCELLED: "closing_cancelled",
    OUTCOME_TRANSFER: "closing_transfer",
    OUTCOME_WRONG_NUMBER: "wrong_number_line",
    OUTCOME_RELAY: "relay_line",
    OUTCOME_UNCLEAR: "closing_unclear",
    OUTCOME_AUTO_DROPPED: "closing_dropped",
    OUTCOME_INQUIRY: "closing_inquiry",
    OUTCOME_LEAD: "closing_lead",
    OUTCOME_NOT_INTERESTED: "closing_not_interested",
    OUTCOME_EMERGENCY: "emergency_line",
}

# How many times an unclear yes/no is re-asked before the call is handed to a human.
MAX_REASKS = 2


@dataclass(frozen=True)
class Terminal:
    """A call-ending outcome tool: its schema and what it writes."""

    name: str
    outcome: str
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    #: Note appended to the record, ``{arg}`` placeholders filled from arguments.
    note_template: dict[str, str] = field(default_factory=dict)
    #: Hearing label the caller's own words must carry ("confirm", "cancel"); None = no gate.
    gate: str | None = None
    #: Only the named person may trigger it (outbound identity gate).
    requires_identity: bool = True

    @property
    def status(self) -> str:
        return OUTCOME_STATUS[self.outcome]


@dataclass(frozen=True)
class Instruction:
    """What happens next, as decided by the backend."""

    stage: str
    text: str
    #: ``True`` — ``text`` is the exact line to speak; ``False`` — guidance for the model.
    verbatim: bool = False
    #: After saying it, the call ends (relay / wrong number / nothing left).
    end_call: bool = False

    def for_model(self, language: str) -> str:
        lang = normalize_language(language)
        if self.verbatim:
            lead = "হুবহু বলুন:" if lang == "bn" else "Say exactly:"
            text = f"{lead} {self.text}"
            if self.end_call:
                tail = (
                    "এরপর অন্য কিছু না বলে end_call টুল কল করুন।"
                    if lang == "bn"
                    else "Then call the end_call tool without saying anything else."
                )
                text = f"{text} {tail}"
            return text
        return self.text


@dataclass
class CommitAction:
    """The write a flow wants once everything is collected and confirmed."""

    outcome: str
    #: Record status after the write ("confirmed", "cancelled", "needs_review", ...).
    status: str
    #: Existing record to update; ``None`` creates a new one.
    record_id: str | None = None
    #: Record columns (customer_name, customer_phone, address, items_summary,
    #: total_amount, catalog_item_id, scheduled_at, kind) and ``details`` (merged).
    fields: dict[str, Any] = field(default_factory=dict)
    #: ``(item_id, slot start, capacity)`` re-checked under a lock before writing.
    capacity: tuple[str | None, datetime, int] | None = None
    note: str = ""


@dataclass
class CommitResult:
    ok: bool
    record_id: str = ""
    #: ``slot_taken`` | ``not_found`` | ``error``
    reason: str = ""


def _get(obj: Any, name: str, default: Any = None) -> Any:
    value = getattr(obj, name, None) if obj is not None else None
    return default if value in (None, "") else value


class Flow:
    """One business engine's conversation for one call direction."""

    #: Registry key, e.g. ``"clinic.inbound"``.
    key: str = ""
    vertical: str = ""
    direction: str = DIRECTION_OUTBOUND
    #: Outbound calls first make sure the named person is on the line.
    identity_gate: bool = True
    #: Boolean slots that commit something: the caller's own words must carry the
    #: matching yes/no before the value is accepted (``True`` → "confirm", ``False`` → "cancel").
    gated_slots: tuple[str, ...] = ()

    # ---- slots ---------------------------------------------------------
    def slot_properties(self) -> dict[str, Any]:
        """JSON-schema properties of the ``save_details`` tool.

        Must not depend on the merchant: the tool list is part of the cached
        prompt prefix, so it stays byte-identical across every call of a flow.
        """
        if not self.identity_gate:
            return {}
        return {
            "identity_confirmed": {
                "type": "boolean",
                "description": (
                    "true when the person on the line says they ARE the named person; "
                    "false when they say they are someone else (family, colleague, friend)."
                ),
            },
            "knows_customer": {
                "type": "boolean",
                "description": (
                    "Only when identity_confirmed is false: true if they know the named person "
                    "(relative, roommate, colleague), false if they do not know them at all."
                ),
            },
            "wrong_person": {
                "type": "boolean",
                "description": (
                    "true only when the caller clearly says this is the wrong number / nobody by "
                    "that name is reachable here. Never infer it from a short or unclear answer."
                ),
            },
        }

    def initial_slots(self, ctx: CallContext) -> dict[str, Any]:
        return {}

    def normalize(
        self, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str
    ) -> tuple[dict[str, Any], Instruction | None]:
        """Validate / resolve what the model saved. Returns the accepted fields and,
        when something was refused, the line to say instead of the next question."""
        return fields, None

    def on_saved(self, saved: dict[str, Any], slots: dict[str, Any], ctx: CallContext) -> None:
        """Hook after accepted fields were written into ``slots``."""

    def derive(self, slots: dict[str, Any], ctx: CallContext) -> None:
        """Fill slots the backend works out itself (e.g. the proposed time)."""

    # ---- the identity gate (outbound) ------------------------------------------
    def identity_stage(self, slots: dict[str, Any]) -> str | None:
        """Next identity-gate stage, or ``None`` once the named person is on the line.

        Named person → carry on. Someone else → ask whether they know them. They
        do → leave a relay message. They don't / wrong number → apologise and hang
        up. Nobody but the named person may decide anything.
        """
        if not self.identity_gate:
            return None
        knows = slots.get("knows_customer")
        if slots.get("wrong_person") is True and knows is not True:
            return STAGE_WRONG_NUMBER
        if slots.get("identity_confirmed") is True:
            return None
        if slots.get("identity_confirmed") is False:
            if knows is True:
                return STAGE_RELAY
            if knows is False:
                return STAGE_WRONG_NUMBER
            return STAGE_KNOWS_PERSON
        return STAGE_IDENTITY

    def person_name(self, ctx: CallContext) -> str:
        return str(ctx.record_value("customer_name", ""))

    def identity_instruction(self, stage: str, ctx: CallContext, language: str) -> Instruction | None:
        name = self.person_name(ctx)
        business = ctx.merchant_value("business_name", "")
        if stage == STAGE_IDENTITY:
            return Instruction(stage, phrase("identity_reask", language, customer_name=name), verbatim=True)
        if stage == STAGE_KNOWS_PERSON:
            return Instruction(stage, self.knows_person_line(ctx, language), verbatim=True)
        if stage == STAGE_RELAY:
            return Instruction(
                stage,
                phrase("relay_line", language, customer_name=name, business_name=business),
                verbatim=True,
                end_call=True,
            )
        if stage == STAGE_WRONG_NUMBER:
            return Instruction(stage, phrase("wrong_number_line", language), verbatim=True, end_call=True)
        return None

    def knows_person_line(self, ctx: CallContext, language: str) -> str:
        return phrase("knows_person_question", language, customer_name=self.person_name(ctx))

    def identity_fast_fields(self, stage: str, text: str, labels: set[str]) -> dict[str, Any] | None:
        """A clean answer to "am I speaking with X?" / "do you know X?" without the model."""
        from app.flows import hearing

        identity_talk = bool(labels & {"not_me", "knows", "wrong_number"})
        if stage == STAGE_IDENTITY:
            if "is_me" in labels and not identity_talk:
                return {"identity_confirmed": True}
            if "wrong_number" in labels:
                return {"identity_confirmed": False, "wrong_person": True}
            if "no" in labels and "is_me" not in labels and hearing.is_pure_answer(text):
                # "না" alone: not them — ask whether they know the person.
                return {"identity_confirmed": False}
        elif stage == STAGE_KNOWS_PERSON:
            if "wrong_number" in labels or ("no" in labels and "knows" not in labels):
                return {"knows_customer": False}
            if "knows" in labels or ("yes" in labels and hearing.is_pure_answer(text)):
                return {"knows_customer": True}
        return None

    # ---- the cascade ----------------------------------------------------
    def next_stage(self, slots: dict[str, Any], ctx: CallContext) -> str:
        raise NotImplementedError

    def node_for_stage(self, stage: str) -> str:
        return {
            STAGE_IDENTITY: NODE_IDENTITY,
            STAGE_KNOWS_PERSON: NODE_KNOWS_PERSON,
            STAGE_RELAY: NODE_WRAP_UP,
            STAGE_WRONG_NUMBER: NODE_WRAP_UP,
            STAGE_COMMIT: NODE_WRAP_UP,
            STAGE_DONE: NODE_WRAP_UP,
        }.get(stage, stage)

    def instruction(self, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction:
        raise NotImplementedError

    def node_directive(self, node: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        return ""

    def fast_fields(self, stage: str, text: str, labels: set[str], slots: dict[str, Any], ctx: CallContext) -> dict[str, Any] | None:
        """Slots a clean yes/no fills without the model (None = let the model decide)."""
        return self.identity_fast_fields(stage, text, labels)

    def confirms_cancellation(self, slots: dict[str, Any], ctx: CallContext) -> bool:
        """The read-back asks "shall I CANCEL …?" — a "yes, cancel it" is a yes there."""
        return False

    def stage_hint(self, stage: str) -> dict[str, Any]:
        """Transport hints for a stage, e.g. ``{"long_answer": True}`` for addresses."""
        return {}

    # ---- writing the result -----------------------------------------------------
    def commit_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        return None

    def on_commit_failed(self, result: CommitResult, slots: dict[str, Any], ctx: CallContext) -> Instruction | None:
        return None

    def fallback_action(self, slots: dict[str, Any], ctx: CallContext) -> CommitAction | None:
        """What to keep when the call ends before a commit (e.g. a partial lead)."""
        return None

    def terminals(self) -> list[Terminal]:
        return []

    # ---- scripted lines --------------------------------------------------
    def greeting(self, ctx: CallContext, language: str) -> str:
        custom = str(ctx.merchant_value("custom_greeting", "") or "").strip()
        if custom:
            return custom
        return phrase("greeting", language, business_name=ctx.merchant_value("business_name", ""))

    def inbound_greeting(self, ctx: CallContext, language: str) -> str:
        """Greeting of a call / chat the customer started."""
        custom = str(ctx.merchant_value("custom_greeting", "") or "").strip()
        if custom:
            return custom
        key = "greeting_chat" if ctx.chat else "greeting_inbound"
        return phrase(key, language, business_name=ctx.merchant_value("business_name", ""))

    def opening_question(self, ctx: CallContext, language: str) -> str:
        return phrase("opening_question", language, customer_name=self.person_name(ctx))

    def opening(self, ctx: CallContext, language: str) -> str:
        """Greeting + first question, spoken as ONE unit the instant the call connects."""
        return " ".join(part for part in (self.greeting(ctx, language), self.opening_question(ctx, language)) if part)

    def closing_line(self, outcome: str, slots: dict[str, Any], ctx: CallContext, language: str) -> str:
        key = OUTCOME_CLOSING_KEY.get(outcome, "closing_unclear")
        return phrase(
            key,
            language,
            customer_name=self.person_name(ctx),
            business_name=ctx.merchant_value("business_name", ""),
        )

    def reask_line(self, attempt: int, language: str) -> str:
        return phrase("decision_reask_2" if attempt >= 2 else "decision_reask_1", language)

    def prefetch_lines(self, ctx: CallContext, language: str) -> list[str]:
        """Every deterministic line a call may speak, for cache warming."""
        lines = [self.opening(ctx, language)]
        if self.identity_gate:
            name = self.person_name(ctx)
            business = ctx.merchant_value("business_name", "")
            lines += [
                phrase("identity_reask", language, customer_name=name),
                self.knows_person_line(ctx, language),
                phrase("relay_line", language, customer_name=name, business_name=business),
                phrase("wrong_number_line", language),
            ]
        lines += [
            phrase("closing_unclear", language),
            phrase("closing_callback", language),
            phrase("closing_transfer", language),
            phrase("closing_transfer_callback", language),
            phrase("closing_dropped", language),
            phrase("closing_timeout", language),
            phrase("still_there", language),
            phrase("recovery", language),
            phrase("ack", language),
        ]
        return [line for line in lines if line]

    def preview_steps(self, ctx: CallContext, language: str) -> list[str]:
        return []

    # ---- prompt parts -------------------------------------------------------------
    def rules(self, language: str) -> str:
        """Static rules for this flow (part of the cached prompt prefix)."""
        return ""

    def business_facts(self, ctx: CallContext, language: str) -> list[str]:
        """Facts that change per business, not per call (catalog, policies)."""
        return []

    def call_facts(self, ctx: CallContext, language: str) -> list[str]:
        """Facts of this one call (record, caller)."""
        return []

    def transcription_hints(self, ctx: CallContext) -> list[str]:
        """Proper nouns the transcriber should spell the business's way."""
        return [str(ctx.merchant_value("business_name", ""))]


__all__ = [
    "MAX_REASKS",
    "OUTCOMES",
    "OUTCOME_STATUS",
    "UNANSWERED_OUTCOMES",
    "CommitAction",
    "CommitResult",
    "Flow",
    "Instruction",
    "Terminal",
]
