"""Render the website's sample calls ("Hear it") with Deepgram Aura-2.

    cd backend && venv/bin/python -m scripts.demo_audio              # render (reuses checked turns)
    cd backend && venv/bin/python -m scripts.demo_audio --no-cache   # re-synthesise every turn

Each turn of a scripted call (``scripts/demo_audio_scripts.py``) is synthesised with the agent's
voice or that call's caller voice, then transcribed back with Deepgram STT: a take that drifts
from the script (TTS occasionally repeats or drops words) is re-synthesised. Checked turns are
cached in ``backend/.tts-cache/demo-audio`` so a re-run only pays for edited lines. Turns are
trimmed, joined with a short pause and encoded to MP3 with ffmpeg.

Writes ``frontend/public/audio/sample-<key>.mp3`` and regenerates ``frontend/lib/site/sample-calls.ts``
(transcripts, durations, line timings, waveform) so the page and the audio never drift apart. Reads
DEEPGRAM_API_KEY from the repo's ``.env``; a full uncached run costs about ten cents.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from array import array
from pathlib import Path

import httpx
from dotenv import load_dotenv

from scripts.demo_audio_scripts import AGENT_VOICE, SAMPLES, Sample

REPO = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO / "frontend" / "public" / "audio"
DATA_FILE = REPO / "frontend" / "lib" / "site" / "sample-calls.ts"
CACHE_DIR = REPO / "backend" / ".tts-cache" / "demo-audio"
SPEAK_URL = "https://api.deepgram.com/v1/speak"
LISTEN_URL = "https://api.deepgram.com/v1/listen"

RATE = 24_000  # Hz, 16-bit mono PCM from Deepgram
GAP_MS = 350  # silence between turns
LEAD_MS = 250
TAIL_MS = 500
BITRATE = "48k"
MAX_BYTES = 600 * 1024
#: Samples quieter than this at either end of a turn are trimmed (keeps every pause the same).
SILENCE = 300
#: A take whose transcript matches the script less than this is re-synthesised.
MIN_MATCH = 0.94
TAKES = 3
#: Bars in the player's waveform.
PEAKS = 60
#: Words STT adds or drops around numbers ("four hundred and eighteen" for "four eighteen").
_LOOSE_WORDS = frozenset({"and", "hundred", "uh", "um"})


def _silence(ms: int) -> bytes:
    return bytes(2 * (RATE * ms // 1000))


def _trim(pcm: bytes, pad_ms: int = 30) -> bytes:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    loud = [i for i, value in enumerate(samples) if abs(value) > SILENCE]
    if not loud:
        return pcm
    pad = RATE * pad_ms // 1000
    start, end = max(0, loud[0] - pad), min(len(samples), loud[-1] + pad)
    return pcm[start * 2 : end * 2]


def peaks(pcm: bytes, count: int = PEAKS) -> list[float]:
    """Loudness (RMS) of ``count`` equal slices of the track, scaled 0–1: the player's waveform."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    size = max(1, len(samples) // count)
    levels = []
    for index in range(count):
        chunk = samples[index * size : (index + 1) * size]
        levels.append(math.sqrt(sum(value * value for value in chunk) / len(chunk)) if chunk else 0.0)
    top = max(levels) or 1.0
    return [round(level / top, 2) for level in levels]


def _letters(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))
    return "".join(word for word in words if word not in _LOOSE_WORDS)


def match(expected: str, heard: str) -> float:
    """How closely a transcript follows the script (1.0 = same words, spacing and punctuation ignored)."""
    return difflib.SequenceMatcher(None, _letters(expected), _letters(heard)).ratio()


def _speak(client: httpx.Client, text: str, voice: str) -> bytes:
    response = client.post(
        SPEAK_URL,
        params={"model": voice, "encoding": "linear16", "sample_rate": RATE, "container": "none"},
        json={"text": text},
    )
    if response.status_code != 200 or not response.content:
        raise SystemExit(f"Deepgram speak {voice}: HTTP {response.status_code} {response.text[:200]}")
    return response.content


def _hear(client: httpx.Client, pcm: bytes) -> str:
    response = client.post(
        LISTEN_URL,
        params={"model": "nova-3", "encoding": "linear16", "sample_rate": RATE, "channels": 1},
        headers={"Content-Type": "application/octet-stream"},
        content=pcm,
    )
    if response.status_code != 200:
        raise SystemExit(f"Deepgram listen: HTTP {response.status_code} {response.text[:200]}")
    return str(response.json()["results"]["channels"][0]["alternatives"][0]["transcript"])


