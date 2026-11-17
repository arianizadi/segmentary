"""Profile frozen final RAD checkpoints without changing deterministic test results.

This CPU-only parent reuses the guarded test runner's idle-GPU discovery, shared
exclusive locks, environment pinning and child UUID monitoring. It requires all
requested test results to be complete first, then writes a separate deployment
profile tree. Only the user's frozen allowed GPUs may be used.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
from scripts.run_rad_test import (
    digest,
    exclusive_locks,
    idle_snapshot,
    now,
    shared_lock_paths,
    stop_child,
    validate_request,
    write,
)
from scripts.run_rad_test import result_complete as test_result_complete

from segmentary import gpu_policy


def require_completed_tests(request: dict, request_hash: str) -> None:
    output = Path(request["output_root"])
    missing = [
        job["name"]
        for job in request["jobs"]
        if not test_result_complete(
            output,
            job,
            request_hash,
            request["class_names"],
            rehearsal=bool(request.get("rehearsal")),
        )
    ]
    if missing:
        raise ValueError(
            f"All test jobs must complete before deployment profiling; missing {len(missing)}: {missing[:5]}"
        )


def result_complete(output: Path, job: dict, request_hash: str, _class_names: list[str]) -> bool:
    path = output / job["name"] / "result.json"
    if not path.exists():
        return False
    result = json.loads(path.read_text())
    if result.get("status") != "completed":
        return False
    if (
        result.get("task") != "rad-final-deployment-profile"
        or result.get("request_sha256") != request_hash
        or result.get("checkpoint_sha256") != job["final_checkpoint_sha256"]
    ):
        raise ValueError(f"Existing deployment profile identity differs: {job['name']}")
    artifacts = result.get("artifacts", {})
    if "performance.json" not in artifacts:
        raise ValueError("Completed deployment profile lacks performance evidence")
    for artifact in artifacts.values():
        p = Path(artifact["path"])
        if not p.is_file() or digest(p) != artifact["sha256"]:
            raise ValueError(f"Deployment profile artifact changed: {p}")
    performance = result.get("performance", {})
    on_disk = json.loads(Path(artifacts["performance.json"]["path"]).read_text())
    if performance != on_disk:
        raise ValueError("Inline deployment profile differs from recorded artifact")
    source, contract = performance.get("source", {}), performance.get("contract", {})
    if (
        source.get("checkpoint_sha256") != job["final_checkpoint_sha256"]
        or source.get("config_sha256") != job["config_sha256"]
    ):
        raise ValueError("Deployment profile uses a different checkpoint/configuration")
    if (
        contract.get("deterministic") is not False
        or contract.get("batch_size") != 1
        or contract.get("input_shape_nchw") != [1, 3, 1024, 1024]
        or contract.get("measured_iterations") != 100
        or contract.get("warmup_iterations") != 20
        or contract.get("precision") != "bf16_autocast"
    ):
        raise ValueError("Deployment profile benchmark contract differs")
    latency = performance.get("measurements", {}).get("latency", {})
    samples = latency.get("raw_ms", [])
    if (
        len(samples) != 100
        or any(not math.isfinite(v) or v <= 0 for v in samples)
        or not math.isclose(latency.get("mean_ms", 0), sum(samples) / 100, rel_tol=1e-10)
        or not math.isclose(latency.get("fps", 0), 1000 / (sum(samples) / 100), rel_tol=1e-10)
    ):
        raise ValueError("Invalid deployment profile latency/FPS")
    return True


def run(args: argparse.Namespace) -> int:
    request_path = args.request.resolve()
    request, policy, request_hash = validate_request(request_path)
    selected_gpu = getattr(args, "gpu", None)
    if request["schema_version"] == 2 or request.get("rehearsal"):
        frozen_gpu = request.get("benchmark_gpu")
        if not isinstance(frozen_gpu, int) or (
            selected_gpu is not None and selected_gpu != frozen_gpu
        ):
            raise ValueError("Use the single benchmark GPU frozen in the paper request")
        selected_gpu = frozen_gpu
    entries = policy["allowed"]
    if selected_gpu is not None:
        entries = [gpu_policy.require_allowed(policy, selected_gpu)]
    test_output = Path(request["output_root"])
    require_completed_tests(request, request_hash)
    output = test_output.parent / "deployment-performance"
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
                "task": "rad-final-deployment-profile",
                "pid": os.getpid(),
                "started_at": started,
                "updated_at": now(),
                "request_sha256": request_hash,
                "allowed_gpus": [entry["index"] for entry in entries],
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
                    str(args.repo / "scripts/profile_rad_test.py"),
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
                                f"Profiler exited with code {process.returncode}; see {log}"
                            )
                    if not result_complete(output, job, request_hash, request["class_names"]):
                        raise RuntimeError("Profiler exited without verified completion evidence")
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
        with ThreadPoolExecutor(max_workers=len(entries)) as executor:
            futures = [executor.submit(worker, int(entry["index"])) for entry in entries]
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
    parser.add_argument("--python", default=sys.executable, help="Profiler runtime interpreter")
    parser.add_argument(
        "--gpu", type=int, default=None, help="single physical GPU for comparable serial profiles"
    )
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
