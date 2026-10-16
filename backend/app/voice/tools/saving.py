"""``save_details``: vet what the model extracted against the caller's words, then save it."""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.flows import hearing
from app.flows.base import MAX_REASKS, STAGE_COMMIT, STAGE_KNOWS_PERSON, STAGE_RELAY, STAGE_WRONG_NUMBER
from app.flows.context import DIRECTION_INBOUND
from app.flows.steps import STAGE_CONFIRM
from app.pipeline.followup import AFTER, LAST
from app.skills.base import DECLINED, REFUSED
from app.verticals.common import NOTICE
from app.voice.languages import phrase
from app.voice.tools.store import ToolResult
from app.voice.tools.text import REPLY_FIELD, _join, answer_only

logger = structlog.get_logger(__name__)

#: A reply that quotes an amount ("that's $25.50", "30 dollars").
_MONEY_RE = re.compile(r"[$€£]\s?\d|\b\d+(?:[.,]\d+)?\s*(?:dollars?|euros?|pounds?|cents?)\b", re.IGNORECASE)
#: Notices that say a requested day/time can't be had (the backend's word is final on these).
SCHEDULING_NOTICES = frozenset({
    "closed_day", "closed_day_doctor", "closed_day_person", "closed_day_resource", "day_full", "day_full_none",
    "date_past", "date_too_far", "date_unclear", "pref_moved", "window_moved", "slot_taken", "ready_moved",
})
#: Slots holding a person's name, and words models put there when they have none.
NAME_SLOTS = frozenset({"customer_name", "patient_name", "caller_name", "owner_name"})
_PLACEHOLDER_NAMES = frozenset({
    "caller", "customer", "client", "patient", "owner", "user", "guest", "unknown", "anonymous", "n/a", "na", "none",
    "not given", "not provided", "declined", "no name", "the caller", "the customer", "me", "you", "sir", "madam",
    "new patient", "existing patient", "new customer", "new client", "returning patient", "first time", "patient name",
    "customer name", "new caller",
})


def _placeholder_name(value: object) -> bool:
    return " ".join(str(value or "").split()).strip(" .").casefold() in _PLACEHOLDER_NAMES


