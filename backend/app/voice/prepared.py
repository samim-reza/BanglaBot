"""Lines composed *before* the customer answers, so the call never waits on the model.

The confirmation question ("You ordered two shirts, total 1,250 taka, cash on
delivery — shall I confirm?") is the one line the model has to *write* rather
than the backend having a fixed phrase for. Writing it while the phone is still
ringing — one short Chat Completions call per supported language, then a TTS
warm-up — means that when the customer says "yes, speaking" the bridge can
answer from the cache in well under a second instead of running two model
round-trips and a fresh synthesis.

The store is in-process (one backend process serves the call it prepared);
entries expire after :data:`TTL_SECONDS`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.config import get_settings
from app.voice.languages import normalize_language, phrase

logger = structlog.get_logger(__name__)

TTL_SECONDS = 30 * 60
MAX_LINE_CHARS = 320

_decision_lines: dict[tuple[str, str], tuple[str, float]] = {}


@dataclass
class CallSnapshot:
    """Everything the media websocket needs the instant the call connects —
    stored when the call is placed (outbound), answered (inbound) or opened
    (browser test), so the greeting never waits on a database round-trip."""

    merchant: Any
    order: Any | None
    ctx: Any | None = None
    call_sid: str = ""
    direction: str = "outbound"
    web: bool = False
    stamp: float = field(default_factory=time.monotonic)


#: call_log_id -> snapshot
_call_snapshots: dict[str, CallSnapshot] = {}


def _get(obj: Any, name: str, default: Any = "") -> Any:
    value = getattr(obj, name, None) if obj is not None else None
    return default if value in (None, "") else value


def _prune(now: float) -> None:
    stale = [key for key, (_, stamp) in _decision_lines.items() if now - stamp > TTL_SECONDS]
    for key in stale:
        _decision_lines.pop(key, None)


def put_decision_line(order_id: str, language: str, line: str) -> None:
    now = time.monotonic()
    _prune(now)
    _decision_lines[(str(order_id), normalize_language(language))] = (line, now)


def get_decision_line(order_id: str, language: str) -> str | None:
    entry = _decision_lines.get((str(order_id), normalize_language(language)))
    if entry is None:
        return None
    line, stamp = entry
    if time.monotonic() - stamp > TTL_SECONDS:
        _decision_lines.pop((str(order_id), normalize_language(language)), None)
        return None
    return line


def put_call_snapshot(call_log_id: str, snapshot: CallSnapshot) -> None:
    now = time.monotonic()
    for key, entry in list(_call_snapshots.items()):
        if now - entry.stamp > TTL_SECONDS:
            _call_snapshots.pop(key, None)
    _call_snapshots[str(call_log_id)] = snapshot


def get_call_snapshot(call_log_id: str) -> CallSnapshot | None:
    entry = _call_snapshots.get(str(call_log_id))
    if entry is None or time.monotonic() - entry.stamp > TTL_SECONDS:
        return None
    return entry


def pop_call_snapshot(call_log_id: str) -> CallSnapshot | None:
    return _call_snapshots.pop(str(call_log_id), None)


def clear() -> None:
    _decision_lines.clear()
    _call_snapshots.clear()


def _ctx(order: Any, merchant: Any) -> Any:
    from app.flows.context import CallContext

    return CallContext(merchant=merchant, record=order)


def fallback_decision_line(flow: Any, order: Any, language: str, merchant: Any = None) -> str:
    facts = flow.order_facts(_ctx(order, merchant), language)
    return phrase("decision_fallback", language, items=facts["items"], amount=facts["amount"], cod=facts["cod"])


def _acceptable(line: str, language: str) -> bool:
    text = " ".join(str(line or "").split())
    if not text or len(text) > MAX_LINE_CHARS:
        return False
    if "?" not in text:
        return False
    if any(ch in text for ch in "*#[]{}<>"):
        return False
    return True


async def compose_decision_line(llm: Any, flow: Any, order: Any, merchant: Any, language: str) -> str:
    """Ask the model to phrase the confirmation question naturally from the order facts."""
    lang = normalize_language(language)
    facts = flow.order_facts(_ctx(order, merchant), lang)
    business = str(_get(merchant, "business_name", ""))
    if lang == "bn":
        system = (
            f"তুমি {business}-এর পক্ষ থেকে ফোন করা একজন ভদ্র কাস্টমার-কেয়ার সহকারী। "
            "কাস্টমার এইমাত্র নিশ্চিত করেছেন যে তিনিই অর্ডার দিয়েছেন। এখন তাঁকে অর্ডারটি এক থেকে দুই বাক্যে "
            "স্বাভাবিক কথ্য বাংলায় বলে জিজ্ঞেস করো তিনি অর্ডারটি কনফার্ম করবেন কি না। "
            "সম্মানসূচক \"আপনি\" ব্যবহার করো। পণ্যের কাঁচা লেখা হুবহু পড়ো না — মানুষ যেভাবে বলে সেভাবে বলো "
            "(যেমন \"শার্ট x2\" হলে \"দুইটা শার্ট\")। টাকার অংক দেওয়া কথায় হুবহু রাখো। "
            "সালাম বা পরিচয় আবার দিও না। ইমোজি, বুলেট বা উদ্ধৃতি চিহ্ন লিখো না। শুধু বলার বাক্যটুকু লেখো, আর কিছু না।"
        )
        user = f"পণ্য: {facts['items']}\nমোট দাম: {facts['amount']}\nপেমেন্ট: {facts['cod']}"
    else:
        system = (
            f"You are a polite customer-care assistant calling on behalf of {business}. "
            "The customer has just confirmed they are the person who placed the order. In one or two natural "
            "spoken sentences tell them what they ordered and the total, then ask whether they would like to "
            "confirm the order. Do not read the raw item text — say it the way a person would (\"shirt x2\" → "
            "\"two shirts\"). Keep the amount exactly as given. Do not greet or introduce yourself again. "
            "No emoji, bullets or quotation marks. Write only the sentence(s) to be spoken, nothing else."
        )
        user = f"Items: {facts['items']}\nTotal: {facts['amount']}\nPayment: {facts['cod']}"
    reply = await llm.complete([{"role": "system", "content": system}, {"role": "user", "content": user}])
    line = " ".join(str(getattr(reply, "content", "") or "").split()).strip("\"'“” ")
    if not _acceptable(line, lang):
        await logger.awarning("decision_line_rejected", language=lang, preview=line[:120])
        return fallback_decision_line(flow, order, lang, merchant)
    return line


async def prepare_call_lines(order: Any, merchant: Any, *, flow: Any | None = None, llm: Any | None = None, tts: Any | None = None) -> dict[str, str]:
    """Compose + cache-warm the confirmation question (flows that have one: e-commerce)."""
    from app.core.regions import region_of
    from app.verticals.ecommerce import DEFAULT_FLOW
    from app.voice.audio import sentence_units
    from app.voice.llm import ChatLLM
    from app.voice.tts import get_tts, normalize_persona, tts_configured, voice_for

    settings = get_settings()
    flow = flow or DEFAULT_FLOW
    if not hasattr(flow, "order_facts"):
        return {}
    order_id = str(_get(order, "id", ""))
    languages = [normalize_language(_get(merchant, "language", None))]  # one call language
    persona = normalize_persona(_get(merchant, "voice_persona", None) or settings.tts_voice_persona)
    own_llm = llm is None
    if own_llm:
        if not settings.openai_api_key:
            return {}
        llm = ChatLLM(
            api_key=settings.openai_api_key,
            model=settings.openai_llm_model,
            reasoning_effort=settings.openai_llm_reasoning_effort,
            max_output_tokens=160,
        )
    if tts is None and tts_configured():
        tts = get_tts()
    prepared: dict[str, str] = {}
    try:
        for language in languages:
            started = time.monotonic()
            try:
                line = await compose_decision_line(llm, flow, order, merchant, language)
            except Exception as exc:  # noqa: BLE001 — preparation is an optimization only
                await logger.awarning("decision_line_compose_failed", order_id=order_id, language=language, error=str(exc))
                line = fallback_decision_line(flow, order, language, merchant)
            put_decision_line(order_id, language, line)
            prepared[language] = line
            if tts is not None:
                try:
                    voice = voice_for(persona, language, region_of(merchant).accent)
                    await tts.warm(sentence_units([line]), language=language, persona=persona, voice=voice)
                except Exception as exc:  # noqa: BLE001
                    await logger.awarning("decision_line_warm_failed", order_id=order_id, language=language, error=str(exc))
            await logger.ainfo(
                "decision_line_prepared",
                order_id=order_id,
                language=language,
                ms=int((time.monotonic() - started) * 1000),
                preview=line[:100],
            )
    finally:
        if own_llm and llm is not None:
            try:
                await llm.aclose()
            except Exception:  # noqa: BLE001
                pass
    return prepared
