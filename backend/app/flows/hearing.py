"""Did the caller's own words support an outcome?

The model is good at *extracting* intent but happy to over-commit: a mumbled
"হুম", an echo of the agent's own question, or a decoder hallucination can all
turn into ``confirm_order``. This module is the backend's second opinion.
Nothing here is clever — small vocabularies of Bangla, romanised Bangla and
English answer words, scored so that a phrase ("লাগবে না", "no problem")
outweighs the single word inside it that points the other way.

Labels produced by :func:`classify`:

``yes``, ``no``, ``later``, ``wrong_number``, ``not_me``, ``is_me``, ``knows``

and the questions the tools ask:

- :func:`supports(text, outcome)` — ``"confirm"`` / ``"cancel"`` / ``"later"`` /
  ``"wrong_number"`` / ``"not_me"`` / ``"is_me"``
- :func:`denies_identity` — the caller said they are not the named person
- :func:`is_unusable` — noise, filler or a hallucinated line; do not act on it
- :func:`echoes_agent_line` / :func:`is_prompt_echo` — STT gave us our own words back
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

_BANGLA = "ঀ-৿"
_TOKEN_RE = re.compile(rf"[{_BANGLA}]+|[a-z']+|\d+")
_PUNCT_RE = re.compile(rf"[^\w\s{_BANGLA}']+")

PHRASE_SCORE = 2
WORD_SCORE = 1

# --- vocabularies -----------------------------------------------------------
# (phrases are matched on the normalised text; words on exact tokens)

YES_PHRASES: tuple[str, ...] = (
    "ঠিক আছে", "ঠিকাছে", "পাঠিয়ে দেন", "পাঠিয়ে দিন", "পাঠায় দেন", "দিয়ে দেন", "দিয়ে দিন", "রেখে দেন",
    "কনফার্ম করেন", "কনফার্ম করুন", "কনফার্ম করে দেন", "কনফার্ম করে দিন", "নিয়ে নিব", "নিয়ে নেব",
    "অর্ডার করেছি", "অর্ডার দিয়েছি", "সমস্যা নাই", "সমস্যা নেই", "অসুবিধা নাই", "অসুবিধা নেই",
    "থিক আছে", "thik ase", "thik ache", "thik acche", "thik ase", "no problem", "no worries", "go ahead",
    "send it", "keep it", "that's right", "that is right", "i'll take it", "i will take it", "i want it",
    "i ordered", "i did order", "please send", "all good", "sounds good", "of course",
)
YES_WORDS: tuple[str, ...] = (
    "হ্যাঁ", "হ্যা", "হা", "হুঁ", "জি", "জ্বি", "জী", "জ্বী", "অবশ্যই", "কনফার্ম", "নিশ্চিত", "ওকে",
    "রাখেন", "রাখুন", "রাখব", "রাখবো", "নিব", "নেব", "নিবো", "নেবো", "লাগবে", "পাঠান", "পাঠাবেন", "চাই",
    "সঠিক", "একদম", "অবশ্যই", "হবে",
    "yes", "yeah", "yep", "yup", "ya", "sure", "ok", "okay", "correct", "right", "confirm", "confirmed",
    "fine", "absolutely", "definitely", "alright", "exactly", "yes'", "confirmed",
    "ji", "jee", "jii", "hya", "hyan", "hae", "ha", "thik",
)

NO_PHRASES: tuple[str, ...] = (
    "লাগবে না", "লাগবেনা", "লাগবে নাহ", "নিব না", "নেব না", "নিবো না", "নেবো না", "চাই না", "চাইনা",
    "বাতিল করেন", "বাতিল করুন", "বাতিল করে দেন", "বাতিল করে দিন", "ক্যান্সেল করেন", "ক্যান্সেল করে দেন",
    "ক্যান্সেল করুন", "অর্ডার করিনি", "অর্ডার করি নাই", "অর্ডার দেইনি", "অর্ডার দেই নাই", "পাঠাবেন না",
    "পাঠানোর দরকার নাই", "দরকার নাই", "দরকার নেই", "নিতে চাই না", "রাখব না", "রাখবো না", "নিব না",
    "lagbe na", "lagbena", "nibo na", "nib na", "chai na", "chaina", "cancel koren", "batil koren",
    "don't want", "do not want", "dont want", "don't need", "do not need", "dont need", "not needed",
    "didn't order", "did not order", "never ordered", "cancel it", "not interested", "don't send",
    "do not send", "cancel the order", "cancel this", "cancel my order", "i don't", "i do not",
)
NO_WORDS: tuple[str, ...] = (
    "না", "নাহ", "নাহ্", "বাতিল", "ক্যান্সেল", "ক্যানসেল", "ক্যান্সেল",
    "no", "nope", "nah", "cancel", "cancelled", "canceled",
    "na", "nah", "batil",
)

LATER_PHRASES: tuple[str, ...] = (
    "পরে বলব", "পরে বলবো", "পরে কল", "পরে ফোন", "এখন না", "এখন পারব না", "এখন পারবো না", "এখন বলতে পারছি না",
    "একটু পরে", "আবার কল", "আবার ফোন", "পরে জানাব", "পরে জানাবো", "ব্যস্ত আছি",
    "pore bolbo", "pore call", "ekhon na", "call back", "call me later", "call later", "call me back",
    "not now", "another time", "in a bit", "call again", "later please", "little later",
)
LATER_WORDS: tuple[str, ...] = ("পরে", "ব্যস্ত", "later", "busy", "pore")

WRONG_NUMBER_PHRASES: tuple[str, ...] = (
    "রং নাম্বার", "রং নম্বর", "ভুল নাম্বার", "ভুল নম্বর", "চিনি না", "চিনিনা", "চিনি নাই", "চিননা", "চিনিনাই",
    "এই নামে কেউ নাই", "এই নামে কেউ নেই", "কেউ নাই", "কেউ নেই", "এখানে নাই", "এখানে নেই", "এই নামের কেউ",
    "wrong number", "wrong person", "don't know", "do not know", "dont know", "no one by that name",
    "nobody by that name", "no such person", "never heard", "doesn't live here", "does not live here",
    "not here", "chini na", "chinina", "vul number", "bhul number", "wrong no",
)
NOT_ME_PHRASES: tuple[str, ...] = (
    "আমি না", "আমি নই", "আমি নাই", "আমি সে না", "আমি উনি না", "উনি না", "ও না", "আমি অন্য", "অন্য কেউ",
    "উনি নাই", "উনি নেই", "উনি বাইরে", "উনি বাসায় নাই", "উনি বাসায় নেই", "ও নাই", "ও নেই", "ও বাইরে",
    "not me", "i am not", "i'm not", "im not", "this is not", "this isn't", "that's not me", "that is not me",
    "he's not here", "she's not here", "he is not here", "she is not here", "he's out", "she's out",
    "not available", "ami na", "ami noi", "ami nai",
)
KNOWS_PHRASES: tuple[str, ...] = (
    "ওর ভাই", "ওর বোন", "ওর মা", "ওর বাবা", "ওর স্ত্রী", "ওর স্বামী", "ওর হাজবেন্ড", "ওর ওয়াইফ", "ওর বউ",
    "ওনার ভাই", "ওনার বোন", "ওনার স্ত্রী", "ওনার স্বামী", "তার ভাই", "তার বোন", "তার স্ত্রী", "তার স্বামী",
    "আমার ভাই", "আমার বোন", "আমার স্বামী", "আমার স্ত্রী", "আমার ছেলে", "আমার মেয়ে", "আমার বাবা", "আমার মা",
    "চিনি", "হ্যাঁ চিনি", "জি চিনি", "বলে দিব", "বলে দিবো", "বলে দেব", "জানিয়ে দিব",
    "his brother", "her brother", "his sister", "her sister", "his wife", "her husband", "his mother",
    "her mother", "his father", "her father", "my brother", "my sister", "my husband", "my wife", "my son",
    "my daughter", "i know", "yes i know", "i'll tell", "i will tell", "i'll let", "i will let", "chini",
)
KNOWS_WORDS: tuple[str, ...] = ("চিনি", "চেনা", "chini")

IS_ME_PHRASES: tuple[str, ...] = (
    "আমি বলছি", "জি বলছি", "হ্যাঁ বলছি", "আমিই", "আমি নিজেই", "আমিই বলছি",
    "ami bolchi", "bolchi", "speaking", "this is me", "that's me", "it's me", "its me", "yes it's me",
    "this is he", "this is she", "yes speaking", "yes this is", "you are speaking",
)
IS_ME_WORDS: tuple[str, ...] = ("বলছি", "আমিই", "bolchi")

# "I didn't catch that" — a request to repeat, never a yes or a no.
REPEAT_PHRASES: tuple[str, ...] = (
    "বুঝলাম না", "বুঝি নাই", "বুঝিনি", "বুঝতে পারলাম না", "বুঝতে পারিনি", "বুঝতে পারছি না", "শুনতে পাইনি",
    "শুনি নাই", "শুনতে পারিনি", "শুনতে পাচ্ছি না", "আবার বলেন", "আবার বলুন", "কী বললেন", "কি বললেন", "কিসের কথা",
    "কী বলছেন", "কি বলছেন",
    "didn't get that", "didn't understand", "don't understand", "didn't hear", "couldn't hear", "can't hear",
    "cannot hear", "say again", "come again", "pardon", "what did you say", "sorry what", "excuse me",
    "bujhlam na", "bujhi nai", "abar bolen",
)
REPEAT_WORDS: tuple[str, ...] = ("মানে", "pardon", "what", "huh")

# Filler that carries no answer at all.
BACKCHANNEL_WORDS: frozenset[str] = frozenset(
    {"hmm", "hm", "mm", "mhm", "uh", "um", "er", "ah", "oh", "হুম", "হু", "উম", "আ", "এ", "হ্যালো", "hello", "hallo"}
)
# Lines transcription models are known to invent from silence / music.
NOISE_PHRASES: tuple[str, ...] = (
    "thank you for watching", "thanks for watching", "subscribe", "like and subscribe", "see you in the next",
    "সাবস্ক্রাইব", "দেখার জন্য ধন্যবাদ", "ধন্যবাদ দেখার জন্য", "www.", ".com", "transcribed by", "amara.org",
)


# --- text helpers --------------------------------------------------------------


def normalize(text: Any) -> str:
    lowered = str(text or "").lower().replace("।", " ").replace("’", "'")
    lowered = _PUNCT_RE.sub(" ", lowered)
    return " ".join(lowered.split())


def tokens(text: Any) -> list[str]:
    return _TOKEN_RE.findall(normalize(text))


def _score(text: str, toks: list[str], phrases: Iterable[str], words: Iterable[str]) -> int:
    padded = f" {text} "
    score = sum(PHRASE_SCORE for phrase in phrases if f" {normalize(phrase)} " in padded)
    word_set = set(words)
    score += sum(WORD_SCORE for tok in toks if tok in word_set)
    return score


# --- classification -----------------------------------------------------------


def scores(text: Any) -> dict[str, int]:
    norm = normalize(text)
    toks = norm.split()
    return {
        "yes": _score(norm, toks, YES_PHRASES, YES_WORDS),
        "no": _score(norm, toks, NO_PHRASES, NO_WORDS),
        "later": _score(norm, toks, LATER_PHRASES, LATER_WORDS),
        "wrong_number": _score(norm, toks, WRONG_NUMBER_PHRASES, ()),
        "not_me": _score(norm, toks, NOT_ME_PHRASES, ()),
        "knows": _score(norm, toks, KNOWS_PHRASES, KNOWS_WORDS),
        "is_me": _score(norm, toks, IS_ME_PHRASES, IS_ME_WORDS),
        "repeat": _score(norm, toks, REPEAT_PHRASES, REPEAT_WORDS),
    }


def classify(text: Any) -> set[str]:
    """Labels the caller line supports. Empty set = nothing usable."""
    if is_unusable(text):
        return set()
    s = scores(text)
    labels: set[str] = set()
    if s["repeat"] >= PHRASE_SCORE or (s["repeat"] and not (s["yes"] or s["no"])):
        # "বুঝলাম না" carries a "না" but is a request to repeat, not an answer.
        return {"repeat"}
    # "no" inside "চিনি না" / "don't know" belongs to the wrong-number reading, not a cancel.
    if s["wrong_number"]:
        labels.add("wrong_number")
        labels.add("not_me")
    if s["not_me"]:
        labels.add("not_me")
    if s["knows"] and not s["wrong_number"]:
        labels.add("knows")
        labels.add("not_me") if _relationship_phrase(text) else None
    if s["later"] and s["later"] >= s["yes"] and s["later"] >= s["no"]:
        labels.add("later")
    yes, no = s["yes"], s["no"]
    if "wrong_number" in labels:
        # "চিনি না" scores a "না" — it is not a cancellation.
        no = max(0, no - WORD_SCORE)
    if yes > no and yes >= WORD_SCORE:
        labels.add("yes")
    elif no > yes and no >= WORD_SCORE:
        labels.add("no")
    if s["is_me"]:
        labels.add("is_me")
    elif "yes" in labels and not labels & {"not_me", "knows", "wrong_number"}:
        labels.add("is_me")
    if "not_me" in labels:
        labels.discard("is_me")
    return labels


def _relationship_phrase(text: Any) -> bool:
    norm = f" {normalize(text)} "
    return any(f" {normalize(p)} " in norm for p in KNOWS_PHRASES if p not in ("চিনি", "হ্যাঁ চিনি", "জি চিনি", "i know", "yes i know", "chini"))


_OUTCOME_LABEL: dict[str, str] = {
    "confirm": "yes",
    "confirmed": "yes",
    "cancel": "no",
    "cancelled": "no",
    "later": "later",
    "wrong_number": "wrong_number",
    "not_me": "not_me",
    "is_me": "is_me",
    "knows": "knows",
}


_QUESTION_TAIL_RE = re.compile(r"(?:\sকি|\sকি\s?না|\sনাকি|\?)$")
_QUESTION_HEAD_RE = re.compile(
    r"^(?:am i|is this|is it|are you|do you|would you|should i|can i|could you|will you|what|which|when|where|how|why)\b"
)


def looks_like_question(text: Any) -> bool:
    """A question of 3+ words is the agent's own line or a counter-question, never an answer."""
    norm = normalize(text)
    if len(norm.split()) < 3:
        return False
    return bool(_QUESTION_TAIL_RE.search(norm) or _QUESTION_HEAD_RE.match(norm) or "?" in str(text or ""))


