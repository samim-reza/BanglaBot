"""Local tiers of the synthesized-speech cache: L1 memory + L2 disk LRU.

Every fixed line the agent speaks (greeting, "are you still there?", working
phrase, goodbye, recaps that repeat word for word) is synthesized **once** and
replayed from here, so the same sentence is never billed to the TTS provider
twice. Entries are keyed by provider + voice + language + output format + the
normalized text, stored as raw audio files on disk, and evicted least-recently
-used first when either the entry count or the byte budget is exceeded.

* **L1** is a byte-bounded in-memory LRU of the hottest lines (no disk, no
  thread hop, safe to read on the event loop).
* **L2** is the disk LRU. Its index is an insertion-ordered dict (oldest first)
  persisted to ``manifest.json`` so hits survive a restart.
* **Pinned** keys (an account's fixed call-flow lines) are never evicted from
  L2; pins are persisted in the manifest too.

The shared L3 tier (Supabase Storage) and in-flight de-duplication live in
:mod:`app.voice.tts_tiers`. All file I/O is small and synchronous; the async
wrappers hand it to a thread so the call loop never blocks on disk.

Modules: ``core`` (``TTSCache``: L1 / L2 LRU, pins, stats, async API) and ``manifest``
(index persistence).
"""

from app.voice.tts_cache.core import HOT_MAX_BYTES, HOT_MAX_ENTRIES, TTSCache, normalize_text
from app.voice.tts_cache.manifest import MANIFEST_NAME, MANIFEST_SAVE_INTERVAL

__all__ = ["HOT_MAX_BYTES", "HOT_MAX_ENTRIES", "MANIFEST_NAME", "MANIFEST_SAVE_INTERVAL", "TTSCache", "normalize_text"]
