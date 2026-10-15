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
from app.voice.languages import normalize_language

logger = structlog.get_logger(__name__)


SAVE_DETAILS = "save_details"
TRANSFER_TO_HUMAN = "transfer_to_human"
END_CALL = "end_call"
REPLY_FIELD = "reply"


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