def supports(text: Any, outcome: str) -> bool:
    """True when the caller's line carries the answer ``outcome`` needs."""
    label = _OUTCOME_LABEL.get(str(outcome or "").lower())
    if label is None:
        return False
    labels = classify(text)
    identity_talk = bool(labels & {"not_me", "knows", "wrong_number"})
    if label == "yes":
        # A yes with a "later" attached ("হ্যাঁ, কিন্তু পরে") is not a confirmation,
        # and neither is a question that merely contains "confirm".
        return "yes" in labels and "later" not in labels and not identity_talk and not looks_like_question(text)
    if label == "no":
        # "আমি না, ওর ভাই" is about identity, not about the order.
        return "no" in labels and "later" not in labels and not identity_talk and not looks_like_question(text)
    return label in labels


def denies_identity(text: Any) -> bool:
    """The caller said they are not the named customer (or nobody here is)."""
    labels = classify(text)
    if labels & {"not_me", "wrong_number"}:
        return True
    return "no" in labels and "is_me" not in labels


# --- usability filters ----------------------------------------------------------


def looks_like_noise(text: Any) -> bool:
    norm = normalize(text)
    if not norm:
        return True
    if any(marker in norm for marker in NOISE_PHRASES):
        return True
    toks = norm.split()
    if all(tok.isdigit() for tok in toks) and len(toks) > 3:
        return True
    return _has_repetition_loop(toks)


