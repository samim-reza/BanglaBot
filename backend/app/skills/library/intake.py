"""Details about the person: name plus the fields the owner switches on (and custom ones).

Each field is one stage (its slot key). A required field is asked until given;
an optional one is asked once — if the caller skips it, the call moves on.
Owners turn built-in fields on/off, make them required, reword the question,
and add up to 12 custom fields (text, number, date, phone, email, choice, yes/no).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.flows.base import Instruction
from app.flows.context import CallContext
from app.flows.steps import SlotSpec
from app.flows.timefmt import parse_date
from app.skills.base import DECLINED, BoundSkill, Skill, lang_pick, render
from app.verticals.base import FieldSpec, L
from app.verticals.reception import clean_phone

ASKED = "_asked"
MAX_CUSTOM = 12
CUSTOM_TYPES = ("text", "number", "date", "phone", "email", "choice", "bool")
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,18}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class IntakeField:
    key: str
    label: Mapping[str, str]
    question: Mapping[str, str]
    type: str = "text"
    on: bool = True
    required: bool = False
    hint: str = ""
    choices: tuple[str, ...] = ()
    long_answer: bool = False
    #: False = saved when the caller mentions it, never asked.
    ask: bool = True

    def schema(self) -> dict[str, Any]:
        if self.type == "number":
            return {"type": "number"}
        if self.type == "bool":
            return {"type": "boolean"}
        if self.type == "choice" and self.choices:
            return {"type": "string", "enum": list(self.choices)}
        return {"type": "string"}

    def description(self) -> str:
        label = lang_pick(self.label, "en")
        fmt = {"date": " as YYYY-MM-DD", "phone": ", digits only", "email": ", e.g. name@example.com"}.get(self.type, "")
        return f"{label}{fmt}.{(' ' + self.hint) if self.hint else ''}"


def custom_field(raw: Mapping[str, Any]) -> IntakeField | None:
    key = str(raw.get("key") or "").strip().lower()
    if not _KEY.match(key):
        return None
    kind = str(raw.get("type") or "text")
    label = str(raw.get("label") or key.replace("_", " ").capitalize())[:60]
    question = str(raw.get("question") or f"What is your {label.lower()}?")[:200]
    choices = tuple(str(c)[:40] for c in (raw.get("choices") or [])[:10] if str(c).strip()) if kind == "choice" else ()
    return IntakeField(
        key=f"f_{key}",
        label={"en": label},
        question={"en": question},
        type=kind if kind in CUSTOM_TYPES else "text",
        on=bool(raw.get("on", True)),
        required=bool(raw.get("required", False)),
        choices=choices,
    )


class IntakeSkill(Skill):
    key = "intake"
    label = L("Personal details")
    description = L("Name and the details you choose to collect.")
    options = (
        FieldSpec("fields", L("Fields to collect"), "fields", help=L("Switch fields on, make them required, reword the question.")),
        FieldSpec("custom", L("Custom fields"), "custom_fields", help=L("Up to 12 extra questions.")),
    )
    goal = "Get the caller's details for the booking."

    def __init__(self, fields: tuple[IntakeField, ...], **overrides: Any) -> None:
        super().__init__(**overrides)
        self.builtin = {f.key: f for f in fields}
        self.defaults = {
            "fields": [
                {"key": f.key, "on": f.on, "required": f.required, "ask": f.ask, "label": dict(f.label), "default_question": dict(f.question)}
                for f in fields
            ],
            "custom": [],
        }
        self.long_answer = frozenset(f.key for f in fields if f.long_answer)
        if "volunteerable" not in overrides:
            # Callers often say their name (or insurance) with the request: keep these fields in the
            # trimmed compact-prompt tool from the first turn so they are saved, not lost in a note.
            self.volunteerable = frozenset(f.key for f in fields if f.on)

    # ---- the account's field list ------------------------------------------------------------
    def fields(self, b: BoundSkill | None) -> list[IntakeField]:
        chosen: list[IntakeField] = []
        settings = {str(row.get("key")): row for row in (b.opt("fields", []) if b else []) if isinstance(row, Mapping)}
        for key, base in self.builtin.items():
            row = settings.get(key, {})
            on = bool(row.get("on", base.on))
            if not on:
                continue
            question = row.get("question")
            chosen.append(
                IntakeField(
                    key=base.key,
                    label=base.label,
                    question={"en": question} if isinstance(question, str) and question.strip() else base.question,
                    type=base.type,
                    on=True,
                    required=bool(row.get("required", base.required)),
                    hint=base.hint,
                    choices=base.choices,
                    long_answer=base.long_answer,
                    ask=bool(row.get("ask", base.ask)),
                )
            )
        for raw in (b.opt("custom", []) if b else [])[:MAX_CUSTOM]:
            extra = custom_field(raw) if isinstance(raw, Mapping) else None
            if extra is not None and extra.on:
                chosen.append(extra)
        return chosen

    def slot_specs(self, b: BoundSkill | None = None) -> tuple[SlotSpec, ...]:
        return tuple(SlotSpec(f.key, f.description(), f.schema()) for f in self.fields(b))

    def required(self, b: BoundSkill) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields(b) if f.required)

    def stages(self, b: BoundSkill) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields(b))

    def validate_options(self, options: Mapping[str, Any]) -> list[tuple[str, str]]:
        problems: list[tuple[str, str]] = []
        custom = options.get("custom") or []
        if not isinstance(custom, list) or len(custom) > MAX_CUSTOM:
            problems.append(("custom", f"at most {MAX_CUSTOM} custom fields"))
            return problems
        seen: set[str] = set()
        for index, raw in enumerate(custom):
            if not isinstance(raw, Mapping) or custom_field(raw) is None:
                problems.append((f"custom.{index}", "key must be 2–19 lowercase letters, digits or _"))
                continue
            key = str(raw["key"]).lower()
            if key in seen:
                problems.append((f"custom.{index}", "duplicate key"))
            seen.add(key)
            if str(raw.get("type") or "text") not in CUSTOM_TYPES:
                problems.append((f"custom.{index}.type", f"one of {', '.join(CUSTOM_TYPES)}"))
        for row in options.get("fields") or []:
            if not isinstance(row, Mapping) or str(row.get("key")) not in self.builtin:
                problems.append(("fields", "unknown field"))
                break
        return problems

    # ---- conversation ---------------------------------------------------------------------------
    def stage(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> str | None:
        asked = set(slots.get(ASKED) or ())
        declined = set(slots.get(DECLINED) or ())
        for f in self.fields(b):
            if slots.get(f.key) not in (None, "") or f.key in declined:
                continue
            if f.required or (f.ask and f.key not in asked):
                return f.key
        return None

    def line(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> Instruction | str:
        target = next((f for f in self.fields(b) if f.key == stage), None)
        if target is None:
            return ""
        if not target.required:
            slots[ASKED] = sorted({*(slots.get(ASKED) or ()), stage})
        return render(lang_pick(target.question, language), {"business": ctx.merchant_value("business_name", "")})

    def brief(self, b: BoundSkill, stage: str, slots: dict[str, Any], ctx: CallContext) -> str:
        target = next((f for f in self.fields(b) if f.key == stage), None)
        if target is None:
            return self.goal
        optional = "" if target.required else " Optional: if they'd rather not say, move on."
        return f"Get the {lang_pick(target.label, 'en').lower()}.{optional}"

    def normalize(self, b: BoundSkill, fields: dict[str, Any], slots: dict[str, Any], ctx: CallContext, language: str):
        by_key = {f.key: f for f in self.fields(b)}
        for key in list(fields):
            spec = by_key.get(key)
            value = fields[key]
            if spec is None:
                continue
            cleaned = _coerce(spec, value, ctx)
            if cleaned is None:
                fields.pop(key)
            else:
                fields[key] = cleaned
        return fields, None

    def commit_details(self, b: BoundSkill, slots: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        values = {f.key: slots[f.key] for f in self.fields(b) if slots.get(f.key) not in (None, "")}
        values.pop(getattr(self, "name_key", ""), None)
        return {"intake": values} if values else {}

    def prefetch(self, b: BoundSkill, ctx: CallContext, language: str) -> list[str]:
        return [lang_pick(f.question, language) for f in self.fields(b)]


def _coerce(spec: IntakeField, value: Any, ctx: CallContext) -> Any:
    if spec.type == "number":
        try:
            number = float(str(value).replace(",", ""))
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    if spec.type == "bool":
        return value if isinstance(value, bool) else None
    if spec.type == "date":
        day = parse_date(value, ctx.today)
        return day.isoformat() if day else None
    if spec.type == "phone":
        return clean_phone(value) or None
    if spec.type == "email":
        text = str(value).strip().replace(" at ", "@").replace(" dot ", ".").replace(" ", "")
        return text.lower() if _EMAIL.match(text) else None
    if spec.type == "choice" and spec.choices:
        text = str(value).strip()
        return next((c for c in spec.choices if c.lower() == text.lower()), None)
    text = " ".join(str(value).split())[:300]
    return text or None


__all__ = ["ASKED", "IntakeField", "IntakeSkill", "custom_field"]