def take(client: httpx.Client, text: str, voice: str, *, use_cache: bool) -> bytes:
    """One checked, trimmed rendering of ``text`` (cached by voice + text)."""
    digest = hashlib.sha256(f"{voice}\n{text}".encode()).hexdigest()[:24]
    cached = CACHE_DIR / f"{digest}.pcm"
    if use_cache and cached.exists():
        return cached.read_bytes()
    best, best_score, heard = b"", -1.0, ""
    for _ in range(TAKES):
        pcm = _trim(_speak(client, text, voice))
        transcript = _hear(client, pcm)
        score = match(text, transcript)
        if score > best_score:
            best, best_score, heard = pcm, score, transcript
        if score >= MIN_MATCH:
            break
    if best_score >= MIN_MATCH:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(best)
    else:
        print(f"  warning: best take {best_score:.2f} — listen to it: {text!r} → heard {heard!r}")
    return best


def render(client: httpx.Client, sample: Sample, *, use_cache: bool) -> tuple[bytes, list[dict[str, object]]]:
    """The call as one PCM track, and each transcript line with its start time (seconds)."""
    track = bytearray(_silence(LEAD_MS))
    lines: list[dict[str, object]] = []
    for index, turn in enumerate(sample.turns):
        voice = AGENT_VOICE if turn.who == "agent" else sample.caller_voice
        if index:
            track += _silence(GAP_MS)
        lines.append({"who": turn.who, "text": turn.text, "at": round(len(track) / 2 / RATE, 2)})
        track += take(client, turn.say or turn.text, voice, use_cache=use_cache)
    track += _silence(TAIL_MS)
    return bytes(track), lines


def encode(pcm: bytes, target: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".pcm") as raw:
        raw.write(pcm)
        raw.flush()
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", raw.name,
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(RATE), "-ac", "1",
                "-c:a", "libmp3lame", "-b:a", BITRATE, "-map_metadata", "-1", str(target),
            ],
            check=True,
        )


def write_data(entries: list[dict[str, object]]) -> None:
    out = [
        "/** Sample calls for the \"Hear it\" player. GENERATED by backend/scripts/demo_audio.py — edit the",
        " * scripts in backend/scripts/demo_audio_scripts.py and re-run it, so audio and transcript stay in step. */",
        "",
        'import type { SampleCall } from "./types";',
        "",
        "export const SAMPLE_CALLS: SampleCall[] = [",
    ]
    for entry in entries:
        out.append("  {")
        for key in ("key", "vertical", "title", "business", "src", "duration", "result", "peaks"):
            out.append(f"    {key}: {json.dumps(entry[key], ensure_ascii=False)},")
        out.append("    lines: [")
        for line in entry["lines"]:  # type: ignore[union-attr]
            out.append(f"      {{ who: {json.dumps(line['who'])}, at: {line['at']}, text: {json.dumps(line['text'], ensure_ascii=False)} }},")
        out.append("    ],")
        out.append("  },")
    out.append("];")
    DATA_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.demo_audio", description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-cache", action="store_true", help="re-synthesise every turn instead of reusing checked takes")
    args = parser.parse_args(argv)
    load_dotenv(REPO / ".env")
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not key:
        raise SystemExit("DEEPGRAM_API_KEY is not set (repo .env).")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), headers={"Authorization": f"Token {key}"}) as client:
        for sample in SAMPLES:
            pcm, lines = render(client, sample, use_cache=not args.no_cache)
            target = AUDIO_DIR / f"sample-{sample.key}.mp3"
            encode(pcm, target)
            seconds = round(len(pcm) / 2 / RATE, 1)
            size = target.stat().st_size
            print(f"{target.relative_to(REPO)}: {seconds:.1f} s, {size / 1024:.0f} KB")
            if size > MAX_BYTES:
                print(f"  warning: over {MAX_BYTES // 1024} KB — shorten the script or lower BITRATE")
            entries.append({
                "key": sample.key, "vertical": sample.vertical, "title": sample.title, "business": sample.business,
                "src": f"/audio/sample-{sample.key}.mp3", "duration": seconds, "result": sample.result,
                "peaks": peaks(pcm), "lines": lines,
            })
    write_data(entries)
    print(f"{DATA_FILE.relative_to(REPO)} updated")


if __name__ == "__main__":
    main()
