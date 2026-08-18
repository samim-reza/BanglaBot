"""Transparent audio cache for pipecat TTS services.

Wraps any provider's TTSService so that a line spoken before is replayed from
disk instead of re-bought from the vendor. On a hit the vendor is never
contacted, which makes repeated lines free and instant (the greeting is the
first thing every caller hears). On a miss the inner service runs unchanged
while its audio frames are copied into the cache for next time.

Correctness notes, verified against pipecat 1.7.0:

- Every service we construct (ElevenLabsHttp, Azure, Google, Gemini) runs with
  ``push_start_frame=True, push_stop_frames=True`` — the base class emits the
  started/stopped framing, so ``run_tts`` yields audio frames only and a replay
  that yields audio frames only is shaped exactly like a synthesis. If a
  service with different flags is ever wrapped, the mixin detects it and falls
  back to pass-through rather than guess at frame choreography.
- eleven_v3 is in pipecat's ELEVENLABS_CONTEXT_UNSUPPORTED_MODELS, so the
  HTTP service never sends ``previous_text`` for it — a replayed clip loses no
  prosody-continuity context.
- A partial synthesis (interruption, vendor error) is never cached: audio is
  written only when the inner generator finishes normally with no ErrorFrame.
- Word-timestamp side channels are not replayed; transcripts still assemble
  from the text frames the base class pushes.

Keying matches the lab exactly: sha256(provider, voice, model, pcm_<rate>,
normalized text) — clips bought in the lab serve live calls and vice versa.
"""

from loguru import logger
from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame

from app.voice.tts_cache import cache

_REPLAY_CHUNK = 8192  # bytes per replayed frame; transports pace regardless
_cached_classes: dict[type, type] = {}


class CachedTTSMixin:
    """Mix in front of a concrete TTSService. Inert until configured."""

    _tts_cache_identity: dict | None = None

    def configure_tts_cache(self, *, provider: str, voice_id: str, model: str) -> None:
        self._tts_cache_identity = {
            "provider": provider,
            "voice_id": voice_id,
            "model": model,
        }

    def _tts_cache_usable(self) -> bool:
        return (
            self._tts_cache_identity is not None
            # Rate is resolved from the pipeline StartFrame; without it the key
            # would be wrong, and mid-call frame shape depends on these flags.
            and bool(self.sample_rate)
            and getattr(self, "_push_start_frame", False)
            and getattr(self, "_push_stop_frames", False)
        )

    async def run_tts(self, text: str, context_id: str):
        if not self._tts_cache_usable():
            async for frame in super().run_tts(text, context_id):
                yield frame
            return

        identity = dict(self._tts_cache_identity)
        identity["output_format"] = f"pcm_{self.sample_rate}"
        key = cache.key(text, **identity)

        audio = await cache.aget(key)
        if audio is not None:
            await self.stop_ttfb_metrics()  # served locally: TTFB is now
            for i in range(0, len(audio), _REPLAY_CHUNK):
                yield TTSAudioRawFrame(
                    audio[i : i + _REPLAY_CHUNK], self.sample_rate, 1, context_id=context_id
                )
            return

        buffer = bytearray()
        clean = True
        async for frame in super().run_tts(text, context_id):
            if isinstance(frame, TTSAudioRawFrame):
                buffer.extend(frame.audio)
            elif isinstance(frame, ErrorFrame):
                clean = False
            yield frame
        # Reached only when the inner generator completed; an interruption
        # closes this generator at a yield above and skips the write.
        if clean and buffer:
            try:
                await cache.aput(key, bytes(buffer), text=text, cost_chars=len(text), **identity)
            except Exception as exc:  # noqa: BLE001 — caching must never break a call
                logger.warning(f"tts-cache: store failed for {key[:12]}…: {exc}")


def cached_class(base: type) -> type:
    """CachedX subclass of service class X, memoized."""
    cls = _cached_classes.get(base)
    if cls is None:
        cls = type(f"Cached{base.__name__}", (CachedTTSMixin, base), {})
        _cached_classes[base] = cls
    return cls
