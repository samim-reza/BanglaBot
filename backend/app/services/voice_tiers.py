"""Voice quality tiers the merchant can pick from.

Merchants see only a rank name, a description and a price multiplier — never
the underlying vendor or model. The multiplier is the price lever: a finished
call's minutes are billed against the plan quota as duration × multiplier
(snapshotted per call, so changing tier mid-month only affects new calls).

The "static" tier is special: no AI at all — the customer hears a spoken
summary and answers by pressing keypad digits (see app/voice/static_call.py).
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceTier:
    key: str
    name_bn: str
    description_bn: str
    multiplier: float  # plan minutes consumed per real minute
    mode: str  # "static" (keypad, no AI) | "ai" (voice agent)
    provider: str  # internal only — never sent to the frontend
    model: str  # internal only (TTS model, or Azure neural voice name)
    sort_order: int
    # UI grouping. "speaker" = named Bengali voices the merchant picks by
    # sound; "quality" = keypad / quality ranks. Never expose the vendor.
    group: str = "quality"
    gender: str = ""  # "female" | "male" | ""
    accent_bn: str = ""


TIERS: dict[str, VoiceTier] = {
    tier.key: tier
    for tier in (
        VoiceTier(
            key="static",
            name_bn="স্ট্যাটিক কল",
            description_bn="এআই কথা বলে না — বার্তা শুনে কাস্টমার বাটন চাপবেন (১ = নিশ্চিত, ২ = বাতিল)",
            multiplier=0.5,
            mode="static",
            provider="static",
            model="",
            sort_order=0,
        ),
        VoiceTier(
            key="nabanita",
            name_bn="নবনীতা",
            description_bn="নরম ও স্পষ্ট মহিলা কণ্ঠ — বাংলাদেশি বাংলা",
            multiplier=1.0,
            mode="ai",
            provider="azure",
            model="bn-BD-NabanitaNeural",
            sort_order=1,
            group="speaker",
            gender="female",
            accent_bn="বাংলাদেশ",
        ),
        VoiceTier(
            key="pradeep",
            name_bn="প্রদ্বীপ",
            description_bn="স্পষ্ট পুরুষ কণ্ঠ — বাংলাদেশি বাংলা",
            multiplier=1.0,
            mode="ai",
            provider="azure",
            model="bn-BD-PradeepNeural",
            sort_order=2,
            group="speaker",
            gender="male",
            accent_bn="বাংলাদেশ",
        ),
        VoiceTier(
            key="tanishaa",
            name_bn="তানিশা",
            description_bn="নরম মহিলা কণ্ঠ — ভারতীয় বাংলা",
            multiplier=1.0,
            mode="ai",
            provider="azure",
            model="bn-IN-TanishaaNeural",
            sort_order=3,
            group="speaker",
            gender="female",
            accent_bn="ভারত",
        ),
        VoiceTier(
            key="bashkar",
            name_bn="ভাস্কর",
            description_bn="স্পষ্ট পুরুষ কণ্ঠ — ভারতীয় বাংলা",
            multiplier=1.0,
            mode="ai",
            provider="azure",
            model="bn-IN-BashkarNeural",
            sort_order=4,
            group="speaker",
            gender="male",
            accent_bn="ভারত",
        ),
        # Azure Dragon HD Omni. Only bn-IN has HD voices — there is no bn-BD HD
        # pair, so these are Indian Bengali only. Billed at Azure's HD rate
        # ($22/1M chars vs $16 for neural) — see COSTS.md §3a.
        VoiceTier(
            key="tanishaa_hd",
            name_bn="তানিশা এইচডি",
            description_bn="আরও প্রাণবন্ত ও স্বাভাবিক মহিলা কণ্ঠ — ভারতীয় বাংলা",
            multiplier=1.25,
            mode="ai",
            provider="azure",
            model="bn-IN-Tanishaa:DragonHDOmniLatestNeural",
            sort_order=5,
            group="speaker",
            gender="female",
            accent_bn="ভারত",
        ),
        VoiceTier(
            key="bashkar_hd",
            name_bn="ভাস্কর এইচডি",
            description_bn="আরও প্রাণবন্ত ও স্বাভাবিক পুরুষ কণ্ঠ — ভারতীয় বাংলা",
            multiplier=1.25,
            mode="ai",
            provider="azure",
            model="bn-IN-Bashkar:DragonHDOmniLatestNeural",
            sort_order=6,
            group="speaker",
            gender="male",
            accent_bn="ভারত",
        ),
        # Google Cloud Chirp 3 HD ($30/1M chars). bn-IN only — Google has no
        # bn-BD locale.
        VoiceTier(
            key="aoede",
            name_bn="অদিতি",
            description_bn="উষ্ণ ও বন্ধুত্বপূর্ণ মহিলা কণ্ঠ — ভারতীয় বাংলা",
            multiplier=1.5,
            mode="ai",
            provider="google",
            model="bn-IN-Chirp3-HD-Aoede",
            sort_order=7,
            group="speaker",
            gender="female",
            accent_bn="ভারত",
        ),
        VoiceTier(
            key="puck",
            name_bn="পার্থ",
            description_bn="প্রাণবন্ত ও স্পষ্ট পুরুষ কণ্ঠ — ভারতীয় বাংলা",
            multiplier=1.5,
            mode="ai",
            provider="google",
            model="bn-IN-Chirp3-HD-Puck",
            sort_order=8,
            group="speaker",
            gender="male",
            accent_bn="ভারত",
        ),
        VoiceTier(
            key="very_basic",
            name_bn="খুব সাধারণ",
            description_bn="দ্রুত ও সাশ্রয়ী এআই ভয়েস — প্রতিদিনের কনফার্মেশন কলের জন্য",
            multiplier=1.0,
            mode="ai",
            provider="gemini",
            model="gemini-2.5-flash-preview-tts",
            sort_order=9,
        ),
        VoiceTier(
            key="basic",
            name_bn="বেসিক",
            description_bn="আরও পরিষ্কার উচ্চারণ ও টোন",
            multiplier=1.5,
            mode="ai",
            provider="gemini",
            model="gemini-2.5-pro-preview-tts",
            sort_order=10,
        ),
        VoiceTier(
            key="good",
            name_bn="ভালো রিজনিং",
            description_bn="স্মার্ট কথোপকথন ও আরও প্রাকৃতিক কণ্ঠ",
            multiplier=2.0,
            mode="ai",
            provider="gemini",
            model="gemini-3.1-flash-tts-preview",
            sort_order=11,
        ),
        VoiceTier(
            key="advance",
            name_bn="অ্যাডভান্স",
            description_bn="সবচেয়ে প্রাকৃতিক প্রিমিয়াম ভয়েস — মানুষের মতো কথা",
            multiplier=2.5,
            mode="ai",
            provider="elevenlabs",
            # eleven_v3 is the ONLY ElevenLabs model that speaks Bengali —
            # multilingual_v2 / flash_v2_5 / turbo_v2_5 don't list it. Don't
            # "optimize" this to a cheaper model.
            model="eleven_v3",
            sort_order=12,
        ),
    )
}

DEFAULT_TIER_KEY = "very_basic"

# Keys from the first (3-tier) catalog, still present on old call-log snapshots
# and any merchant row bootstrap hasn't remapped yet.
LEGACY_ALIASES = {"standard": "very_basic", "better": "basic", "best": "advance"}


def get_tier(key: str | None) -> VoiceTier:
    key = LEGACY_ALIASES.get(key or "", key or "")
    return TIERS.get(key, TIERS[DEFAULT_TIER_KEY])


def is_valid_tier(key: str) -> bool:
    return key in TIERS


def billed_seconds(duration_secs: int, tier_key: str | None) -> int:
    """Plan-quota seconds a finished call consumes under its tier."""
    if duration_secs <= 0:
        return 0
    return math.ceil(duration_secs * get_tier(tier_key).multiplier)


def public_catalog() -> list[dict]:
    """What the frontend sees: rank names, mode and pricing — no vendor names."""
    return [
        {
            "key": tier.key,
            "name_bn": tier.name_bn,
            "description_bn": tier.description_bn,
            "multiplier": tier.multiplier,
            "mode": tier.mode,
            "group": tier.group,
            "gender": tier.gender,
            "accent_bn": tier.accent_bn,
        }
        for tier in sorted(TIERS.values(), key=lambda t: t.sort_order)
    ]
