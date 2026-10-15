"""The conversation brain of one call — independent of how audio gets in and out.

``CallAgent`` owns the prompt, the flow runtime, the tools and the model loop.
A *speaker* (the phone/browser audio bridge, or the text chat session) gives
it caller turns and speaks what it decides:

    caller text ─▶ fast path? (clean yes/no on a scripted step → no model at all)
                 └▶ model (gpt-5.4-mini + flow tools) ─▶ tools ─▶ line to speak

Turn economics: a backend-owned next line (verbatim instruction) is spoken
straight from the tool result, so a normal turn is ONE model round-trip —
and a clean yes/no on a scripted step is zero.

Modules: ``core`` (``CallAgent``: setup, directives, endings, state), ``turn``
(model ↔ tool loop), ``fast_path`` (no-model turns: scripted yes/no, Jev, FAQ
cache), ``prompt_profile`` (compact vs cached requests), ``protocol`` (``Speaker``).
"""

from app.voice.agent.core import CallAgent
from app.voice.agent.protocol import Speaker
from app.voice.agent.turn import MAX_TOOL_HOPS

__all__ = ["MAX_TOOL_HOPS", "CallAgent", "Speaker"]
