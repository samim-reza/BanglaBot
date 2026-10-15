"""Repeat questions are answered from the cache — never twice from the model."""

from __future__ import annotations

import pytest

from app.flows.context import DIRECTION_INBOUND, CallContext
from app.pipeline import faq_cache
from tests.test_pipeline import DOCTORS, NOW, Account


def _ctx(knowledge: str = "We accept Aetna and Cigna.") -> CallContext:
    return CallContext(merchant=Account(knowledge=knowledge), catalog=list(DOCTORS), direction=DIRECTION_INBOUND, now=NOW)


@pytest.fixture(autouse=True)
def fresh():
    faq_cache.clear()
    yield
    faq_cache.clear()


@pytest.mark.asyncio
async def test_same_question_is_reused_and_knowledge_edits_invalidate():
    ctx = _ctx()
    await faq_cache.store(ctx, "intent", "en", "Do you take Aetna insurance?", "Yes, we accept Aetna.")
    assert await faq_cache.lookup(ctx, "intent", "en", "so, do you take Aetna insurance") == "Yes, we accept Aetna."  # same question, different words around it
    assert await faq_cache.lookup(ctx, "intent", "en", "Do you take Aetna insurance?") == "Yes, we accept Aetna."
    assert await faq_cache.lookup(_ctx("We accept Cigna only."), "intent", "en", "Do you take Aetna insurance?") == ""


@pytest.mark.asyncio
async def test_time_sensitive_and_in_flow_questions_are_never_cached():
    ctx = _ctx()
    await faq_cache.store(ctx, "intent", "en", "Are you open today?", "Yes, until 6.")
    assert await faq_cache.lookup(ctx, "intent", "en", "Are you open today?") == ""
    await faq_cache.store(ctx, "date", "en", "Does Dr Carter see kids?", "Yes, she's a pediatrician.")
    assert await faq_cache.lookup(ctx, "date", "en", "Does Dr Carter see kids?") == ""
    await faq_cache.store(ctx, "intent", "en", "Where do I park the car?", "Would you like the address?")
    assert await faq_cache.lookup(ctx, "intent", "en", "Where do I park the car?") == ""  # answers that ask back aren't reused
