"""System prompt for the call agent, layered for OpenAI prompt caching.

Prompt caching only reuses an *exact prefix* (≥ 1024 tokens, tools included),
so the prompt is built from the most stable part to the least stable one:

1. core voice-agent rules (per language) + the flow's rules  — identical for every
   call of that flow on the platform;
2. the business: name, catalog, knowledge, transfer availability — identical for
   every call of that account until the owner edits something;
3. this call: calendar, caller / record, what was already said, the first step.

Node directives are appended to the conversation tail by the runtime, never
spliced into this text, so the head stays cacheable for the whole call.
"""

from __future__ import annotations

from typing import Any

from app.flows.base import Flow
from app.flows.context import CallContext
from app.voice.languages import language_name, normalize_language, phrase

_STYLE = {
    "bn": "Use natural, polite, colloquial Bangladeshi Bangla with the respectful \"আপনি\".",
    "en": "Use warm, friendly, professional English.",
}
_NUMBERS = {
    "bn": "Say numbers, prices, dates and times in words, the way a person would on the phone.",
    "en": "Write times, prices and numbers the normal way (9 AM, $140, 2:30 PM) — the voice reads them naturally.",
}

_CORE_RULES = """You are the voice agent on a live phone call for the business described below. Everything you write is spoken aloud by a text-to-speech voice.

How to speak:
- Speak only {language}, even if the caller uses another language. {style}
- Short, natural spoken sentences — one or two per turn. No lists, bullet points, emoji, markdown, links or symbols.
- At most one question per turn.
- {numbers}

How to work:
- Whenever the caller gives you any detail, call save_details BEFORE you speak, with every detail from that turn in one call. If they also asked something, put a one-sentence answer in `reply`; the system then speaks your reply and asks the next question itself — do not write the next question yourself.
- Save what the caller MEANT in the format the field asks for: a day such as "tomorrow", "Wednesday" or "next Monday" becomes its YYYY-MM-DD date from the calendar in the facts (a bare weekday is the NEAREST coming one — on a Friday, "Saturday" is tomorrow); times become HH:MM (24 h). Never say you noted something you did not save in that same call.
- A tool result's "instruction" says what happens next. "(Already said to the caller …)" means it was spoken for you — just wait for the caller's answer.
- Never ask again for something already saved.
- Refs such as D1, P2, S3 or A1 are only for tool calls — never say them to the caller; use the name.
- Use only the facts below and tool results. Never invent prices, availability, times, policies or promises. If you do not know, say a team member will follow up, or call transfer_to_human.
- Never say something is booked, confirmed, cancelled or changed unless a tool result says so.
- If the caller asks something unrelated to the business, answer briefly and politely, then steer back.
- The caller wants a human → transfer_to_human. The conversation is finished or the caller wants to stop → end_call (the system says goodbye). After any call-ending tool, say nothing more.
- If you could not understand the caller, briefly ask them to repeat."""


def _get(obj: Any, name: str, default: Any = "") -> Any:
    value = getattr(obj, name, None) if obj is not None else None
    return default if value in (None, "") else value


_CHAT_HEAD = """You are the assistant in the website chat of the business described below. The customer types; you reply with short chat messages.

How to write:
- Write only {language}, even if the customer uses another language. {style}
- One or two short sentences per message, plain text. No lists, markdown or emoji.
- At most one question per message.
- Numbers, prices, dates and times may be written normally.
"""


def core_rules(language: str, channel: str = "voice") -> str:
    lang = normalize_language(language)
    text = _CORE_RULES
    if channel == "chat":
        # Same working rules; only the medium differs ("caller" reads as "customer").
        text = _CHAT_HEAD + text[text.index("\nHow to work:"):]
    return text.format(
        language=language_name(lang).split(" (")[0],
        style=_STYLE.get(lang, _STYLE["en"]),
        numbers=_NUMBERS.get(lang, _NUMBERS["en"]),
    )


def business_block(flow: Flow, ctx: CallContext, language: str) -> str:
    merchant = ctx.merchant
    business = str(_get(merchant, "business_name", ""))
    lines = [f"Business: {business}."]
    lines += flow.business_facts(ctx, language)
    knowledge = str(_get(merchant, "knowledge", "") or "").strip()
    if knowledge:
        lines.append("Business information you may answer from (address, hours, policies, FAQs):")
        lines.append(knowledge[:8000])
    support = str(_get(merchant, "support_phone", "") or "").strip()
    lines.append(
        "Transfer to a human: available (transfer_to_human)."
        if support
        else "Transfer to a human: not available right now — say a team member will call back (transfer_to_human records that)."
    )
    lines.append(f"Currency: {ctx.currency}. Time zone: {ctx.timezone}.")
    return "\n".join(line for line in lines if line)


def call_block(flow: Flow, ctx: CallContext, language: str, *, opening: str, initial_directive: str = "") -> str:
    lines = ["This call:"]
    if ctx.chat:
        lines.append("- Channel: website chat (the customer is typing).")
    else:
        lines.append(f"- Direction: {'the caller phoned the business' if ctx.inbound else 'the business is calling this person'}.")
    lines += flow.call_facts(ctx, language)
    lines.append(f"You have ALREADY said: \"{opening}\" — do not greet again; continue from the caller's answer.")
    if initial_directive:
        lines.append(initial_directive)
    return "\n".join(line for line in lines if line)


def build_messages(flow: Flow, ctx: CallContext, *, language: str | None = None, opening: str = "", initial_directive: str = "") -> list[dict[str, Any]]:
    """The three system messages of a call, most-stable first."""
    lang = normalize_language(language or _get(ctx.merchant, "language", "en"))
    head = core_rules(lang, ctx.channel)
    rules = flow.rules(lang)
    if rules:
        head = f"{head}\n\n{rules}"
    return [
        {"role": "system", "content": head},
        {"role": "system", "content": business_block(flow, ctx, lang)},
        {"role": "system", "content": call_block(flow, ctx, lang, opening=opening, initial_directive=initial_directive)},
    ]


def build_system_prompt(flow: Flow, ctx: CallContext, *, language: str | None = None, opening: str = "", initial_directive: str = "") -> str:
    """The same prompt as one string (tests, debugging)."""
    return "\n\n".join(m["content"] for m in build_messages(flow, ctx, language=language, opening=opening, initial_directive=initial_directive))


def transcription_prompt(supported: list[str]) -> str:
    """Vocabulary hint for the STT session, one line per supported language."""
    return " ".join(phrase("transcription_prompt", code) for code in supported).strip()


__all__ = ["build_messages", "build_system_prompt", "core_rules", "transcription_prompt"]
