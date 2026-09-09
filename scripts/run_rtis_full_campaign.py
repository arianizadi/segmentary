"""Train, collect and profile each RTIS job before marking it complete."""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime

from segmentary.utils.resource_tracking import run_recorded


def validate_collection(state, diagnostics, performance, attempts, smoke=False):
    if diagnostics.get("test_evaluated") is not False:
        raise RuntimeError("Test-set boundary was not preserved")
    if not smoke and (
        diagnostics.get("smoke_limit") or not diagnostics.get("standalone_confusion_exact_match")
    ):
        raise RuntimeError("Incomplete or smoke-only diagnostics")
    required = {"best-auto-train", "best-auto-val", "best-alternate-val", "final-auto-val"}
    if set(diagnostics.get("results", {})) != required:
        raise RuntimeError("Missing train/val/raw-EMA/final evidence")
    if performance.get("status") != "complete":
        raise RuntimeError("Missing standardized performance evidence")
    if performance["source"]["checkpoint_sha256"] != state["checkpoints"]["best"]["sha256"]:
        raise RuntimeError("Performance checkpoint differs from selected checkpoint")
    for value in [
        performance["model"]["parameter_count"],
        performance["measurements"]["latency"]["fps"],
        performance["measurements"]["peak_reserved_bytes"],
    ]:
        if not math.isfinite(value) or value <= 0:
            raise RuntimeError("Invalid performance measurement")
    if not attempts or any(a["status"] in ("running", "incomplete") for a in attempts):
        raise RuntimeError("Resource accounting contains an unresolved attempt")
    for phase in ("training", "diagnostics", "performance"):
        if not any(
            a["phase"] == phase and a["status"] == "completed" and a["wall_clock_s"] > 0
            for a in attempts
        ):
            raise RuntimeError(f"Missing timing for {phase}")


def collect_job(root, repo, job, gpu, campaign):
    from scripts.collect_rtis_statistics import validate_dataset

    from segmentary.config import load_experiment

    started = time.monotonic()
    validate_dataset(root, job, load_experiment([Path(job["config"])]), campaign)
    runtime.run_job(root, repo, job, gpu, campaign)
    state_path = root / "state" / (job["name"] + ".json")
    state = runtime.read(state_path)
    if state["status"] != "collecting":
        raise RuntimeError("Full collection contract is required")
    state.pop("finished_at", None)
    runtime.write(state_path, state)
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": str(gpu),
        "PYTHONPATH": str(repo / "src"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "OMP_NUM_THREADS": "4",
    }
    commands = [
        (
            "diagnostics",
            [
                sys.executable,
                str(repo / "scripts/collect_rtis_statistics.py"),
                "--campaign",
                str(root),
                "--job",
                job["name"],
            ],
        ),
        (
            "performance",
            [
                sys.executable,
                str(repo / "scripts/profile_rtis_campaign.py"),
                "--campaign",
                str(root),
                "--repo",
                str(repo),
                "--measure",
                job["name"],
            ],
        ),
    ]
    smoke = bool(campaign.get("smoke"))
    if smoke:
        commands[0][1].extend(["--limit-per-split", "2"])
    with (root / "logs" / (job["name"] + ".log")).open("a") as log:
        for phase, command in commands:
            state["collection_phase"] = phase
            runtime.write(state_path, state)
            run_recorded(
                command,
                cwd=repo,
                env=env,
                stdout=log,
                records=root / "attempts" / job["name"],
                phase=phase,
            )
    run = Path(state["checkpoints"]["best"]["path"]).parent
    diagnostics = runtime.read(run / "diagnostics/summary.json")
    performance = runtime.read(root / "performance" / (job["name"] + ".json"))
    attempts = [runtime.read(p) for p in sorted((root / "attempts" / job["name"]).glob("*.json"))]
    validate_collection(state, diagnostics, performance, attempts, smoke)
    phases = {}
    for attempt in attempts:
        phases[attempt["phase"]] = phases.get(attempt["phase"], 0) + attempt["wall_clock_s"]
    artifacts = {}
    for key, result in diagnostics["results"].items():
        artifacts[key] = {}
        for name, path in result["artifacts"].items():
            source = Path(path)
            artifacts[key][name] = {
                "path": str(source),
                "sha256": runtime.digest(source),
                "bytes": source.stat().st_size,
            }
    telemetry_path = run / "diagnostics/resource-telemetry.csv"
    with telemetry_path.open("w", newline="") as stream:
        columns = [
            "phase",
            "attempt_started_at",
            "elapsed_seconds",
            "device_used_mib",
            "gpu_utilization_percent",
            "board_power_w",
            "temperature_c",
        ]
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for attempt in attempts:
            for sample in attempt.get("telemetry", []):
                writer.writerow(
                    {
                        "phase": attempt["phase"],
                        "attempt_started_at": attempt["started_at"],
                        **sample,
                    }
                )
    artifacts["resources"] = {
        "telemetry.csv": {
            "path": str(telemetry_path),
            "sha256": runtime.digest(telemetry_path),
            "bytes": telemetry_path.stat().st_size,
        }
    }
    attempt_summaries = [
        {
            **{k: v for k, v in a.items() if k != "telemetry"},
            "telemetry_samples": len(a.get("telemetry", [])),
            "sampled_peak_device_used_mib": max(
                (
                    t["device_used_mib"]
                    for t in a.get("telemetry", [])
                    if t.get("device_used_mib") is not None
                ),
                default=None,
            ),
        }
        for a in attempts
    ]
    state.update(
        status="collecting",
        collection_phase="cleanup",
        performance=performance,
        collection={
            "contract": "rtis-full-statistics-v1",
            "diagnostics": diagnostics,
            "artifacts": artifacts,
            "resources": {
                "phase_wall_seconds_including_failed_attempts": phases,
                "phase_gpu_hours_including_failed_attempts": {
                    k: v / 3600 for k, v in phases.items()
                },
                "job_wrapper_wall_seconds": time.monotonic() - started,
                "attempts": attempt_summaries,
            },
            "verified": True,
            "smoke": smoke,
        },
    )
    runtime.write(state_path, state)
    try:
        state["checkpoint_bytes_removed"] = runtime.cleanup(
            run, {**state, "status": "completed"}, root / "cleanup" / (job["name"] + ".json")
        )
    except Exception as error:
        state["cleanup_error"] = str(error)
    runtime.write(state_path, state)


