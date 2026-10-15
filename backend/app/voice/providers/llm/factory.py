"""Build the LLM for a call or chat, and warm provider connections at startup."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.voice.llm import shared_client
from app.voice.providers.llm.endpoints import Link, resolve_links
from app.voice.providers.llm.router import RoutedLLM
from app.voice.providers.settings import get_provider_settings

#: Warm this many links of the chain (primary + first fallback).
WARM_LINKS = 2


def chain_for(merchant: Any | None = None) -> list[Link]:
    """The account's chain (admin override in ``provider_settings.llm_chain``) or the platform default."""
    overrides = getattr(merchant, "provider_settings", None) or {}
    chain = overrides.get("llm_chain") if isinstance(overrides, dict) else None
    links = resolve_links(chain) if chain else []
    return links or resolve_links()


def llm_configured(merchant: Any | None = None) -> bool:
    return bool(chain_for(merchant))


def llm_for_call(
    *,
    flow_key: str,
    merchant: Any | None = None,
    channel: str = "voice",
    max_output_tokens: int | None = None,
) -> RoutedLLM:
    pset = get_provider_settings()
    merchant_id = str(getattr(merchant, "id", "") or "")
    cache_key = ":".join(part for part in (flow_key, "chat" if channel == "chat" else "", merchant_id) if part)
    return RoutedLLM(
        chain_for(merchant),
        max_output_tokens=max_output_tokens or pset.llm_max_output_tokens,
        timeout_seconds=pset.llm_timeout_seconds,
        prompt_cache_key=cache_key,
        prompt_cache_retention=get_settings().openai_prompt_cache_retention,
    )


async def warm_llm() -> None:
    """Open TLS connections to the first providers of the chain (best effort)."""
    seen: set[str] = set()
    for link in resolve_links()[:WARM_LINKS]:
        base = link.endpoint.url.rsplit("/chat/completions", 1)[0]
        if base in seen:
            continue
        seen.add(base)
        try:
            await shared_client().get(f"{base}/models", headers={"Authorization": f"Bearer {link.api_key}"}, timeout=5.0)
        except Exception:  # noqa: BLE001 — an optimization only
            continue


__all__ = ["chain_for", "llm_configured", "llm_for_call", "warm_llm"]
