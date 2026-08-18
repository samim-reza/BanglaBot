#!/usr/bin/env python3
"""Generate Bangla TTS listen samples from Piper bn_BD and Meta MMS-TTS-ben."""

from __future__ import annotations

import subprocess
import time
import wave
from pathlib import Path

import numpy as np
import scipy.io.wavfile
import torch
from huggingface_hub import hf_hub_download
from piper import PiperVoice, SynthesisConfig
from piper.download_voices import download_voice
from transformers import AutoTokenizer, VitsModel

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
SAMPLES = ROOT / "samples"
TEXT = (
    "আসসালামু আলাইকুম, আমি বাংলাবট থেকে কল করছি। "
    "আপনার অর্ডারটি নিশ্চিত করতে চাই। আপনি কি অর্ডারটি রিসিভ করবেন?"
)
# A few of the 16 Piper speakers so you can hear the range without 16 files.
PIPER_SPEAKERS = [0, 1, 6, 10, 15]


def wav_to_mp3(wav_path: Path, mp3_path: Path, phone: bool = False) -> None:
    cmd = ["ffmpeg", "-y", "-i", str(wav_path)]
    if phone:
        cmd += ["-ar", "8000", "-ac", "1", "-af", "highpass=f=300,lowpass=f=3400"]
    cmd += ["-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def save_float_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    audio = np.asarray(audio, dtype=np.float32).squeeze()
    peak = np.max(np.abs(audio)) or 1.0
    pcm = (audio / peak * 0.95 * 32767.0).astype(np.int16)
    scipy.io.wavfile.write(path, sample_rate, pcm)


def generate_piper() -> list[dict]:
    MODELS.mkdir(parents=True, exist_ok=True)
    print("Downloading Piper bn_BD-google-medium …")
    download_voice("bn_BD-google-medium", MODELS)
    model_path = MODELS / "bn_BD-google-medium.onnx"
    print(f"Loading {model_path}")
    voice = PiperVoice.load(model_path)

    results = []
    for spk in PIPER_SPEAKERS:
        stem = f"piper-bn_BD-google-spk{spk:02d}"
        wav_path = SAMPLES / f"{stem}.wav"
        print(f"  Piper speaker {spk} …")
        t0 = time.perf_counter()
        with wave.open(str(wav_path), "wb") as wav_file:
            voice.synthesize_wav(
                TEXT,
                wav_file,
                syn_config=SynthesisConfig(speaker_id=spk),
            )
        elapsed = time.perf_counter() - t0
        with wave.open(str(wav_path), "rb") as wav_file:
            duration = wav_file.getnframes() / float(wav_file.getframerate())
        mp3 = SAMPLES / f"{stem}.mp3"
        phone = SAMPLES / f"{stem}-phone.mp3"
        wav_to_mp3(wav_path, mp3)
        wav_to_mp3(wav_path, phone, phone=True)
        rtf = elapsed / duration if duration else 0
        print(f"    {duration:.2f}s audio in {elapsed:.2f}s  RTF={rtf:.2f}")
        results.append(
            {
                "id": stem,
                "title": f"Piper bn_BD-google medium — speaker {spk}",
                "engine": "Piper VITS ONNX (CPU)",
                "size": "~77 MB, 16 speakers, 22.05 kHz",
                "note": "Official Piper Bangladeshi Bengali voice (OpenSLR 37 + CMU Indic). Same architecture as the CPU path we talked about.",
                "rtf": round(rtf, 3),
                "duration": round(duration, 2),
                "mp3": mp3.name,
                "phone": phone.name,
            }
        )
    return results


def generate_mms() -> list[dict]:
    cache = MODELS / "hf"
    print("Loading facebook/mms-tts-ben (first run downloads ~150 MB) …")
    model = VitsModel.from_pretrained("facebook/mms-tts-ben", cache_dir=cache)
    tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-ben", cache_dir=cache)
    model.eval()
    inputs = tokenizer(TEXT, return_tensors="pt")
    torch.manual_seed(0)
    t0 = time.perf_counter()
    with torch.no_grad():
        waveform = model(**inputs).waveform
    elapsed = time.perf_counter() - t0
    audio = waveform.squeeze().cpu().numpy()
    sr = int(model.config.sampling_rate)
    duration = len(audio) / sr
    stem = "mms-tts-ben"
    wav_path = SAMPLES / f"{stem}.wav"
    save_float_wav(wav_path, audio, sr)
    mp3 = SAMPLES / f"{stem}.mp3"
    phone = SAMPLES / f"{stem}-phone.mp3"
    wav_to_mp3(wav_path, mp3)
    wav_to_mp3(wav_path, phone, phone=True)
    rtf = elapsed / duration if duration else 0
    print(f"  MMS {duration:.2f}s audio in {elapsed:.2f}s  RTF={rtf:.2f}")
    return [
        {
            "id": stem,
            "title": "Meta MMS-TTS Bengali (facebook/mms-tts-ben)",
            "engine": "Hugging Face VITS, 36M params, CPU PyTorch",
            "size": "~36M params / ~140 MB weights",
            "note": "One small VITS trained only on Bengali — this is 'Bangla extracted' the right way. License is CC-BY-NC-4.0 (non-commercial).",
            "rtf": round(rtf, 3),
            "duration": round(duration, 2),
            "mp3": mp3.name,
            "phone": phone.name,
        }
    ]


def write_manifest(rows: list[dict]) -> None:
    import json

    (SAMPLES / "manifest.json").write_text(
        json.dumps({"text": TEXT, "voices": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    rows.extend(generate_piper())
    rows.extend(generate_mms())
    write_manifest(rows)
    print("Wrote", SAMPLES / "manifest.json")


if __name__ == "__main__":
    main()