def run_job(root, repo, job, gpu, campaign):
    records = root / "job-attempts" / job["name"]
    records.mkdir(parents=True, exist_ok=True)
    path = records / f"{len(list(records.glob('*.json'))):04d}.json"
    started = time.monotonic()
    record = {"started_at": runtime.now(), "status": "running", "gpu": gpu}
    runtime.write(path, record)
    try:
        collect_job(root, repo, job, gpu, campaign)
    except BaseException:
        record["status"] = "failed"
        raise
    else:
        record["status"] = "completed"
    finally:
        record.update(finished_at=runtime.now(), wall_clock_s=time.monotonic() - started)
        runtime.write(path, record)
        state_path = root / "state" / (job["name"] + ".json")
        state = runtime.read(state_path)
        if state.get("collection"):
            spans = [runtime.read(p) for p in sorted(records.glob("*.json"))]
            resources = state["collection"]["resources"]
            resources["worker_attempts"] = spans
            resources["total_reserved_gpu_wall_seconds"] = sum(
                s.get("wall_clock_s", 0) for s in spans
            )
            resources["total_reserved_gpu_hours"] = (
                resources["total_reserved_gpu_wall_seconds"] / 3600
            )
            resources["whole_run_accounting_complete"] = all(
                s["status"] != "running" and s.get("wall_clock_s", 0) > 0 for s in spans
            )
            if record["status"] == "completed" and resources["whole_run_accounting_complete"]:
                state.update(status="completed", collection_phase="complete")
            if not resources["whole_run_accounting_complete"]:
                state.update(
                    status="failed",
                    error="An earlier worker attempt has incomplete timing; fresh run required for full accounting",
                )
            state["finished_at"] = runtime.now()
            runtime.write(state_path, state)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--gpu", type=int, required=True)
    args = ap.parse_args()
    runtime.worker(
        args.campaign.resolve(), Path(__file__).resolve().parents[1], args.gpu, run=run_job
    )


if __name__ == "__main__":
    main()
