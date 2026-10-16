"""Did the caller's own words support an outcome?

The model is good at *extracting* intent but happy to over-commit: a mumbled
"hmm", an echo of the agent's own question, or a decoder hallucination can all
turn into ``confirm_order``. This module is the backend's second opinion.
Nothing here is clever — small vocabularies of English answer words, scored so
that a phrase ("don't need", "no problem") outweighs the single word inside it
that points the other way.

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

_TOKEN_RE = re.compile(r"[a-z']+|\d+")
_PUNCT_RE = re.compile(r"[^\w\s']+")

PHRASE_SCORE = 2
WORD_SCORE = 1

# --- vocabularies -----------------------------------------------------------
# (phrases are matched on the normalised text; words on exact tokens)

YES_PHRASES: tuple[str, ...] = (
    "no problem", "no worries", "go ahead", "send it", "keep it", "that's right", "that is right",
    "i'll take it", "i will take it", "i want it", "i ordered", "i did order", "please send", "all good",
    "sounds good", "of course",
    # bookings / reminders / follow-ups
    "book it", "that works", "works for me", "i'll come", "i will come", "i'll be there", "still interested",
    "i am interested", "i'm interested", "sounds great", "sounds perfect", "that's perfect", "that's great",
    "please do", "go for it", "do it", "yes please", "yeah sure", "sure thing", "that's fine", "that is fine",
    "let's do it",
)
YES_WORDS: tuple[str, ...] = (
    "yes", "yeah", "yep", "yup", "ya", "sure", "ok", "okay", "correct", "right", "confirm", "confirmed",
    "fine", "absolutely", "definitely", "alright", "exactly", "yes'", "interested",
    "perfect", "great", "awesome", "excellent", "lovely", "brilliant", "wonderful", "cool", "certainly",
)

NO_PHRASES: tuple[str, ...] = (
    "don't want", "do not want", "dont want", "don't need", "do not need", "dont need", "not needed",
    "didn't order", "did not order", "never ordered", "cancel it", "not interested", "don't send",
    "do not send", "cancel the order", "cancel this", "cancel my order", "i don't", "i do not",
    # bookings / reminders / follow-ups
    "can't come", "cannot come", "won't come", "not coming", "can't make it", "doesn't work", "does not work",
    "no longer interested", "not great", "not good", "not really", "not fine", "not perfect", "not ok", "not okay",
    "doesn't suit", "does not suit", "not that time", "not that day",
    "can't make that", "cannot make that", "can't make it then", "won't make it", "won't be able", "unable to make",
    "can't do that", "cannot do that", "can't come in", "not going to make",
)
NO_WORDS: tuple[str, ...] = ("no", "nope", "nah", "cancel", "cancelled", "canceled")

LATER_PHRASES: tuple[str, ...] = (
    "call back", "call me later", "call later", "call me back", "not now", "another time", "in a bit",
    "call again", "later please", "little later",
)
LATER_WORDS: tuple[str, ...] = ("later", "busy")
#: "an hour later", "later than mine", "later that day" — a time the caller wants, not "call me later".
_TIME_LATER_RE = re.compile(
    r"\b(?:\d+|an?|one|two|three|half an?|a few|few|couple of)\s+(?:hours?|minutes?|mins?|days?)\s+later\b"
    r"|\blater\s+(?:than|that|in the|on|time|slot|appointment|today|tonight)\b|\ba (?:little|bit) later\s+(?:in|on)\b"
)

WRONG_NUMBER_PHRASES: tuple[str, ...] = (
    "wrong number", "wrong person", "don't know", "do not know", "dont know", "no one by that name",
    "nobody by that name", "no such person", "never heard", "doesn't live here", "does not live here",
    "not here", "wrong no",
)
NOT_ME_PHRASES: tuple[str, ...] = (
    "not me", "i am not", "i'm not", "im not", "this is not", "this isn't", "that's not me", "that is not me",
    "he's not here", "she's not here", "he is not here", "she is not here", "he's out", "she's out",
    "not available",
)
KNOWS_PHRASES: tuple[str, ...] = (
    "his brother", "her brother", "his sister", "her sister", "his wife", "her husband", "his mother",
    "her mother", "his father", "her father", "my brother", "my sister", "my husband", "my wife", "my son",
    "my daughter", "i know", "yes i know", "i'll tell", "i will tell", "i'll let", "i will let",
)
KNOWS_WORDS: tuple[str, ...] = ()

IS_ME_PHRASES: tuple[str, ...] = (
    "speaking", "this is me", "that's me", "it's me", "its me", "yes it's me",
    "this is he", "this is she", "yes speaking", "yes this is", "you are speaking",
)
IS_ME_WORDS: tuple[str, ...] = ()

# "I didn't catch that" — a request to repeat, never a yes or a no.
REPEAT_PHRASES: tuple[str, ...] = (
    "didn't get that", "didn't understand", "don't understand", "didn't hear", "couldn't hear", "can't hear",
    "cannot hear", "say again", "come again", "pardon", "what did you say", "sorry what", "excuse me",
)
REPEAT_WORDS: tuple[str, ...] = ("pardon", "what", "huh")

# Filler that carries no answer at all.
BACKCHANNEL_WORDS: frozenset[str] = frozenset({"hmm", "hm", "mm", "mhm", "uh", "um", "er", "ah", "oh", "hello", "hallo"})
# Lines transcription models are known to invent from silence / music.
NOISE_PHRASES: tuple[str, ...] = (
    "thank you for watching", "thanks for watching", "subscribe", "like and subscribe", "see you in the next",
    "transcribed by", "amara.org",
)


# --- text helpers --------------------------------------------------------------


def normalize(text: Any) -> str:
    lowered = str(text or "").lower().replace("’", "'")
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
        "later": _score(_TIME_LATER_RE.sub(" ", norm), tokens(_TIME_LATER_RE.sub(" ", norm)), LATER_PHRASES, LATER_WORDS),
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
        # "didn't understand" carries a negation but is a request to repeat, not an answer.
        return {"repeat"}
    # "no" inside "don't know" belongs to the wrong-number reading, not a cancel.
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
        # "no, don't know them" scores a "no" — it is not a cancellation.
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
    return any(f" {normalize(p)} " in norm for p in KNOWS_PHRASES if p not in ("i know", "yes i know"))


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


_QUESTION_HEAD_RE = re.compile(
    r"^(?:am i|is this|is it|are you|do you|would you|should i|can i|could you|will you|what|which|when|where|how|why)\b"
)


def looks_like_question(text: Any) -> bool:
    """A question of 3+ words is the agent's own line or a counter-question, never an answer."""
    norm = normalize(text)
    if len(norm.split()) < 3:
        return False
    return bool(_QUESTION_HEAD_RE.match(norm) or "?" in str(text or ""))


