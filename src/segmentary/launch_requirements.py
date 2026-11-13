"""Opt-in pre-launch requirements and cooperative host-wide GPU ownership.

Legacy campaigns without launch_requirements retain their existing behavior.
Nothing here initializes CUDA or stops another process. GPU telemetry is read-only.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from segmentary import gpu_policy

SHARED_LOCK_ROOT = Path("/data/izadia1/projects/segmentary-runs/.gpu-locks")
KEYS = {
    "expected_gpu_allowlist",
    "require_queue_priority",
    "shared_gpu_lock_and_idle",
    "require_non_rad_sources",
}


def requirements_from_spec(spec: dict[str, Any]) -> dict[str, Any] | None:
    if "launch_requirements" not in spec:
        return None
    value = spec["launch_requirements"]
    if not isinstance(value, dict) or not value:
        raise ValueError("launch_requirements must be a nonempty object")
    unknown = set(value) - KEYS
    if unknown:
        raise ValueError(f"Unknown launch_requirements: {sorted(unknown)}")
    for key in KEYS - {"expected_gpu_allowlist"}:
        if key in value and type(value[key]) is not bool:
            raise ValueError(f"launch_requirements.{key} must be boolean")
    if "expected_gpu_allowlist" in value:
        gpus = value["expected_gpu_allowlist"]
        if not isinstance(gpus, list) or not gpus or any(type(g) is not int or g < 0 for g in gpus):
            raise ValueError(
                "expected_gpu_allowlist must be a nonempty list of nonnegative integers"
            )
        if gpus != sorted(set(gpus)):
            raise ValueError("expected_gpu_allowlist must be unique and sorted")
    return copy.deepcopy(value)


def check_expected_allowlist(requirements: dict[str, Any] | None, allowed) -> None:
    if (
        requirements
        and "expected_gpu_allowlist" in requirements
        and sorted(allowed) != requirements["expected_gpu_allowlist"]
    ):
        raise gpu_policy.GpuPolicyError("GPU allowlist differs from opt-in expected_gpu_allowlist")


def validate_plan(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Fail before GPU inspection if an opt-in frozen plan omits its safeguards."""
    requirements = requirements_from_spec(plan)
    if requirements is None:
        return None
    check_expected_allowlist(requirements, plan.get("gpu_allowlist", []))
    if requirements.get("require_queue_priority"):
        provenance = plan.get("queue_priority_provenance")
        if not isinstance(provenance, dict):
            raise ValueError(
                "Required queue_priority_provenance is missing; prioritize before init"
            )
        for key in ["source_priority_sha256", "source_csv_sha256"]:
            if not isinstance(provenance.get(key), str) or not re.fullmatch(
                "[0-9a-f]{64}", provenance[key]
            ):
                raise ValueError(f"Invalid queue_priority_provenance.{key}")
        jobs = plan.get("jobs")
        if not isinstance(jobs, list) or not jobs or provenance.get("jobs") != len(jobs):
            raise ValueError("Queue priority provenance job count differs from plan")
        names = [job.get("name") for job in jobs]
        if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
            raise ValueError("Prioritized plan has duplicate or invalid job names")
        for index, job in enumerate(jobs, 1):
            if type(job.get("queue_priority")) is not int or job["queue_priority"] != index:
                raise ValueError("Jobs must have consecutive queue_priority in actual list order")
        source_path = provenance.get("source_priority_file")
        if not isinstance(source_path, str) or not source_path:
            raise ValueError("Queue priority source file is missing")
        source = Path(source_path)
        try:
            raw = source.read_bytes()
        except OSError as error:
            raise ValueError(f"Cannot verify queue priority source: {source}") from error
        if hashlib.sha256(raw).hexdigest() != provenance["source_priority_sha256"]:
            raise ValueError("Frozen queue priority source SHA-256 changed")
        source_data = json.loads(raw)
        if source_data.get("source_csv_sha256") != provenance["source_csv_sha256"]:
            raise ValueError("Queue priority source CSV SHA-256 disagrees")
        expected = [(j["model"], j["protocol"]) for j in source_data.get("jobs", [])]
        actual = [(j.get("model"), j.get("protocol")) for j in jobs]
        if expected != actual:
            raise ValueError("Actual plan job order differs from the frozen historical priority")
        if provenance.get("models") != list(dict.fromkeys(j.get("model") for j in jobs)):
            raise ValueError("Actual plan model order differs from its priority provenance")
    return requirements


def shared_lock_paths(gpu: int, uuid: str, root: Path = SHARED_LOCK_ROOT) -> list[Path]:
    """Same lock identities as the RAD test/medical launchers; never unlink locks."""
    temporary = Path(tempfile.gettempdir())
    return [
        root / f"gpu-{gpu}.lock",
        temporary / f"segmentary-exclusive-gpu-{gpu}.lock",
        temporary / f"segmentary-gpu-{uuid}.lock",
        temporary / f"segmentary-medical-{os.getuid()}" / f"gpu-{gpu}.lock",
    ]


@contextlib.contextmanager
def exclusive_locks(paths: list[Path]):
    handles = []
    try:
        for path in sorted(set(paths)):
            path.parent.mkdir(parents=True, exist_ok=True)
            stream = path.open("a")
            handles.append(stream)
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
        yield True
    finally:
        # Closing only our handles releases only our locks. Existing files and
        # foreign ownership stay intact; stale files are never deleted/unlocked.
        for stream in reversed(handles):
            stream.close()


def gpu_is_idle(policy: dict[str, Any], gpu: int) -> bool:
    """Assigned GPU must have no compute PID, <=64MiB memory and exactly 0% utilization."""
    entry = gpu_policy.require_allowed(policy, gpu)
    uuid = gpu_policy.normalize_uuid(entry["uuid"])
    busy = {gpu_policy.normalize_uuid(value) for _, value in gpu_policy.compute_apps()}
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--id=" + entry["uuid"],
                "--query-gpu=index,uuid,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise gpu_policy.GpuInspectionError(
            f"Cannot inspect assigned GPU {gpu}: {error}"
        ) from error
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) != 1:
        raise gpu_policy.GpuInspectionError(f"Expected exactly one telemetry row for GPU {gpu}")
    cells = [cell.strip() for cell in next(csv.reader(lines))]
    if len(cells) != 4 or not cells[0].isdigit():
        raise gpu_policy.GpuInspectionError(f"Malformed telemetry for GPU {gpu}")
    if int(cells[0]) != gpu or gpu_policy.normalize_uuid(cells[1]) != uuid:
        raise gpu_policy.GpuPolicyError(
            f"Assigned GPU {gpu} identity differs from the frozen policy"
        )
    try:
        memory, utilization = float(cells[2]), float(cells[3])
    except ValueError as error:
        raise gpu_policy.GpuInspectionError(f"Unreadable telemetry for GPU {gpu}") from error
    if (
        not math.isfinite(memory)
        or not math.isfinite(utilization)
        or memory < 0
        or not 0 <= utilization <= 100
    ):
        raise gpu_policy.GpuInspectionError(f"Invalid telemetry for GPU {gpu}")
    return uuid not in busy and memory <= 64 and utilization == 0
