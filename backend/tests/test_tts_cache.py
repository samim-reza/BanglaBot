"""Speech cache tiers: L1 memory, L2 disk + pins, L3 shared bucket, in-flight de-dup."""

import asyncio

import httpx
import pytest

from app.voice import tts_shared_cache
from app.voice.tts_cache import TTSCache
from app.voice.tts_shared_cache import SupabaseTTSStore
from app.voice.tts_tiers import TieredTTSCache


def _key(text: str) -> str:
    return TTSCache.make_key(provider="azure", voice="bn-BD-NabanitaNeural", language="bn-BD", output_format="mulaw", text=text)


def test_lru_eviction_by_entry_count(tmp_path):
    cache = TTSCache(tmp_path, max_entries=2, max_bytes=10_000)
    cache.put(_key("a"), b"aaa")
    cache.put(_key("b"), b"bbb")
    assert cache.get(_key("a")) == b"aaa"  # touch a → b is now the oldest
    cache.put(_key("c"), b"ccc")
    assert cache.get(_key("b")) is None
    assert cache.get(_key("a")) == b"aaa" and cache.get(_key("c")) == b"ccc"
    stats = cache.stats()
    assert stats["entries"] == 2 and stats["evictions"] == 1 and stats["hits"] == 3 and stats["misses"] == 1


def test_lru_eviction_by_bytes_and_manifest_survives_restart(tmp_path):
    cache = TTSCache(tmp_path, max_entries=100, max_bytes=8)
    cache.put(_key("x"), b"12345")
    cache.put(_key("y"), b"12345")  # 10 bytes > 8 → x evicted
    assert cache.get(_key("x")) is None and cache.get(_key("y")) == b"12345"
    reopened = TTSCache(tmp_path, max_entries=100, max_bytes=8)
    assert reopened.contains(_key("y")) and not reopened.contains(_key("x"))


def test_key_is_whitespace_insensitive():
    assert _key("হ্যালো   বিশ্ব") == _key(" হ্যালো বিশ্ব ")
    assert _key("a") != _key("b")


# ---------------------------------------------------------------- L1 / pins

def test_hot_layer_is_byte_bounded_and_lookup_reports_the_tier(tmp_path):
    cache = TTSCache(tmp_path, hot_max_bytes=10)
    cache.put(_key("a"), b"aaaaaa")
    cache.put(_key("b"), b"bbbbbb")  # 12 bytes > 10 → "a" leaves L1 but stays on disk
    assert cache.lookup(_key("b")) == (b"bbbbbb", "l1")
    assert cache.lookup(_key("a")) == (b"aaaaaa", "l2")
    assert cache.lookup(_key("zz")) == (None, "")
    stats = cache.stats()
    assert stats["hot_bytes"] <= 10 and stats["hot_hits"] == 1 and stats["disk_hits"] == 1


def test_pinned_keys_survive_eviction_and_restart(tmp_path):
    cache = TTSCache(tmp_path, max_entries=2)
    assert cache.pin([_key("greeting")]) == 1
    cache.put(_key("greeting"), b"g")
    cache.put(_key("x"), b"x")
    cache.put(_key("y"), b"y")  # over the limit: the oldest UNPINNED entry ("x") goes
    assert cache.contains(_key("greeting")) and not cache.contains(_key("x")) and cache.contains(_key("y"))
    reopened = TTSCache(tmp_path, max_entries=2)
    assert reopened.is_pinned(_key("greeting")) and reopened.stats()["pinned"] == 1
    reopened.clear()
    assert reopened.is_pinned(_key("greeting"))  # pins are intent, kept across clear()
    assert reopened.unpin([_key("greeting")]) == 1 and not reopened.is_pinned(_key("greeting"))


