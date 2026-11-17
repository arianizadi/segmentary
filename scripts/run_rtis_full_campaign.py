"""Train, collect and profile each RTIS job before marking it complete."""

from __future__ import annotations

import argparse
import csv
import math
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime

from segmentary import gpu_policy
from segmentary.utils.resource_tracking import run_recorded

PAPER_MAXIMUM_ATTEMPTS = 3


def process_alive(record):
    """Signal zero checks ownership without changing a process or its device state."""
    pid = record.get("pid")
    if (
        not isinstance(pid, int)
        or pid <= 0
        or record.get("hostname", socket.gethostname()) != socket.gethostname()
    ):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def observed_end(record):
    """The last recorded execution observation, excluding later recovery downtime."""
    values = []
    for field in ("finished_at", "last_observed_at"):
        if record.get(field):
            values.append(datetime.fromisoformat(record[field]))
    elapsed = [record.get("wall_clock_s", 0)] + [
        sample.get("elapsed_seconds", 0) for sample in record.get("telemetry", [])
    ]
    measured = [
        value
        for value in elapsed
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
    ]
    if record.get("started_at") and measured:
        values.append(
            datetime.fromisoformat(record["started_at"]) + timedelta(seconds=max(measured))
        )
    return max(values) if values else None


def normalize_paper_interruptions(root, job):
    """Called while the job lock is held, before resuming the same frozen run."""
    paths = sorted((root / "attempts" / job["name"]).glob("*.json")) + sorted(
        (root / "job-attempts" / job["name"]).glob("*.json")
    )
    records = [(path, runtime.read(path)) for path in paths]
    pending = [
        (path, record)
        for path, record in records
        if record.get("status") in ("running", "incomplete")
    ]
    if any(process_alive(record) for _, record in pending):
        raise RuntimeError("A paper job still has a live attempt owner")
    worker_starts = [
        datetime.fromisoformat(record["started_at"])
        for path, record in records
        if path.parent.parent.name == "job-attempts" and record.get("started_at")
    ]
    worker_paths = sorted(path for path, _ in records if path.parent.parent.name == "job-attempts")
    for path, record in pending:
        end = observed_end(record)
        start = datetime.fromisoformat(record["started_at"]) if record.get("started_at") else None
        worker_record = path.parent.parent.name == "job-attempts"
        if worker_record and start:
            next_start = min((value for value in worker_starts if value > start), default=None)
            observations = []
            for phase_path, phase in records:
                if phase_path.parent.parent.name != "attempts" or not phase.get("started_at"):
                    continue
                phase_start = datetime.fromisoformat(phase["started_at"])
                if phase_start >= start and (next_start is None or phase_start < next_start):
                    observations.append(observed_end(phase))
            end = max((value for value in [end, *observations] if value is not None), default=None)
        lower_bound = max(0.0, (end - start).total_seconds()) if end and start else 0.0
        failure = (
            {
                "failure": paper_failure(
                    job,
                    worker_paths.index(path) + 1,
                    "infrastructure",
                    "Interrupted infrastructure attempt",
                )
            }
            if worker_record
            else {}
        )
        runtime.write(
            path,
            {
                **record,
                "status": "interrupted",
                "wall_clock_s": lower_bound,
                "duration_lower_bound_s": lower_bound,
                "wall_clock_s_is_lower_bound": True,
                "accounting_complete": False,
                "missing_tail_seconds": None,
                "last_observed_at": end.isoformat() if end else None,
                "interruption_recorded_at": runtime.now(),
                **failure,
            },
        )


def paper_failure(job, attempt, kind, error):
    return {
        "kind": kind,
        "retryable": kind == "infrastructure" and attempt < PAPER_MAXIMUM_ATTEMPTS,
        "attempt": attempt,
        "maximum_attempts": PAPER_MAXIMUM_ATTEMPTS,
        "config_sha256": job["config_sha256"],
        "seed": job["seed"],
        "error": str(error),
    }


