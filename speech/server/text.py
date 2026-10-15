"""Split TTS text into Kokoro-sized chunks (bounded GPU memory, earlier first audio)."""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"')\]]*\s+")
_CLAUSE_END = re.compile(r"(?<=[,;:—–])\s+")

#: Kokoro's activation memory grows with output length (~20 s of audio needs ~1.3 GB); 200
#: characters is ~11 s of speech and keeps a call under ~600 MB.
MAX_CHUNK_CHARS = 200
SENTENCE_PAUSE_S = 0.25
CLAUSE_PAUSE_S = 0.1


def _pack(pieces: list[str], max_chars: int) -> list[str]:
    out: list[str] = []
    for piece in pieces:
        if out and len(out[-1]) + 1 + len(piece) <= max_chars:
            out[-1] = f"{out[-1]} {piece}"
        else:
            out.append(piece)
    return out


def _split_long(sentence: str, max_chars: int) -> list[str]:
    """Clause boundaries first, then plain word boundaries."""
    pieces: list[str] = []
    for clause in _CLAUSE_END.split(sentence):
        if len(clause) <= max_chars:
            pieces.append(clause)
        else:
            words = [w[i : i + max_chars] for w in clause.split() for i in range(0, len(w), max_chars)]
            pieces.extend(_pack(words, max_chars))
    return _pack(pieces, max_chars)


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[tuple[str, float]]:
    """``[(chunk, pause_after_seconds), ...]``; short replies stay a single chunk (one model call)."""
    text = " ".join(text.split())
    if not text:
        return []
    pieces: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        sentence = sentence.strip()
        if sentence:
            pieces.extend([sentence] if len(sentence) <= max_chars else _split_long(sentence, max_chars))
    chunks = _pack(pieces, max_chars)
    return [
        (chunk, 0.0 if i == len(chunks) - 1 else SENTENCE_PAUSE_S if chunk[-1] in ".!?…\"')" else CLAUSE_PAUSE_S)
        for i, chunk in enumerate(chunks)
    ]
