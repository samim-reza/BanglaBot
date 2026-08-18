#!/usr/bin/env python3
"""Generate Bangla TTS samples from community Coqui VITS checkpoints."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from huggingface_hub import hf_hub_download
from TTS.utils.synthesizer import Synthesizer

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models" / "community"
SAMPLES = ROOT / "samples"
TEXT = (
    "আসসালামু আলাইকুম, আমি বাংলাবট থেকে কল করছি। "
    "আপনার অর্ডারটি নিশ্চিত করতে চাই। আপনি কি অর্ডারটি রিসিভ করবেন?"
)

VOICES = [
    {
        "id": "community-emtiaz-female",
        "title": "Community VITS — EMTIAZZ Bangladeshi female",
        "engine": "Coqui VITS (CPU)",
        "size": "Coqui checkpoint ~1 GB on disk (training dump; inference is smaller)",
        "note": "Trained for Bangladeshi Bangla pronunciation. Grapheme VITS, no espeak.",
        "repo": "EMTIAZZ/bangladeshi-bangla-tts-vits",
        "weight": "pytorch_model.pth",
        "config": "config.json",
        "subdir": "emtiaz",
    },
    {
        "id": "community-bsp-female",
        "title": "Community VITS — bangla-speech-processing female",
        "engine": "Coqui VITS (CPU)",
        "size": "Coqui checkpoint ~1 GB on disk",
        "note": "Well-known Bangla female VITS (IIT Madras / Common Voice mix). MOS claimed ~4.1.",
        "repo": "bangla-speech-processing/bangla_tts_female",
        "weight": "pytorch_model.pth",
        "config": "config.json",
        "subdir": "bsp-female",
    },
    {
        "id": "community-bsp-male",
        "title": "Community VITS — bangla-speech-processing male",
        "engine": "Coqui VITS (CPU)",
        "size": "Coqui checkpoint ~1 GB on disk",
        "note": "Male counterpart of the same Bangla VITS family.",
        "repo": "bangla-speech-processing/bangla_tts_male",
        "weight": "pytorch_model.pth",
        "config": "config.json",
        "subdir": "bsp-male",
    },
]


def wav_to_mp3(wav_path: Path, mp3_path: Path, phone: bool = False) -> None:
    cmd = ["ffmpeg", "-y", "-i", str(wav_path)]
    if phone:
        cmd += ["-ar", "8000", "-ac", "1", "-af", "highpass=f=300,lowpass=f=3400"]
    cmd += ["-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def synth_one(spec: dict) -> dict:
    dest = MODELS / spec["subdir"]
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {spec['repo']} …")
    ckpt = hf_hub_download(spec["repo"], spec["weight"], local_dir=dest)
    cfg = hf_hub_download(spec["repo"], spec["config"], local_dir=dest)
    print(f"Loading {spec['id']} …")
    t_load = time.perf_counter()
    synthesizer = Synthesizer(
        tts_checkpoint=ckpt,
        tts_config_path=cfg,
        use_cuda=False,
    )
    print(f"  loaded in {time.perf_counter() - t_load:.1f}s")
    t0 = time.perf_counter()
    wav = synthesizer.tts(TEXT)
    elapsed = time.perf_counter() - t0
    wav_path = SAMPLES / f"{spec['id']}.wav"
    synthesizer.save_wav(wav, str(wav_path))
    import numpy as np

    audio = np.asarray(wav, dtype=np.float32).squeeze()
    sr = int(getattr(synthesizer, "output_sample_rate", None) or 22050)
    duration = len(audio) / sr if sr else 0
    mp3 = SAMPLES / f"{spec['id']}.mp3"
    phone = SAMPLES / f"{spec['id']}-phone.mp3"
    wav_to_mp3(wav_path, mp3)
    wav_to_mp3(wav_path, phone, phone=True)
    rtf = elapsed / duration if duration else 0
    print(f"  {duration:.2f}s audio in {elapsed:.2f}s  RTF={rtf:.2f}")
    row = dict(spec)
    row.update(
        {
            "rtf": round(rtf, 3),
            "duration": round(duration, 2),
            "mp3": mp3.name,
            "phone": phone.name,
        }
    )
    for k in ("repo", "weight", "config", "subdir"):
        row.pop(k, None)
    return row


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    manifest_path = SAMPLES / "manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        data = {"text": TEXT, "voices": []}

    existing_ids = {v["id"] for v in data.get("voices", [])}
    for spec in VOICES:
        if spec["id"] in existing_ids:
            print(f"skip existing {spec['id']}")
            continue
        try:
            row = synth_one(spec)
            data["voices"].append(row)
            manifest_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"FAILED {spec['id']}: {type(e).__name__}: {e}")
            data["voices"].append(
                {
                    "id": spec["id"],
                    "title": spec["title"],
                    "engine": spec["engine"],
                    "error": f"{type(e).__name__}: {e}",
                }
            )
            manifest_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