def recover_paper_job(root, job, campaign):
    """Requeue a stopped infrastructure attempt under the same config and seed."""
    if not campaign.get("research_protocol"):
        return False
    with runtime.lock(root / "locks" / f"{job['name']}.lock") as acquired:
        if not acquired:
            return False
        path = root / "state" / (job["name"] + ".json")
        state = runtime.read(path)
        if state.get("status") in ("queued", "completed"):
            return False
        if (
            runtime.digest(job["config"]) != job["config_sha256"]
            or state.get("config_sha256") != job["config_sha256"]
        ):
            raise RuntimeError("Paper recovery configuration differs from the frozen run")
        spans = sorted((root / "job-attempts" / job["name"]).glob("*.json"))
        if not spans:
            raise RuntimeError("Paper recovery requires a durable worker attempt record")
        for span in spans:
            record = runtime.read(span)
            if (
                record.get("config_sha256", job["config_sha256"]) != job["config_sha256"]
                or record.get("seed", job["seed"]) != job["seed"]
            ):
                raise RuntimeError("Paper recovery attempt identity differs from the frozen run")
        failure = state.get("failure")
        if state.get("status") == "failed" and (
            not failure or failure.get("kind") != "infrastructure"
        ):
            return False
        normalize_paper_interruptions(root, job)
        failure = (
            paper_failure(job, len(spans), "infrastructure", "Interrupted infrastructure attempt")
            if state.get("status") != "failed"
            else failure
        )
        if (
            failure.get("config_sha256") != job["config_sha256"]
            or failure.get("seed") != job["seed"]
            or failure.get("attempt") != len(spans)
            or failure.get("maximum_attempts") != PAPER_MAXIMUM_ATTEMPTS
        ):
            raise RuntimeError("Paper failure identity differs from the frozen run")
        if len(spans) >= PAPER_MAXIMUM_ATTEMPTS or not failure.get("retryable"):
            state.update(status="failed", failure={**failure, "retryable": False})
            runtime.write(path, state)
            return False
        state.update(
            status="queued",
            failure=failure,
            recovery={"method": "same_config_seed_checkpoint_resume", "queued_at": runtime.now()},
        )
        runtime.write(path, state)
        return True


def classify_paper_failure(error, log_text):
    if "NONFINITE_TRAINING_LOSS" in str(error) + log_text:
        return "nonfinite_training_loss"
    if isinstance(error, (OSError, subprocess.TimeoutExpired, gpu_policy.GpuInspectionError)):
        return "infrastructure"
    if isinstance(error, gpu_policy.GpuPolicyError) and "could not be verified for" in str(error):
        return "infrastructure"
    if isinstance(error, subprocess.CalledProcessError) and error.returncode in (-9, -15, 137, 143):
        return "infrastructure"
    return "model_or_contract"