def supports(text: Any, outcome: str, *, identity: bool = True) -> bool:
    """True when the caller's line carries the answer ``outcome`` needs.

    ``identity=False`` (inbound calls, no "is this X?" check): "my husband" is not identity talk."""
    label = _OUTCOME_LABEL.get(str(outcome or "").lower())
    if label is None:
        return False
    labels = classify(text)
    identity_talk = identity and bool(labels & {"not_me", "knows", "wrong_number"})
    if label == "yes":
        # A yes with a "later" attached ("yes, but later") is not a confirmation,
        # and neither is a question that merely contains "confirm".
        return "yes" in labels and "later" not in labels and not identity_talk and not looks_like_question(text)
    if label == "no":
        # "not me, I'm his brother" is about identity, not about the order.
        return "no" in labels and "later" not in labels and not identity_talk and not looks_like_question(text)
    return label in labels


_CANCEL_WORDS = ("cancel", "cancelled", "canceled")
_KEEP_PHRASES = ("don't cancel", "do not cancel", "dont cancel", "no don't", "keep it", "keep the appointment", "keep my")


def declines_cancel(text: Any) -> bool:
    """The caller does NOT want the thing cancelled ("no, keep it")."""
    norm = f" {normalize(text)} "
    if any(f" {normalize(p)} " in norm for p in _KEEP_PHRASES):
        return True
    labels = classify(text)
    return "no" in labels and not any(word in norm.split() for word in _CANCEL_WORDS)


def affirms_cancel(text: Any) -> bool:
    """A yes to "shall I cancel it?" — including "yes, cancel it"."""
    if is_unusable(text) or declines_cancel(text) or looks_like_question(text):
        return False
    norm = normalize(text)
    if any(word in norm.split() for word in _CANCEL_WORDS):
        return True
    labels = classify(text)
    return "yes" in labels and "no" not in labels


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
    if all(tok.isdigit() for tok in toks) and len(toks) > 15:
        return True  # a phone number read out (≤ 15 groups) is an answer, a long digit run is not
    return _has_repetition_loop(toks)


