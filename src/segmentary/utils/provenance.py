"""Run provenance: which commit, which libraries, which GPUs, how much memory.

Separated from results.py because this file only *observes* the machine, while
results.py owns the record format. The observations are all best-effort: a
missing git binary or nvidia-smi degrades to a recorded ``None``/``"unknown"``
rather than killing a training run at the moment it tries to save its numbers.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import torch

# Distribution names, not import names: importlib.metadata reads installed
# metadata, so this stays cheap and does not import the packages themselves.
_TRACKED_PACKAGES = (
    "segmentary",
    "torch",
    "torchvision",
    "transformers",
    "timm",
    "segmentation-models-pytorch",
    "albumentations",
    "lightning",
    "numpy",
)

_SUBPROCESS_TIMEOUT_S = 10.0


def discover_git_root(candidates: Iterable[str | os.PathLike[str]]) -> Path | None:
    """Find the first Git worktree containing one of ``candidates``.

    Command-line runs may come from an installed wheel, so ``__file__`` points
    at site-packages rather than at the user's experiment.  Config paths are the
    most reliable ownership signal; callers normally append ``Path.cwd()`` as a
    fallback.  Missing candidates are skipped and absence of Git remains a
    supported, pessimistically recorded state.
    """
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            path = path.parent
        if not path.is_dir():
            continue
        root = _git(path, "rev-parse", "--show-toplevel")
        if root:
            return Path(root).resolve()
    return None


def git_sha(repo: str | os.PathLike[str]) -> tuple[str, bool]:
    """Return ``(sha, dirty)`` for the repo, or ``("unknown", True)``.

    Provenance is best-effort by design: a missing git binary, an export without
    a .git directory, or a fresh repo with no commits must not abort a training
    run. The fallback is deliberately pessimistic -- an unknown commit is also
    reported dirty, so nothing downstream mistakes it for a reproducible build.
    Untracked files count as dirty, since a new module changes behaviour just as
    much as an edited one.
    """
    path = Path(repo)
    if not path.is_dir():
        return ("unknown", True)
    sha = _git(path, "rev-parse", "HEAD")
    if not sha:
        return ("unknown", True)
    status = _git(path, "status", "--porcelain")
    return (sha, status is None or status != "")


def _git(repo: Path, *args: str) -> str | None:
    """Run a read-only git command, returning None if git cannot answer."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # git absent or unrunnable; caller degrades to "unknown"
    if proc.returncode != 0:
        return None  # not a repo, or no commits yet
    return proc.stdout.strip()


def _package_versions() -> dict[str, str | None]:
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, str | None] = {}
    for name in _TRACKED_PACKAGES:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = None  # genuinely not installed; absence is the fact worth recording
    return out


def _driver_version() -> str | None:
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip().splitlines()[0].strip()


def collect_env() -> dict[str, Any]:
    """Capture the interpreter, CUDA stack and library versions of this run.

    Unlike ``peak_vram``, this initialises CUDA (``get_device_name`` forces the
    lazy init), so it must not run before ``seed_everything(deterministic=True)``
    -- that call refuses to proceed once cuBLAS can no longer see
    CUBLAS_WORKSPACE_CONFIG. Call it at record time, not at startup.
    """
    cuda_available = torch.cuda.is_available()
    return {
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version() if cuda_available else None,
        "driver_version": _driver_version(),
        "cuda_available": cuda_available,
        "gpu_count": torch.cuda.device_count() if cuda_available else 0,
        "gpu_names": (
            [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
            if cuda_available
            else []
        ),
        # Records which physical GPUs the visible-device indices actually meant.
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "packages": _package_versions(),
    }


def peak_vram() -> dict[str, int]:
    """Peak *reserved* bytes per visible CUDA device, keyed ``"cuda:i"``.

    Reserved, not allocated: the caching allocator hands back freed blocks only
    to itself, so allocated is always the smaller number and reporting it as
    "peak VRAM" understates what the run actually needs to fit. Reserved is the
    high-water mark that decides whether a config OOMs on a smaller card. It
    still excludes the ~0.5 GB CUDA context, so nvidia-smi reads slightly higher.

    Querying an untouched device does not create a context on it, so this is
    safe to call on a 10-GPU box from a job that only uses one.
    """
    if not torch.cuda.is_available():
        return {}
    return {
        f"cuda:{i}": int(torch.cuda.max_memory_reserved(i))
        for i in range(torch.cuda.device_count())
    }


def reset_peak_vram() -> None:
    """Rebase the per-device peak counters onto current usage.

    torch resets the peak to what is reserved *now*, not to zero, so memory the
    model already holds when a RunTimer opens stays in the number -- which is the
    right accounting: it still has to fit on the card.
    """
    if not torch.cuda.is_available() or not torch.cuda.is_initialized():
        # Before the first CUDA call the counters are already zero, and resetting
        # would pointlessly create a context on every visible device.
        return
    for i in range(torch.cuda.device_count()):
        torch.cuda.reset_peak_memory_stats(i)
