from app.voice.tts_cache import TTSCache


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