# --------------------------------------------------------------- tiered cache
class _Bucket:
    """In-memory Supabase Storage behind an httpx.MockTransport."""

    def __init__(self, *, fail: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []
        self.fail = fail

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            return httpx.Response(503)
        path = request.url.path
        if request.method == "POST":
            self.objects[path] = request.content
            return httpx.Response(200, json={"Key": path})
        if path in self.objects:
            return httpx.Response(200, content=self.objects[path])
        return httpx.Response(400, json={"statusCode": "404", "error": "not_found"})

    def store(self) -> SupabaseTTSStore:
        return SupabaseTTSStore(
            base_url="https://proj.supabase.co", secret_key="sb-secret", transport=httpx.MockTransport(self.handler)
        )


def _counting_factory(audio: bytes = b"\x10" * 400):
    calls = {"n": 0}

    async def factory() -> bytes:
        calls["n"] += 1
        return audio

    return factory, calls


async def test_get_or_create_synthesizes_once_then_hits_l1_and_l2(tmp_path):
    factory, calls = _counting_factory()
    tiers = TieredTTSCache(TTSCache(tmp_path))
    assert await tiers.get_or_create(_key("hi"), factory) == (b"\x10" * 400, "synth")
    assert (await tiers.get_or_create(_key("hi"), factory))[1] == "l1"
    restarted = TieredTTSCache(TTSCache(tmp_path))
    assert (await restarted.get_or_create(_key("hi"), factory))[1] == "l2"
    assert calls["n"] == 1
    stats = tiers.stats()
    assert stats["misses"] == 1 and stats["hits"]["l1"] == 1 and stats["synthesized"] == 1


async def test_shared_tier_uploads_in_background_and_serves_a_fresh_instance(tmp_path):
    bucket = _Bucket()
    factory, calls = _counting_factory(b"\x22" * 300)
    first = TieredTTSCache(TTSCache(tmp_path / "a"), bucket.store())
    assert (await first.get_or_create(_key("hello"), factory))[1] == "synth"
    await first.shared.drain()
    upload = next(r for r in bucket.requests if r.method == "POST")
    assert upload.url.path == f"/storage/v1/object/tts-cache/{_key('hello')}.ulaw"
    assert upload.headers["x-upsert"] == "true" and upload.headers["apikey"] == "sb-secret"
    assert upload.headers["authorization"] == "Bearer sb-secret"
    assert upload.headers["content-type"] == "application/octet-stream"

    second = TieredTTSCache(TTSCache(tmp_path / "b"), bucket.store())  # a new deploy: empty disk
    assert await second.get_or_create(_key("hello"), factory) == (b"\x22" * 300, "l3")
    assert calls["n"] == 1 and second.local.contains(_key("hello"))  # copied down to L2
    assert second.stats()["shared"]["hits"] == 1


async def test_a_broken_shared_tier_never_blocks_synthesis_and_trips_its_breaker(tmp_path):
    bucket = _Bucket(fail=True)
    tiers = TieredTTSCache(TTSCache(tmp_path), bucket.store())
    for index in range(tts_shared_cache.BREAKER_ERRORS + 2):
        factory, _ = _counting_factory()
        assert (await tiers.get_or_create(_key(f"line {index}"), factory))[1] == "synth"
    await tiers.shared.drain()
    reads = [r for r in bucket.requests if r.method == "GET"]
    assert len(reads) == tts_shared_cache.BREAKER_ERRORS  # later lookups skip the paused tier
    assert tiers.shared.available is False


async def test_concurrent_requests_share_one_synthesis(tmp_path):
    gate = asyncio.Event()
    calls = {"n": 0}

    async def slow() -> bytes:
        calls["n"] += 1
        await gate.wait()
        return b"\x30" * 160

    tiers = TieredTTSCache(TTSCache(tmp_path))
    tasks = [asyncio.create_task(tiers.get_or_create(_key("same"), slow)) for _ in range(5)]
    await asyncio.sleep(0.01)
    assert tiers.inflight() == 1
    gate.set()
    results = await asyncio.gather(*tasks)
    assert calls["n"] == 1
    assert sorted(source for _, source in results) == ["inflight"] * 4 + ["synth"]
    assert tiers.stats()["hits"]["inflight"] == 4 and tiers.inflight() == 0


async def test_cancelled_caller_still_caches_paid_audio(tmp_path):
    gate = asyncio.Event()

    async def slow() -> bytes:
        await gate.wait()
        return b"\x40" * 160

    tiers = TieredTTSCache(TTSCache(tmp_path))
    waiter = asyncio.create_task(tiers.get_or_create(_key("barge"), slow))
    await asyncio.sleep(0.01)
    waiter.cancel()  # barge-in
    with pytest.raises(asyncio.CancelledError):
        await waiter
    gate.set()
    for _ in range(50):
        if tiers.local.contains(_key("barge")):
            break
        await asyncio.sleep(0.01)
    assert tiers.local.contains(_key("barge"))


async def test_failed_synthesis_is_not_cached_and_can_be_retried(tmp_path):
    async def boom() -> bytes:
        raise RuntimeError("provider down")

    tiers = TieredTTSCache(TTSCache(tmp_path))
    with pytest.raises(RuntimeError):
        await tiers.get_or_create(_key("x"), boom)
    factory, calls = _counting_factory()
    assert (await tiers.get_or_create(_key("x"), factory))[1] == "synth" and calls["n"] == 1


def test_shared_store_is_off_without_supabase_settings(monkeypatch):
    from types import SimpleNamespace

    from app.voice.providers import tts as tts_registry

    monkeypatch.setattr(tts_registry, "get_provider_settings", lambda: SimpleNamespace(supabase_url=None, supabase_secret_key=None))
    assert tts_registry._shared_store() is None
