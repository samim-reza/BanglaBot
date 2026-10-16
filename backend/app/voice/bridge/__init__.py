"""Audio transport for one call: Telnyx media streaming (or the browser test console).

One ``CallBridge`` owns one media websocket and plugs it into a
:class:`~app.voice.agent.CallAgent`:

    caller μ-law ──▶ STT session (open_stt: local / Deepgram / Groq / OpenAI chain)
                          │ completed caller turns
                          ▼
                     CallAgent (flow + tools + LLM)
                          │ lines to speak
                          ▼
                     TTS chain (get_tts_for: μ-law 8 kHz, tier-cached) ──▶ caller

Telnyx (bidirectional RTP mode) and the browser test console speak the same
event set (``start`` / ``media`` / ``mark`` / ``clear`` / ``stop``), so a test
call exercises exactly the production path. The console uses Twilio's field
names (``streamSid``, camelCase) and also gets ``transcript`` and ``state``
events; Telnyx frames carry no stream id.

Turn design
-----------
* **Speaking** is serialized through one speaker task fed by a queue of
  ``_Utterance`` objects. Text is cut into TTS units, synthesized (two in
  flight) and paced to the caller in 20 ms frames ~0.6 s ahead of real time, so
  a ``clear`` on barge-in cuts the line within half a second. A ``mark`` after
  the last frame tells us when the caller actually finished hearing the line —
  that drives the transcript, the silence watchdog and the post-goodbye hangup.
* **Hearing** is half-duplex while the agent speaks: only *sustained* loud
  caller audio (a real interruption) reaches the STT, and that same crossing
  interrupts playback. Scripted lines (greeting, closings) are protected.
  Held-back frames are never sent, so a streaming STT that bills by audio
  duration isn't paid for the agent's own talk time (sessions keep their
  socket alive themselves, e.g. Deepgram's ``KeepAlive``); a pre-roll buffer
  flushes the start of a real interruption.
* **Caller turns** arrive as ``completed`` STT events, are merged over a short
  window (longer on steps that expect a long answer — an address, a phone
  number) and held open while the STT still hears words, filtered against echo /
  prompt echo / noise, and answered one at a time by the agent. A caller who
  keeps talking while the agent is still thinking cancels that reply and the
  text is merged; every turn is answered (hold line, deadline, recovery line).
* **Silence**: after ``silence_hangup_secs`` of idle the agent asks whether the
  caller can hear it and repeats its last question, ``voice_silence_reprompts``
  times (default 2); the next silent stretch says goodbye and the call is
  settled as ``auto_dropped`` (record → ``no_answer``, callable again).

Layout
------
``core``        ``CallBridge`` — shared state, agent views, per-call limits
``lifecycle``   run / teardown / finalize (usage), forwarded-call shortcut
``media``       media-socket loop, inbound frames, half-duplex gating, barge-in
``stt_loop``    STT connect / reconnect / events, phantom-transcript filters
``turns``       caller-turn merging and agent-turn serialization
``speaker``     speech queue, synthesis, paced playout, playback marks
``transcript``  transcript keeping + console events
``watchdog``    silence re-prompts / drop, false barge-in resume, max-duration limits
``hangup``      goodbye hangup, transfer, closing the socket / phone leg
"""

from app.voice.bridge.core import CallBridge
from app.voice.bridge.media import PREROLL_FRAMES
from app.voice.bridge.speaker import PLAYOUT_LEAD_SECONDS
from app.voice.bridge.transcript import TRANSCRIPT_SAVE_EVERY
from app.voice.bridge.turns import LONG_TURN_MERGE_SECONDS, TURN_MERGE_SECONDS

__all__ = [
    "LONG_TURN_MERGE_SECONDS",
    "PLAYOUT_LEAD_SECONDS",
    "PREROLL_FRAMES",
    "TRANSCRIPT_SAVE_EVERY",
    "TURN_MERGE_SECONDS",
    "CallBridge",
]
