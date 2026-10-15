"""The transport contract: what the agent needs from whoever carries the call's audio
(or text) — the phone/browser bridge or the text chat session."""

from __future__ import annotations

from typing import Any, Protocol


class Speaker(Protocol):
    """What the agent needs from a transport."""

    closed: bool
    closing: bool
    assistant_speaking: bool

    def speak(
        self,
        text: str,
        *,
        allow_barge_in: bool = True,
        message_ref: dict[str, Any] | None = None,
        close_after: bool = False,
        transfer_to: str = "",
    ) -> Any: ...

    def schedule_hangup(self) -> None: ...
