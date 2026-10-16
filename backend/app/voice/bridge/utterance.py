"""One line queued for the caller — the speaker task's unit of work."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.voice.audio import split_sentences


@dataclass
class _Utterance:
    text: str
    allow_barge_in: bool = True
    message_ref: dict[str, Any] | None = None
    close_after: bool = False
    transfer_to: str = ""
    #: The instant ack / hold line — sound while the reply is thought out, not a reply.
    filler: bool = False
    interrupted: bool = False
    #: Cut off by the caller's barge-in (not a hangup / divert): the rest may be resumed.
    barged_in: bool = False
    spoken_text: str = ""
    done: asyncio.Event = field(default_factory=asyncio.Event)


def unheard_text(units: list[str], cut_at: int, fraction: float) -> str:
    """What the caller did not hear: the unit cut ``fraction`` of the way in, from the
    sentence that was playing, and every unit after it."""
    if cut_at >= len(units):
        return ""
    sentences = split_sentences(units[cut_at])
    total = sum(len(sentence) for sentence in sentences) or 1
    heard = 0
    start = len(sentences)
    for index, sentence in enumerate(sentences):
        if heard + len(sentence) > fraction * total:
            start = index
            break
        heard += len(sentence)
    return " ".join([*sentences[start:], *units[cut_at + 1 :]]).strip()
