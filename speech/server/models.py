"""Model file registry: where each model lives on disk and where it is downloaded from."""

from __future__ import annotations

import logging
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("speech.models")

STT_NAME = "nemo-parakeet-tdt-0.6b-v2"
TTS_NAME = "kokoro-82m-v1.0"
VAD_NAME = "silero-vad-v6"

PARAKEET_DIR = "parakeet-tdt-0.6b-v2"
# onnx-asr's official export (fp32 + int8) and a community fp16 export of the same weights.
PARAKEET_REPO = ("istupakov/parakeet-tdt-0.6b-v2-onnx", "0bbb45a3365852604aef28b538a8f066f4ccaa85")
PARAKEET_FP16_REPO = ("ysdede/parakeet-tdt-0.6b-v2-onnx", "db4a768f5795e0f508187a34241fbeeef6ebb0d3")
PARAKEET_COMMON = ("config.json", "vocab.txt")
PARAKEET_FILES: dict[str, tuple[tuple[str, str], tuple[str, ...]]] = {
    "int8": (PARAKEET_REPO, ("encoder-model.int8.onnx", "decoder_joint-model.int8.onnx")),
    "fp16": (PARAKEET_FP16_REPO, ("encoder-model.fp16.onnx", "decoder_joint-model.fp16.onnx")),
    "fp32": (PARAKEET_REPO, ("encoder-model.onnx", "encoder-model.onnx.data", "decoder_joint-model.onnx")),
}

_KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_DIR = "kokoro"
KOKORO_FILES = {
    "kokoro-v1.0.onnx": f"{_KOKORO_RELEASE}/kokoro-v1.0.onnx",
    "voices-v1.0.bin": f"{_KOKORO_RELEASE}/voices-v1.0.bin",
}

SILERO_DIR = "silero"
SILERO_FILE = "silero_vad.onnx"
SILERO_URL = "https://github.com/snakers4/silero-vad/raw/v6.2.1/src/silero_vad/data/silero_vad.onnx"


@dataclass(frozen=True)
class ModelPaths:
    """Resolved on-disk locations for every model."""

    root: Path

    @property
    def parakeet(self) -> Path:
        return self.root / PARAKEET_DIR

    @property
    def kokoro_model(self) -> Path:
        return self.root / KOKORO_DIR / "kokoro-v1.0.onnx"

    @property
    def kokoro_voices(self) -> Path:
        return self.root / KOKORO_DIR / "voices-v1.0.bin"

    @property
    def silero(self) -> Path:
        return self.root / SILERO_DIR / SILERO_FILE

    def parakeet_ready(self, precision: str) -> bool:
        """True when the config, vocab and encoder/decoder for ``precision`` exist."""
        if precision not in PARAKEET_FILES:
            return False
        names = (*PARAKEET_COMMON, *PARAKEET_FILES[precision][1])
        return all((self.parakeet / name).is_file() for name in names)

    def missing(self, precisions: list[str]) -> list[str]:
        """Human-readable list of model pieces not yet on disk."""
        out = [f"parakeet-{p}" for p in precisions if not self.parakeet_ready(p)]
        if not (self.kokoro_model.is_file() and self.kokoro_voices.is_file()):
            out.append("kokoro")
        if not self.silero.is_file():
            out.append("silero")
        return out


def download_url(url: str, dest: Path) -> None:
    """Stream ``url`` to ``dest`` atomically (``.part`` file, then rename)."""
    if dest.is_file():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    log.info("downloading %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "banglabot-speech/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as fh:  # noqa: S310 (fixed https URLs)
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        next_report = 0.0
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if total and done / total >= next_report:
                print(f"  {dest.name}: {done / 1e6:7.1f} / {total / 1e6:.1f} MB", flush=True)
                next_report += 0.25
    tmp.replace(dest)


def download_parakeet(paths: ModelPaths, precision: str) -> None:
    """Fetch the Parakeet files for one precision from Hugging Face."""
    from huggingface_hub import hf_hub_download

    (common_repo, common_rev) = PARAKEET_REPO
    (repo, rev), files = PARAKEET_FILES[precision]
    jobs = [(common_repo, common_rev, name) for name in PARAKEET_COMMON] + [(repo, rev, name) for name in files]
    paths.parakeet.mkdir(parents=True, exist_ok=True)
    for repo_id, revision, name in jobs:
        target = paths.parakeet / name
        if target.is_file():
            continue
        log.info("downloading %s/%s", repo_id, name)
        print(f"  {repo_id} :: {name}", flush=True)
        hf_hub_download(repo_id, name, revision=revision, local_dir=paths.parakeet)
    # hf_hub_download leaves a .cache folder with metadata next to the files; it is harmless but noisy.
    shutil.rmtree(paths.parakeet / ".cache", ignore_errors=True)


def download_kokoro(paths: ModelPaths) -> None:
    for name, url in KOKORO_FILES.items():
        download_url(url, paths.root / KOKORO_DIR / name)


def download_silero(paths: ModelPaths) -> None:
    download_url(SILERO_URL, paths.silero)
