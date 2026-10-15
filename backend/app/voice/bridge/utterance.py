"""One line queued for the caller — the speaker task's unit of work."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Utterance:
    text: str
    allow_barge_in: bool = True
    message_ref: dict[str, Any] | None = None
    close_after: bool = False
    transfer_to: str = ""
    interrupted: bool = False
    spoken_text: str = ""
    done: asyncio.Event = field(default_factory=asyncio.Event)
