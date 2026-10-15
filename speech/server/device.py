"""ONNX Runtime device selection: CUDA when it really works, CPU otherwise."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import onnxruntime as ort

log = logging.getLogger("speech.device")

CUDA_EP = "CUDAExecutionProvider"
CPU_EP = "CPUExecutionProvider"


@lru_cache(maxsize=1)
def preload_cuda_libs() -> bool:
    """Load the pip-installed CUDA/cuDNN libraries so the CUDA EP can find them."""
    if CUDA_EP not in ort.get_available_providers():
        return False
    try:
        ort.preload_dlls()
        return True
    except Exception as exc:  # pragma: no cover - depends on the machine
        log.warning("could not preload CUDA libraries: %s", exc)
        return False


def nvidia_gpu_present() -> bool:
    """Cheap check (no ORT session): does ``nvidia-smi`` see a GPU?"""
    if not shutil.which("nvidia-smi"):
        return False
    try:
        out = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and "GPU" in out.stdout


@lru_cache(maxsize=4)
def cuda_usable(probe_model: Path) -> bool:
    """Open a tiny model on the CUDA EP and confirm ORT did not silently fall back to CPU."""
    if not nvidia_gpu_present() or not preload_cuda_libs():
        return False
    try:
        sess = ort.InferenceSession(str(probe_model), sess_options=session_options(), providers=[CUDA_EP, CPU_EP])
    except Exception as exc:  # pragma: no cover - depends on the machine
        log.warning("CUDA EP failed to initialise, using CPU: %s", exc)
        return False
    return sess.get_providers()[0] == CUDA_EP


def resolve_device(requested: str, probe_model: Path) -> str:
    """Map ``auto|cuda|cpu`` to the device that will actually be used."""
    if requested == "cpu":
        return "cpu"
    if cuda_usable(probe_model):
        return "cuda"
    if requested == "cuda":
        log.warning("SPEECH_DEVICE=cuda requested but CUDA is not usable; falling back to CPU")
    return "cpu"


def session_options(threads: int = 2) -> ort.SessionOptions:
    """Quiet session options with a bounded, non-spinning CPU thread pool.

    ORT's default pool spin-waits on every core after each run, which starves the event loop,
    the VAD and the resampler; GPU sessions only need a couple of threads for CPU-side nodes.
    """
    opts = ort.SessionOptions()
    opts.log_severity_level = 3  # errors only (memcpy-node warnings are expected with CUDA EP)
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = max(1, threads)
    opts.inter_op_num_threads = 1
    opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
    opts.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return opts


def providers_for(device: str, gpu_mem_mb: int) -> list[Any]:
    """Execution providers for ``device``; CUDA uses heuristic conv search (inputs vary in length)."""
    if device != "cuda":
        return [CPU_EP]
    cuda_opts: dict[str, Any] = {
        "device_id": 0,
        "arena_extend_strategy": "kSameAsRequested",
        "cudnn_conv_algo_search": "HEURISTIC",
        "cudnn_conv_use_max_workspace": "0",
    }
    if gpu_mem_mb > 0:
        cuda_opts["gpu_mem_limit"] = gpu_mem_mb * 1024 * 1024
    return [(CUDA_EP, cuda_opts), CPU_EP]


def cpu_threads() -> int:
    """Threads for CPU inference: physical-ish cores, leaving room for the event loop."""
    return max(1, min(8, (os.cpu_count() or 4) // 2))


def gpu_memory_mb(pid: int | None = None) -> int | None:
    """VRAM used by ``pid`` (default: this process) according to nvidia-smi, or None."""
    if not shutil.which("nvidia-smi"):
        return None
    pid = pid or os.getpid()
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[0] == str(pid) and parts[1].isdigit():
            return int(parts[1])
    return 0
