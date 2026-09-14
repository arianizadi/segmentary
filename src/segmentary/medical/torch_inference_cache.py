"""Stage-verified image-only inference snapshots with immutable mapped arrays.

A loader instance hashes each raw CT and each cache file on first use. Subsequent
uses check device/inode/size/mtime/ctime/mode signatures, including membership and
path resolution, before and after use. Retain the instance across validation
epochs; create a new one at the next independent prediction stage to reverify all
bytes. This assumes normal filesystem change-time semantics, not an adversary
with control over the kernel or filesystem metadata. No label keys are read.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import importlib.metadata
import json
import os
import shutil
import stat
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

from .geometry import _nibabel, _save_new_nifti, assert_same_geometry, sha256_file
from .torch_config import TorchConfig

_SCHEMA = 1
_FILES = {"image.npy", "affine.npy", "cache.json"}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    result = json.loads(
        path.read_text(),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Nonfinite JSON: {value}")),
    )
    if not isinstance(result, dict):
        raise ValueError("Inference cache metadata must be an object")
    return result


def _signature(path: Path) -> tuple[int, ...]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Inference input must be a regular file, not a symlink: {path}")
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_mode,
    )


def _cache_signature(directory: Path) -> dict[str, tuple[int, ...]]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Inference cache directory is missing or is a symlink")
    children = list(directory.iterdir())
    if {path.name for path in children} != _FILES:
        raise ValueError("Inference cache membership changed")
    return {path.name: _signature(path) for path in children}


def _native_reference(case: dict) -> dict[str, Any]:
    """Read only audited image identity/geometry fields, never supervision."""
    expected = case.get("image_sha256")
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(letter not in "0123456789abcdef" for letter in expected)
    ):
        raise ValueError("Inference cache requires an audited image SHA256")
    shape, spacing = case.get("shape"), case.get("spacing_mm")
    if (
        not isinstance(shape, (list, tuple))
        or len(shape) != 3
        or any(type(size) is not int or size <= 0 for size in shape)
    ):
        raise ValueError("Inference cache requires audited native 3D shape")
    affine = np.asarray(case.get("affine"), dtype=np.float64)
    spacing_array = np.asarray(spacing, dtype=np.float64)
    if (
        affine.shape != (4, 4)
        or spacing_array.shape != (3,)
        or not np.isfinite(affine).all()
        or not np.isfinite(spacing_array).all()
        or np.any(spacing_array <= 0)
        or abs(float(np.linalg.det(affine[:3, :3]))) < 1e-8
        or not np.allclose(affine[3], [0, 0, 0, 1], atol=1e-7, rtol=0)
        or not np.allclose(
            np.linalg.norm(affine[:3, :3], axis=0), spacing_array, atol=1e-4, rtol=1e-4
        )
    ):
        raise ValueError("Inference cache requires consistent audited native affine/spacing")
    return {
        "shape": list(shape),
        "spacing_mm": spacing_array.tolist(),
        "affine": affine.tolist(),
        "sha256": expected,
        "image_sha256": expected,
        "spatial_units": "mm",
    }


def _pipeline_identity(config: TorchConfig) -> dict[str, Any]:
    directory = Path(__file__).parent
    return {
        "schema": _SCHEMA,
        "kind": "image_only_inference",
        "spacing_mm": list(config.spacing_mm),
        "hu_window": list(config.hu_window),
        "source_code": {
            name: sha256_file(directory / name)
            for name in ("torch_inference_cache.py", "torch_data.py", "geometry.py")
        },
        "dependencies": {
            name: importlib.metadata.version(name) for name in ("numpy", "scipy", "nibabel")
        },
    }


def _arrays(directory: Path, *, full_check: bool) -> dict[str, Any]:
    image = np.load(directory / "image.npy", mmap_mode="r", allow_pickle=False)
    affine = np.load(directory / "affine.npy", mmap_mode="r", allow_pickle=False)
    if (
        image.ndim != 3
        or any(size <= 0 for size in image.shape)
        or image.dtype != np.float32
        or affine.shape != (4, 4)
        or affine.dtype != np.float64
        or not np.isfinite(affine).all()
        or abs(float(np.linalg.det(affine[:3, :3]))) < 1e-8
        or not np.allclose(affine[3], [0, 0, 0, 1], atol=1e-7, rtol=0)
    ):
        raise ValueError("Inference cache array contract is invalid")
    if full_check and (
        not np.isfinite(image).all() or float(image.min()) < 0 or float(image.max()) > 1
    ):
        raise ValueError("Inference cache image contains invalid normalized intensities")
    return {"image": image, "affine": affine}


class InferenceImageCache:
    """Reusable per-stage source verification plus a bounded mapping LRU.

    ``load`` verifies bytes on first use; ``check`` is a cheap change guard and
    must also be called after inference/reconstruction before a result is used.
    ``export_prediction`` performs those guards around native output publication.
    Files are read-only and published atomically. A damaged published cache is an
    error, never an invitation to silently regenerate evidence.

    ``max_open_cases`` bounds mappings retained by this object. In-flight callers
    retain their own array references; release those after each bounded pipeline
    operation. Eviction never closes mappings still held by an active caller.
    """

    def __init__(
        self, cache_root: str | Path, config: TorchConfig, *, max_open_cases: int = 2
    ) -> None:
        if type(max_open_cases) is not int or max_open_cases <= 0:
            raise ValueError("max_open_cases must be a positive integer")
        self.root = Path(cache_root).expanduser().resolve()
        self.config = config
        self.max_open_cases = max_open_cases
        self._pipeline = _pipeline_identity(config)
        self._verified: dict[tuple[str, str], dict[str, Any]] = {}
        self._mapped: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        self._closed = False
        self._load_lock = threading.RLock()
        self._metadata_lock = threading.RLock()
        self._stats = {
            "loads": 0,
            "source_verifications": 0,
            "cache_verifications": 0,
            "builds": 0,
            "memory_hits": 0,
            "disk_hits": 0,
        }

    @property
    def stats(self) -> dict[str, int]:
        with self._metadata_lock:
            return {
                **self._stats,
                "open_cases": len(self._mapped),
                "verified_cases": len(self._verified),
            }

    def _count(self, name: str) -> None:
        with self._metadata_lock:
            self._stats[name] += 1

    def __enter__(self) -> InferenceImageCache:
        if self._closed:
            raise RuntimeError("Inference cache loader is closed")
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        with self._load_lock, self._metadata_lock:
            self._mapped.clear()
            self._verified.clear()
            self._closed = True

    def _description(self, case: dict) -> tuple[tuple[str, str], Path, dict, dict]:
        if self._closed:
            raise RuntimeError("Inference cache loader is closed")
        source = Path(case["image"]).expanduser().absolute()
        reference = _native_reference(case)
        identity = {**self._pipeline, "source": reference}
        fingerprint = _digest(identity)
        return (str(source), fingerprint), source, identity, reference

    @staticmethod
    def _guard(source: Path, record: dict) -> None:
        if (
            source.resolve() != Path(record["source_resolved"])
            or _signature(source) != record["source_signature"]
        ):
            raise ValueError("Inference source changed after stage verification")
        if _cache_signature(Path(record["directory"])) != record["cache_signature"]:
            raise ValueError("Inference cache changed after stage verification")

    def check(self, case: dict) -> None:
        key, source, _identity, _reference = self._description(case)
        with self._metadata_lock:
            record = self._verified.get(key)
        if record is None:
            raise ValueError("Inference source has not been verified by this stage loader")
        self._guard(source, record)

    def verify_stage(self, cases: list[dict]) -> None:
        """Eagerly verify/build a fixed set; lazy first ``load`` is equivalent."""
        for case in cases:
            self.load(case)

    def _build(
        self,
        source: Path,
        case: dict,
        identity: dict,
        reference: dict,
        destination: Path,
        source_signature: tuple[int, ...],
        source_resolved: str,
    ) -> None:
        from .torch_data import preprocess_case

        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=self.root))
        try:
            if _signature(source) != source_signature or str(source.resolve()) != source_resolved:
                raise ValueError("Inference source changed before preprocessing")
            # This is the existing arithmetic, including its full CT audit.
            # Pass a deliberately image-only mapping so supervision is inaccessible.
            data = preprocess_case({"image": str(source)}, self.config, with_label=False)
            native = _nibabel().load(str(source))
            actual = {"shape": list(native.shape), "affine": native.affine.tolist()}
            assert_same_geometry(reference, actual, where="inference cache native reference")
            for name in ("image", "affine"):
                path = temporary / f"{name}.npy"
                with path.open("wb") as stream:
                    np.save(stream, data[name], allow_pickle=False)
                    stream.flush()
                    os.fsync(stream.fileno())
            metadata = {
                "schema": _SCHEMA,
                "kind": "image_only_inference",
                "fingerprint": destination.name,
                "identity": identity,
                "files": {
                    name: sha256_file(temporary / name) for name in ("image.npy", "affine.npy")
                },
            }
            with (temporary / "cache.json").open("w") as stream:
                json.dump(metadata, stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            _arrays(temporary, full_check=True)
            for path in temporary.iterdir():
                path.chmod(0o444)
            if _signature(source) != source_signature or str(source.resolve()) != source_resolved:
                raise ValueError(
                    "Inference source changed during preprocessing; cache not published"
                )
            temporary.rename(destination)
            fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            self._count("builds")
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def _verify(self, source: Path, case: dict, identity: dict, reference: dict) -> dict[str, Any]:
        before = _signature(source)
        resolved = str(source.resolve())
        if sha256_file(source) != reference["sha256"]:
            raise ValueError("Inference source contents differ from the audited image SHA256")
        if _signature(source) != before or str(source.resolve()) != resolved:
            raise ValueError("Inference source changed during stage verification")
        self._count("source_verifications")
        self.root.mkdir(parents=True, exist_ok=True)
        fingerprint = _digest(identity)
        destination = self.root / fingerprint
        with (self.root / f".{fingerprint}.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if _signature(source) != before or str(source.resolve()) != resolved:
                raise ValueError("Inference source changed while waiting for its cache lock")
            if not destination.exists() and not destination.is_symlink():
                self._build(source, case, identity, reference, destination, before, resolved)
            else:
                self._count("disk_hits")
            cache_before = _cache_signature(destination)
            metadata = _read_json(destination / "cache.json")
            if (
                set(metadata) != {"schema", "kind", "fingerprint", "identity", "files"}
                or metadata.get("schema") != _SCHEMA
                or metadata.get("kind") != "image_only_inference"
                or metadata.get("fingerprint") != fingerprint
                or metadata.get("identity") != identity
                or metadata.get("files")
                != {name: sha256_file(destination / name) for name in ("image.npy", "affine.npy")}
            ):
                raise ValueError("Inference cache identity or content hash changed")
            _arrays(destination, full_check=True)
            if cache_before != _cache_signature(destination):
                raise ValueError("Inference cache changed during full verification")
            if _signature(source) != before or str(source.resolve()) != resolved:
                raise ValueError("Inference source changed during cache preparation")
        self._count("cache_verifications")
        return {
            "source_resolved": resolved,
            "source_signature": before,
            "cache_signature": cache_before,
            "directory": str(destination),
            "reference": copy.deepcopy(reference),
        }

    def load(self, case: dict) -> dict[str, Any]:
        # Serialize preparation, not the postprocessing thread's cheap guards.
        # This also ensures concurrent requests verify each source only once.
        with self._load_lock:
            return self._load(case)

    def _load(self, case: dict) -> dict[str, Any]:
        key, source, identity, reference = self._description(case)
        self._count("loads")
        with self._metadata_lock:
            record = self._verified.get(key)
        if record is None:
            record = self._verify(source, case, identity, reference)
            with self._metadata_lock:
                self._verified[key] = record
        self._guard(source, record)
        with self._metadata_lock:
            data = self._mapped.pop(key, None)
        if data is None:
            data = _arrays(Path(record["directory"]), full_check=False)
        else:
            self._count("memory_hits")
        with self._metadata_lock:
            self._mapped[key] = data
            while len(self._mapped) > self.max_open_cases:
                self._mapped.popitem(last=False)
        self._guard(source, record)
        native = copy.deepcopy(record["reference"])
        return {
            **data,
            "native_shape": tuple(native["shape"]),
            "native_affine": np.asarray(native["affine"], dtype=np.float64),
            "reference": native,
        }

    def export_prediction(
        self,
        case: dict,
        prediction: Any,
        output: str | Path,
        *,
        allowed_labels: tuple[int, ...] = (0, 1, 2),
    ) -> dict[str, Any]:
        """Export using this loader's private verified CT geometry, with guards."""
        self.check(case)
        key, _source, _identity, _reference = self._description(case)
        with self._metadata_lock:
            reference = copy.deepcopy(self._verified[key]["reference"])
        destination = Path(output).expanduser().absolute()
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite {destination}")
        values = np.asarray(prediction)
        if list(values.shape) != reference["shape"]:
            raise ValueError("prediction shape is not the original reference grid")
        if values.dtype.kind not in "biuf" or not np.isfinite(values).all():
            raise ValueError("prediction must contain finite discrete labels")
        if not np.equal(values, np.rint(values)).all() or not set(
            np.unique(values).tolist()
        ) <= set(allowed_labels):
            raise ValueError("prediction contains fractional or unexpected labels")
        if not allowed_labels or min(allowed_labels) < 0 or max(allowed_labels) > 65535:
            raise ValueError("export label IDs must fit unsigned 16-bit storage")
        nib = _nibabel()
        affine = np.asarray(reference["affine"])
        dtype = np.uint8 if max(allowed_labels) <= 255 else np.uint16
        volume = nib.Nifti1Image(values.astype(dtype), affine)
        volume.header.set_xyzt_units("mm")
        volume.set_sform(affine, code=1)
        try:
            volume.set_qform(affine, code=1, strip_shears=False)
        except nib.spatialimages.HeaderDataError:
            volume.set_qform(None, code=0)
        self.check(case)
        result = _save_new_nifti(
            volume, destination, allowed_labels=allowed_labels, expected_geometry=reference
        )
        self.check(case)
        return result
