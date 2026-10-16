"""End-to-end check against a running speech server (what the Callisa backend does).

Usage (from ``speech/``, server already running)::

    uv run python scripts/client_check.py [--url http://127.0.0.1:8100] [--fast]

Uses ``SPEECH_SERVER_KEY`` from the environment when set (and checks that a missing key is refused).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.codec import ulaw_to_float, write_wav_pcm16  # noqa: E402

TEXT = "Hello, this is Sunrise Clinic. Would you like to book an appointment with Dr. Rahman tomorrow at five?"
MULTI = "Thanks for calling Sunrise Clinic. Dr. Rahman has a slot tomorrow at five. Shall I book it for you?"


def ws_url(base: str) -> str:
    return base.replace("https://", "wss://").replace("http://", "ws://") + "/stt?language=en&silence_ms=600"


async def check_http(client: httpx.AsyncClient, base: str, key: str) -> bytes:
    r = await client.get(f"{base}/health")
    print("GET /health", r.status_code, json.dumps({k: v for k, v in r.json().items() if k != "voices"}))
    if key:
        r = await client.post(f"{base}/tts", json={"text": "hi"}, headers={"X-Speech-Key": ""})
        print("POST /tts without key ->", r.status_code, "(expect 401)")
    r = await client.post(f"{base}/tts", json={"text": "  "})
    print("POST /tts empty text ->", r.status_code, "(expect 400)")

    t = time.perf_counter()
    r = await client.post(f"{base}/tts", json={"text": TEXT, "voice": "female", "language": "en", "format": "ulaw8k"})
    total = (time.perf_counter() - t) * 1000
    print(f"POST /tts ulaw8k  {r.status_code} {r.headers.get('content-type')} {len(r.content)} bytes "
          f"({len(r.content) / 8000:.2f}s) in {total:.0f} ms (server synth {r.headers.get('x-first-chunk-ms')} ms)")
    ulaw = r.content

    t = time.perf_counter()
    first_ms = None
    size = 0
    async with client.stream("POST", f"{base}/tts", json={"text": MULTI, "voice": "male"}) as resp:
        async for chunk in resp.aiter_bytes():
            if first_ms is None:
                first_ms = (time.perf_counter() - t) * 1000
            size += len(chunk)
    print(f"POST /tts 3 sentences (male): first audio after {first_ms:.0f} ms, all {size / 8000:.2f}s "
          f"after {(time.perf_counter() - t) * 1000:.0f} ms")

    r = await client.post(f"{base}/tts", json={"text": "Testing PCM output.", "format": "pcm16_24k"})
    print(f"POST /tts pcm16_24k {r.status_code} {r.headers.get('content-type')} {len(r.content) / 48000:.2f}s")

    for label, body, ctype in (
        ("mu-law", ulaw, "audio/basic"),
        ("wav8k", write_wav_pcm16(ulaw_to_float(ulaw), 8000), "audio/wav"),
    ):
        t = time.perf_counter()
        r = await client.post(f"{base}/stt?language=en", content=body, headers={"Content-Type": ctype})
        print(f"POST /stt {label:6s} {r.status_code} in {(time.perf_counter() - t) * 1000:.0f} ms -> {r.json()}")
    return ulaw


async def check_ws(base: str, key: str, ulaw: bytes, realtime: bool) -> bool:
    if key:
        try:
            async with websockets.connect(ws_url(base), open_timeout=3):
                print("WS without key: accepted (UNEXPECTED)")
        except websockets.InvalidStatus as exc:
            print("WS without key -> HTTP", exc.response.status_code, "(expect 401)")
    headers = {"X-Speech-Key": key} if key else {}
    frames = [ulaw[i : i + 160] for i in range(0, len(ulaw), 160)] + [b"\xff" * 160] * 75  # +1.5 s silence
    speech_end = len(ulaw) / 8000
    got_completed = False
    async with websockets.connect(ws_url(base), additional_headers=headers, open_timeout=3) as ws:
        start = time.perf_counter()
        marks: dict[str, float] = {}

        async def reader() -> None:
            nonlocal got_completed
            async for raw in ws:
                msg = json.loads(raw)
                at = time.perf_counter() - start
                marks.setdefault(msg["type"], at)
                print(f"  WS <- {at:5.2f}s {json.dumps(msg)}")
                if msg["type"] == "completed":
                    got_completed = True
                    return

        task = asyncio.create_task(reader())
        await ws.send(json.dumps({"type": "clear"}))
        for i, frame in enumerate(frames):
            await ws.send(json.dumps({"type": "audio", "audio": base64.b64encode(frame).decode()}))
            if realtime:
                await asyncio.sleep(max(0.0, start + (i + 1) * 0.02 - time.perf_counter()))
        try:
            await asyncio.wait_for(task, timeout=10)
        except TimeoutError:
            print("  no completed event within 10 s")
    if got_completed and realtime and "speech_stopped" in marks:
        stopped, done = marks["speech_stopped"], marks["completed"]
        print(f"WS timing: speech ended at {speech_end:.2f}s, speech_stopped +{(stopped - speech_end) * 1000:.0f} ms "
              f"(silence_ms=600), completed +{(done - stopped) * 1000:.0f} ms after speech_stopped")
    return got_completed


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("SPEECH_SERVER_URL", "http://127.0.0.1:8100"))
    parser.add_argument("--fast", action="store_true", help="stream WS frames as fast as possible")
    args = parser.parse_args()
    key = os.environ.get("SPEECH_SERVER_KEY", "")
    base = args.url.rstrip("/")
    async with httpx.AsyncClient(timeout=30, headers={"X-Speech-Key": key} if key else {}) as client:
        ulaw = await check_http(client, base, key)
    ok = await check_ws(base, key, ulaw, realtime=not args.fast)
    print("CLIENT CHECK OK" if ok else "CLIENT CHECK FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
