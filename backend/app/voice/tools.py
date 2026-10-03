"""The tools the model may call during a call, and what they do.

* ``save_details``      → validated by the flow, stored in the runtime. When the
                          next line is backend-owned (verbatim) the tool result
                          carries it as ``say`` and the turn ends — the model's
                          optional ``reply`` (an answer to a side question) is
                          spoken first. One model round-trip per caller turn.
                          Reaching the *commit* stage writes the result through
                          the store (booking with a capacity re-check, record
                          update) and speaks the closing line.
* terminals             → flow-specific call-ending tools (``confirm_order``,
                          ``report_emergency``, …), gated by :mod:`app.flows.hearing`:
                          an outcome is only committed when the caller's own
                          words support it; otherwise the backend re-asks
                          (twice), then settles as ``needs_review`` / ``unclear``.
* ``transfer_to_human`` → ``needs_review`` / ``transfer``; the bridge dials the
                          business's support line after the transfer line.
* ``end_call``          → settles relay / wrong number / "call me later" /
                          inquiry, speaks the matching closing line, hangs up.

Persistence goes through a small ``CallStore`` so calls can be driven in tests
(and the text simulator) without a database.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from app.flows import hearing
from app.flows.base import (
    MAX_REASKS,
    OUTCOME_AUTO_DROPPED,
    OUTCOME_DIVERTED,
    OUTCOME_EMERGENCY,
    OUTCOME_INQUIRY,
    OUTCOME_RELAY,
    OUTCOME_STATUS,
    OUTCOME_TRANSFER,
    OUTCOME_UNCLEAR,
    OUTCOME_VOICEMAIL,
    OUTCOME_WRONG_NUMBER,
    STAGE_COMMIT,
    STAGE_KNOWS_PERSON,
    STAGE_RELAY,
    STAGE_WRONG_NUMBER,
    CommitAction,
    CommitResult,
    Terminal,
)
from app.flows.context import DIRECTION_INBOUND
from app.flows.runtime import FlowRuntime
from app.flows.scheduling import slot_key
from app.flows.steps import STAGE_CONFIRM
from app.voice.languages import normalize_language, phrase

logger = structlog.get_logger(__name__)

SAVE_DETAILS = "save_details"
TRANSFER_TO_HUMAN = "transfer_to_human"
END_CALL = "end_call"
REPLY_FIELD = "reply"


@dataclass
class ToolResult:
    #: JSON the model reads back as the tool message.
    payload: dict[str, Any]
    #: A line the agent speaks verbatim right after the tool (bypasses the model).
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

    async def commit(self, action: CommitAction, *, final_node: str, flow_data: dict[str, Any], language: str) -> CommitResult: ...

    async def save_transcript(self, transcript: str, *, language: str, final_node: str) -> None: ...

    async def save_usage(self, **counters: int) -> None: ...


class NullCallStore:
    """Keeps every write in memory (tests, the text simulator, dry runs).

    ``taken`` is a set of :func:`slot_key` strings that already have a booking —
    a commit into one of them fails with ``slot_taken`` (the race the database
    lock guards against in production).
    """

    def __init__(self, *, taken: set[str] | None = None) -> None:
        self.outcomes: list[dict[str, Any]] = []
        self.commits: list[dict[str, Any]] = []
        self.transcripts: list[dict[str, Any]] = []
        self.usage: list[dict[str, int]] = []
        self.taken: set[str] = set(taken or ())

    async def set_outcome(self, **kwargs: Any) -> None:
        self.outcomes.append(kwargs)

    async def commit(self, action: CommitAction, **kwargs: Any) -> CommitResult:
        if action.capacity is not None:
            item_id, start, _capacity = action.capacity
            key = slot_key(item_id, start)
            if key in self.taken:
                self.taken.discard(key)
                return CommitResult(ok=False, reason="slot_taken")
        record_id = action.record_id or f"rec-{len(self.commits) + 1}"
        self.commits.append({"action": action, "record_id": record_id, **kwargs})
        self.outcomes.append({"outcome": action.outcome, "status": action.status, "note": action.note, **kwargs})
        return CommitResult(ok=True, record_id=record_id)

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
            "en": "The customer did not answer / rejected the call and the carrier forwarded it. They can be called again.",
        },
        OUTCOME_VOICEMAIL: {
            "bn": "কলটি ভয়েসমেইলে গেছে; কথা না বলে কেটে দেওয়া হয়েছে। আবার কল করা যাবে।",
            "en": "The call went to voicemail; hung up without speaking. They can be called again.",
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
        "commit_failed": {
            "bn": "বুকিং সেভ করা যায়নি (সিস্টেম সমস্যা); কাস্টমারকে ফোন করে নিশ্চিত করুন।",
            "en": "The booking could not be saved (system error); call the customer back to confirm.",
        },
    }
    text = templates.get(outcome, {}).get(lang) or templates.get(outcome, {}).get("en") or ""
    try:
        return text.format(**fields)
    except (KeyError, IndexError, ValueError):
        return text


def _join(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


_SENTENCE_RE = re.compile(r"[^.!?।]+[.!?।]?")


def answer_only(reply: str) -> str:
    """The model's ``reply`` minus any question: the system asks the next question
    itself, so a question in the reply would be asked twice."""
    sentences = [part.strip() for part in _SENTENCE_RE.findall(reply or "") if part.strip()]
    return " ".join(sentence for sentence in sentences if not sentence.endswith("?"))


class CallTools:
    def __init__(self, runtime: FlowRuntime, store: CallStore, *, support_phone: str = "") -> None:
        self.runtime = runtime
        self.store = store
        self.support_phone = str(support_phone or "").strip()
        self.flow = runtime.flow
        self._terminals: dict[str, Terminal] = {t.name: t for t in self.flow.terminals()}
        self.outcome: str = ""
        self.record_id: str = str(getattr(runtime.ctx.record, "id", "") or "")
        self.note_lines: list[str] = []
        self.closing_spoken: bool = False
        #: Stage whose backend line was spoken last (a repeated read-back is shortened).
        self._spoken_stage: str = ""

    # ---- schemas -------------------------------------------------------------
    def schemas(self) -> list[dict[str, Any]]:
        """Tool list for this flow. Deterministic and merchant-independent, so it
        stays byte-identical across calls (part of the cached prompt prefix)."""

        def fn(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
            params: dict[str, Any] = {"type": "object", "properties": properties}
            if required:
                params["required"] = required
            return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}

        slot_props = dict(self.flow.slot_properties())
        slot_props[REPLY_FIELD] = {
            "type": "string",
            "description": (
                "Optional: ONE short sentence answering something the caller asked in this turn, in the call's "
                "language. Never the next question (the system asks it), never a promise, and never mention a "
                "detail you did not save in this same call."
            ),
        }
        tools = [
            fn(
                SAVE_DETAILS,
                "Save what the caller just told you. Call it BEFORE replying whenever the caller gives any detail, "
                "with every detail from this turn in one call. If they also asked something, put your short answer "
                "in `reply`; the system then speaks your reply and the next question itself.",
                slot_props,
            )
        ]
        for terminal in self._terminals.values():
            tools.append(fn(terminal.name, terminal.description, dict(terminal.properties)))
        tools.append(
            fn(
                TRANSFER_TO_HUMAN,
                "The caller wants to talk to a real person, or needs something you cannot handle "
                "(negotiation, a complaint, anything not in the facts).",
                {"reason": {"type": "string", "description": "Why the transfer is needed, briefly."}},
            )
        )
        tools.append(
            fn(
                END_CALL,
                "End the call: the conversation is over, the caller wants to stop or to be called later, or the "
                "instruction says so. The system speaks the goodbye.",
                {"reason": {"type": "string", "description": "Short reason (e.g. done, call later, wrong number)."}},
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

    @property
    def language(self) -> str:
        return self.runtime.language

    # ---- save_details ---------------------------------------------------------------
    async def _save_details(self, fields: dict[str, Any], caller_text: str) -> ToolResult:
        if self.outcome and self.closing_spoken:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        reply = answer_only(" ".join(str(fields.pop(REPLY_FIELD, "") or "").split()))
        rejected: list[str] = []
        if self.flow.identity_gate:
            fields, rejected = self._vet_identity(fields, caller_text)
        fields, gate_rejected, later = self._vet_gated(fields, caller_text)
        if later:
            return await self._settle_later()
        fields = self._snap_dates(fields, caller_text)
        result = self.runtime.save(fields)
        rejected += gate_rejected
        if rejected:
            result["rejected"] = rejected
            result["hint"] = (
                "The caller's words did not clearly support those fields; they were not saved. "
                "The system asked again."
            )
        stage = self.runtime.stage
        if stage in (STAGE_RELAY, STAGE_WRONG_NUMBER) and not self.outcome:
            # Wrap-up reached: the backend speaks the closing line and hangs up
            # itself rather than trusting the model to call end_call afterwards.
            closing = await self._end_call({}, caller_text)
            closing.payload = {**result, **closing.payload}
            return closing
        if stage == STAGE_COMMIT and not self.outcome:
            return await self._commit(reply)
        if self.runtime.done and self.outcome and not self.closing_spoken:
            return await self.closing_result()
        if gate_rejected:
            self.runtime.reasks += 1
            if self.runtime.reasks > MAX_REASKS:
                return await self._settle_unclear()
            line = self.flow.reask_line(self.runtime.reasks, self.language)
            return self._speak_next(result, _join(reply, line))
        instruction = self.runtime.last_instruction
        if instruction is not None and instruction.verbatim and not instruction.end_call:
            line = instruction.text
            if stage == STAGE_CONFIRM and self._spoken_stage == STAGE_CONFIRM and not result.get("saved") and reply:
                # The caller asked something at the read-back: answer, then just re-ask.
                line = phrase("confirm_reprompt", self.language)
            return self._speak_next(result, _join(reply, line), stage=stage)
        return ToolResult(payload=result)

    def _speak_next(self, payload: dict[str, Any], line: str, *, stage: str = "") -> ToolResult:
        self._spoken_stage = stage
        payload = {**payload, "instruction": f"(Already said to the caller: \"{line}\") Wait for the caller's answer."}
        return ToolResult(payload=payload, say=line, stop=True)

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
            if self.runtime.stage == "identity" and "identity_confirmed" not in fields and hearing.denies_identity(caller_text):
                fields["identity_confirmed"] = False
        if fields.get("identity_confirmed") is True and (hearing.is_unusable(caller_text) or hearing.denies_identity(caller_text)):
            fields.pop("identity_confirmed", None)
            rejected.append("identity_confirmed")
        return fields, rejected

    def _snap_dates(self, fields: dict[str, Any], caller_text: str) -> dict[str, Any]:
        """Dates the caller named, checked against their own words.

        A bare weekday means the nearest one (see :func:`timefmt.snap_weekday`); and
        when the model left out a day the caller clearly named ("বুধবার সকালে"), the
        backend reads it from the words — on the step that asks for it, or when the
        caller gave several details at once."""
        from app.flows.timefmt import date_from_text, parse_date, snap_weekday

        if not caller_text:
            return fields
        known = self.flow.slot_properties()
        date_keys = [key for key in getattr(self.flow, "date_slots", ()) if key in known]
        if not date_keys:
            return fields
        fields = dict(fields)
        today = self.runtime.ctx.today
        for key in date_keys:
            if fields.get(key):
                day = parse_date(fields[key], today)
                if day is not None:
                    fields[key] = snap_weekday(day, caller_text, today).isoformat()
                continue
            if self.runtime.slots.get(key):
                continue
            expects = key in (getattr(self.flow, "stage_slots", {}).get(self.runtime.stage) or ())
            several = len([name for name in fields if name not in ("reply", "note")]) >= 1 and key == date_keys[0] and key == "date"
            if expects or several:
                day = date_from_text(caller_text, today)
                if day is not None:
                    fields[key] = day.isoformat()
        return fields

    def _vet_gated(self, fields: dict[str, Any], caller_text: str) -> tuple[dict[str, Any], list[str], bool]:
        """Yes/no slots that commit something need the caller's own yes/no.

        Returns the accepted fields, the rejected gated keys, and whether the
        caller actually asked to be called later instead.
        """
        gated = [key for key in self.flow.gated_slots if isinstance(fields.get(key), bool)]
        if not gated or not caller_text:
            return fields, [], False
        if hearing.supports(caller_text, "later"):
            return fields, [], True
        fields = dict(fields)
        rejected: list[str] = []
        cancelling = self.flow.confirms_cancellation(self.runtime.slots, self.runtime.ctx)
        for key in gated:
            if cancelling and key == "confirmed":
                # "Yes, cancel it" answers "shall I cancel your appointment?" with a yes.
                backed = hearing.affirms_cancel(caller_text) if fields[key] else hearing.declines_cancel(caller_text)
                if not backed:
                    fields.pop(key)
                    rejected.append(key)
                continue
            label = "confirm" if fields[key] else "cancel"
            if not hearing.supports(caller_text, label):
                fields.pop(key)
                rejected.append(key)
        return fields, rejected, False

    # ---- commit ---------------------------------------------------------------------------
    async def _commit(self, reply: str = "") -> ToolResult:
        language = self.language
        ctx = self.runtime.ctx
        action = self.flow.commit_action(self.runtime.slots, ctx)
        if action is None:
            await logger.awarning("commit_action_missing", flow=self.flow.key, slots=sorted(self.runtime.slots))
            return await self._settle_unclear(note=_note("commit_failed", language))
        try:
            result = await self.store.commit(
                action,
                final_node=self.runtime.current_node,
                flow_data=self.runtime.flow_data(),
                language=language,
            )
        except Exception as exc:  # noqa: BLE001 — the line must never go dead over a DB hiccup
            await logger.awarning("commit_failed", flow=self.flow.key, error=str(exc))
            result = CommitResult(ok=False, reason="error")
        if result.ok:
            if result.record_id:
                self.record_id = result.record_id
            self.outcome = action.outcome
            self.runtime.mark_decided(action.outcome)
            if action.note:
                self.note_lines.append(action.note)
            self.closing_spoken = True
            say = self.flow.closing_line(action.outcome, self.runtime.slots, ctx, language)
            say = self._with_sms_note(say, action)
            await logger.ainfo("flow_committed", flow=self.flow.key, outcome=action.outcome, record_id=result.record_id)
            return ToolResult(
                payload={"ok": True, "outcome": action.outcome, "instruction": "Say nothing."},
                say=say,
                hang_up=True,
                stop=True,
                outcome=action.outcome,
            )
        await logger.ainfo("flow_commit_refused", flow=self.flow.key, reason=result.reason)
        if result.reason != "slot_taken":
            return await self._settle_unclear(note=_note("commit_failed", language))
        override = self.flow.on_commit_failed(result, self.runtime.slots, ctx)
        payload = self.runtime.advance(override=override)
        instruction = self.runtime.last_instruction
        if instruction is not None and instruction.verbatim:
            return self._speak_next(payload, instruction.text, stage=self.runtime.stage)
        return ToolResult(payload=payload)

    # ---- terminals ----------------------------------------------------------------------
    async def _terminal(self, terminal: Terminal, args: dict[str, Any], caller_text: str) -> ToolResult:
        if self.outcome:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        language = self.language
        if terminal.requires_identity and self.flow.identity_gate and (
            self.runtime.stage in (STAGE_RELAY, STAGE_WRONG_NUMBER) or self.runtime.slots.get("identity_confirmed") is not True
        ):
            # Only the named person decides; anyone else goes through end_call.
            instruction = self.runtime.current_instruction().for_model(language)
            return ToolResult(payload={"ok": False, "reason": "identity_not_confirmed", "instruction": instruction})
        if terminal.gate:
            if hearing.supports(caller_text, "later"):
                return await self._settle_later()
            if not hearing.supports(caller_text, terminal.gate):
                self.runtime.reasks += 1
                if self.runtime.reasks <= MAX_REASKS:
                    line = self.flow.reask_line(self.runtime.reasks, language)
                    return ToolResult(
                        payload={"ok": False, "reason": "answer_unclear", "reasked": self.runtime.reasks, "instruction": f"(said) {line}"},
                        say=line,
                        stop=True,
                    )
                return await self._settle_unclear()
        note = ""
        template = terminal.note_template.get(normalize_language(language)) or terminal.note_template.get("en") or ""
        if template:
            try:
                note = template.format(**{key: str(args.get(key) or "") for key in terminal.properties})
            except (KeyError, IndexError, ValueError):
                note = template
        self.runtime.mark_decided(terminal.outcome)
        await self._set_outcome(terminal.outcome, note)
        if terminal.outcome == OUTCOME_EMERGENCY:
            self.closing_spoken = True
            line = self.flow.closing_line(OUTCOME_EMERGENCY, self.runtime.slots, self.runtime.ctx, language)
            if self.support_phone:
                return ToolResult(
                    payload={"ok": True, "outcome": OUTCOME_EMERGENCY, "instruction": "Say nothing."},
                    say=_join(line, phrase("closing_transfer", language)),
                    transfer_to=self.support_phone,
                    stop=True,
                    outcome=OUTCOME_EMERGENCY,
                )
            return ToolResult(
                payload={"ok": True, "outcome": OUTCOME_EMERGENCY, "instruction": "Say nothing."},
                say=line,
                hang_up=True,
                stop=True,
                outcome=OUTCOME_EMERGENCY,
            )
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
            say=self.flow.closing_line(terminal.outcome, self.runtime.slots, self.runtime.ctx, language),
            hang_up=True,
            stop=True,
            outcome=terminal.outcome,
        )

    def _with_sms_note(self, say: str, action: CommitAction) -> str:
        """Tell the caller a text is coming, just before the goodbye."""
        from app.services.sms_service import planned_kind

        ctx = self.runtime.ctx
        phone = str(action.fields.get("customer_phone") or ctx.record_value("customer_phone", "") or "")
        kind = str(action.fields.get("kind") or ctx.record_value("kind", "") or "")
        if not planned_kind(ctx.merchant, action.outcome, record_kind=kind, phone=phone):
            return say
        note = phrase("sms_follows", self.language)
        for marker in (" Thank you", " ধন্যবাদ"):
            index = say.rfind(marker)
            if index > 0:
                return f"{say[:index]} {note}{say[index:]}"
        return f"{say} {note}"

    async def closing_result(self) -> ToolResult:
        """The closing line for an outcome that was recorded earlier (address step done).

        Re-persists the outcome so what the address step collected (address_correct,
        new_address) reaches the record's flow_data."""
        language = self.language
        self.closing_spoken = True
        await self._set_outcome(self.outcome, "")
        return ToolResult(
            payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
            say=self.flow.closing_line(self.outcome, self.runtime.slots, self.runtime.ctx, language),
            hang_up=True,
            stop=True,
            outcome=self.outcome,
        )

    async def _settle_later(self) -> ToolResult:
        await self._set_outcome(OUTCOME_UNCLEAR, _note("later", self.language))
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": OUTCOME_UNCLEAR, "instruction": "Say nothing."},
            say=phrase("closing_callback", self.language),
            hang_up=True,
            stop=True,
            outcome=OUTCOME_UNCLEAR,
        )

    async def _settle_unclear(self, *, note: str = "") -> ToolResult:
        """Unclear after the re-asks (or a failed write): a person follows up.

        An inbound caller's partial details are kept as a lead when the flow can."""
        language = self.language
        kept = await self._keep_fallback(note=note or _note(OUTCOME_UNCLEAR, language))
        if not kept:
            await self._set_outcome(OUTCOME_UNCLEAR, note or _note(OUTCOME_UNCLEAR, language))
        self.closing_spoken = True
        return ToolResult(
            payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
            say=self.flow.closing_line(OUTCOME_UNCLEAR, self.runtime.slots, self.runtime.ctx, language),
            hang_up=True,
            stop=True,
            outcome=self.outcome,
        )

    async def _keep_fallback(self, *, note: str = "") -> bool:
        """Write the flow's fallback (e.g. a partial lead) for an inbound call that ends early."""
        if self.outcome or self.flow.direction != DIRECTION_INBOUND:
            return False
        action = self.flow.fallback_action(self.runtime.slots, self.runtime.ctx)
        if action is None:
            return False
        if note and not action.note:
            action.note = note
        try:
            result = await self.store.commit(
                action, final_node=self.runtime.current_node, flow_data=self.runtime.flow_data(), language=self.language
            )
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("fallback_commit_failed", flow=self.flow.key, error=str(exc))
            return False
        if not result.ok:
            return False
        self.record_id = result.record_id or self.record_id
        self.outcome = action.outcome
        self.runtime.outcome = action.outcome
        return True

    # ---- transfer --------------------------------------------------------------------------
    async def _transfer(self, args: dict[str, Any]) -> ToolResult:
        language = self.language
        if self.outcome:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        note = _note(OUTCOME_TRANSFER, language)
        reason = str(args.get("reason") or "").strip()
        if reason:
            note = f"{note} ({reason})"
        kept = await self._keep_fallback(note=note)
        if not kept:
            await self._set_outcome(OUTCOME_TRANSFER, note)
        self.closing_spoken = True
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
        language = self.language
        if self.outcome:
            if not self.closing_spoken:
                # Outcome recorded before the address step; say goodbye now.
                return await self.closing_result()
            # A terminal already spoke its closing; the agent is hanging up.
            return ToolResult(payload={"ok": True, "outcome": self.outcome}, hang_up=True, stop=True, outcome=self.outcome)
        stage = self.runtime.stage
        ctx = self.runtime.ctx
        reason = str(args.get("reason") or "").strip()
        if stage == STAGE_RELAY:
            outcome, say, note = OUTCOME_RELAY, self.flow.closing_line(OUTCOME_RELAY, self.runtime.slots, ctx, language), _note(OUTCOME_RELAY, language)
        elif stage == STAGE_WRONG_NUMBER:
            outcome, say, note = (
                OUTCOME_WRONG_NUMBER,
                self.flow.closing_line(OUTCOME_WRONG_NUMBER, self.runtime.slots, ctx, language),
                _note(OUTCOME_WRONG_NUMBER, language),
            )
        elif hearing.supports(caller_text, "later") or "later" in reason.lower():
            if await self._keep_fallback(note=_note("later", language)):
                self.closing_spoken = True
                return ToolResult(
                    payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
                    say=self.flow.closing_line(self.outcome, self.runtime.slots, ctx, language),
                    hang_up=True,
                    stop=True,
                    outcome=self.outcome,
                )
            outcome, say, note = OUTCOME_UNCLEAR, phrase("closing_callback", language), _note("later", language)
        elif self.flow.direction == DIRECTION_INBOUND:
            if await self._keep_fallback():
                self.closing_spoken = True
                return ToolResult(
                    payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."},
                    say=self.flow.closing_line(self.outcome, self.runtime.slots, ctx, language),
                    hang_up=True,
                    stop=True,
                    outcome=self.outcome,
                )
            # A caller who only asked questions: nothing to follow up.
            outcome, say, note = OUTCOME_INQUIRY, phrase("closing_inquiry", language), ""
        else:
            outcome, say = OUTCOME_UNCLEAR, self.flow.closing_line(OUTCOME_UNCLEAR, self.runtime.slots, ctx, language)
            note = _note(OUTCOME_UNCLEAR, language)
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

    # ---- silence / timeout (called by the agent, not the model) ---------------------------------
    async def abandon(self, outcome: str, *, note: str = "") -> None:
        """Record an outcome for a call nobody we should talk to answered (divert / voicemail)."""
        if not self.outcome:
            await self._set_outcome(outcome, note or _note(outcome, self.language))

    async def settle(self, outcome: str, *, note: str = "") -> str:
        """Commit an agent-decided outcome (auto-dropped, timeout). Returns the closing line."""
        language = self.language
        if not self.outcome:
            if not await self._keep_fallback(note=note or _note(outcome, language)):
                await self._set_outcome(outcome, note or _note(outcome, language))
        if outcome == OUTCOME_AUTO_DROPPED:
            return phrase("closing_dropped", language)
        return phrase("closing_timeout", language)

    async def finish_inbound(self) -> None:
        """An inbound call ended without an outcome (the caller hung up)."""
        if self.outcome:
            return
        if not await self._keep_fallback():
            await self._set_outcome(OUTCOME_INQUIRY, "")

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
                language=self.language,
            )
        except Exception as exc:  # noqa: BLE001 — the line must never go dead over a DB hiccup
            await logger.awarning("call_outcome_persist_failed", outcome=outcome, error=str(exc))


__all__ = ["END_CALL", "REPLY_FIELD", "SAVE_DETAILS", "TRANSFER_TO_HUMAN", "CallStore", "CallTools", "NullCallStore", "ToolResult"]