class SavingMixin:
    async def _save_details(self, fields: dict[str, Any], caller_text: str) -> ToolResult:
        if self.outcome and self.closing_spoken:
            return ToolResult(payload={"ok": True, "outcome": self.outcome, "instruction": "Say nothing."}, stop=True)
        reply = answer_only(" ".join(str(fields.pop(REPLY_FIELD, "") or "").split()))
        asked_stage = self.runtime.stage
        fields = self._new_request(fields, caller_text)
        if fields.get("intent") and caller_text and (hearing.is_greeting_check(caller_text) or hearing.just_asking(caller_text)):
            # "Hello, is this the pizza place?" / "just looking for pricing" — a question is not a request to book.
            fields.pop("intent")
        if fields.get("message") and caller_text and ("repeat" in hearing.classify(caller_text) or len(hearing.tokens(caller_text)) < 2):
            fields.pop("message")  # "what?" is not a message for the team
        fields = {key: value for key, value in fields.items() if not (key in NAME_SLOTS and _placeholder_name(value))}
        rejected: list[str] = []
        if self.flow.direction != DIRECTION_INBOUND and hearing.supports(caller_text, "later"):
            # "I'm driving, call me back this evening" wins over anything the model saved from the same turn.
            return await self._settle_later()
        if self.flow.identity_gate:
            fields, rejected = self._vet_identity(fields, caller_text)
        fields, gate_rejected, later = self._vet_gated(fields, caller_text)
        if later:
            return await self._settle_later()
        fields = self._snap_dates(fields, caller_text)
        date_keys = [key for key in getattr(self.flow, "date_slots", ()) if key in (self.flow.stage_slots.get(asked_stage) or ())]
        if date_keys and not fields.get(date_keys[0]) and hearing.wants_earliest(caller_text):
            fields[date_keys[0]] = "earliest"  # the schedule step turns it into the first open day
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
        if not result.get("saved") and stage == asked_stage and hearing.declines_detail(caller_text) and stage in self.flow.stage_slots:
            # Still on the question they refused (an optional one may already have moved on by itself).
            return await self._declined(stage, reply)
        changed = [key for key in result.get("saved", []) if key not in ("confirmed", "note")]
        if gate_rejected and not changed:
            self.runtime.reasks += 1
            if self.runtime.reasks > MAX_REASKS:
                return await self._settle_unclear()
            line = self.flow.reask_line(self.runtime.reasks, self.language)
            return self._speak_next(result, _join(reply, line))
        instruction = self.runtime.last_instruction
        if (self.runtime.slots.get(NOTICE) or {}).get("code") in SCHEDULING_NOTICES:
            reply = ""  # the system explains why that time isn't possible — the model's "that's available" must not precede it
        if stage == STAGE_CONFIRM and _MONEY_RE.search(reply):
            reply = ""  # the read-back states the exact amounts; the model's own sum must not precede it
        if instruction is not None and instruction.verbatim and not instruction.end_call:
            line = instruction.text
            if stage == STAGE_CONFIRM and self._spoken_stage == STAGE_CONFIRM and not result.get("saved") and reply:
                if self.runtime.slots.get(NOTICE):
                    # They asked again for what isn't available: the read-back with its notice says why, not "noted".
                    reply = ""
                else:
                    # The caller asked something at the read-back: answer, then just re-ask.
                    line = phrase("confirm_reprompt", self.language)
            if self._stuck_on(line, caller_text):
                # The same question a third time in a row: we're going in circles — hand it to a person.
                await logger.awarning("flow_stuck", flow=self.flow.key, stage=stage)
                return await self._settle_unclear(note="stuck")
            return self._speak_next(result, _join(reply, line), stage=stage)
        return ToolResult(payload=result)

    def _new_request(self, fields: dict[str, Any], caller_text: str) -> dict[str, Any]:
        """After "anything else?": "and a second visit for my husband" starts a new request of the same kind."""
        slots = self.runtime.slots
        last_intent = ((slots.get(LAST) or {}).get("slots") or {}).get("intent")
        if slots.get(AFTER) and not slots.get("intent") and fields.get("intent") == last_intent and hearing.wants_change(caller_text) and not hearing.wants_another(caller_text):
            # "Move it to Thursday" is a change to what was just booked, whatever the model called it.
            return {key: value for key, value in fields.items() if key != "intent"}
        if not slots.get(AFTER) or slots.get("intent") or fields.get("intent") or not hearing.wants_another(caller_text):
            return fields
        intent = ((slots.get(LAST) or {}).get("slots") or {}).get("intent")
        fields = {**fields, "intent": intent} if intent else dict(fields)
        other = hearing.named_other(caller_text)
        person = next((key for key in NAME_SLOTS if key in self.flow.slot_properties()), "")
        if other and person and not fields.get(person):
            fields[person] = other  # the new request is for them, not the caller
        return fields

    async def declined(self, stage: str) -> ToolResult:
        """The caller refused the current step's detail (called by the agent's fast path)."""
        return await self._declined(stage, "")

    async def _declined(self, stage: str, reply: str) -> ToolResult:
        """The caller won't give this detail: explain once, then go on without it (never ask a third time)."""
        slots = self.runtime.slots
        refused = {**(slots.get(REFUSED) or {}), stage: int((slots.get(REFUSED) or {}).get(stage, 0)) + 1}
        slots[REFUSED] = refused
        if refused[stage] == 1 and stage in NAME_SLOTS:
            # Only a name is worth one explanation; anything else is skipped at the first "rather not".
            line = _join(phrase("detail_why", self.language), self.runtime.current_instruction().text)
            return self._speak_next({"ok": True, "saved": [], "declined": stage}, line, stage=stage)
        slots[DECLINED] = sorted({*(slots.get(DECLINED) or ()), stage})
        payload = self.runtime.advance()
        if self.runtime.stage == STAGE_COMMIT and not self.outcome:
            return await self._commit(reply)
        instruction = self.runtime.last_instruction
        question = instruction.text if instruction is not None and instruction.verbatim and not instruction.end_call else ""
        return self._speak_next(payload, _join(phrase("detail_skipped", self.language), question), stage=self.runtime.stage)

    def _stuck_on(self, line: str, caller_text: str = "") -> bool:
        if len(hearing.tokens(caller_text)) < 4 or hearing.is_greeting_check(caller_text) or "repeat" in hearing.classify(caller_text):
            return False  # "what?" / "hello?" / noise is not the caller going in circles
        recent = getattr(self, "_recent_lines", [])
        self._recent_lines = [*recent[-1:], line]
        return len(recent) == 2 and recent[0] == recent[1] == line

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
        # A bare "no" to "am I speaking with X?" only means "not me" — the caller
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
        when the model left out a day the caller clearly named ("Wednesday morning"), the
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
        # The yes/no the current step is asking for; a gated slot set at any other step without the
        # caller's words behind it is a model slip — dropped quietly, not answered with "yes or no?".
        asked = (getattr(self.flow, "yes_no_stages", None) or {}).get(self.runtime.stage)
        for key in gated:
            if cancelling and key == "confirmed":
                # "Yes, cancel it" answers "shall I cancel your appointment?" with a yes.
                backed = hearing.affirms_cancel(caller_text) if fields[key] else hearing.declines_cancel(caller_text)
            else:
                backed = hearing.supports(caller_text, "confirm" if fields[key] else "cancel", identity=bool(self.flow.identity_gate))
            if not backed:
                fields.pop(key)
                if key == asked:
                    rejected.append(key)
        return fields, rejected, False

