"""Tool names and the small text helpers the tools share (notes, joins, answer-only replies)."""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.flows.base import (
    OUTCOME_AUTO_DROPPED,
    OUTCOME_DIVERTED,
    OUTCOME_RELAY,
    OUTCOME_TRANSFER,
    OUTCOME_UNCLEAR,
    OUTCOME_VOICEMAIL,
    OUTCOME_WRONG_NUMBER,
)
from app.voice.languages import normalize_language, phrase

logger = structlog.get_logger(__name__)


SAVE_DETAILS = "save_details"
TRANSFER_TO_HUMAN = "transfer_to_human"
END_CALL = "end_call"
REPLY_FIELD = "reply"


def _note(outcome: str, language: str, **fields: Any) -> str:
    lang = normalize_language(language)
    templates = {
        OUTCOME_RELAY: {
            "en": "Someone who knows the customer answered; asked them to pass the message on.",
        },
        OUTCOME_WRONG_NUMBER: {
            "en": "The person who answered said this is the wrong number / does not know the customer.",
        },
        OUTCOME_TRANSFER: {
            "en": "Customer asked to speak with a team member.",
        },
        OUTCOME_DIVERTED: {
            "en": "The customer did not answer / rejected the call and the carrier forwarded it. They can be called again.",
        },
        OUTCOME_VOICEMAIL: {
            "en": "The call went to voicemail; hung up without speaking. They can be called again.",
        },
        OUTCOME_UNCLEAR: {
            "en": "The customer's answer was unclear; needs a follow-up.",
        },
        "later": {
            "en": "Customer asked to be called later.",
        },
        OUTCOME_AUTO_DROPPED: {
            "en": "No response from the customer; the call was dropped.",
        },
        "commit_failed": {
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


def unclear_line(attempt: int, instruction: Any, language: str) -> str:
    """A re-ask that doesn't sound like a broken record: a rotating lead-in + the current question."""
    lead = phrase(f"unclear_{(max(attempt, 1) - 1) % 3 + 1}", language)
    question = instruction.text if instruction is not None and instruction.verbatim and not instruction.end_call else ""
    return _join(lead, question)


_SENTENCE_RE = re.compile(r"[^.!?।]+[.!?।]?")


def answer_only(reply: str) -> str:
    """The model's ``reply`` minus any question: the system asks the next question
    itself, so a question in the reply would be asked twice."""
    sentences = [part.strip() for part in _SENTENCE_RE.findall(reply or "") if part.strip()]
    return " ".join(sentence for sentence in sentences if not sentence.endswith("?"))


