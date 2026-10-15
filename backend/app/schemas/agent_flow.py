"""Request bodies of the call-flow editor (owner) and the admin lock / provider screens."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentFlowSave(BaseModel):
    #: The sparse settings document (see app.pipeline.config): {"steps", "branches", "order"}.
    config: dict[str, Any] = Field(default_factory=dict)
    #: The ``hash`` the editor loaded — a stale one gets 409 instead of overwriting someone else's change.
    base_hash: str | None = None


class AgentFlowPreview(BaseModel):
    config: dict[str, Any] | None = None
    #: Preview language (default: the account's); lets an English account check its Bangla lines.
    language: str | None = None


class AgentFlowLocks(BaseModel):
    #: path → locked value; ``null`` freezes the current value.
    locks: dict[str, Any] = Field(default_factory=dict)


class ProviderOverrides(BaseModel):
    """Admin-only per-account provider chains; empty string = platform default."""

    llm_chain: str = ""
    stt_chain: str = ""
    tts_chain: str = ""


__all__ = ["AgentFlowLocks", "AgentFlowPreview", "AgentFlowSave", "ProviderOverrides"]