def _has_repetition_loop(toks: list[str]) -> bool:
    if len(toks) >= 6:
        most_common = Counter(toks).most_common(1)[0][1]
        if most_common >= max(5, int(len(toks) * 0.8)):
            return True
    if len(toks) >= 8:
        bigrams = Counter(zip(toks, toks[1:]))
        if bigrams.most_common(1)[0][1] >= 4:
            return True
    return False


def is_backchannel(text: Any) -> bool:
    toks = tokens(text)
    return bool(toks) and all(tok in BACKCHANNEL_WORDS for tok in toks)


def is_unusable(text: Any) -> bool:
    """Noise, pure filler, or a hallucinated line — never act on it."""
    norm = normalize(text)
    if not norm:
        return True
    if looks_like_noise(norm):
        return True
    return is_backchannel(norm)


def is_pure_answer(text: Any) -> bool:
    """A short line made only of answer words (safe to keep even if it overlaps the agent's question)."""
    toks = tokens(text)
    if not toks or len(toks) > 4:
        return False
    answer_words = set(YES_WORDS) | set(NO_WORDS) | set(LATER_WORDS) | set(IS_ME_WORDS) | set(KNOWS_WORDS)
    return all(tok in answer_words for tok in toks) or bool(classify(text))


def echoes_agent_line(text: Any, agent_lines: Iterable[str], *, min_tokens: int = 5, threshold: float = 0.8) -> bool:
    """The transcript is (mostly) the agent's own recent words coming back over the line."""
    toks = tokens(text)
    if len(toks) < min_tokens or is_pure_answer(text):
        return False
    text_set = set(toks)
    for line in agent_lines:
        line_toks = set(tokens(line))
        if not line_toks:
            continue
        overlap = len(text_set & line_toks) / len(text_set)
        if overlap >= threshold:
            return True
    return False


def is_prompt_echo(text: Any, prompt: Any, *, min_tokens: int = 3) -> bool:
    """STT repeated the vocabulary prompt instead of hearing the caller."""
    norm = normalize(text)
    prompt_norm = normalize(prompt)
    if not norm or not prompt_norm or len(norm.split()) < min_tokens:
        return False
    if norm == prompt_norm or norm in prompt_norm:
        return True
    text_set, prompt_set = set(norm.split()), set(prompt_norm.split())
    return len(prompt_set) >= 6 and len(text_set & prompt_set) >= int(len(prompt_set) * 0.75)
