"""Download the speech models (Parakeet, Kokoro, Silero) into ``speech/models``.

Usage (from ``speech/``)::

    uv run python scripts/download_models.py            # int8 always, + fp16 if an NVIDIA GPU is present
    uv run python scripts/download_models.py --precision int8
    uv run python scripts/download_models.py --check    # exit 1 if anything is missing
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.config import get_settings  # noqa: E402
from server.device import nvidia_gpu_present  # noqa: E402
from server.models import (  # noqa: E402
    PARAKEET_FILES,
    ModelPaths,
    download_kokoro,
    download_parakeet,
    download_silero,
)


def wanted_precisions(arg: str) -> list[str]:
    """``auto`` -> int8 (CPU path) plus fp16 when a GPU exists; otherwise a comma list."""
    if arg == "auto":
        return ["int8", "fp16"] if nvidia_gpu_present() else ["int8"]
    out = [p.strip() for p in arg.split(",") if p.strip()]
    bad = [p for p in out if p not in PARAKEET_FILES]
    if bad:
        raise SystemExit(f"unknown precision(s): {bad}; choose from {sorted(PARAKEET_FILES)}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--precision", default="auto", help="auto | int8 | fp16 | fp32 (comma-separated ok)")
    parser.add_argument("--check", action="store_true", help="only report what is missing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    paths = ModelPaths(get_settings().models_dir)
    precisions = wanted_precisions(args.precision)
    missing = paths.missing(precisions)
    if args.check:
        print("missing: " + (", ".join(missing) if missing else "nothing"))
        return 1 if missing else 0
    if not missing:
        print(f"all models present in {paths.root}")
        return 0

    print(f"downloading into {paths.root}: {', '.join(missing)}")
    download_silero(paths)
    download_kokoro(paths)
    for precision in precisions:
        download_parakeet(paths, precision)
    still = paths.missing(precisions)
    print("done" if not still else f"still missing: {still}")
    return 1 if still else 0


if __name__ == "__main__":
    raise SystemExit(main())
