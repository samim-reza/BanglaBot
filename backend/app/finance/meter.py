"""The per-call meter: provider usage reports → priced ledger lines.

Accepts the provider layer's dicts loosely — ``RoutedLLM.stats()`` (``by_model``),
STT ``usage()`` dicts, TTS stats (per provider chars / cached chars) — and falls
back to the plain call counters (``llm_prompt_tokens``, ``tts_chars``, ...)
priced on the platform's first configured provider (lines marked
``meta.estimated``). Pure: no I/O, so the math is unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from app.finance import attribution
from app.finance.ledger import LedgerLine, totals
from app.finance.pricebook import PriceBook
from app.finance.pricebook_defaults import FX_USD
from app.finance.prices import ZERO, dec

#: A cached TTS line's length when only the number of cache hits is known.
AVG_CACHED_LINE_CHARS = 48
PHONE_DIRECTIONS = ("inbound", "outbound")
#: Directions with speech in and out (phone calls + the portal's browser voice test).
SPEECH_DIRECTIONS = ("inbound", "outbound", "web")


def _qty(value: Any) -> Decimal:
    return max(ZERO, dec(value))


def _first(row: Mapping[str, Any], *names: str) -> Decimal:
    for name in names:
        value = _qty(row.get(name))
        if value > 0:
            return value
    return ZERO


class CallMeter:
    def __init__(self, book: PriceBook, *, language: str = "", merchant: Any | None = None) -> None:
        self.book = book
        self.language = language
        self.merchant = merchant
        self.lines: list[LedgerLine] = []
        self.unpriced: list[str] = []

    # ------------------------------------------------------------------ core
    def add(
        self, category: str, provider: str, sku: str, quantity: Any, *, cache_hit: bool = False, charge: bool = True,
        list_sku: str | None = None, meta: dict[str, Any] | None = None,
    ) -> LedgerLine | None:
        """One priced line. ``charge=False``: costs nothing (a cache hit served by us);
        ``list_sku``: the list cost is that SKU's (the uncached price of a cached token)."""
        qty = _qty(quantity)
        if qty <= 0 or not provider or not sku:
            return None
        info = dict(meta or {})
        price = self.book.find(provider, sku)
        if price is None:
            self.unpriced.append(f"{provider}|{sku}")
            line = LedgerLine(category, provider, sku, "unit", qty, ZERO, ZERO, ZERO, cache_hit=cache_hit, meta={**info, "unpriced": True})
        else:
            cost, list_cost = price.cost(qty)
            rate = price.unit_rate()
            reference = self.book.find(provider, list_sku) if list_sku else None
            if reference is not None:
                list_cost = qty * reference.list_rate()
            if not charge:
                cost, rate = ZERO, ZERO
            line = LedgerLine(category, provider, sku, price.unit, qty, rate, cost, list_cost, free_tier=price.free_tier, cache_hit=cache_hit, meta=info)
        self.lines.append(line)
        return line

    # ------------------------------------------------------------------ LLM
    def add_llm(self, stats: Mapping[str, Any] | None = None, *, prompt_tokens: Any = 0, completion_tokens: Any = 0,
                cached_tokens: Any = 0, fallback: tuple[str, str] | None = None) -> None:
        rows: list[tuple[str, str, Any, Any, Any, dict[str, Any]]] = []
        by_model = stats.get("by_model") if isinstance(stats, Mapping) else None
        if isinstance(by_model, Mapping) and by_model:
            for key, row in by_model.items():
                provider, _, model = str(key).partition(":")
                if isinstance(row, Mapping):
                    rows.append((provider, model, row.get("prompt_tokens"), row.get("completion_tokens"), row.get("cached_tokens", row.get("cached_prompt_tokens")), {}))
        elif isinstance(stats, Mapping) and stats.get("provider") and stats.get("model") and (stats.get("prompt_tokens") or stats.get("completion_tokens")):
            rows.append((str(stats["provider"]), str(stats["model"]), stats.get("prompt_tokens"), stats.get("completion_tokens"), stats.get("cached_prompt_tokens"), {}))
        elif _qty(prompt_tokens) > 0 or _qty(completion_tokens) > 0:
            provider, model = fallback or attribution.default_llm(self.merchant)
            rows.append((provider, model, prompt_tokens, completion_tokens, cached_tokens, {"estimated": True}))
        for provider, model, prompt, completion, cached, meta in rows:
            prompt_q = _qty(prompt)
            cached_q = min(_qty(cached), prompt_q)
            self.add("llm", provider, f"{model}:input", prompt_q - cached_q, meta=meta)
            if cached_q > 0:
                has_cached = self.book.find(provider, f"{model}:cached") is not None
                sku = f"{model}:cached" if has_cached else f"{model}:input"
                self.add("llm", provider, sku, cached_q, cache_hit=True, list_sku=f"{model}:input", meta={**meta, "cached_tokens": True})
            self.add("llm", provider, f"{model}:output", completion, meta=meta)

    # ------------------------------------------------------------------ STT
    def add_stt(self, usages: Mapping[str, Any] | Iterable[Mapping[str, Any]] | None = None, *, fallback_seconds: Any = 0,
                fallback: tuple[str, str] | None = None) -> None:
        items = [usages] if isinstance(usages, Mapping) else list(usages or [])
        grouped: dict[tuple[str, str], Decimal] = {}
        for usage in items:
            if not isinstance(usage, Mapping) or not usage.get("provider"):
                continue
            provider = str(usage["provider"])
            model = "local" if provider == "local" else str(usage.get("model") or attribution.stt_model(provider))
            seconds = _first(usage, "billed_seconds", "audio_seconds", "streamed_seconds")
            grouped[(provider, model)] = grouped.get((provider, model), ZERO) + seconds
        if grouped:
            for (provider, model), seconds in grouped.items():
                self.add("stt", provider, model, seconds / 60, meta={"seconds": float(seconds)})
            return
        seconds = _qty(fallback_seconds)
        if seconds > 0:
            provider, model = fallback or attribution.default_stt(self.language)
            self.add("stt", provider, model, seconds / 60, meta={"seconds": float(seconds), "estimated": True})

    # ------------------------------------------------------------------ TTS
    @staticmethod
    def _tts_entries(usage: Any) -> list[tuple[str, Mapping[str, Any]]]:
        if isinstance(usage, Mapping) and isinstance(usage.get("providers"), Mapping):
            return [(str(name), row) for name, row in usage["providers"].items() if isinstance(row, Mapping)]
        if isinstance(usage, Mapping) and usage.get("provider"):
            return [(str(usage["provider"]), usage)]
        if isinstance(usage, (list, tuple)):
            return [(str(row["provider"]), row) for row in usage if isinstance(row, Mapping) and row.get("provider")]
        return []

    def add_tts(self, usage: Any = None, *, chars: Any = 0, cache_hits: Any = 0, cached_chars: Any = None,
                fallback: tuple[str, str] | None = None) -> None:
        entries = self._tts_entries(usage)
        if entries:
            for provider, row in entries:
                sku = str(row.get("sku") or attribution.tts_sku(provider))
                self.add("tts", provider, sku, row.get("chars"))
                self.add("tts", provider, sku, row.get("cached_chars"), cache_hit=True, charge=False)
            return
        if _qty(chars) <= 0 and _qty(cache_hits) <= 0 and _qty(cached_chars) <= 0:
            return
        provider, sku = fallback or attribution.default_tts(self.language)
        self.add("tts", provider, sku, chars, meta={"estimated": True})
        if cached_chars is not None:
            self.add("tts", provider, sku, cached_chars, cache_hit=True, charge=False, meta={"estimated": True})
        else:
            hits = _qty(cache_hits)
            self.add("tts", provider, sku, hits * AVG_CACHED_LINE_CHARS, cache_hit=True, charge=False,
                     meta={"estimated": True, "cache_hits": int(hits), "chars_estimated": True})

    # ------------------------------------------------------------------ telephony / SMS / fees
    def add_telephony(self, *, direction: str, seconds: Any, provider: str = "telnyx", streaming: bool = True) -> None:
        secs = _qty(seconds)
        if direction not in PHONE_DIRECTIONS or secs <= 0:
            return
        for sku in (f"voice_{direction}",) + (("media_streaming",) if streaming else ()):
            price = self.book.find(provider, sku)
            minutes = price.billed_minutes(float(secs)) if price is not None else secs / 60
            self.add("telephony", provider, sku, minutes, meta={"seconds": int(secs)})

    def add_sms(self, segments: Any, *, provider: str = "telnyx", sku: str = "sms_segment", meta: dict[str, Any] | None = None) -> None:
        self.add("sms", provider, sku, segments, meta=meta)

    def add_payment_fee(self, amount: Any, currency: str, *, provider: str = "stripe", meta: dict[str, Any] | None = None) -> None:
        info = {"amount": str(dec(amount)), "currency": currency, **(meta or {})}
        rate = FX_USD.get(str(currency or "").upper())
        if rate is not None:
            self.add("payment", provider, "card_percent", dec(amount) * rate, meta=info)
        else:
            info["fx_unknown"] = True
        self.add("payment", provider, "card_fixed", 1, meta=info)

    def totals(self) -> dict[str, Any]:
        return totals(self.lines)


def meter_call(
    book: PriceBook, *, direction: str, seconds: Any, language: str = "", counters: Mapping[str, Any] | None = None,
    llm_stats: Mapping[str, Any] | None = None, stt_usage: Any = None, tts_usage: Any = None, merchant: Any | None = None,
) -> CallMeter:
    """Every line one finished call / chat produced."""
    c = counters or {}
    meter = CallMeter(book, language=language, merchant=merchant)
    meter.add_telephony(direction=direction, seconds=seconds)
    if direction in SPEECH_DIRECTIONS:
        meter.add_stt(stt_usage, fallback_seconds=seconds)
        meter.add_tts(tts_usage, chars=c.get("tts_chars"), cache_hits=c.get("tts_cache_hits"), cached_chars=c.get("tts_cached_chars"))
    meter.add_llm(llm_stats, prompt_tokens=c.get("llm_prompt_tokens"), completion_tokens=c.get("llm_completion_tokens"), cached_tokens=c.get("llm_cached_tokens"))
    return meter


__all__ = ["AVG_CACHED_LINE_CHARS", "PHONE_DIRECTIONS", "SPEECH_DIRECTIONS", "CallMeter", "meter_call"]