def _has_repetition_loop(toks: list[str]) -> bool:
    if len(toks) >= 6:
        most_common = Counter(toks).most_common(1)[0][1]
        if most_common >= max(5, int(len(toks) * 0.8)):
            return True
    if len(toks) >= 8:
        bigrams = Counter(zip(toks, toks[1:]))
        # "and then" four times in a long story is speech; the same pair making up most of a short line is a loop.
        if bigrams.most_common(1)[0][1] >= max(4, len(toks) // 4):
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
    for line in agent_lines:
        line_toks = tokens(line)
        if not line_toks:
            continue
        # A real echo repeats the agent's words IN ORDER ("am I speaking with
        # Nusrat Jahan"); a genuine answer that reuses the same words ("yes,
        # this is Nusrat speaking") shares vocabulary but not the sequence.
        if _longest_common_run(toks, line_toks) / len(toks) >= threshold:
            return True
    return False


def _longest_common_run(a: list[str], b: list[str]) -> int:
    """Length of the longest contiguous token run present in both sequences."""
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


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


# --- "I'm done" and "get me a person" ------------------------------------------------

_DONE_PHRASES = (
    "that's all", "that is all", "that's it", "that is it", "nothing else", "no thanks", "no thank you",
    "i'm good", "i am good", "i'm fine", "all set", "that's everything", "that'll be all", "that will be all",
    "nope that's", "no that's", "that was all", "i'm all set", "we're good", "thats all", "thats it",
)
_BYE_WORDS = ("bye", "goodbye", "byebye", "cheers", "thanks", "thank", "you", "no", "nope", "nah", "that's", "all", "ok", "okay")
_HUMAN_PHRASES = (
    "real person", "a person", "a human", "speak to someone", "talk to someone", "speak with someone",
    "talk with someone", "speak to a", "talk to a", "the manager", "a manager", "representative", "operator",
    "receptionist", "someone else", "a real", "staff member", "customer service", "complaint", "complain",
    "refund", "speak to the", "talk to the", "call me back", "have someone call",
)


def is_done(text: Any) -> bool:
    """The caller has nothing more ("no thanks, that's all", "bye") — not a "no" with a new request in it."""
    norm = normalize(text)
    toks = tokens(norm)
    if not toks or len(toks) > 8:
        return False
    if any(phrase in norm for phrase in _DONE_PHRASES):
        return True
    return "bye" in toks or "goodbye" in toks or all(tok in _BYE_WORDS for tok in toks)


def asks_for_human(text: Any) -> bool:
    """The caller asked for a person, a callback, or made a complaint (a transfer is justified)."""
    norm = normalize(text)
    return bool(norm) and any(phrase in norm for phrase in _HUMAN_PHRASES)


_GOODBYE_PHRASES = (
    "that's all i needed", "that is all i needed", "that's all i wanted", "that's all i need", "talk to you later",
    "have a good day", "have a nice day", "have a great day", "see you", "take care", "thank you for your time",
    "thanks for your time", "thanks anyway", "thank you anyway", "i'll look elsewhere", "i will look elsewhere",
    "thank you for your help", "thanks for your help", "thank you for checking", "thanks for checking",
)
_REFUSAL_PHRASES = (
    "rather not", "prefer not", "don't want to give", "dont want to give", "don't want to say", "dont want to say",
    "not comfortable", "won't give", "wont give", "no comment", "skip that", "skip it", "not telling", "none of your business",
    "don't want to share", "do not want to share", "i won't say", "not going to say", "not gonna say", "i'd rather keep",
    "rather get a valuation", "rather get the valuation", "rather get your valuation", "not naming", "not sure yet", "haven't decided", "have not decided", "no idea",
    "don't know yet", "dont know yet", "not ready to say", "would rather not", "prefer to wait", "rather wait",
    "before naming", "rather not guess", "not guess", "not sure about that",
)


def says_goodbye(text: Any) -> bool:
    """An explicit goodbye ("thanks, that's all I needed — bye")."""
    norm = normalize(text)
    toks = tokens(norm)
    if not toks or len(toks) > 20:
        return False
    return bool({"bye", "goodbye", "byebye"} & set(toks)) or any(phrase in norm for phrase in _GOODBYE_PHRASES)


def declines_detail(text: Any) -> bool:
    """The caller won't give what was asked ("I'd rather not say")."""
    norm = normalize(text)
    return bool(norm) and any(phrase in norm for phrase in _REFUSAL_PHRASES)


_ANOTHER_PHRASES = (
    "another appointment", "another booking", "another visit", "another one", "another viewing", "another order",
    "a second", "second one", "second appointment", "second booking", "second visit", "one more", "separate",
    "also book", "book one for", "one for my",
)
_FAMILY_RE = re.compile(r"\bfor (?:my|our) (?:husband|wife|son|daughter|mom|mum|mother|dad|father|partner|friend|kid|child|children|brother|sister|boss|colleague)\b")


def wants_another(text: Any) -> bool:
    """A new, separate request ("a second visit for my husband") — not a change to the one just made."""
    norm = normalize(text)
    return bool(norm) and (any(phrase in norm for phrase in _ANOTHER_PHRASES) or bool(_FAMILY_RE.search(norm)))


_REQUEST_WORDS = frozenset({
    "book", "booking", "order", "reserve", "reservation", "table", "cancel", "change", "move", "reschedule", "message",
    "appointment", "schedule", "buy", "rent", "sell", "selling", "need", "want", "like", "looking", "leave", "pickup",
    "delivery", "deliver", "visit", "viewing", "repair", "fix", "check", "status", "help", "speak", "talk",
})


def states_request(text: Any) -> bool:
    """The caller says what they want ("I'd like to order", "can I book …") — not just "is this the pizza place?"."""
    return bool(set(tokens(text)) & _REQUEST_WORDS)


_CHECK_PHRASES = ("is this", "is that", "are you", "am i speaking", "am i talking", "can you hear", "hello", "hi there", "anyone there")


def is_greeting_check(text: Any) -> bool:
    """"Hello? Is this the pizza place?" — checking who answered, not asking for anything."""
    norm = normalize(text)
    return bool(norm) and len(tokens(norm)) <= 8 and any(p in norm for p in _CHECK_PHRASES) and not states_request(norm)


def dialed_wrong(text: Any) -> bool:
    """An inbound caller who reached the wrong business ("sorry, wrong number")."""
    norm = normalize(text)
    return any(p in norm for p in ("wrong number", "dialed the wrong", "dialled the wrong", "misdialed", "misdialled", "called the wrong"))


_EARLIEST_PHRASES = ("first available", "earliest", "soonest", "next available", "first opening", "whichever day", "any day", "first free")


def wants_earliest(text: Any) -> bool:
    """"Whatever's first available" — the caller leaves the day to us."""
    norm = normalize(text)
    return bool(norm) and any(p in norm for p in _EARLIEST_PHRASES)


_CHANGE_WORDS = frozenset({"move", "change", "reschedule", "instead", "switch", "push", "earlier", "later", "different"})


def wants_change(text: Any) -> bool:
    """"Can you move it to Thursday instead?" — a change to something already arranged."""
    return bool(set(tokens(text)) & _CHANGE_WORDS)


_ASKING_PHRASES = (
    "just looking", "just asking", "just wanted to ask", "just wondering", "quick question", "how much", "pricing",
    "what does it cost", "what do you charge", "what's your price", "only wanted to know", "just want to know", "not booking",
)
_BOOKING_WORDS = frozenset({"book", "booking", "schedule", "appointment", "come", "visit", "reserve", "order"})


def just_asking(text: Any) -> bool:
    """A question about prices or details with no wish to book ("just looking for pricing — how much is it?")."""
    norm = normalize(text)
    if not norm or not any(p in norm for p in _ASKING_PHRASES):
        return False
    return "not booking" in norm or not (set(tokens(norm)) & _BOOKING_WORDS)


_NAME_RE = re.compile(r"(?i:\b(?:i'?m|i am|my name is|this is|it's|name's))\s+([A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)?)")
_NOT_NAMES = frozenset({"Just", "Calling", "Looking", "Not", "Sorry", "Fine", "Good", "Done", "Here", "Busy", "Interested", "Happy", "Okay", "Ok"})


def spoken_name(text: Any) -> str:
    """"I'm Emma Stone" / "my name is Emma" → the name as said (capitalised words only), else ""."""
    match = _NAME_RE.search(str(text or "").replace("\u2019", "'"))
    if not match or match.group(1).split()[0] in _NOT_NAMES:
        return ""
    return match.group(1)


_FOR_SOMEONE_RE = re.compile(
    r"(?i:\bfor (?:my|our) (?:husband|wife|son|daughter|mom|mum|mother|dad|father|partner|friend|kid|child|brother|sister|boss|colleague))"
    r"\s*,?\s*(?:named\s+|called\s+)?([A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)?)"
)


def named_other(text: Any) -> str:
    """"…for my husband, Mark Stone" → "Mark Stone" (the person a new request is for), else ""."""
    match = _FOR_SOMEONE_RE.search(str(text or "").replace("\u2019", "'"))
    return match.group(1) if match else ""
