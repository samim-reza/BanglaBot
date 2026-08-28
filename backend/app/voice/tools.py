"""The tools the model may call during a confirmation call, and what they do.

* ``save_details``      → runtime.save → ``{ok, saved, stage, instruction}``
* ``confirm_order`` /
  ``cancel_order``      → gated by :mod:`app.flows.hearing`: an outcome is
                          only committed when the caller's own words support
                          it; otherwise the backend re-asks (twice), then
                          settles as ``needs_review`` / ``unclear``.
* ``transfer_to_human`` → ``needs_review`` / ``transfer``; the bridge dials the
                          merchant's support line after the transfer line.
* ``end_call``          → settles relay / wrong number / "call me later", speaks
                          the matching closing line, then the bridge hangs up.

Persistence goes through a small ``CallStore`` so the bridge can be driven in
tests with a fake instead of a database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from app.flows import hearing
from app.flows.base import (
    MAX_REASKS,
    OUTCOME_AUTO_DROPPED,
    OUTCOME_DIVERTED,
    OUTCOME_RELAY,
    OUTCOME_STATUS,
    OUTCOME_TRANSFER,
    OUTCOME_UNCLEAR,
    OUTCOME_VOICEMAIL,
    OUTCOME_WRONG_NUMBER,
    STAGE_IDENTITY,
    STAGE_KNOWS_PERSON,
    STAGE_RELAY,
    STAGE_WRONG_NUMBER,
    Terminal,
)
from app.flows.runtime import FlowRuntime
from app.voice.languages import normalize_language, phrase

logger = structlog.get_logger(__name__)

SAVE_DETAILS = "save_details"
TRANSFER_TO_HUMAN = "transfer_to_human"
END_CALL = "end_call"


@dataclass
class ToolResult:
    #: JSON the model reads back as the tool message.
    payload: dict[str, Any]
    #: A line the bridge speaks verbatim right after the tool (bypasses the model).
    say: str = ""
    #: Hang up once ``say`` has played.
    hang_up: bool = False
    #: Dial this number once ``say`` has played (transfer).
    transfer_to: str = ""
    #: Do not call the model again in this turn.
    stop: bool = False
    #: Outcome committed by this call, if any.
    outcome: str = ""


class CallStore(Protocol):
    async def set_outcome(
        self, *, outcome: str, status: str, final_node: str, flow_data: dict[str, Any], note: str, language: str
    ) -> None: ...

    async def save_transcript(self, transcript: str, *, language: str, final_node: str) -> None: ...

    async def save_usage(self, **counters: int) -> None: ...


class NullCallStore:
    """Keeps every write in memory (tests, dry runs)."""

    def __init__(self) -> None:
        self.outcomes: list[dict[str, Any]] = []
        self.transcripts: list[dict[str, Any]] = []
        self.usage: list[dict[str, int]] = []

    async def set_outcome(self, **kwargs: Any) -> None:
        self.outcomes.append(kwargs)

    async def save_transcript(self, transcript: str, **kwargs: Any) -> None:
        self.transcripts.append({"transcript": transcript, **kwargs})

    async def save_usage(self, **counters: int) -> None:
        self.usage.append(dict(counters))


def _note(outcome: str, language: str, **fields: Any) -> str:
    lang = normalize_language(language)
    templates = {
        OUTCOME_RELAY: {
            "bn": "কলে অন্য কেউ ধরেছেন যিনি কাস্টমারকে চেনেন; তাঁকে জানাতে বলা হয়েছে।",
            "en": "Someone who knows the customer answered; asked them to pass the message on.",
        },
        OUTCOME_WRONG_NUMBER: {
            "bn": "ফোন ধরা ব্যক্তি জানিয়েছেন নম্বরটি ভুল / কাস্টমারকে চেনেন না।",
            "en": "The person who answered said this is the wrong number / does not know the customer.",
        },
        OUTCOME_TRANSFER: {
            "bn": "কাস্টমার প্রতিনিধির সাথে কথা বলতে চেয়েছেন।",
            "en": "Customer asked to speak with a team member.",
        },
        OUTCOME_DIVERTED: {
            "bn": "কাস্টমার কল ধরেননি / কেটে দিয়েছেন; অপারেটর কলটি অন্যত্র ফরোয়ার্ড করেছে। আবার কল করা যাবে।",
            "en": "The customer did not answer / rejected the call and the carrier forwarded it. The order can be called again.",
        },
        OUTCOME_VOICEMAIL: {
            "bn": "কলটি ভয়েসমেইলে গেছে; কথা না বলে কেটে দেওয়া হয়েছে। আবার কল করা যাবে।",
            "en": "The call went to voicemail; hung up without speaking. The order can be called again.",
        },
        OUTCOME_UNCLEAR: {
            "bn": "কাস্টমারের উত্তর স্পষ্ট ছিল না; ফলো-আপ দরকার।",
            "en": "The customer's answer was unclear; needs a follow-up.",
        },
        "later": {
            "bn": "কাস্টমার পরে কথা বলতে চেয়েছেন।",
            "en": "Customer asked to be called later.",
        },
        OUTCOME_AUTO_DROPPED: {
            "bn": "কাস্টমারের সাড়া পাওয়া যায়নি; কল ছেড়ে দেওয়া হয়েছে।",
            "en": "No response from the customer; the call was dropped.",
        },
    }
    text = templates.get(outcome, {}).get(lang) or templates.get(outcome, {}).get("en") or ""
    try:
        return text.format(**fields)
    except (KeyError, IndexError, ValueError):
        return text


class CallTools:
    def __init__(self, runtime: FlowRuntime, store: CallStore, *, support_phone: str = "") -> None:
        self.runtime = runtime
        self.store = store
        self.support_phone = str(support_phone or "").strip()
        self.flow = runtime.flow
        self._terminals: dict[str, Terminal] = {t.name: t for t in self.flow.terminals()}
        self.outcome: str = ""
        self.note_lines: list[str] = []
        self.closing_spoken: bool = False

    # ---- schemas -------------------------------------------------------------
    def schemas(self) -> list[dict[str, Any]]:
        def fn(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
            params: dict[str, Any] = {"type": "object", "properties": properties}
            if required:
                params["required"] = required
            return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}

        tools = [
            fn(
                SAVE_DETAILS,
                "Save what the customer just told you (identity, whether they know the customer, address answers, "
                "notes). Call it BEFORE replying. The result's 'instruction' is what to say next.",
                self.flow.slot_properties(),
            )
        ]
        for terminal in self._terminals.values():
            tools.append(fn(terminal.name, terminal.description, dict(terminal.properties)))
        tools.append(
            fn(
                TRANSFER_TO_HUMAN,
                "The customer wants to talk to a real person, or asks something you cannot answer "
                "(price negotiation, delivery date, return policy).",
                {"reason": {"type": "string", "description": "Why the transfer is needed, briefly."}},
            )
        )
        tools.append(
            fn(
                END_CALL,
                "End the call: after the instruction told you to, when the customer wants to be called later, "
                "or when nothing more can be done on this call. The system speaks the goodbye.",
                {"reason": {"type": "string", "description": "Short reason (e.g. relay, wrong number, call later)."}},
            )
        )
        return tools

    # ---- dispatch ---------------------------------------------------------------
    async def execute(self, name: str, arguments: Any, *, caller_text: str = "") -> ToolResult:
        args = self._parse_args(arguments)
        caller_text = str(caller_text or "")
        if name == SAVE_DETAILS:
            return await self._save_details(args, caller_text)
        if name in self._terminals:
            return await self._terminal(self._terminals[name], args, caller_text)
        if name == TRANSFER_TO_HUMAN:
            return await self._transfer(args)
        if name == END_CALL:
            return await self._end_call(args, caller_text)
        return ToolResult(payload={"ok": False, "error": f"unknown tool {name}"})

    @staticmethod
    def _parse_args(arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return dict(arguments)
        try:
            parsed = json.loads(arguments) if str(arguments or "").strip() else {}
        except json.JSONDecodeError:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}

    # ---- save_details ---------------------------------------------------------------
    async def _save_details(self, fields: dict[str, Any], caller_text: str) -> ToolResult:
        fields, rejected = self._vet_identity(fields, caller_text)
        result = self.runtime.save(fields)
        if rejected:
            result["rejected"] = rejected
            result["hint"] = (
                "The caller's words did not clearly support those identity fields; they were not saved. "
                "Follow the instruction to ask again."
            )
        if self.runtime.stage in (STAGE_RELAY, STAGE_WRONG_NUMBER) and not self.outcome:
            # Wrap-up reached: the backend speaks the closing line and hangs up
            # itself rather than trusting the model to call end_call afterwards.
            closing = await self._end_call({}, caller_text)
            closing.payload = {**result, **closing.payload}
            return closing
        return ToolResult(payload=result)

    def _vet_identity(self, fields: dict[str, Any], caller_text: str) -> tuple[dict[str, Any], list[str]]:
        """Identity denials and confirmations must be backed by the caller's own words."""
        fields = dict(fields)
        rejected: list[str] = []
        if not caller_text:
            return fields, rejected
        denial_keys = [
            key
            for key in ("identity_confirmed", "knows_customer", "wrong_person")
            if (key == "wrong_person" and fields.get(key) is True) or (key != "wrong_person" and fields.get(key) is False)
        ]
        if denial_keys:
            backed = hearing.denies_identity(caller_text) or hearing.supports(caller_text, "knows")
            if not backed:
                for key in denial_keys:
                    fields.pop(key, None)
                    rejected.append(key)
        # A bare "না" to "am I speaking with X?" only means "not me" — the caller
        # has not said they don't know X. "Wrong number" needs those words (or a
        # "no" to the knows-them question), otherwise the flow asks first.
        labels = hearing.classify(caller_text)
        explicit_wrong = "wrong_number" in labels or (self.runtime.stage == STAGE_KNOWS_PERSON and "no" in labels)
        if not explicit_wrong:
            for key in ("wrong_person", "knows_customer"):
                if (key == "wrong_person" and fields.get(key) is True) or (key == "knows_customer" and fields.get(key) is False):
                    fields.pop(key, None)
                    if key not in rejected:
                        rejected.append(key)
            if self.runtime.stage == STAGE_IDENTITY and "identity_confirmed" not in fields and hearing.denies_identity(caller_text):
                fields["identity_confirmed"] = False
        if fields.get("identity_confirmed") is True and (
            hearing.is_unusable(caller_text) or hearing.denies_identity(caller_text)
        ):
            fields.pop("identity_confirmed", None)
            rejected.append("identity_confirmed")
        return fields, rejected

    # ---- terminals ----------------------------------------------------------------------
    async def _terminal(self, terminal: Terminal, args: dict[str, Any], caller_text: str) -> ToolResult:
        if self.outcome:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        language = self.runtime.language
        if self.runtime.stage in (STAGE_RELAY, STAGE_WRONG_NUMBER) or self.runtime.slots.get("identity_confirmed") is not True:
            # Only the named customer decides; anyone else goes through end_call.
            instruction = self.runtime.current_instruction().for_model(language)
            return ToolResult(
                payload={"ok": False, "reason": "identity_not_confirmed", "instruction": instruction},
            )
        if hearing.supports(caller_text, "later"):
            return await self._settle_later(language)
        if not hearing.supports(caller_text, terminal.outcome):
            self.runtime.reasks += 1
            if self.runtime.reasks <= MAX_REASKS:
                line = self.flow.reask_line(self.runtime.reasks, language)
                return ToolResult(
                    payload={"ok": False, "reason": "answer_unclear", "reasked": self.runtime.reasks, "instruction": f"(said) {line}"},
                    say=line,
                    stop=True,
                )
            note = _note(OUTCOME_UNCLEAR, language)
            await self._set_outcome(OUTCOME_UNCLEAR, note)
            self.closing_spoken = True
            return ToolResult(
                payload={"ok": True, "outcome": OUTCOME_UNCLEAR, "instruction": "Say nothing."},
                say=self.flow.closing_line(OUTCOME_UNCLEAR, self.runtime.order, self.runtime.merchant, language),
                hang_up=True,
                stop=True,
                outcome=OUTCOME_UNCLEAR,
            )
        note = ""
        template = terminal.note_template.get(normalize_language(language)) or terminal.note_template.get("en") or ""
        if template:
            try:
                note = template.format(**{key: str(args.get(key) or "") for key in terminal.properties})
            except (KeyError, IndexError, ValueError):
                note = template
        self.runtime.mark_decided(terminal.outcome)
        await self._set_outcome(terminal.outcome, note)
        if not self.runtime.done:
            # Confirmed, but the merchant wants the address checked: the backend
            # asks it right away and the closing line waits for end_call.
            instruction = self.runtime.current_instruction()
            return ToolResult(
                payload={"ok": True, "outcome": terminal.outcome, "stage": self.runtime.stage, "instruction": instruction.for_model(language)},
                say=instruction.text if instruction.verbatim else "",
                stop=bool(instruction.verbatim),
                outcome=terminal.outcome,
            )
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": terminal.outcome, "instruction": "Say nothing."},
            say=self.flow.closing_line(terminal.outcome, self.runtime.order, self.runtime.merchant, language),
            hang_up=True,
            stop=True,
            outcome=terminal.outcome,
        )

    async def closing_result(self) -> ToolResult:
        """The closing line for an outcome that was recorded earlier (address step done).

        Re-persists the outcome so what the address step collected (address_correct,
        new_address) reaches the order's flow_data."""
        language = self.runtime.language
        self.closing_spoken = True
        await self._set_outcome(self.outcome, "")
        return ToolResult(
            payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
            say=self.flow.closing_line(self.outcome, self.runtime.order, self.runtime.merchant, language),
            hang_up=True,
            stop=True,
            outcome=self.outcome,
        )

    async def _settle_later(self, language: str) -> ToolResult:
        await self._set_outcome(OUTCOME_UNCLEAR, _note("later", language))
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": OUTCOME_UNCLEAR, "instruction": "Say nothing."},
            say=phrase("closing_callback", language),
            hang_up=True,
            stop=True,
            outcome=OUTCOME_UNCLEAR,
        )

    # ---- transfer --------------------------------------------------------------------------
    async def _transfer(self, args: dict[str, Any]) -> ToolResult:
        language = self.runtime.language
        if self.outcome:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        note = _note(OUTCOME_TRANSFER, language)
        reason = str(args.get("reason") or "").strip()
        if reason:
            note = f"{note} ({reason})"
        await self._set_outcome(OUTCOME_TRANSFER, note)
        if self.support_phone:
            return ToolResult(
                payload={"ok": True, "outcome": OUTCOME_TRANSFER, "instruction": "Say nothing."},
                say=phrase("closing_transfer", language),
                transfer_to=self.support_phone,
                stop=True,
                outcome=OUTCOME_TRANSFER,
            )
        return ToolResult(
            payload={"ok": True, "outcome": OUTCOME_TRANSFER, "instruction": "Say nothing."},
            say=phrase("closing_transfer_callback", language),
            hang_up=True,
            stop=True,
            outcome=OUTCOME_TRANSFER,
        )

    # ---- end_call ------------------------------------------------------------------------------
    async def _end_call(self, args: dict[str, Any], caller_text: str) -> ToolResult:
        language = self.runtime.language
        if self.outcome:
            if not self.closing_spoken:
                # Outcome recorded before the address step; say goodbye now.
                return await self.closing_result()
            # A terminal already spoke its closing; the bridge is hanging up.
            return ToolResult(payload={"ok": True, "outcome": self.outcome}, hang_up=True, stop=True, outcome=self.outcome)
        stage = self.runtime.stage
        if stage == STAGE_RELAY:
            outcome, say = OUTCOME_RELAY, self.flow.closing_line(OUTCOME_RELAY, self.runtime.order, self.runtime.merchant, language)
            note = _note(OUTCOME_RELAY, language)
        elif stage == STAGE_WRONG_NUMBER:
            outcome, say = OUTCOME_WRONG_NUMBER, self.flow.closing_line(OUTCOME_WRONG_NUMBER, self.runtime.order, self.runtime.merchant, language)
            note = _note(OUTCOME_WRONG_NUMBER, language)
        elif hearing.supports(caller_text, "later") or "later" in str(args.get("reason") or "").lower():
            outcome, say = OUTCOME_UNCLEAR, phrase("closing_callback", language)
            note = _note("later", language)
        else:
            outcome, say = OUTCOME_UNCLEAR, self.flow.closing_line(OUTCOME_UNCLEAR, self.runtime.order, self.runtime.merchant, language)
            note = _note(OUTCOME_UNCLEAR, language)
            reason = str(args.get("reason") or "").strip()
            if reason:
                note = f"{note} ({reason})"
        await self._set_outcome(outcome, note)
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": outcome, "instruction": "Say nothing."},
            say=say,
            hang_up=True,
            stop=True,
            outcome=outcome,
        )

    # ---- silence / timeout (called by the bridge, not the model) ---------------------------------
    async def abandon(self, outcome: str, *, note: str = "") -> None:
        """Record an outcome for a call nobody we should talk to answered (divert / voicemail)."""
        if not self.outcome:
            await self._set_outcome(outcome, note or _note(outcome, self.runtime.language))

    async def settle(self, outcome: str, *, note: str = "") -> str:
        """Commit a bridge-decided outcome (auto-dropped, timeout). Returns the closing line."""
        language = self.runtime.language
        if not self.outcome:
            await self._set_outcome(outcome, note or _note(outcome, language))
        if outcome == OUTCOME_AUTO_DROPPED:
            return phrase("closing_dropped", language)
        return phrase("closing_timeout", language)

    # ---- persistence ------------------------------------------------------------------------------
    async def _set_outcome(self, outcome: str, note: str) -> None:
        self.outcome = outcome
        self.runtime.outcome = outcome
        if note:
            self.note_lines.append(note)
        try:
            await self.store.set_outcome(
                outcome=outcome,
                status=OUTCOME_STATUS.get(outcome, "needs_review"),
                final_node=self.runtime.current_node,
                flow_data=self.runtime.flow_data(),
                note=note,
                language=self.runtime.language,
            )
        except Exception as exc:  # noqa: BLE001 — the line must never go dead over a DB hiccup
            await logger.awarning("call_outcome_persist_failed", outcome=outcome, error=str(exc))
