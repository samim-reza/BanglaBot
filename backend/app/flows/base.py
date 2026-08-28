"""Slot-derived conversation flow: the contract every call flow implements.

The idea in one paragraph: the *current node* is never stored. On every tool
call the backend looks at the slots collected so far and asks "what is the
next thing the customer still owes us?" — that stage is the node. Skipping a
question the caller already answered (volunteered early, or pre-filled from
the order) is simply the absence of a return further down the cascade, and a
correction can never leave a stale pointer behind.

The backend also owns the *wording* of the next question: every tool result
carries an ``instruction`` the model must follow, and a node change appends a
short directive to the tail of the conversation instead of rewriting the
system prompt (which keeps the prompt head cacheable).

Everything here is plain Python over duck-typed ``order`` / ``merchant``
objects (ORM rows in production, small dataclasses in tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.voice.languages import normalize_language, phrase

# --- Stages: the finest-grained "what is still missing" answers ------------
STAGE_IDENTITY = "identity"
STAGE_KNOWS_PERSON = "knows_person"
STAGE_RELAY = "relay"
STAGE_WRONG_NUMBER = "wrong_number"
STAGE_ADDRESS = "address"
STAGE_NEW_ADDRESS = "new_address"
STAGE_DECISION = "decision"
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
#: The callee rejected / was busy and the carrier forwarded the call (voicemail,
#: divert service). Nobody we should talk to answered.
OUTCOME_DIVERTED = "diverted"
#: Twilio's answering-machine detection heard a machine.
OUTCOME_VOICEMAIL = "voicemail"

#: Order status each outcome settles the order to.
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
}

#: Outcomes that mean the customer never actually took the call — the order
#: goes back to ``no_answer`` and stays callable.
UNANSWERED_OUTCOMES = frozenset({OUTCOME_AUTO_DROPPED, OUTCOME_DIVERTED, OUTCOME_VOICEMAIL})

#: Phrase key of the closing line spoken for each outcome.
OUTCOME_CLOSING_KEY: dict[str, str] = {
    OUTCOME_CONFIRMED: "closing_confirmed",
    OUTCOME_CANCELLED: "closing_cancelled",
    OUTCOME_TRANSFER: "closing_transfer",
    OUTCOME_WRONG_NUMBER: "wrong_number_line",
    OUTCOME_RELAY: "relay_line",
    OUTCOME_UNCLEAR: "closing_unclear",
    OUTCOME_AUTO_DROPPED: "closing_dropped",
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
    #: Note appended to the order, ``{arg}`` placeholders filled from arguments.
    note_template: dict[str, str] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return OUTCOME_STATUS[self.outcome]


@dataclass(frozen=True)
class Instruction:
    """What the model should do next, as decided by the backend."""

    stage: str
    text: str
    #: ``True`` — say ``text`` word for word; ``False`` — ``text`` is guidance.
    verbatim: bool = False
    #: After saying it, call ``end_call`` (relay / wrong number).
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


def _get(obj: Any, name: str, default: Any = None) -> Any:
    value = getattr(obj, name, None) if obj is not None else None
    return default if value in (None, "") else value


class Flow:
    """One vertical's conversation. Subclasses fill in the stage cascade."""

    key: str = ""

    # ---- slots ---------------------------------------------------------
    def slot_properties(self) -> dict[str, Any]:
        """JSON-schema properties of the ``save_details`` tool."""
        return {
            "identity_confirmed": {
                "type": "boolean",
                "description": (
                    "true when the person on the line says they ARE the named customer; "
                    "false when they say they are someone else (family, colleague, friend)."
                ),
            },
            "knows_customer": {
                "type": "boolean",
                "description": (
                    "Only when identity_confirmed is false: true if they know the named customer "
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
            "note": {
                "type": "string",
                "description": "Anything important the customer asked us to pass on (short, in their words).",
            },
        }

    def initial_slots(self, order: Any, merchant: Any) -> dict[str, Any]:
        return {}

    # ---- the cascade ----------------------------------------------------
    def identity_stage(self, slots: dict[str, Any]) -> str | None:
        """Next identity-gate stage, or ``None`` once the named person is on the line.

        Named person → carry on. Someone else → ask whether they know the
        customer. They do → leave a relay message. They don't / wrong number →
        apologise and hang up. Nobody but the named customer may confirm.
        """
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

    def next_stage(self, slots: dict[str, Any], order: Any, merchant: Any) -> str:
        raise NotImplementedError

    def node_for_stage(self, stage: str) -> str:
        return {
            STAGE_IDENTITY: NODE_IDENTITY,
            STAGE_KNOWS_PERSON: NODE_KNOWS_PERSON,
            STAGE_RELAY: NODE_WRAP_UP,
            STAGE_WRONG_NUMBER: NODE_WRAP_UP,
            STAGE_ADDRESS: NODE_ADDRESS,
            STAGE_NEW_ADDRESS: NODE_ADDRESS,
            STAGE_DECISION: NODE_DECISION,
            STAGE_DONE: NODE_WRAP_UP,
        }.get(stage, NODE_WRAP_UP)

    # ---- scripted lines --------------------------------------------------
    def greeting(self, merchant: Any, language: str) -> str:
        custom = str(_get(merchant, "custom_greeting", "") or "").strip()
        if custom:
            return custom
        return phrase("greeting", language, business_name=_get(merchant, "business_name", ""))

    def opening_question(self, order: Any, language: str) -> str:
        return phrase("opening_question", language, customer_name=_get(order, "customer_name", ""))

    def closing_line(self, outcome: str, order: Any, merchant: Any, language: str) -> str:
        key = OUTCOME_CLOSING_KEY.get(outcome, "closing_unclear")
        return phrase(
            key,
            language,
            customer_name=_get(order, "customer_name", ""),
            business_name=_get(merchant, "business_name", ""),
        )

    def reask_line(self, attempt: int, language: str) -> str:
        return phrase("decision_reask_2" if attempt >= 2 else "decision_reask_1", language)

    def identity_instruction(self, stage: str, order: Any, merchant: Any, language: str) -> Instruction | None:
        name = _get(order, "customer_name", "")
        business = _get(merchant, "business_name", "")
        if stage == STAGE_IDENTITY:
            return Instruction(stage, phrase("identity_reask", language, customer_name=name), verbatim=True)
        if stage == STAGE_KNOWS_PERSON:
            return Instruction(stage, phrase("knows_person_question", language, customer_name=name), verbatim=True)
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

    def instruction(self, stage: str, slots: dict[str, Any], order: Any, merchant: Any, language: str) -> Instruction:
        raise NotImplementedError

    def node_directive(self, node: str, order: Any, merchant: Any, language: str) -> str:
        raise NotImplementedError

    def terminals(self) -> list[Terminal]:
        raise NotImplementedError

    def prefetch_lines(self, order: Any, merchant: Any, language: str) -> list[str]:
        """Every deterministic line a call may speak, for cache warming."""
        raise NotImplementedError

    def preview_steps(self, merchant: Any, language: str) -> list[str]:
        raise NotImplementedError
