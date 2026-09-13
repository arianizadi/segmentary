"""Verified, reusable training-only NPY caches with read-only memory mapping.

Callers must restrict construction to the bound training partition. Prediction
does not use this cache: its image-only preprocessing must never consult labels.
A run stores the returned record in its immutable plan and checks its hashes
before passing ``verify=False`` to the hot-path loader.
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .geometry import sha256_file
from .torch_config import TorchConfig

_SCHEMA = 1
_ARRAYS = ("image", "label", "affine", "foreground_1", "foreground_2")
_FILES = {f"{name}.npy" for name in _ARRAYS} | {"cache.json"}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _sources(case: dict) -> dict[str, str]:
    sources = {}
    for name in ("image", "label"):
        expected = case.get(f"{name}_sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"Shared cache requires audited {name} SHA256")
        path = Path(case[name])
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"Shared cache source {name} changed")
        sources[name] = expected
    return sources


def _identity(case: dict, config: TorchConfig) -> dict[str, Any]:
    directory = Path(__file__).parent
    return {
        "schema": _SCHEMA,
        "sources": _sources(case),
        "spacing_mm": list(config.spacing_mm),
        "hu_window": list(config.hu_window),
        "source_code": {
            name: sha256_file(directory / name)
            for name in ("torch_cache.py", "torch_data.py", "geometry.py")
        },
        "dependencies": {
            name: importlib.metadata.version(name) for name in ("numpy", "scipy", "nibabel")
        },
    }


def _cache_paths(directory: Path) -> list[Path]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Training cache directory is missing or is a symlink")
    children = list(directory.iterdir())
    if {path.name for path in children} != _FILES or any(
        path.is_symlink() or not path.is_file() for path in children
    ):
        raise ValueError("Training cache membership changed")
    return children


def cache_file_records(record: dict) -> dict[str, str]:
    """Verify exact membership/content against the record saved in a run plan.

    Reject symlinks rather than following a mutable indirection to another cache.
    This deliberately hashes the complete contents, not only file size or mtime.
    """
    directory = Path(record["path"])
    children = _cache_paths(directory)
    files = {path.name: sha256_file(path) for path in children}
    if record.get("files") != files:
        raise ValueError("Training cache content changed")
    metadata = json.loads((directory / "cache.json").read_text())
    if (
        metadata.get("schema") != _SCHEMA
        or metadata.get("fingerprint") != record["fingerprint"]
        or _digest(metadata["identity"]) != record["fingerprint"]
        or metadata.get("files")
        != {name: digest for name, digest in files.items() if name != "cache.json"}
    ):
        raise ValueError("Training cache identity changed")
    return files


def _record(directory: Path, fingerprint: str) -> dict:
    return {
        "path": str(directory),
        "fingerprint": fingerprint,
        "files": {path.name: sha256_file(path) for path in _cache_paths(directory)},
    }


def build_cached_case(case: dict, config: TorchConfig, cache_root: str | Path) -> dict:
    """Build or verify one content-addressed, immutable training examination.

    Model, patch size, sampling, seed and workspace do not alter preprocessing,
    so distinct model runs can share these arrays. Incomplete writes live in a
    separate temporary directory and never become an apparently valid cache.
    A lock serializes builders for the same content key, including other runs.
    Corrupt published caches fail loudly; they are never silently regenerated.
    """
    from .torch_data import preprocess_case

    identity = _identity(case, config)
    fingerprint = _digest(identity)
    root = Path(cache_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / fingerprint
    with (root / f".{fingerprint}.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Another builder can take a while; recheck sources after acquiring it.
        if _sources(case) != identity["sources"]:
            raise ValueError("Shared cache sources changed while waiting for its lock")
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_dir():
                raise ValueError("Shared cache destination is not a real directory")
            record = _record(destination, fingerprint)
            cache_file_records(record)
            return record
        temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.building-", dir=root))
        try:
            data = preprocess_case(case, config, with_label=True)
            arrays = {name: data[name] for name in ("image", "label", "affine")}
            arrays.update(
                {
                    f"foreground_{label}": np.argwhere(data["label"] == label).astype(np.int32)
                    for label in (1, 2)
                }
            )
            for name, array in arrays.items():
                path = temporary / f"{name}.npy"
                with path.open("wb") as stream:
                    np.save(stream, array, allow_pickle=False)
                    stream.flush()
                    os.fsync(stream.fileno())
            if _sources(case) != identity["sources"]:
                raise ValueError("Shared cache source changed during preprocessing")
            metadata = {
                "schema": _SCHEMA,
                "fingerprint": fingerprint,
                "identity": identity,
                "files": {path.name: sha256_file(path) for path in temporary.iterdir()},
            }
            with (temporary / "cache.json").open("w") as stream:
                json.dump(metadata, stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            # Publication is atomic on this filesystem. Read-only files prevent
            # accidental writes through training code; hashes remain authoritative.
            for path in temporary.iterdir():
                path.chmod(0o444)
            temporary.rename(destination)
            directory_fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        record = _record(destination, fingerprint)
        cache_file_records(record)
        return record


def load_cached_case(record: dict, *, verify: bool = True) -> dict[str, Any]:
    """Map published arrays without decompressing or copying whole volumes.

    ``verify=False`` is only for repeated loads after a stage has verified the
    record against its immutable plan. Returned arrays cannot be written to.
    """
    if verify:
        cache_file_records(record)
    directory = Path(record["path"])
    arrays = {
        name: np.load(directory / f"{name}.npy", mmap_mode="r", allow_pickle=False)
        for name in _ARRAYS
    }
    image, label = arrays["image"], arrays["label"]
    if (
        image.ndim != 3
        or image.shape != label.shape
        or image.dtype != np.float32
        or label.dtype != np.uint8
        or arrays["affine"].shape != (4, 4)
        or any(
            arrays[f"foreground_{class_id}"].ndim != 2
            or arrays[f"foreground_{class_id}"].shape[1] != 3
            or arrays[f"foreground_{class_id}"].dtype != np.int32
            for class_id in (1, 2)
        )
    ):
        raise ValueError("Training cache array contract is invalid")
    return {
        "image": image,
        "label": label,
        "affine": arrays["affine"],
        "foreground_coordinates": {
            class_id: arrays[f"foreground_{class_id}"] for class_id in (1, 2)
        },
    }
