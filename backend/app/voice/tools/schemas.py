"""The tool list a call's model sees."""

from __future__ import annotations

from typing import Any

import structlog

from app.voice.tools.text import END_CALL, REPLY_FIELD, SAVE_DETAILS, TRANSFER_TO_HUMAN

logger = structlog.get_logger(__name__)


class SchemasMixin:
    def schemas(self) -> list[dict[str, Any]]:
        """Tool list for this flow. Deterministic and merchant-independent, so it
        stays byte-identical across calls (part of the cached prompt prefix)."""

        def fn(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
            params: dict[str, Any] = {"type": "object", "properties": properties}
            if required:
                params["required"] = required
            return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}

        slot_props = dict(self.flow.slot_properties())
        slot_props[REPLY_FIELD] = {
            "type": "string",
            "description": (
                "Optional: ONE short sentence answering something the caller asked in this turn, in the call's "
                "language. Never the next question (the system asks it), never a promise, and never mention a "
                "detail you did not save in this same call."
            ),
        }
        tools = [
            fn(
                SAVE_DETAILS,
                "Save what the caller just told you. Call it BEFORE replying whenever the caller gives any detail, "
                "with every detail from this turn in one call. If they also asked something, put your short answer "
                "in `reply`; the system then speaks your reply and the next question itself.",
                slot_props,
            )
        ]
        for terminal in self._terminals.values():
            tools.append(fn(terminal.name, terminal.description, dict(terminal.properties)))
        extra = getattr(self.flow, "extra_tool_schemas", None)
        if extra is not None:
            tools += extra()
        tools.append(
            fn(
                TRANSFER_TO_HUMAN,
                "The caller wants to talk to a real person, or needs something you cannot handle "
                "(negotiation, a complaint, anything not in the facts).",
                {"reason": {"type": "string", "description": "Why the transfer is needed, briefly."}},
            )
        )
        tools.append(
            fn(
                END_CALL,
                "End the call: the conversation is over, the caller wants to stop or to be called later, or the "
                "instruction says so. The system speaks the goodbye.",
                {"reason": {"type": "string", "description": "Short reason (e.g. done, call later, wrong number)."}},
            )
        )
        return tools

