"""Run explicitly authorized held-out RAD evaluations on frozen, idle GPUs.

The parent imports no torch and never creates a CUDA context. It holds the shared
GPU locks for every child, rechecks live idleness after locking, and monitors that
child's process tree against its assigned physical GPU UUID. Original training
campaigns and validation-only collectors are never modified.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import fcntl
import hashlib
import json
import math
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from segmentary import gpu_policy

AUTHORIZED_GPUS = frozenset((0, 1, 2, 3, 7, 8, 9))


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def validate_request(path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    request = json.loads(path.read_text())
    if (
        request.get("schema_version") not in (1, 2)
        or request.get("test_evaluation_authorized") is not True
    ):
        raise ValueError("An explicitly authorized schema-1 or schema-2 test request is required")
    campaign_path = Path(request["campaign_json"])
    campaign = json.loads(campaign_path.read_text())
    request_hash = digest(path)
    if campaign.get("request_sha256") != request_hash:
        raise ValueError("Frozen request SHA-256 does not match campaign.json")
    policy = gpu_policy.load(campaign)
    indices = set(gpu_policy.allowed_indices(policy))
    authorized = AUTHORIZED_GPUS
    if request["schema_version"] == 2:
        from scripts.rad_test_contract import validate_v2

        authorized = validate_v2(request, campaign)
    if not indices or not indices <= authorized:
        raise ValueError(f"GPU policy exceeds the authorized GPUs: {sorted(indices)}")
    if campaign.get("gpu_policy_sha256") != gpu_policy.policy_sha256(policy):
        raise ValueError("GPU policy SHA-256 mismatch")
    names = request.get("class_names", [])
    if len(names) != 21 or len(set(names)) != 21:
        raise ValueError("Exactly 21 distinct class names are required")
    jobs = request.get("jobs", [])
    identifiers = [job["name"] for job in jobs]
    if not jobs or len(identifiers) != len(set(identifiers)):
        raise ValueError("Jobs must have unique names")
    if any(Path(name).name != name or name in (".", "..") for name in identifiers):
        raise ValueError("Unsafe job name")
    if not Path(request["output_root"]).is_absolute():
        raise ValueError("output_root must be an absolute, separate evaluation directory")
    return request, policy, request_hash


def idle_snapshot(policy: dict[str, Any]) -> dict[int, bool]:
    """Refuse malformed/partial telemetry; do not infer idleness from silence."""
    gpu_policy.verify_inventory(policy)
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=20,
    )
    busy = {gpu_policy.normalize_uuid(uuid) for _, uuid in gpu_policy.compute_apps()}
    expected = {int(entry["index"]): entry for entry in policy["allowed"]}
    result = {}
    for line in output.splitlines():
        cells = [cell.strip() for cell in next(csv.reader([line]))]
        if len(cells) != 4 or not cells[0].isdigit():
            raise gpu_policy.GpuInspectionError(f"Malformed GPU utilization row: {line!r}")
        index = int(cells[0])
        if index not in expected:
            continue
        if index in result:
            raise gpu_policy.GpuInspectionError(f"Repeated GPU telemetry row: {index}")
        uuid = gpu_policy.normalize_uuid(cells[1])
        if uuid != gpu_policy.normalize_uuid(expected[index]["uuid"]):
            raise gpu_policy.GpuPolicyError(f"GPU {index} UUID differs from the frozen policy")
        try:
            memory, utilization = float(cells[2]), float(cells[3])
        except ValueError as error:
            raise gpu_policy.GpuInspectionError(f"Unreadable GPU {index} telemetry") from error
        if not all(math.isfinite(value) and value >= 0 for value in (memory, utilization)):
            raise gpu_policy.GpuInspectionError(f"Invalid GPU {index} telemetry")
        result[index] = uuid not in busy and memory <= 64 and utilization == 0
    if set(result) != set(expected):
        raise gpu_policy.GpuInspectionError("Incomplete telemetry for the frozen allowed GPUs")
    return result


@contextlib.contextmanager
def exclusive_locks(paths: list[Path]):
    """Nonblocking locks; retained handles prevent a second cooperating launcher."""
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
        for stream in reversed(handles):
            stream.close()


def shared_lock_paths(root: Path, gpu: int, uuid: str) -> list[Path]:
    temporary = Path(tempfile.gettempdir())
    return [
        root / f"gpu-{gpu}.lock",
        temporary / f"segmentary-exclusive-gpu-{gpu}.lock",
        temporary / f"segmentary-gpu-{uuid}.lock",
        temporary / f"segmentary-medical-{os.getuid()}" / f"gpu-{gpu}.lock",
    ]


def result_complete(
    output: Path, job: dict[str, Any], request_hash: str, class_names: list[str]
) -> bool:
    """Only a complete, hash-verified result for this exact frozen request resumes."""
    path = output / job["name"] / "result.json"
    if not path.exists():
        return False
    result = json.loads(path.read_text())
    if result.get("status") != "completed":
        return False
    if (
        result.get("request_sha256") != request_hash
        or result.get("checkpoint_sha256") != job["final_checkpoint_sha256"]
        or result.get("split") != "test"
        or result.get("test_evaluated") is not True
    ):
        raise ValueError(
            f"Existing result belongs to a different request/checkpoint: {job['name']}"
        )
    if result.get("images", 0) <= 0:
        raise ValueError(f"Completed result has no test images: {job['name']}")
    artifacts = result.get("artifacts", {})
    required = {"metrics.json", "per-image.csv", "per-image-confusion.json.gz", "coverage.json"}
    if not required <= set(artifacts):
        raise ValueError(f"Completed result lacks required evidence: {job['name']}")
    for entry in artifacts.values():
        artifact = Path(entry["path"])
        if not artifact.is_file() or digest(artifact) != entry["sha256"]:
            raise ValueError(f"Completed result artifact changed: {artifact}")
    coverage = json.loads(Path(artifacts["coverage.json"]["path"]).read_text())
    if set(coverage) != set(class_names) or any(
        not isinstance(coverage[name].get("positive_images"), int)
        or not 0 < coverage[name]["positive_images"] <= result["images"]
        or not isinstance(coverage[name].get("pixels"), int)
        or coverage[name]["pixels"] <= 0
        for name in class_names
    ):
        raise ValueError(f"Completed result lacks all-21-class test support: {job['name']}")
    present = result.get("present_image", {})
    if (
        present.get("miou_present_images_classes") != 21
        or set(present.get("per_class", {})) != set(class_names)
        or present.get("images") != result["images"]
    ):
        raise ValueError(f"Completed result has incomplete class metrics: {job['name']}")
    if result.get("schema_version") == 2:
        import gzip

        import numpy as np
        from scripts.rad_paper_metrics import paper_metrics

        if "paper-metrics.json" not in artifacts:
            raise ValueError("Completed paper result lacks its recomputable statistics")
        directory = output / job["name"]
        with (directory / "per-image.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        groups = {row["key"]: row["group"] for row in rows}
        if len(groups) != len(rows) or len(rows) != result["images"]:
            raise ValueError("Paper result has duplicate or missing per-image evidence")
        for row in rows:
            path = directory / "predictions" / (row["key"] + ".png")
            if not path.is_file() or digest(path) != row["prediction_sha256"]:
                raise ValueError(f"Paper prediction changed or is missing: {path}")
        matrices = {
            key: np.asarray(value, dtype=np.int64)
            for key, value in json.loads(
                gzip.decompress((directory / "per-image-confusion.json.gz").read_bytes())
            ).items()
        }
        recomputed = paper_metrics(matrices, class_names, groups)
        if recomputed != json.loads(Path(artifacts["paper-metrics.json"]["path"]).read_text()):
            raise ValueError("Paper statistics disagree with per-image confusion evidence")
    # The evaluator independently verifies every prediction digest on resume.
    # The parent's artifact hashes make missing/truncated aggregate evidence fatal.
    return True


def stop_child(process: subprocess.Popen) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def run(args: argparse.Namespace) -> int:
    request_path = args.request.resolve()
    request, policy, request_hash = validate_request(request_path)
    output = Path(request["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    jobs = request["jobs"]
    states: dict[str, dict[str, Any]] = {}
    pending: queue.Queue = queue.Queue()
    mutex, stop = threading.Lock(), threading.Event()
    for job in jobs:
        complete = result_complete(output, job, request_hash, request["class_names"])
        states[job["name"]] = {"status": "completed" if complete else "queued"}
        if not complete:
            pending.put(job)
    status_path = output / "runner-status.json"
    started = now()

    def status() -> None:
        write(
            status_path,
            {
                "schema_version": 1,
                "pid": os.getpid(),
                "started_at": started,
                "updated_at": now(),
                "request_sha256": request_hash,
                "allowed_gpus": list(gpu_policy.allowed_indices(policy)),
                "counts": {
                    value: sum(state["status"] == value for state in states.values())
                    for value in ("queued", "running", "completed", "failed")
                },
                "jobs": states,
                "stopping": stop.is_set(),
            },
        )

    def update(name: str, **values: Any) -> None:
        with mutex:
            states[name].update(values)
            status()

    def worker(gpu: int) -> None:
        entry = gpu_policy.require_allowed(policy, gpu)
        while not stop.is_set() and not pending.empty():
            try:
                idle = idle_snapshot(policy)[gpu]
            except (gpu_policy.GpuPolicyError, OSError, subprocess.SubprocessError) as error:
                stop.set()
                with mutex:
                    states[f"gpu-{gpu}-inspection"] = {"status": "failed", "error": str(error)}
                    status()
                return
            if not idle:
                stop.wait(args.poll_seconds)
                continue
            with exclusive_locks(shared_lock_paths(args.lock_root, gpu, entry["uuid"])) as acquired:
                if not acquired:
                    stop.wait(args.poll_seconds)
                    continue
                if not idle_snapshot(policy)[gpu]:
                    continue
                try:
                    job = pending.get_nowait()
                except queue.Empty:
                    return
                log = output / "logs" / (job["name"] + ".log")
                log.parent.mkdir(exist_ok=True)
                command = [
                    args.python,
                    "-u",
                    str(args.repo / "scripts/evaluate_rad_test.py"),
                    "--request",
                    str(request_path),
                    "--job",
                    job["name"],
                    "--gpu",
                    str(gpu),
                ]
                environment = gpu_policy.child_env(
                    {
                        **os.environ,
                        "PYTHONPATH": str(args.repo / "src"),
                        "HF_HUB_OFFLINE": "1",
                        "TRANSFORMERS_OFFLINE": "1",
                        "OMP_NUM_THREADS": "4",
                    },
                    policy,
                    gpu,
                    request["campaign_json"],
                )
                process = None
                try:
                    with log.open("a") as stream:
                        process = subprocess.Popen(
                            command,
                            cwd=args.repo,
                            env=environment,
                            stdin=subprocess.DEVNULL,
                            stdout=stream,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                        update(
                            job["name"],
                            status="running",
                            gpu=gpu,
                            gpu_uuid=entry["uuid"],
                            pid=process.pid,
                            started_at=now(),
                            log=str(log),
                        )
                        while process.poll() is None:
                            if stop.wait(args.poll_seconds):
                                stop_child(process)
                                raise RuntimeError(
                                    "Runner stopped; partial evidence is not complete"
                                )
                            gpu_policy.assert_pid_on_uuid(process.pid, entry["uuid"])
                        if process.returncode != 0:
                            raise RuntimeError(
                                f"Evaluator exited with code {process.returncode}; see {log}"
                            )
                    if not result_complete(output, job, request_hash, request["class_names"]):
                        raise RuntimeError("Evaluator exited without verified completion evidence")
                    update(job["name"], status="completed", finished_at=now())
                except BaseException as error:
                    if process is not None:
                        stop_child(process)
                    update(job["name"], status="failed", finished_at=now(), error=str(error))
                    if isinstance(error, gpu_policy.GpuPolicyError):
                        stop.set()
                finally:
                    pending.task_done()

    def interrupt(_signum, _frame):
        stop.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupt)
    gpu_policy.verify_inventory(policy)
    with exclusive_locks([output / "locks/runner.lock"]) as acquired:
        if not acquired:
            raise RuntimeError("This test request already has a runner")
        with mutex:
            status()
        with ThreadPoolExecutor(max_workers=len(policy["allowed"])) as executor:
            futures = [executor.submit(worker, int(entry["index"])) for entry in policy["allowed"]]
            for future in futures:
                try:
                    future.result()
                except BaseException:
                    stop.set()
                    raise
        with mutex:
            status()
    return 0 if all(state["status"] == "completed" for state in states.values()) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--python", default=sys.executable, help="Evaluator runtime interpreter")
    parser.add_argument(
        "--lock-root",
        type=Path,
        default=Path("/data/izadia1/projects/segmentary-runs/.gpu-locks"),
    )
    parser.add_argument("--poll-seconds", type=float, default=3)
    args = parser.parse_args()
    args.repo = args.repo.resolve()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
