"""Traffic simulator for the TTS cache: answers "what happens at 10k calls/day".

Drives the real cache engine (same code path live calls use) with statistically
realistic traffic — zipf-weighted names, per-merchant catalogs, repeat
customers, four voice tiers — but a synthetic vendor, so it costs nothing and
runs a multi-day volume in about a minute per simulated day.

Audio is fake but correctly *sized* (~2,133 bytes per Bengali character at
pcm_16000, per COSTS.md's 900 chars/minute), so storage growth, eviction
pressure and lookup latency are measured against real files on the real disk,
through the real SQLite manifest. Amount texts use a length-faithful (not
linguistically perfect) Bangla number-to-words; what matters here is that each
distinct amount is a distinct, realistically sized string.

The last simulated day can start with a file wipe (manifest kept) to measure
the disaster case: how much a lost cache actually costs and how fast traffic
rebuilds it organically.
"""

import shutil
import statistics
import tempfile
import time
from hashlib import blake2b
from pathlib import Path
from random import Random

from app.voice.tts_cache import TTSCache

BYTES_PER_CHAR = 2133  # pcm_16000 at ~900 Bengali chars/minute
PAD_BYTES = 9600  # ~300 ms lead/tail silence per clip

# ── pools (weights follow rank^-0.8, roughly how BD names distribute) ───────

_MALE = """রহিম করিম আব্দুল্লাহ হাসান হোসেন ইব্রাহিম রফিক শফিক জামাল কামাল আরিফ শরীফ সাইফুল রুবেল
সোহেল রাসেল মাসুদ মাহমুদ ফারুক মামুন সুমন লিটন মিলন শামীম নাঈম তানভীর তৌহিদ ইমরান শাকিল সজীব
রাকিব সাকিব জাহিদ শাহেদ মেহেদী পারভেজ ফয়সাল নাসির মনির জুয়েল বাবু আলমগীর জসিম নয়ন রিপন
আশরাফ মোস্তফা ইউসুফ ইসমাইল খালেদ""".split()
_FEMALE = """ফাতেমা আয়েশা খাদিজা মরিয়ম রহিমা করিমা সালমা শাহানা রাবেয়া হালিমা নাসরিন শিরিন পারভীন
ইয়াসমিন শারমিন রুমা ঝুমা রিমা সীমা নাজমা রুনা মুন্নী শাপলা শিউলি রোজিনা তাসলিমা ফারজানা
সাবিনা রুবিনা তানিয়া সোনিয়া মৌসুমী শবনম লাবণী পপি লিপি শিল্পী বৃষ্টি মিতু ঋতু""".split()
_SURNAME = """উদ্দিন আহমেদ হোসেন ইসলাম রহমান আলী খান মিয়া শেখ চৌধুরী তালুকদার সরকার মোল্লা
হাওলাদার ব্যাপারী মজুমদার ভূঁইয়া কাজী সিকদার প্রামাণিক আক্তার বেগম খাতুন বানু সুলতানা""".split()
_ITEM = """পাঞ্জাবি শাড়ি থ্রি-পিস টি-শার্ট পোলো-শার্ট হুডি জিন্স প্যান্ট বোরকা হিজাব ওড়না লুঙ্গি
ফতুয়া কুর্তি লেহেঙ্গা ব্লাউজ শার্ট শাল সোয়েটার জ্যাকেট""".split()
_COLOR = "লাল নীল সাদা কালো সবুজ হলুদ গোলাপি বেগুনি খয়েরি ছাই আকাশি কমলা".split()
_SHOP = """ফ্যাশন হাউস বুটিকস কালেকশন গ্যালারি এম্পোরিয়াম ফেব্রিকস স্টাইল ক্লথিং মার্ট বাজার""".split()

_DIGIT_WORDS = "শূন্য এক দুই তিন চার পাঁচ ছয় সাত আট নয়".split()
_TENS_WORDS = "  বিশ ত্রিশ চল্লিশ পঞ্চাশ ষাট সত্তর আশি নব্বই".split(" ")


