"""Speech providers without a network: codecs, VAD, STT sessions, TTS engines, chains.

REST providers run against ``httpx.MockTransport``; streaming providers get a
fake websocket. Nothing here talks to a real service or a database.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
from array import array
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.voice import codec
from app.voice.providers.base import ProviderUnavailable
from app.voice.providers.stt import health
from app.voice.providers.stt.deepgram import DeepgramSTT
from app.voice.providers.stt.groq import GroqWhisperSTT, is_noise
from app.voice.providers.stt.local import LocalSTT
from app.voice.providers.stt.vad import EnergyVAD
from app.voice.providers.tts.azure import OUTPUT_FORMAT, AzureTTS
from app.voice.providers.tts.base import CachedTTSEngine, TTSError, TTSUnavailable
from app.voice.providers.tts.deepgram import DeepgramTTS
from app.voice.providers.tts.fallback import FallbackTTS
from app.voice.providers.tts.gemini import GeminiTTS
from app.voice.providers.tts.local import LocalTTS
from app.voice.tts_cache import TTSCache
from app.voice.tts_tiers import TieredTTSCache


@pytest.fixture(autouse=True)
def _fresh_health():
    health.reset()
    yield
    health.reset()


def _sine_pcm(ms: int, amp: int, rate: int = 8000, freq: float = 300.0) -> bytes:
    return array("h", [int(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(rate * ms // 1000)]).tobytes()


def _tone(ms: int, amp: int = 6000) -> bytes:
    return codec.pcm16_to_ulaw(_sine_pcm(ms, amp))


def _silence(ms: int) -> bytes:
    return b"\xff" * (8 * ms)


def _frames_b64(ulaw: bytes) -> list[str]:
    return [base64.b64encode(ulaw[i : i + 160]).decode() for i in range(0, len(ulaw), 160)]


def _zero_crossings(pcm: bytes) -> int:
    s = array("h", pcm)
    return sum(1 for a, b in zip(s, s[1:]) if (a < 0) != (b < 0))


# ------------------------------------------------------------------ codec
def test_ulaw_round_trip_and_reference_values():
    for byte in range(256):
        linear = codec.ULAW_TO_LINEAR[byte]
        assert codec.ULAW_TO_LINEAR[codec.linear_to_ulaw(linear)] == linear
    assert codec.linear_to_ulaw(0) == 0xFF and codec.linear_to_ulaw(32767) == 0x80 and codec.linear_to_ulaw(-32768) == 0x00
    pcm = _sine_pcm(100, 8000)
    assert len(codec.pcm16_to_ulaw(pcm)) == len(pcm) // 2
    assert len(codec.ulaw_to_pcm16(codec.pcm16_to_ulaw(pcm))) == len(pcm)


@pytest.mark.parametrize("resample", [codec.resample_pcm16, codec._resample_python], ids=["miniaudio", "python"])
def test_resample_keeps_speech_band_and_length(resample):
    out = resample(_sine_pcm(500, 8000, rate=24000, freq=440), 24000, 8000)
    assert abs(len(out) // 2 - 4000) <= 40
    assert abs(_zero_crossings(out) - 440) <= 12  # 440 Hz survives (2 crossings per cycle × 0.5 s)


def test_python_resampler_filters_what_8k_cannot_carry():
    out = codec._resample_python(_sine_pcm(300, 8000, rate=24000, freq=6000), 24000, 8000)
    rms = math.sqrt(sum(v * v for v in array("h", out)) / (len(out) // 2))
    assert rms < 800  # a 6 kHz tone would alias to 2 kHz without the low-pass


def test_wav_and_mime_helpers():
    pcm = _sine_pcm(50, 1000)
    assert codec.read_wav(codec.wav_bytes(pcm, 8000)) == (pcm, 8000)
    assert codec.l16_rate("audio/L16;codec=pcm;rate=24000") == 24000 and codec.l16_rate("audio/L16") == 24000
    assert codec.b64_decoded_len(base64.b64encode(b"x" * 161).decode()) == 161


# ------------------------------------------------------------------ VAD
def test_vad_cuts_one_utterance_with_preroll_and_hangover():
    events = EnergyVAD().push(_silence(500) + _tone(600) + _silence(1000))
    assert [e.type for e in events] == ["start", "end"]
    assert 0.6 <= events[1].seconds <= 1.2


def test_vad_discards_short_bursts_and_handles_odd_chunks():
    assert [e.type for e in EnergyVAD().push(_silence(300) + _tone(100) + _silence(1000))] == ["start", "discard"]
    audio = _silence(400) + _tone(500) + _silence(900)
    vad = EnergyVAD()
    events = [e for i in range(0, len(audio), 97) for e in vad.push(audio[i : i + 97])]
    assert [e.type for e in events] == ["start", "end"]


def test_vad_adapts_to_steady_line_noise():
    vad = EnergyVAD()
    vad.push(_tone(3000, amp=900))  # a hum: may trip once while the floor learns it
    assert not [e for e in vad.push(_tone(2000, amp=900)) if e.type == "start"]


# ------------------------------------------------------------- fake socket
class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def send(self, message) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        self.closed = True
        await self.inbox.put(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.inbox.get()
        if item is None:
            raise StopAsyncIteration
        return item

    def json_sent(self) -> list[dict]:
        return [json.loads(m) for m in self.sent if isinstance(m, str)]


def _connector(socket: FakeSocket, seen: dict):
    async def connect(url, **kwargs):
        seen["url"], seen["headers"] = url, kwargs.get("additional_headers")
        return socket

    return connect


async def _drain(session, count: int):
    events = []
    async for event in session.events():
        events.append(event)
        if len(events) >= count:
            break
    return events


# --------------------------------------------------------------- Deepgram STT
async def test_deepgram_stt_url_audio_and_utterance_events():
    socket, seen = FakeSocket(), {}
    stt = DeepgramSTT(api_key="dg-key", language="en", keyterms=["Demo Clinic", "Dr. Rahman", "demo clinic"], connector=_connector(socket, seen))
    await stt.connect()
    query = parse_qs(urlparse(seen["url"]).query)
    assert query["encoding"] == ["mulaw"] and query["sample_rate"] == ["8000"] and query["model"] == ["nova-3"]
    assert query["keyterm"] == ["Demo Clinic", "Dr. Rahman"] and query["language"] == ["en"]
    assert seen["headers"] == {"Authorization": "Token dg-key"}
    await stt.send_audio_b64(base64.b64encode(b"\x7f" * 160).decode())
    assert socket.sent[-1] == b"\x7f" * 160 and stt.usage()["audio_seconds"] == 0.02

    for message in (
        {"type": "SpeechStarted"},
        {"type": "Results", "is_final": False, "channel": {"alternatives": [{"transcript": "hello"}]}},
        {"type": "Results", "is_final": True, "speech_final": False, "channel": {"alternatives": [{"transcript": "hello there"}]}},
        {"type": "Results", "is_final": True, "speech_final": True, "channel": {"alternatives": [{"transcript": "how are you"}]}},
        {"type": "UtteranceEnd"},
    ):
        await socket.inbox.put(json.dumps(message))
    events = await _drain(stt, 5)
    assert [e.type for e in events] == ["speech_started", "delta", "delta", "speech_stopped", "completed"]
    assert events[-1].text == "hello there how are you"
    await stt.close()
    assert {"type": "CloseStream"} in socket.json_sent() and socket.closed


async def test_deepgram_stt_utterance_end_flushes_and_non_english_skips_keyterms():
    socket, seen = FakeSocket(), {}
    stt = DeepgramSTT(api_key="k", language="es", keyterms=["Demo"], connector=_connector(socket, seen))
    await stt.connect()
    assert "keyterm" not in parse_qs(urlparse(seen["url"]).query)
    assert stt.translate({"type": "Results", "is_final": True, "channel": {"alternatives": [{"transcript": "sure"}]}})[0].type == "speech_started"
    events = stt.translate({"type": "UtteranceEnd"})
    assert [(e.type, e.text) for e in events] == [("speech_stopped", ""), ("completed", "sure")]
    await stt.close()


async def test_deepgram_stt_keepalive_and_finalize_when_audio_stops():
    socket = FakeSocket()
    stt = DeepgramSTT(api_key="k", language="en", keepalive_seconds=0.05, tick_seconds=0.02, connector=_connector(socket, {}))
    await stt.connect()
    stt.translate({"type": "Results", "is_final": False, "channel": {"alternatives": [{"transcript": "half a sen"}]}})
    stt._last_audio -= 1.0  # the bridge stopped forwarding (agent speaking)
    await asyncio.sleep(0.15)
    kinds = [m["type"] for m in socket.json_sent()]
    assert "Finalize" in kinds and "KeepAlive" in kinds
    await stt.close()


async def test_deepgram_stt_finalizes_when_the_caller_goes_quiet():
    # Telnyx keeps streaming the caller's silence, so waiting for Deepgram's endpointing took seconds.
    from app.voice.codec import linear_to_ulaw

    socket = FakeSocket()
    stt = DeepgramSTT(api_key="k", language="en", end_silence_ms=600, connector=_connector(socket, {}))
    await stt.connect()
    speech, quiet = bytes([linear_to_ulaw(6000)]) * 160, b"\xff" * 160
    for frame in [speech] * 20 + [quiet] * 25:
        await stt.send_audio_b64(base64.b64encode(frame).decode())
    assert "Finalize" not in [m["type"] for m in socket.json_sent()]  # 0.5 s of quiet: a pause, not the end
    for frame in [quiet] * 6:
        await stt.send_audio_b64(base64.b64encode(frame).decode())
    assert [m["type"] for m in socket.json_sent()].count("Finalize") == 1
    await stt.close()


# ------------------------------------------------------------------ Groq STT
def _scripted_transport(responses: list[httpx.Response], seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses.pop(0)

    return httpx.MockTransport(handler)


async def test_groq_stt_transcribes_vad_utterances():
    seen: list[httpx.Request] = []
    body = {"text": " Yes, confirm it. ", "segments": [{"avg_logprob": -0.3}]}
    stt = GroqWhisperSTT(api_key="gq", language="en", prompt="Demo Shop.", transport=_scripted_transport([httpx.Response(200, json=body)], seen))
    await stt.connect()
    for frame in _frames_b64(_silence(400) + _tone(700) + _silence(900)):
        await stt.send_audio_b64(frame)
    events = await asyncio.wait_for(_drain(stt, 3), timeout=2)
    assert [(e.type, e.text) for e in events] == [("speech_started", ""), ("speech_stopped", ""), ("completed", "Yes, confirm it.")]
    request = seen[0]
    assert request.url.path == "/openai/v1/audio/transcriptions" and request.headers["authorization"] == "Bearer gq"
    for needle in (b"whisper-large-v3-turbo", b"verbose_json", b'name="language"', b"Demo Shop.", b"RIFF"):
        assert needle in request.content
    usage = stt.usage()
    assert usage["requests"] == 1 and usage["billed_seconds"] == 10.0 and 0.7 <= usage["audio_seconds"] < 2
    await stt.close()


async def test_groq_stt_drops_noise_and_pauses_on_quota():
    assert is_noise([{"avg_logprob": -1.1}, {"avg_logprob": -1.2}]) and not is_noise([{"avg_logprob": -1.1}, {"avg_logprob": -0.5}])
    seen: list[httpx.Request] = []
    responses = [httpx.Response(200, json={"text": "Thank you.", "segments": [{"avg_logprob": -1.15}]}), httpx.Response(429, text="rate limit")]
    stt = GroqWhisperSTT(api_key="gq", language="en", transport=_scripted_transport(responses, seen))
    await stt.connect()
    assert await stt.transcribe(_tone(800)) == "" and stt.dropped_noise == 1
    with pytest.raises(RuntimeError):
        await stt.transcribe(_tone(800))
    assert health.is_down("groq")
    events = await asyncio.wait_for(_drain(stt, 1), timeout=1)
    assert events[0].type == "closed"  # the bridge reconnects → next provider in the chain
    await stt.close()


# ------------------------------------------------------------------ local STT
async def test_local_stt_contract():
    socket, seen = FakeSocket(), {}
    stt = LocalSTT(base_url="https://gpu.example.com/", key="sk", language="en", prompt="Yes.", connector=_connector(socket, seen))
    await stt.connect()
    url = urlparse(seen["url"])
    assert url.scheme == "wss" and url.path == "/stt" and parse_qs(url.query)["language"] == ["en"]
    assert seen["headers"] == {"X-Speech-Key": "sk"}
    await stt.send_audio_b64("AAAA")
    await stt.clear_input()
    assert socket.json_sent() == [{"type": "audio", "audio": "AAAA"}, {"type": "clear"}]
    for message in ({"type": "speech_started"}, {"type": "partial", "text": "yes"}, {"type": "completed", "text": "yes sure", "audio_seconds": 1.2}):
        await socket.inbox.put(json.dumps(message))
    events = await _drain(stt, 3)
    assert [(e.type, e.text) for e in events] == [("speech_started", ""), ("delta", "yes"), ("completed", "yes sure")]
    assert stt.usage()["billed_seconds"] == 0.0
    await stt.close()


async def test_speech_server_probe_is_cached():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True, "device": "cuda"})

    transport = httpx.MockTransport(handler)
    assert await health.speech_server_healthy("http://gpu.local:9000", "k", transport=transport)
    assert await health.speech_server_healthy("http://gpu.local:9000", "k", transport=transport)
    assert calls["n"] == 1 and health.speech_server_info("http://gpu.local:9000")["device"] == "cuda"
    assert not await health.speech_server_healthy(None)


# --------------------------------------------------------------- STT registry
class FakeSession:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name, self.fail, self.closed = name, fail, False

    async def connect(self) -> None:
        if self.fail:
            raise ConnectionError("refused")

    async def close(self) -> None:
        self.closed = True


async def test_open_stt_walks_the_chain(monkeypatch):
    from app.voice.providers import stt as registry

    built: list[FakeSession] = []

    def provider(name: str, *, configured: bool = True, fail: bool = False):
        def build(language, prompt, keyterms):
            session = FakeSession(name, fail)
            built.append(session)
            return session

        return registry.STTProvider(name, lambda: configured, build)

    monkeypatch.setattr(
        registry,
        "PROVIDERS",
        {"local": provider("local"), "deepgram": provider("deepgram", configured=False), "groq": provider("groq", fail=True), "openai": provider("openai")},
    )

    async def local_down() -> bool:
        return False

    monkeypatch.setattr(registry, "_local_ready", local_down)
    session = await registry.open_stt(language="en", chain=["local", "deepgram", "groq", "openai"])
    assert session.name == "openai"
    assert [s.name for s in built] == ["groq", "openai"] and built[0].closed
    assert health.is_down("groq")  # a failed connect pauses it for the next call
    with pytest.raises(ProviderUnavailable):
        await registry.open_stt(language="en", chain=["deepgram", "groq"])


# --------------------------------------------------------------- TTS engines
def _tiers(tmp_path) -> TieredTTSCache:
    return TieredTTSCache(TTSCache(tmp_path))


def _recording(content: bytes, seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=content)

    return httpx.MockTransport(handler)


async def test_deepgram_tts_request_and_voices(tmp_path):
    seen: list[httpx.Request] = []
    tts = DeepgramTTS(api_key="dg", cache=_tiers(tmp_path), transport=_recording(b"\x55" * 800, seen))
    assert await tts.synthesize("Hello there.", language="en", persona="male") == b"\x55" * 800
    assert dict(seen[0].url.params) == {"model": "aura-2-orion-en", "encoding": "mulaw", "sample_rate": "8000", "container": "none"}
    assert seen[0].headers["authorization"] == "Token dg" and json.loads(seen[0].content) == {"text": "Hello there."}
    assert tts.resolve_voice(voice="en-GB-SoniaNeural", persona="female", language="en") == "aura-2-pandora-en"
    assert tts.supports("en")
    assert (await tts.synthesize_ex("Hello there.", language="en", persona="male"))[1] == "l1" and len(seen) == 1


async def test_gemini_tts_decodes_l16_and_falls_back_to_second_model(tmp_path):
    seen: list[httpx.Request] = []
    pcm24 = _sine_pcm(300, 8000, rate=24000)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "lite" in request.url.path:
            return httpx.Response(404, json={"error": "model not found"})
        part = {"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm24).decode()}}
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [part]}}]})

    tts = GeminiTTS(api_key="gm", cache=_tiers(tmp_path), transport=httpx.MockTransport(handler))
    audio = await tts.synthesize("Shall I confirm your order?", language="en", persona="female")
    assert abs(len(audio) - 2400) <= 30  # 0.3 s at 8 kHz, one byte per sample
    body = json.loads(seen[-1].content)
    assert body["contents"][0]["parts"][0]["text"] == "Shall I confirm your order?"  # bare text, no "Say:"
    assert body["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert seen[0].headers["x-goog-api-key"] == "gm" and "gemini-3.8-flash-tts" in seen[-1].url.path


async def test_gemini_auth_error_is_unavailable(tmp_path):
    transport = httpx.MockTransport(lambda request: httpx.Response(403, json={"error": "denied"}))
    with pytest.raises(TTSUnavailable):
        await GeminiTTS(api_key="bad", cache=_tiers(tmp_path), transport=transport).synthesize("Hi.", language="en")


async def test_azure_tts_keeps_legacy_cache_keys_and_ssml(tmp_path):
    seen: list[httpx.Request] = []
    tts = AzureTTS(key="az", region="southeastasia", cache=_tiers(tmp_path), transport=_recording(b"\x66" * 320, seen))
    await tts.synthesize("Hello", language="en", persona="female")
    assert b'<voice name="en-US-AvaNeural">' in seen[0].content
    assert seen[0].headers["x-microsoft-outputformat"] == OUTPUT_FORMAT
    legacy = TTSCache.make_key(provider="azure", voice="en-US-AvaNeural", language="en-US", output_format=OUTPUT_FORMAT, text="Hello", extra="0%")
    assert tts.key_for("Hello", language="en", persona="female") == legacy


async def test_local_tts_posts_persona_and_format(tmp_path):
    seen: list[httpx.Request] = []
    probe = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    tts = LocalTTS(base_url="http://gpu:9000", key="sk", cache=_tiers(tmp_path), transport=_recording(b"\x77" * 160, seen), probe_transport=probe)
    assert await tts.synthesize("Hello.", language="en", persona="male", voice="en-US-AndrewNeural") == b"\x77" * 160
    assert json.loads(seen[0].content) == {"text": "Hello.", "voice": "male", "language": "en", "format": "ulaw8k"}
    assert seen[0].headers["x-speech-key"] == "sk"


# ------------------------------------------------------------- fallback chain
class ScriptedEngine(CachedTTSEngine):
    def __init__(self, name: str, cache: TieredTTSCache, *, fail: Exception | None = None, languages=None) -> None:
        super().__init__(cache=cache)
        self.name = name
        self.fail = fail
        self.languages = languages
        self.calls = 0

    def resolve_voice(self, *, voice, persona, language):
        return f"{self.name}-{persona or 'female'}"

    async def render(self, text, *, voice, language):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return self.name.encode() * 10


async def test_fallback_order_breaker_and_recovery(tmp_path):
    cache = _tiers(tmp_path)
    now = {"t": 1000.0}
    first = ScriptedEngine("first", cache, fail=TTSError("boom"))
    second = ScriptedEngine("second", cache)
    chain = FallbackTTS([first, second], cache=cache, error_threshold=2, cooldown_seconds=60, clock=lambda: now["t"])
    assert (await chain.synthesize_ex("one", language="en"))[1] == "second"
    assert (await chain.synthesize_ex("two", language="en"))[1] == "second"
    assert chain.is_open("first") and first.calls == 2
    await chain.synthesize("three", language="en")
    assert first.calls == 2  # benched: not even tried
    now["t"] += 61
    first.fail = None
    assert (await chain.synthesize_ex("four", language="en"))[1] == "first" and not chain.is_open("first")
    stats = chain.stats()
    assert stats["fallbacks"] == 3 and stats["providers"]["second"]["requests"] == 3
    assert stats["providers"]["first"]["errors"] == 2 and stats["providers"]["first"]["trips"] == 1


async def test_fallback_quota_benches_immediately_and_all_benched_still_tries(tmp_path):
    cache = _tiers(tmp_path)
    first = ScriptedEngine("first", cache, fail=TTSUnavailable("429"))
    second = ScriptedEngine("second", cache, fail=TTSError("down"))
    chain = FallbackTTS([first, second], cache=cache, error_threshold=1)
    with pytest.raises(TTSError):
        await chain.synthesize("hello", language="en")
    assert chain.is_open("first") and chain.is_open("second")
    second.fail = None
    assert await chain.synthesize("hello", language="en") == b"second" * 10  # half-open retry


async def test_fallback_skips_unsupported_language_and_serves_cache(tmp_path):
    cache = _tiers(tmp_path)
    spanish_only = ScriptedEngine("spanish", cache, languages=frozenset({"es"}))
    anything = ScriptedEngine("any", cache)
    chain = FallbackTTS([spanish_only, anything], cache=cache)
    assert (await chain.synthesize_ex("Okay.", language="en"))[1:] == ("any", "synth")
    assert spanish_only.calls == 0 and not chain.is_open("spanish")
    assert chain.is_cached("Okay.", language="en")
    assert (await chain.synthesize_ex("Okay.", language="en"))[2] == "l1" and anything.calls == 1
    assert chain.pin_lines(["Hello."], language="en", persona="female") == 1  # one key per English-capable engine
    assert await chain.warm(["Okay.", "Anything else?"], language="en", persona="female") == 1


# ------------------------------------------------------------------ registry
async def test_get_tts_for_uses_the_platform_chain(monkeypatch, tmp_path):
    from app.voice import tts as tts_shim
    from app.voice.providers import tts as registry

    registry.reset_registry(_tiers(tmp_path))
    monkeypatch.setattr(registry, "get_provider_settings", lambda: SimpleNamespace(tts_chain="alpha,beta,ghost"))
    monkeypatch.setattr(
        registry,
        "FACTORIES",
        {"alpha": lambda c: ScriptedEngine("alpha", c), "beta": lambda c: ScriptedEngine("beta", c), "ghost": lambda c: None},
    )
    try:
        english = registry.get_tts_for("en")
        assert english.chain == ["alpha", "beta"] and registry.get_tts_for("en") is english
        assert registry.get_tts_for(None) is english
        assert await tts_shim.get_tts().synthesize("Hi.", language="en") == b"alpha" * 10
        assert tts_shim.tts_configured("en")
        monkeypatch.setattr(registry, "get_provider_settings", lambda: SimpleNamespace(tts_chain="ghost"))
        assert not registry.tts_available("en")
        with pytest.raises(TTSError):
            registry.get_tts_for("en")
    finally:
        registry.reset_registry()
