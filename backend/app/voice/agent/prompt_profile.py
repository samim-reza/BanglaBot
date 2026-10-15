"""Which request shape the model gets: ``compact`` (small per-step prompts for free tiers)
or ``cached`` (the full conversation behind a stable, cache-friendly prefix)."""

from __future__ import annotations

from typing import Any


class PromptProfileMixin:
    """Mixed into :class:`~app.voice.agent.core.CallAgent`."""

    @property
    def prompt_profile(self) -> str:
        """``compact`` (free tiers: small per-step requests) or ``cached`` (OpenAI: stable cached prefix)."""
        from app.voice.providers.settings import get_provider_settings

        chosen = get_provider_settings().llm_prompt_profile
        if chosen in ("compact", "cached"):
            return chosen
        preferred = getattr(self.llm, "preferred_profile", None)
        return preferred() if callable(preferred) else "cached"

    def _request(self, caller_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if self.prompt_profile != "compact":
            return self.messages, self.current_tools
        from app.pipeline.prompt import compact_messages, compact_tools

        messages = compact_messages(self.flow, self.runtime, self.ctx, self.messages, self.language, caller_text)
        return messages, compact_tools(self.current_tools, self.flow, self.runtime)
