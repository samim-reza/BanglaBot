"""Answers to repeat questions, reused across calls so the same question never costs a model call twice.

Only general questions asked at the "how can I help?" step are cached ("do you take
Aetna?", "where do I park?"). The key is a hash of the account, its knowledge text,
its catalog, the language and the normalised question, so editing the knowledge or
the catalog invalidates old answers automatically. Time-sensitive questions
("are you open now?", "today", "tomorrow") are never cached. Memory LRU per process,
plus Redis (24 h) when it is connected, so all workers share answers.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import Any

from app.flows import hearing
from app.flows.context import CallContext
from app.pipeline.knowledge import knowledge_digest, words

MAX_ENTRIES = 2000
TTL_SECONDS = 24 * 3600
MIN_WORDS = 2
_TIME_SENSITIVE = re.compile(
    r"\b(now|today|tonight|tomorrow|yesterday|right now|currently|this (morning|afternoon|evening|week)|available|free|slot|my|mine|"
    r"আজ|এখন|কাল|পরশু)\b",
    re.IGNORECASE,
)
ROUTER_STAGES = frozenset({"intent", "help"})

_memory: OrderedDict[str, str] = OrderedDict()
stats = {"hits": 0, "misses": 0, "stores": 0}


def _catalog_digest(ctx: CallContext) -> str:
    rows = sorted((item.id, item.name, json.dumps(item.data, sort_keys=True, default=str)) for item in ctx.catalog)
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()[:12]


_FILLER = frozenset(
    "so um uh er well hey just also actually okay ok please tell know want wanted wondering could would can "
    "i'd i'm like quick question sir madam maam".split()
)


def normalize_question(text: str) -> str:
    """Content words in order, without conversational filler ("so, um, could you tell me …")."""
    return " ".join(w for w in words(text) if w not in _FILLER)


def _without_lead_filler(text: str) -> str:
    """"So, um, do you …" → "do you …" (so the question shape is recognised)."""
    tokens = str(text or "").split()
    while tokens and re.sub(r"[^\w']", "", tokens[0].lower()) in _FILLER:
        tokens.pop(0)
    return " ".join(tokens)


def eligible(stage: str, text: str) -> bool:
    question = normalize_question(text)
    return (
        stage in ROUTER_STAGES
        and (hearing.looks_like_question(_without_lead_filler(text)) or "?" in text)
        and len(question.split()) >= MIN_WORDS
        and not _TIME_SENSITIVE.search(text)
    )


def key_for(ctx: CallContext, language: str, text: str) -> str:
    raw = "|".join(
        (
            str(getattr(ctx.merchant, "id", "") or ""),
            knowledge_digest(str(ctx.merchant_value("knowledge", "") or "")),
            _catalog_digest(ctx),
            language,
            ctx.channel,
            normalize_question(text),
        )
    )
    return "faq:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def lookup(ctx: CallContext, stage: str, language: str, text: str) -> str:
    if not eligible(stage, text):
        return ""
    key = key_for(ctx, language, text)
    answer = _memory.get(key)
    if answer is None:
        answer = await _redis_get(key)
        if answer:
            _remember(key, answer)
    if answer:
        _memory.move_to_end(key)
        stats["hits"] += 1
        return answer
    stats["misses"] += 1
    return ""


async def store(ctx: CallContext, stage: str, language: str, text: str, answer: str) -> None:
    answer = " ".join(str(answer or "").split())
    # Answers that ask something back depend on the conversation — don't reuse them.
    if not answer or answer.endswith("?") or not eligible(stage, text):
        return
    key = key_for(ctx, language, text)
    _remember(key, answer)
    stats["stores"] += 1
    await _redis_set(key, answer)


def _remember(key: str, answer: str) -> None:
    _memory[key] = answer
    _memory.move_to_end(key)
    while len(_memory) > MAX_ENTRIES:
        _memory.popitem(last=False)


async def _redis_get(key: str) -> str:
    try:
        from app.core.redis import get_json

        value: Any = await get_json(key)
        return str(value or "")
    except Exception:  # noqa: BLE001 — the memory tier is enough
        return ""


async def _redis_set(key: str, answer: str) -> None:
    try:
        from app.core.redis import set_json

        await set_json(key, answer, ttl_seconds=TTL_SECONDS)
    except Exception:  # noqa: BLE001
        return


def clear() -> None:
    _memory.clear()
    for name in stats:
        stats[name] = 0


__all__ = ["clear", "eligible", "key_for", "lookup", "normalize_question", "stats", "store"]
