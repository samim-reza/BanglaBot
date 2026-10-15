"""``save_details``: vet what the model extracted against the caller's words, then save it."""

from __future__ import annotations

from typing import Any

import structlog

from app.flows import hearing
from app.flows.base import MAX_REASKS, STAGE_COMMIT, STAGE_KNOWS_PERSON, STAGE_RELAY, STAGE_WRONG_NUMBER
from app.flows.steps import STAGE_CONFIRM
from app.voice.languages import phrase
from app.voice.tools.store import ToolResult
from app.voice.tools.text import REPLY_FIELD, _join, answer_only

logger = structlog.get_logger(__name__)


class SavingMixin:
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
        # The yes/no the current step is asking for; a gated slot set at any other step without the
        # caller's words behind it is a model slip — dropped quietly, not answered with "yes or no?".
        asked = (getattr(self.flow, "yes_no_stages", None) or {}).get(self.runtime.stage)
        for key in gated:
            if cancelling and key == "confirmed":
                # "Yes, cancel it" answers "shall I cancel your appointment?" with a yes.
                backed = hearing.affirms_cancel(caller_text) if fields[key] else hearing.declines_cancel(caller_text)
            else:
                backed = hearing.supports(caller_text, "confirm" if fields[key] else "cancel")
            if not backed:
                fields.pop(key)
                if key == asked:
                    rejected.append(key)
        return fields, rejected, False

