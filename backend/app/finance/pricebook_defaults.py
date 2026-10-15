"""Default unit prices in USD (public list prices, 2026-10 — verify before relying on them).

The admin console overrides any of these from a date on (``finance.pricebook``
in ``platform_settings``). Free tiers cost 0 but keep the paid list price as a
shadow price, so "what would this cost on a paid plan" is always answerable.
LLM SKUs are ``<model>:input|cached|output`` per 1M tokens; a model with no
``:cached`` price is charged its input price for cached tokens.
"""

from __future__ import annotations

from decimal import Decimal

from app.finance.prices import P, Price

M = 1_000_000
K = 1_000

DEFAULT_PRICES: tuple[Price, ...] = (
    # --- Telnyx: voice (TeXML), media streaming to our websocket, SMS ------------------------------
    P("telnyx", "voice_inbound", "telephony", "minute", 1, "0.0055", increment=60, note="US local inbound incl. programmable voice fee"),
    P("telnyx", "voice_outbound", "telephony", "minute", 1, "0.0070", increment=60, note="US outbound incl. programmable voice fee"),
    P("telnyx", "media_streaming", "telephony", "minute", 1, "0.0035", increment=60, note="WebSocket media streaming"),
    P("telnyx", "sms_segment", "sms", "segment", 1, "0.0055", note="US long code ~0.004 + carrier pass-through"),
    # --- Twilio: WhatsApp sender (chat channel) -----------------------------------------------------
    P("twilio", "whatsapp_message", "sms", "message", 1, "0.0050", note="per message in or out"),
    # --- Deepgram -----------------------------------------------------------------------------------
    P("deepgram", "nova-3", "stt", "minute", 1, "0.0077", note="streaming, monolingual, pay as you go"),
    P("deepgram", "nova-3-multi", "stt", "minute", 1, "0.0092", note="streaming, multilingual"),
    P("deepgram", "aura-2", "tts", "char", K, "0.030"),
    # --- Groq (free tier; shadow = paid list) --------------------------------------------------------
    P("groq", "openai/gpt-oss-120b:input", "llm", "token", M, "0.15", free=True),
    P("groq", "openai/gpt-oss-120b:cached", "llm", "token", M, "0.075", free=True),
    P("groq", "openai/gpt-oss-120b:output", "llm", "token", M, "0.60", free=True),
    P("groq", "openai/gpt-oss-20b:input", "llm", "token", M, "0.075", free=True),
    P("groq", "openai/gpt-oss-20b:cached", "llm", "token", M, "0.0375", free=True),
    P("groq", "openai/gpt-oss-20b:output", "llm", "token", M, "0.30", free=True),
    P("groq", "qwen/qwen3.8-27b:input", "llm", "token", M, "0.29", free=True, note="qwen3-32b list price"),
    P("groq", "qwen/qwen3.8-27b:output", "llm", "token", M, "0.59", free=True, note="qwen3-32b list price"),
    P("groq", "whisper-large-v3-turbo", "stt", "minute", 1, "0.000667", free=True, note="$0.04 / audio hour"),
    P("groq", "whisper-large-v3", "stt", "minute", 1, "0.00185", free=True, note="$0.111 / audio hour"),
    # --- Google Gemini (free tier; shadow = paid list) -----------------------------------------------
    P("gemini", "gemini-3.1-flash-lite:input", "llm", "token", M, "0.10", free=True),
    P("gemini", "gemini-3.1-flash-lite:cached", "llm", "token", M, "0.025", free=True),
    P("gemini", "gemini-3.1-flash-lite:output", "llm", "token", M, "0.40", free=True),
    P("gemini", "gemini-3.8-flash:input", "llm", "token", M, "0.30", free=True),
    P("gemini", "gemini-3.8-flash:cached", "llm", "token", M, "0.075", free=True),
    P("gemini", "gemini-3.8-flash:output", "llm", "token", M, "2.50", free=True),
    P("gemini", "gemini-tts", "tts", "char", M, "18.00", free=True, note="≈ audio tokens per character, preview free tier"),
    # --- OpenAI (paid) --------------------------------------------------------------------------------
    P("openai", "gpt-5.4-mini:input", "llm", "token", M, "0.25"),
    P("openai", "gpt-5.4-mini:cached", "llm", "token", M, "0.025"),
    P("openai", "gpt-5.4-mini:output", "llm", "token", M, "2.00"),
    P("openai", "gpt-4o-mini-transcribe", "stt", "minute", 1, "0.003"),
    P("openai", "gpt-4o-transcribe", "stt", "minute", 1, "0.006"),
    # --- Azure Speech ---------------------------------------------------------------------------------
    P("azure", "neural-tts", "tts", "char", M, "15.00", note="standard neural voices"),
    # --- Free engines ---------------------------------------------------------------------------------
    P("edge", "tts", "tts", "char", M, "0", free=True, note="unofficial Edge voices"),
    P("local", "tts", "tts", "char", M, "0", free=True, note="own GPU; electricity ignored"),
    P("local", "local", "stt", "minute", 1, "0", free=True, note="own GPU; electricity ignored"),
    # --- Stripe (card payments on platform links) ----------------------------------------------------
    P("stripe", "card_percent", "payment", "usd", 100, "2.9", note="2.9 % of the amount"),
    P("stripe", "card_fixed", "payment", "txn", 1, "0.30"),
)

#: TTS SKU per provider (TTS usage reports characters per provider, not per model).
TTS_SKUS = {"deepgram": "aura-2", "azure": "neural-tts", "gemini": "gemini-tts", "edge": "tts", "local": "tts"}

#: Rough USD value of one unit of a currency, for processor fees on non-USD payments.
FX_USD: dict[str, Decimal] = {
    "USD": Decimal("1"), "EUR": Decimal("1.08"), "GBP": Decimal("1.27"), "CAD": Decimal("0.73"),
    "AUD": Decimal("0.66"), "INR": Decimal("0.012"), "BDT": Decimal("0.0082"),
}

__all__ = ["DEFAULT_PRICES", "FX_USD", "TTS_SKUS"]
