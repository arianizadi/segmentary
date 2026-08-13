"""The results.json every run writes.

Benchmark tables are generated from these files, never hand-copied, so the writer
has two jobs beyond serialisation: record enough provenance to reconstruct the
run (commit, config hash, seed, library versions), and never leave a truncated
file behind. A half-written results.json breaks the table generator at the exact
moment it is least welcome -- after the run is already over.

This module owns the record format and the atomic write; the machine
observations it embeds come from ``segmentary.utils.provenance``.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import tempfile
import time
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import torch

# Re-exported so callers have one import for everything that lands in results.json.
from segmentary.utils.provenance import (
    collect_env,
    discover_git_root,
    git_sha,
    peak_vram,
    reset_peak_vram,
)

__all__ = [
    "RunRecord",
    "RunTimer",
    "collect_env",
    "discover_git_root",
    "git_sha",
    "load_results",
    "peak_vram",
    "reset_peak_vram",
    "sanitise",
    "write_results",
]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class RunRecord:
    """One run's provenance and results, serialised to results.json."""

    name: str
    stage: str
    config_hash: str
    git_sha: str
    git_dirty: bool
    seed: int
    started_at: str = field(default_factory=_utc_now)
    finished_at: str | None = None
    wall_clock_s: float | None = None
    peak_vram_bytes: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    env: dict[str, Any] = field(default_factory=dict)
    dataset_sizes: dict[str, int] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict with numpy/torch scalars and NaN already resolved."""
        # Deliberately not dataclasses.asdict: that deep-copies every value, so a
        # CUDA tensor left in metrics would be reallocated on the GPU on every
        # mid-run write, and an uncopyable value would raise from copy.deepcopy
        # instead of from sanitise's actionable message.
        return sanitise({f.name: getattr(self, f.name) for f in fields(self)})

    @classmethod
    def from_dict(cls, data: dict) -> RunRecord:
        """Rebuild a record, rejecting unknown and missing keys loudly."""
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"results.json has unknown keys {sorted(unknown)}; expected only "
                f"{sorted(known)}. It was probably written by a different version "
                "of segmentary, so the table generator cannot trust its columns."
            )
        required = {
            f.name
            for f in fields(cls)
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        }
        missing = required - set(data)
        if missing:
            raise ValueError(
                f"results.json is missing required keys {sorted(missing)}; the run "
                "cannot be traced back to a commit or config without them."
            )
        return cls(**data)


def sanitise(obj: Any) -> Any:
    """Convert numpy/torch scalars, arrays and Paths to plain JSON types.

    Non-finite floats become ``None``: bare ``NaN`` and ``Infinity`` are what
    ``json.dumps`` emits by default and neither is legal JSON, so a single absent
    class (whose IoU is NaN) would otherwise produce a file that strict parsers
    reject.
    """
    if isinstance(obj, np.generic):
        # Before the plain-type checks: np.float64 subclasses float and np.str_
        # subclasses str, so those branches would return the numpy object itself
        # and leave numpy types in what is documented to be plain JSON data.
        return sanitise(obj.item())
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):  # after bool, which is a subclass of int
        return int(obj)
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, torch.Tensor):
        return sanitise(obj.item() if obj.ndim == 0 else obj.tolist())
    if isinstance(obj, np.ndarray):
        return sanitise(obj.tolist())
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return sanitise(obj.value)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return sanitise(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        # json.dumps(sort_keys=True) cannot order mixed key types, so normalise
        # every key to str here rather than failing at write time. Two keys can
        # collide once stringified (1 and "1", True and "True"); dropping one
        # silently would lose a metric, so that is an error, not a merge.
        out: dict[str, Any] = {}
        for key, value in obj.items():
            name = str(key)
            if name in out:
                raise ValueError(
                    f"dict keys {key!r} and a previous key both stringify to {name!r}. "
                    "results.json keys must be strings, and merging them would silently "
                    "drop one of the two values."
                )
            out[name] = sanitise(value)
        return out
    if isinstance(obj, (list, tuple)):
        return [sanitise(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        # Set iteration order varies with PYTHONHASHSEED, so two byte-identical
        # runs would otherwise write results.json files that differ by ordering
        # alone and pollute every diff. Sort naturally when the members are one
        # comparable scalar type, by repr when they are not comparable at all.
        values = [sanitise(v) for v in obj]
        kinds = {type(v) for v in values}
        if len(kinds) == 1 and isinstance(values[0], (int, float, str)):
            return sorted(values)
        return sorted(values, key=repr)
    raise TypeError(
        f"cannot serialise {type(obj).__name__} into results.json. Convert it to a "
        "plain int/float/str/list/dict before putting it in metrics or config."
    )


def write_results(path: str | os.PathLike[str], record: RunRecord) -> None:
    """Write results.json atomically: a reader never sees a partial file.

    The temp file is created in the destination directory so ``os.replace`` is a
    same-filesystem rename, which is atomic. Runs write this repeatedly (at every
    validation), so an interrupt mid-write must leave the previous file intact
    rather than a truncated one.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record.to_dict(), indent=2, sort_keys=True, allow_nan=False)

    tmp_fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())  # rename is atomic, but only durable after fsync
        # mkstemp hard-codes 0600; a runs directory is read by collaborators and by
        # the table generator, possibly under a different account.
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, dest)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def load_results(path: str | os.PathLike[str]) -> RunRecord:
    """Read a results.json back into a RunRecord."""
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"no results file at {src}; the run may not have written one.")
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{src} is not valid JSON ({exc}). If a run was killed mid-write this "
            "should not happen -- write_results is atomic -- so suspect manual edits."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"{src} holds a {type(data).__name__}, expected a JSON object.")
    return RunRecord.from_dict(data)


class RunTimer:
    """Context manager measuring wall clock and peak VRAM over a run.

    Elapsed time and peak memory are readable while still inside the block, so
    mid-run results.json writes carry live numbers; ``finished_at`` stays None
    until the block exits, which is how a reader tells a crashed run from a
    complete one.
    """

    def __init__(self) -> None:
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self._t0: float | None = None
        self._elapsed: float | None = None

    def __enter__(self) -> RunTimer:
        reset_peak_vram()
        self.started_at = _utc_now()
        self.finished_at = None
        self._elapsed = None
        self._t0 = time.perf_counter()  # monotonic: immune to NTP steps mid-run
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._elapsed = time.perf_counter() - self._t0  # type: ignore[operator]
        self.finished_at = _utc_now()
        return None  # never swallow the exception that ended the run

    @property
    def wall_clock_s(self) -> float:
        if self._t0 is None:
            raise RuntimeError("RunTimer.wall_clock_s read before entering the context.")
        return self._elapsed if self._elapsed is not None else time.perf_counter() - self._t0

    def peak_vram_bytes(self) -> dict[str, int]:
        return peak_vram()

    def stamp(self, record: RunRecord) -> None:
        """Copy timing and memory measurements onto a record before writing."""
        if self.started_at is None:
            raise RuntimeError("RunTimer.stamp called before entering the context.")
        record.started_at = self.started_at
        record.finished_at = self.finished_at
        record.wall_clock_s = self.wall_clock_s
        record.peak_vram_bytes = self.peak_vram_bytes()