def _bn_words(n: int) -> str:
    """Length-faithful Bangla words for an amount (deterministic per value)."""
    if n >= 1000:
        rest = n % 1000
        head = _bn_words(n // 1000) + " হাজার"
        return head if not rest else f"{head} {_bn_words(rest)}"
    if n >= 100:
        rest = n % 100
        head = _DIGIT_WORDS[n // 100] + "শ"
        return head if not rest else f"{head} {_bn_words(rest)}"
    if n >= 10:
        return (_TENS_WORDS[n // 10] + (_DIGIT_WORDS[n % 10] if n % 10 else "")).strip()
    return _DIGIT_WORDS[n]


def _zipf_pick(rng: Random, items: list, s: float = 0.8):
    weights = [1 / (rank + 1) ** s for rank in range(len(items))]
    return rng.choices(items, weights=weights, k=1)[0]


def _fake_pcm(text: str) -> bytes:
    """Deterministic pseudo-audio, sized like real pcm_16000 speech."""
    size = len(text) * BYTES_PER_CHAR + PAD_BYTES
    seed = blake2b(text.encode(), digest_size=32).digest()
    return (seed * (size // 32 + 1))[:size]


# The four voice tiers merchants actually spread across (COSTS.md mix).
_TIERS = [
    ("azure", "bn-BD-NabanitaNeural", "", 0.30),
    ("azure", "bn-BD-PradeepNeural", "", 0.20),
    ("gemini", "Kore", "gemini-2.5-flash-preview-tts", 0.35),
    ("elevenlabs", "EXAVITQu4vr4xnSDxMaL", "eleven_v3", 0.15),
]

_FIXED_LINES = [
    "আপনি কি",
    "বলছেন?",
    "আপনার অর্ডার,",
    "মোট",
    "টাকা, ক্যাশ অন ডেলিভারি।",
    "আপনি কি অর্ডারটি নিশ্চিত করছেন?",
    "ধন্যবাদ! আপনার অর্ডারটি নিশ্চিত করা হয়েছে। ভালো থাকবেন।",
    "ঠিক আছে, আপনার অর্ডারটি বাতিল করা হয়েছে। ধন্যবাদ।",
    "আপনাকে একজন প্রতিনিধির সাথে সংযোগ দেওয়া হচ্ছে, একটু লাইনে থাকুন।",
    "আপনাকে শুনতে পাচ্ছি না, তাই কলটি রাখছি। পরে আবার কল করা হবে, ধন্যবাদ।",
]


class _Merchant:
    def __init__(self, rng: Random, idx: int):
        first = rng.choice(_MALE + _FEMALE)
        self.shop = f"{first} {rng.choice(_SHOP)}"
        tiers, weights = zip(*[(t[:3], t[3]) for t in _TIERS])
        self.provider, self.voice, self.model = rng.choices(tiers, weights=weights, k=1)[0]
        self.catalog = []
        for _ in range(rng.randint(30, 80)):
            item = f"{rng.choice(_COLOR)} {rng.choice(_ITEM)}"
            base = rng.choice([290, 390, 490, 590, 790, 990, 1190, 1490, 1990, 2490, 2990, 3990])
            self.catalog.append((item, base))
        self.customers: list[str] = []
        self.greeting = f"আসসালামু আলাইকুম, আমি {self.shop}-এর পক্ষ থেকে বলছি।"

    def customer(self, rng: Random) -> str:
        if self.customers and rng.random() < 0.45:
            return _zipf_pick(rng, self.customers)
        if rng.random() < 0.5:
            name = f"{_zipf_pick(rng, _MALE)} {_zipf_pick(rng, _SURNAME)}"
            if rng.random() < 0.35:
                name = "মোঃ " + name
        else:
            name = f"{_zipf_pick(rng, _FEMALE)} {_zipf_pick(rng, _SURNAME)}"
        self.customers.append(name)
        return name


def run_simulation(
    calls_per_day: int = 10_000,
    days: int = 4,
    cap_mb: int = 1024,
    wipe_last_day: bool = True,
    merchants: int = 150,
    seed: int = 7,
    workdir: str | None = None,
) -> dict:
    rng = Random(seed)
    root = Path(workdir) if workdir else Path(tempfile.gettempdir()) / "banglabot-tts-sim"
    shutil.rmtree(root, ignore_errors=True)
    cache = TTSCache(
        root / "blobs", manifest_path=root / "manifest.db", max_bytes=cap_mb * 1024 * 1024
    )

    shops = [_Merchant(rng, i) for i in range(merchants)]
    shop_weights = [1 / (i + 1) ** 0.6 for i in range(merchants)]

    def lookup(merchant: _Merchant, kind: str, text: str, day_row: dict, latencies: list) -> None:
        key = cache.key(
            text,
            provider=merchant.provider,
            voice_id=merchant.voice,
            model=merchant.model,
            output_format="pcm_16000",
        )
        started = time.perf_counter()
        audio = cache.get(key)
        latencies.append(time.perf_counter() - started)
        day_row["lookups"] += 1
        day_row["chars_spoken"] += len(text)
        if audio is None:
            clip = _fake_pcm(text)
            cache.put(
                key, clip, text=text,
                provider=merchant.provider, voice_id=merchant.voice, model=merchant.model,
                output_format="pcm_16000", cost_chars=len(text),
                pin=(kind in ("fixed", "greeting")),
            )
            day_row["chars_bought"] += len(text)
            day_row["bytes_bought"] += len(clip)
            day_row["buys"][kind] = day_row["buys"].get(kind, 0) + 1
        else:
            day_row["hits"] += 1

    report_days = []
    wiped_info = None
    for day in range(1, days + 1):
        if wipe_last_day and day == days:
            # Disaster: every audio file deleted, manifest survives.
            removed = 0
            for shard in (root / "blobs").iterdir():
                if shard.is_dir():
                    for blob in shard.iterdir():
                        blob.unlink()
                        removed += 1
                    shard.rmdir()
            sweep = cache.sweep()
            wiped_info = {
                "files_deleted": removed,
                "sweep_found_missing": sweep["newly_missing"],
                "rebuildable_clips": sweep["rebuildable_clips"],
                "proactive_rebuild_cost_chars": sweep["rebuild_cost_chars"],
            }

        row = {"day": day, "calls": calls_per_day, "lookups": 0, "hits": 0,
               "chars_spoken": 0, "chars_bought": 0, "bytes_bought": 0, "buys": {}}
        latencies: list[float] = []
        evictions_before = cache.stats()["evictions"]
        wall = time.perf_counter()

        for _ in range(calls_per_day):
            shop = rng.choices(shops, weights=shop_weights, k=1)[0]
            name = shop.customer(rng)
            item, base = _zipf_pick(rng, shop.catalog)
            amount = _bn_words(base * rng.choices([1, 2, 3], weights=[8, 2, 1], k=1)[0])
            outcome = rng.choices([6, 7, 8, 9], weights=[78, 12, 6, 4], k=1)[0]
            script = [
                ("greeting", shop.greeting),
                ("fixed", _FIXED_LINES[0]), ("name", name), ("fixed", _FIXED_LINES[1]),
                ("fixed", _FIXED_LINES[2]), ("product", item), ("fixed", _FIXED_LINES[3]),
                ("amount", f"{amount} টাকা"), ("fixed", _FIXED_LINES[4]),
                ("fixed", _FIXED_LINES[5]), ("fixed", _FIXED_LINES[outcome]),
            ]
            for kind, text in script:
                lookup(shop, kind, text, row, latencies)

        stats = cache.stats()
        lat_ms = sorted(x * 1000 for x in latencies)
        row.update(
            hit_rate=round(row["hits"] / row["lookups"], 4),
            buy_ratio_chars=round(row["chars_bought"] / row["chars_spoken"], 4),
            evictions=stats["evictions"] - evictions_before,
            resident_mb=round(stats["bytes"] / 1024 / 1024, 1),
            resident_clips=stats["clips"],
            get_ms_p50=round(statistics.median(lat_ms), 3),
            get_ms_p95=round(lat_ms[int(len(lat_ms) * 0.95)], 3),
            get_ms_p99=round(lat_ms[int(len(lat_ms) * 0.99)], 3),
            sim_seconds=round(time.perf_counter() - wall, 1),
        )
        report_days.append(row)

    final = cache.stats()
    cache.close()
    total_spoken = sum(d["chars_spoken"] for d in report_days)
    total_bought = sum(d["chars_bought"] for d in report_days)
    return {
        "params": {
            "calls_per_day": calls_per_day, "days": days, "cap_mb": cap_mb,
            "wipe_last_day": wipe_last_day, "merchants": merchants, "seed": seed,
            "workdir": str(root),
        },
        "days": report_days,
        "wipe": wiped_info,
        "totals": {
            "chars_spoken": total_spoken,
            "chars_bought": total_bought,
            "chars_saved_pct": round(100 * (1 - total_bought / total_spoken), 2),
            "bytes_bought_mb": round(sum(d["bytes_bought"] for d in report_days) / 1024**2, 1),
            "resident_mb": round(final["bytes"] / 1024**2, 1),
            "resident_clips": final["clips"],
            "evictions": final["evictions"],
        },
    }
