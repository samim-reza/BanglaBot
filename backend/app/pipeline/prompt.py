"""The compact prompt profile: what one model request carries on a free-tier LLM.

Free tiers (Groq, Gemini) count every prompt token against per-minute and
per-day limits, cached or not, so instead of the growing full conversation a
request carries:

1. short core rules + the vertical's rules;
2. a business header (no wholesale knowledge text);
3. the active step's brief: its goal, the facts only that step needs, what is
   already known, what the system just asked, the calendar;
4. knowledge paragraphs only when the caller's words match them;
5. the last few exchanges.

``save_details`` is trimmed to the slots of the active path (plus volunteerable
ones) with short descriptions. OpenAI keeps the ``cached`` profile (a large
stable prefix is cheapest there).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.flows.base import Flow
from app.flows.closures import call_facts as closure_facts
from app.flows.context import CallContext
from app.pipeline.knowledge import relevant
from app.voice.languages import language_name, normalize_language

#: Caller turns of history kept in a compact request.
WINDOW_TURNS = 3
FACTS_CHARS = 1600
KNOWN_CHARS = 400
DESCRIPTION_CHARS = 70
TOOL_DESCRIPTION_CHARS = 140
CALENDAR_DAYS = 8
#: Slots every flow may need in any step.
ALWAYS_SLOTS = frozenset({"reply", "note", "confirmed", "identity_confirmed", "knows_customer", "wrong_person"})

_CORE = """You are the {medium} for the business below. {spoken}
- Use only {language}. {style} One or two short sentences; at most one question; no lists or symbols.
- When the {person} gives ANY detail, call save_details first with every detail of the turn, saving what they meant (dates YYYY-MM-DD from the calendar — a bare weekday is the next one; times HH:MM 24 h). If they also asked something, put a one-sentence answer in `reply`; the system asks the next question itself.
- Use only the facts and tool results. Never invent prices, times, availability or policies; never say something is booked, confirmed or cancelled unless a tool result says so. Refs like D1 or A1 are for tools only — say names.
- Off-topic questions (weather, other businesses, general chat): say briefly in reply that you can only help with this business, then continue.
- A question isn't a request: answer it, and collect booking details only once they say they want to book.
- Answer questions completely from the facts in one or two sentences (asked "when?" → the days and the hours).
- Asked for something the business doesn't offer → say so plainly in reply ("Sorry, we don't offer roof repairs") before offering what it does.
- Wants a human → transfer_to_human. Done or wants to stop → end_call (the system says goodbye). Unclear or garbled words → a short 'Sorry, could you say that again?' in reply; never transfer or end the call for it."""

_STYLE = {"en": "Warm, friendly, professional."}


def core_rules(language: str, chat: bool) -> str:
    lang = normalize_language(language)
    return _CORE.format(
        medium="assistant in the website chat" if chat else "voice agent on a live phone call",
        spoken="The customer types; you reply in short chat messages." if chat else "Everything you write is spoken aloud.",
        person="customer" if chat else "caller",
        language=language_name(lang),
        style=_STYLE.get(lang, _STYLE["en"]),
    )


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def step_facts(flow: Flow, stage: str, slots: dict[str, Any], ctx: CallContext, language: str) -> list[str]:
    """Facts for this step only: the owning skill's (pipeline flows) or the flow's business facts, trimmed."""
    owner = flow.owner(stage, slots) if hasattr(flow, "owner") else None
    facts: list[str] = []
    if owner is not None:
        facts = owner.skill.facts(owner, ctx, language)
    if not facts and (owner is None or owner.skill.kind == "router"):
        # At the router (or on a legacy flow) callers ask about anything: give the catalog, trimmed.
        facts = flow.business_facts(ctx, language)
    text = "\n".join(facts)
    return [_clip(text, FACTS_CHARS)] if text else []


def brief(flow: Flow, runtime: Any, ctx: CallContext, language: str, caller_text: str) -> str:
    stage = runtime.stage
    slots = runtime.slots
    lines: list[str] = []
    directive = flow.node_directive(runtime.current_node, slots, ctx, language)
    if hasattr(flow, "step_position") and directive:
        n, total = flow.step_position(stage, slots)
        directive = directive.replace("[STEP:", f"[STEP {n}/{total}:", 1)
    if directive:
        lines.append(directive)
    known = {key: value for key, value in runtime.flow_data().items()}
    if known:
        lines.append("Known: " + _clip(json.dumps(known, ensure_ascii=False, default=str), KNOWN_CHARS))
    last = runtime.last_instruction
    if last is not None and last.verbatim:
        lines.append(f'The system last said: "{_clip(last.text, 240)}"')
    lines += step_facts(flow, stage, slots, ctx, language)
    lines += [line for line in flow.call_facts(ctx, language) if line]
    lines += closure_facts(ctx)
    snippets = relevant(str(ctx.merchant_value("knowledge", "") or ""), caller_text)
    if snippets:
        lines.append("Business information that may answer them: " + " | ".join(snippets))
    return "\n".join(_shorten_calendar(line) for line in dict.fromkeys(lines))


_CALENDAR_ROW = re.compile(r"(Next days: )(.*)\.$")


def _shorten_calendar(line: str) -> str:
    """The two-week calendar line → the next ``CALENDAR_DAYS`` days (plenty for a phone booking)."""
    match = _CALENDAR_ROW.search(line)
    if not match or not line.startswith("Today is"):
        return line
    rows = match.group(2).split(", ")[:CALENDAR_DAYS]
    return line[: match.start(2)] + ", ".join(rows) + "."


def business_header(ctx: CallContext, has_transfer: bool) -> str:
    name = ctx.merchant_value("business_name", "")
    transfer = "available (transfer_to_human)" if has_transfer else "not available — say a team member will call back"
    return f"Business: {name}. Transfer to a human: {transfer}. Currency: {ctx.currency}. Time zone: {ctx.timezone}."


def window(messages: list[dict[str, Any]], turns: int = WINDOW_TURNS) -> list[dict[str, Any]]:
    """The last ``turns`` caller turns and everything after (tool calls stay paired; no system notes)."""
    convo = [m for m in messages if m.get("role") != "system"]
    users = [i for i, m in enumerate(convo) if m.get("role") == "user"]
    if len(users) > turns:
        convo = convo[users[-turns]:]
    elif users:
        # Keep the opening line the agent spoke before the first caller turn.
        convo = convo[max(0, users[0] - 1):]
    return convo


def compact_messages(flow: Flow, runtime: Any, ctx: CallContext, messages: list[dict[str, Any]], language: str, caller_text: str) -> list[dict[str, Any]]:
    head = core_rules(language, ctx.chat)
    compact = getattr(flow, "compact_rules", None)
    rules = compact(language) if callable(compact) else flow.rules(language)
    if rules:
        head = f"{head}\n\n{rules}"
    support = bool(str(ctx.merchant_value("support_phone", "") or "").strip())
    context = f"{business_header(ctx, support)}\n{brief(flow, runtime, ctx, language, caller_text)}"
    return [{"role": "system", "content": head}, {"role": "system", "content": context}, *window(messages)]


def compact_tools(tools: list[dict[str, Any]], flow: Flow, runtime: Any) -> list[dict[str, Any]]:
    """``save_details`` limited to the active path's slots (+ volunteerable ones), descriptions shortened."""
    allowed: set[str] | None = None
    if hasattr(flow, "active") and hasattr(flow, "cp"):
        allowed = set(ALWAYS_SLOTS) | set(flow.cp.volunteerable)
        for bound in flow.active(runtime.slots):
            allowed |= set(bound.skill.slot_keys(bound))
    out: list[dict[str, Any]] = []
    for tool in tools:
        function = dict(tool.get("function") or {})
        if function.get("description"):
            function["description"] = _clip(function["description"], TOOL_DESCRIPTION_CHARS)
        if function.get("name") != "save_details":
            params = dict(function.get("parameters") or {})
            params["properties"] = {
                key: {**spec, "description": _clip(spec.get("description", ""), DESCRIPTION_CHARS)} if "description" in spec else spec
                for key, spec in (params.get("properties") or {}).items()
            }
            out.append({"type": "function", "function": {**function, "parameters": params}})
            continue
        params = dict(function.get("parameters") or {})
        props = {}
        for key, spec in (params.get("properties") or {}).items():
            if allowed is not None and key not in allowed:
                continue
            spec = dict(spec)
            if "description" in spec:
                spec["description"] = _clip(spec["description"], DESCRIPTION_CHARS)
            props[key] = spec
        params["properties"] = props
        out.append({"type": "function", "function": {**function, "parameters": params}})
    return out


def estimate_tokens(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> int:
    chars = sum(len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls") or "")) for m in messages)
    return (chars + (len(json.dumps(tools)) if tools else 0)) // 4


__all__ = ["compact_messages", "compact_tools", "core_rules", "estimate_tokens", "window"]
