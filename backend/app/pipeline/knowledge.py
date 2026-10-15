"""Pick the few knowledge paragraphs a turn needs instead of sending the whole text every time.

The owner's knowledge (hours, address, policies, FAQs — up to 8,000 chars) is
split once per content hash into short chunks; a turn gets the top matches by
keyword overlap (BM25-style scoring, no embeddings, microseconds) only when the
caller's words actually match something.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from functools import lru_cache

CHUNK_CHARS = 320
_WORD = re.compile(r"[\w']+", re.UNICODE)
_STOP = frozenset(
    "a an the and or but is are was were be to of in on at for with by from it this that you your we our i me my do does "
    "can could would will what when where which who how please hi hello yes no ok okay".split()
)


def words(text: str) -> list[str]:
    return [w for w in _WORD.findall(str(text or "").lower()) if w not in _STOP and len(w) > 1]


def _split(text: str) -> list[str]:
    """Paragraphs, then sentences, packed into chunks of about ``CHUNK_CHARS``."""
    chunks: list[str] = []
    for paragraph in re.split(r"\n\s*\n|\n(?=[-•*]\s)", text):
        sentences = re.split(r"(?<=[.!?।])\s+", " ".join(paragraph.split()))
        current = ""
        for sentence in sentences:
            if current and len(current) + len(sentence) + 1 > CHUNK_CHARS:
                chunks.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            chunks.append(current)
    return [chunk for chunk in chunks if chunk]


@lru_cache(maxsize=512)
def _index(digest: str, text: str) -> tuple[tuple[str, ...], tuple[Counter, ...], dict[str, int], float]:
    chunks = tuple(_split(text))
    bags = tuple(Counter(words(chunk)) for chunk in chunks)
    df: Counter = Counter()
    for bag in bags:
        df.update(bag.keys())
    avg = sum(sum(bag.values()) for bag in bags) / max(1, len(bags))
    return chunks, bags, dict(df), avg


def knowledge_digest(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def relevant(text: str, query: str, *, limit: int = 2, min_score: float = 1.0) -> list[str]:
    """Top ``limit`` chunks of ``text`` for ``query`` (empty when nothing really matches)."""
    if not text or not query:
        return []
    chunks, bags, df, avg = _index(knowledge_digest(text), text)
    terms = set(words(query))
    if not terms or not chunks:
        return []
    n = len(chunks)
    scored: list[tuple[float, int]] = []
    for index, bag in enumerate(bags):
        length = sum(bag.values()) or 1
        score = 0.0
        for term in terms:
            tf = bag.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / avg))
        if score >= min_score:
            scored.append((score, index))
    scored.sort(reverse=True)
    return [chunks[index] for _, index in scored[:limit]]


__all__ = ["knowledge_digest", "relevant", "words"]