def validate_collection(
    state,
    diagnostics,
    performance,
    attempts,
    smoke=False,
    primary_checkpoint="best",
    collection_contract="rtis-full-statistics-v1",
    allow_interrupted_accounting=False,
):
    final_train = collection_contract == runtime.FINAL_TRAIN_CONTRACT
    anchor = runtime.primary_checkpoint(
        {"primary_checkpoint": primary_checkpoint, "collection_contract": collection_contract}
    )
    if diagnostics.get("test_evaluated") is not False:
        raise RuntimeError("Test-set boundary was not preserved")
    if not smoke and (
        diagnostics.get("smoke_limit") or not diagnostics.get("standalone_confusion_exact_match")
    ):
        raise RuntimeError("Incomplete or smoke-only diagnostics")
    required = (
        {"final-auto-train", "final-alternate-train"}
        if final_train
        else {"best-auto-train", "best-auto-val", "best-alternate-val", "final-auto-val"}
    )
    if set(diagnostics.get("results", {})) != required:
        raise RuntimeError("Missing train/val/raw-EMA/final evidence for the collection contract")
    if final_train:
        if diagnostics.get("contract") != collection_contract:
            raise RuntimeError("Final-train diagnostic contract differs from the campaign")
        if set(state.get("checkpoints", {})) != {"final"}:
            raise RuntimeError("Final-train collection requires exactly one final checkpoint")
        if (
            state.get("evaluation_split") != "train"
            or state.get("evaluation", {}).get("config", {}).get("evaluation", {}).get("split")
            != "train"
            or diagnostics.get("standalone_variant") != "final-auto-train"
        ):
            raise RuntimeError("Final-train collection requires genuine train evaluation evidence")
        if (
            not state.get("evaluation_result", {}).get("sha256")
            or performance.get("source", {}).get("result_sha256")
            != state["evaluation_result"]["sha256"]
        ):
            raise RuntimeError("Performance result differs from the final-train evaluation")
        if any(
            diagnostics["results"][variant].get("checkpoint_sha256")
            != state["checkpoints"]["final"]["sha256"]
            for variant in required
        ):
            raise RuntimeError("Diagnostics checkpoint differs from the final checkpoint")
    if performance.get("status") != "complete":
        raise RuntimeError("Missing standardized performance evidence")
    if performance["source"]["checkpoint_sha256"] != state["checkpoints"][anchor]["sha256"]:
        raise RuntimeError("Performance checkpoint differs from primary checkpoint")
    if diagnostics.get("primary_checkpoint", anchor) != anchor:
        raise RuntimeError("Diagnostics checkpoint differs from primary checkpoint")
    if state.get("evaluation_checkpoint", anchor) != anchor:
        raise RuntimeError("Standalone evaluation differs from primary checkpoint")
    for value in [
        performance["model"]["parameter_count"],
        performance["measurements"]["latency"]["fps"],
        performance["measurements"]["peak_reserved_bytes"],
    ]:
        if not math.isfinite(value) or value <= 0:
            raise RuntimeError("Invalid performance measurement")
    if not attempts or any(a["status"] in ("running", "incomplete") for a in attempts):
        raise RuntimeError("Resource accounting contains an unresolved attempt")
    for attempt in attempts:
        if attempt["status"] == "interrupted" and not (
            allow_interrupted_accounting
            and attempt.get("accounting_complete") is False
            and attempt.get("wall_clock_s_is_lower_bound") is True
            and attempt.get("missing_tail_seconds") is None
            and isinstance(attempt.get("wall_clock_s"), (int, float))
            and math.isfinite(attempt["wall_clock_s"])
            and attempt["wall_clock_s"] >= 0
            and attempt.get("duration_lower_bound_s") == attempt["wall_clock_s"]
        ):
            raise RuntimeError(
                "Interrupted resource accounting lacks an explicit duration lower bound"
            )
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
    policy = gpu_policy.load(campaign)
    state["gpu_uuid"] = gpu_policy.require_allowed(policy, gpu)["uuid"]
    runtime.write(state_path, state)
    env = gpu_policy.child_env(
        {
            **os.environ,
            "PYTHONPATH": str(repo / "src"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "OMP_NUM_THREADS": "4",
        },
        policy,
        gpu,
        root / "campaign.json",
    )
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
                expected_gpu_uuid=state["gpu_uuid"],
            )
    run = Path(state["checkpoints"][runtime.primary_checkpoint(campaign)]["path"]).parent
    diagnostics = runtime.read(run / "diagnostics/summary.json")
    performance = runtime.read(root / "performance" / (job["name"] + ".json"))
    attempts = [runtime.read(p) for p in sorted((root / "attempts" / job["name"]).glob("*.json"))]
    validate_collection(
        state,
        diagnostics,
        performance,
        attempts,
        smoke,
        primary_checkpoint=runtime.primary_checkpoint(campaign),
        collection_contract=campaign.get("collection_contract", "rtis-full-statistics-v1"),
        allow_interrupted_accounting=bool(campaign.get("research_protocol")),
    )
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
    resources = {
        "phase_wall_seconds_including_failed_attempts": phases,
        "phase_gpu_hours_including_failed_attempts": {k: v / 3600 for k, v in phases.items()},
        "job_wrapper_wall_seconds": time.monotonic() - started,
        "attempts": attempt_summaries,
    }
    if campaign.get("research_protocol"):
        resources["phase_accounting_complete"] = {
            phase: all(a.get("accounting_complete", True) for a in attempts if a["phase"] == phase)
            for phase in phases
        }
        resources["phase_wall_seconds_are_lower_bounds"] = {
            phase: any(
                a.get("wall_clock_s_is_lower_bound", False) for a in attempts if a["phase"] == phase
            )
            for phase in phases
        }
    state.update(
        status="collecting",
        collection_phase="cleanup",
        performance=performance,
        collection={
            "contract": (
                runtime.FINAL_TRAIN_CONTRACT
                if campaign.get("collection_contract") == runtime.FINAL_TRAIN_CONTRACT
                else "rtis-full-statistics-v1"
            ),
            "diagnostics": diagnostics,
            "artifacts": artifacts,
            "resources": resources,
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
    gpu_uuid = gpu_policy.require_allowed(gpu_policy.load(campaign), gpu)["uuid"]
    records = root / "job-attempts" / job["name"]
    records.mkdir(parents=True, exist_ok=True)
    paper = bool(campaign.get("research_protocol"))
    if paper:
        normalize_paper_interruptions(root, job)
        if len(list(records.glob("*.json"))) >= PAPER_MAXIMUM_ATTEMPTS:
            raise RuntimeError("Paper infrastructure retry budget exhausted")
    path = records / f"{len(list(records.glob('*.json'))):04d}.json"
    started = time.monotonic()
    record = {"started_at": runtime.now(), "status": "running", "gpu": gpu, "gpu_uuid": gpu_uuid}
    log_path = root / "logs" / (job["name"] + ".log")
    log_offset = log_path.stat().st_size if log_path.exists() else 0
    if paper:
        record.update(
            pid=os.getpid(),
            hostname=socket.gethostname(),
            config_sha256=job["config_sha256"],
            seed=job["seed"],
        )
    runtime.write(path, record)
    try:
        collect_job(root, repo, job, gpu, campaign)
    except BaseException as error:
        record["status"] = "failed"
        if paper:
            log_text = ""
            if log_path.exists():
                with log_path.open("rb") as stream:
                    stream.seek(max(log_offset, log_path.stat().st_size - 65536))
                    log_text = stream.read().decode(errors="replace")
            record["failure"] = paper_failure(
                job,
                len(list(records.glob("*.json"))),
                classify_paper_failure(error, log_text),
                error,
            )
            state_path = root / "state" / (job["name"] + ".json")
            state = runtime.read(state_path)
            state.update(status="failed", failure=record["failure"])
            runtime.write(state_path, state)
        raise
    else:
        record["status"] = "completed"
    finally:
        record.update(finished_at=runtime.now(), wall_clock_s=time.monotonic() - started)
        runtime.write(path, record)
        state_path = root / "state" / (job["name"] + ".json")
        state = runtime.read(state_path)
        spans = [runtime.read(p) for p in sorted(records.glob("*.json"))]
        if paper:
            state["failure_history"] = [span["failure"] for span in spans if span.get("failure")]
        if state.get("collection"):
            resources = state["collection"]["resources"]
            resources["worker_attempts"] = spans
            resources["total_reserved_gpu_wall_seconds"] = sum(
                s.get("wall_clock_s", 0) for s in spans
            )
            resources["total_reserved_gpu_hours"] = (
                resources["total_reserved_gpu_wall_seconds"] / 3600
            )
            resources["whole_run_accounting_complete"] = all(
                s["status"] != "running"
                and s.get("wall_clock_s", 0) > 0
                and s.get("accounting_complete", True)
                for s in spans
            )
            if paper:
                resources["reserved_gpu_wall_seconds_is_lower_bound"] = not resources[
                    "whole_run_accounting_complete"
                ]
                resources["unknown_missing_tail_seconds"] = (
                    None if not resources["whole_run_accounting_complete"] else 0
                )
            if record["status"] == "completed" and (
                resources["whole_run_accounting_complete"] or paper
            ):
                state.update(status="completed", collection_phase="complete")
            if not resources["whole_run_accounting_complete"] and not paper:
                state.update(
                    status="failed",
                    error="An earlier worker attempt has incomplete timing; fresh run required for full accounting",
                )
            state["finished_at"] = runtime.now()
            runtime.write(state_path, state)
        elif paper:
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
