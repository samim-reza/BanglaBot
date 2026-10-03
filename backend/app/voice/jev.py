"""Jev (TypeSafe's System One model): fast yes/no decisions for scripted steps.

The keyword matcher (:mod:`app.flows.hearing`) settles clean answers ("yes",
"that's right") in microseconds. Natural replies it can't settle ("yeah that
works for me", "nope, wrong day") would otherwise cost a full LLM round-trip
(~1–2 s). Jev answers a typed Choice question in ~70–500 ms for a fraction of a
cent, with a calibrated confidence: only a confident "yes" / "no" is acted on —
anything else goes to the main model as before.

Off unless ``TYPESAFE_API_KEY`` is set. Docs: https://docs.typesafe.ai/api
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

API_URL = "https://api.typesafe.ai/v1/systemone"
#: Longer replies carry more than a yes/no; the main model reads them.
MAX_WORDS = 14

YES_NO_CRITERIA = {
    "yes": "The caller clearly agrees or confirms, and asks for nothing to change or add.",
    "no": "The caller clearly declines or says it is not right, and gives no new details.",
    "other": "Anything else: a question, a change to a detail, new information, hesitation, or a mixed or unclear answer.",
}

_client: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=1.0))
    return _client


def enabled(language: str = "en") -> bool:
    # English is Jev's strongest language; Bangla stays on the keyword matcher + main model.
    return bool(get_settings().typesafe_api_key) and language == "en"


async def decide_yes_no(question: str, reply: str, *, language: str = "en") -> str | None:
    """``"yes"`` / ``"no"`` when Jev is confident the caller answered just that, else ``None``."""
    if not enabled(language):
        return None
    words = reply.split()
    if not words or len(words) > MAX_WORDS:
        return None
    settings = get_settings()
    body: dict[str, Any] = {
        "model": settings.typesafe_model,
        "state": {"agent_question": question[-600:], "caller_reply": reply[:300]},
        "questions": {
            "answer": {
                "type": "choice",
                "instructions": "On a phone call, how did the caller answer `agent_question`? Judge only `caller_reply`.",
                "criteria": YES_NO_CRITERIA,
            }
        },
    }
    started = time.monotonic()
    try:
        response = await http().post(
            API_URL,
            json=body,
            headers={"Authorization": f"Bearer {settings.typesafe_api_key}"},
            timeout=settings.typesafe_timeout_seconds,
        )
        response.raise_for_status()
        answer = (response.json().get("answers") or {}).get("answer") or {}
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("jev_unavailable", error=str(exc)[:160], ms=int((time.monotonic() - started) * 1000))
        return None
    choice = str(answer.get("choice") or "")
    confidence = float(answer.get("confidence") or 0.0)
    logger.info("jev_decision", choice=choice, confidence=round(confidence, 3), ms=int((time.monotonic() - started) * 1000))
    if choice in ("yes", "no") and confidence >= settings.typesafe_min_confidence:
        return choice
    return None


__all__ = ["decide_yes_no", "enabled"]
