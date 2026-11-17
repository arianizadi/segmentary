"""Evaluate frozen Cityscapes and City-to-Rail source checkpoints on native validation.

The CPU parent schedules one pinned child per idle, shared-locked GPU. Each child
re-hashes its original source files, runs full deterministic auto-bank validation,
then profiles that exact bank in a fresh BF16 deployment process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import queue
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

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
    write,
)

from segmentary import gpu_policy

STAGES = {"cityscapes": ("cityscapes", 500), "cityscapes_to_railsem19": ("railsem19", 850)}


def verify_checkout(repo: Path, expected: str) -> None:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip()
    if sha != expected or dirty:
        raise ValueError("Source-stage evaluation requires its frozen clean code checkout")


def validate_request(path: Path, repo: Path, *, verify_code: bool = True) -> tuple[dict, dict, str]:
    request = json.loads(path.read_text())
    if (
        request.get("schema_version") != 1
        or request.get("source_stage_evaluation_authorized") is not True
    ):
        raise ValueError("An explicitly authorized schema-1 source-stage request is required")
    request_sha = digest(path)
    campaign = json.loads(Path(request["campaign_json"]).read_text())
    binding = campaign.get("research_protocol", {}).get("source_stage_reports", {})
    if binding != {"spec": str(path.resolve()), "spec_sha256": request_sha}:
        raise ValueError("Main campaign does not bind this exact source-stage request")
    protocol = campaign["research_protocol"]
    protocol_sha = hashlib.sha256(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if campaign.get("research_protocol_sha256") != protocol_sha:
        raise ValueError("Main campaign research protocol SHA-256 changed")
    if request.get("code_sha") != campaign.get("code_sha"):
        raise ValueError("Source-stage code SHA differs from the main campaign")
    if verify_code:
        verify_checkout(repo, request["code_sha"])
    policy = gpu_policy.load(campaign)
    if set(gpu_policy.allowed_indices(policy)) != set(range(10)):
        raise ValueError("Source stages require the explicitly frozen 0-9 campaign policy")
    if campaign.get("gpu_policy_sha256") != gpu_policy.policy_sha256(policy):
        raise ValueError("Main campaign GPU policy SHA-256 changed")
    output = Path(request["output_root"])
    if not output.is_absolute():
        raise ValueError("Source-stage output_root must be absolute")
    models, jobs = request.get("models"), request.get("jobs")
    if not isinstance(models, list) or len(models) != 8 or len(set(models)) != 8:
        raise ValueError("Source stages require eight distinct frozen models")
    if not isinstance(jobs, list) or len(jobs) != 16:
        raise ValueError("Source stages require exactly sixteen jobs")
    keys = []
    for job in jobs:
        model, stage = job.get("model"), job.get("stage")
        if (
            model not in models
            or stage not in STAGES
            or type(job.get("seed")) is not int
            or job["seed"] != 0
        ):
            raise ValueError("Source jobs must use the two native stages and source seed 0")
        if job.get("name") != f"{model}--{stage}--seed-0" or Path(model).name != model:
            raise ValueError("Unexpected source-stage job name")
        if (job.get("dataset"), job.get("expected_images")) != STAGES[stage]:
            raise ValueError("Native source-stage dataset/count mismatch")
        if type(job.get("checkpoint_global_step")) is not int or job["checkpoint_global_step"] < 1:
            raise ValueError("A positive recorded source checkpoint step is required")
        for key in ("config_sha256", "checkpoint_sha256"):
            value = job.get(key)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("Full lowercase source SHA-256 values are required")
        names = job.get("class_names")
        if (
            not isinstance(names, list)
            or len(names) != (19 if stage == "cityscapes" else 21)
            or len(set(names)) != len(names)
        ):
            raise ValueError("Every native taxonomy class must be retained")
        if (
            not isinstance(job.get("taxonomy"), str)
            or not job.get("training_receipt", {}).get("record")
            or not job.get("public_pretraining")
        ):
            raise ValueError(
                "Source taxonomy, complete training receipt and public provenance are required"
            )
        data = job.get("evaluation_data", {})
        if data.get("dataset") != job["dataset"] or not Path(data.get("root", "")).is_absolute():
            raise ValueError("Pinned native evaluation data is required")
        if stage == "cityscapes_to_railsem19" and (
            not Path(data.get("split_file", "")).is_absolute()
            or not isinstance(data.get("split_file_sha256"), str)
            or len(data["split_file_sha256"]) != 64
        ):
            raise ValueError("RailSem19 requires its byte-bound native validation split file")
        if any(
            not Path(value).is_absolute()
            for value in (job["config"], job["checkpoint"], job["training_receipt"]["path"])
        ):
            raise ValueError("Source config, checkpoint and receipt paths must be absolute")
        keys.append((model, stage))
    if len(set(keys)) != 16 or set(keys) != {
        (model, stage) for model in models for stage in STAGES
    }:
        raise ValueError("Source request must cover every model/stage pair exactly once")
    return request, policy, request_sha


def verify_source(job: dict) -> None:
    for filename, expected in (
        (job["config"], job["config_sha256"]),
        (job["checkpoint"], job["checkpoint_sha256"]),
        (job["training_receipt"]["path"], job["training_receipt"]["sha256"]),
    ):
        if digest(Path(filename)) != expected:
            raise ValueError(f"Frozen source bytes changed: {filename}")
    if (
        json.loads(Path(job["training_receipt"]["path"]).read_text())
        != job["training_receipt"]["record"]
    ):
        raise ValueError("Source training receipt differs from its frozen complete record")
    if job["training_receipt"]["record"].get("seed") != 0:
        raise ValueError("The source training receipt must record source seed 0")
    data_override = job["evaluation_data"]
    if not Path(data_override["root"]).is_dir():
        raise ValueError("Pinned native dataset root is missing")
    if data_override.get("split_file") is not None and digest(
        Path(data_override["split_file"])
    ) != data_override.get("split_file_sha256"):
        raise ValueError("Pinned source validation split bytes changed")
    cfg = yaml.safe_load(Path(job["config"]).read_text())
    data = cfg["stages"][-1]["data"][0]
    if (
        cfg["train"]["seed"] != 0
        or cfg["space"] != job["taxonomy"]
        or data["name"] != job["dataset"]
        or data.get("limit") is not None
    ):
        raise ValueError("Source config differs from its native full-validation request")


def verified_result(request: dict, job: dict, request_sha: str) -> dict | None:
    path = Path(request["output_root"]) / job["name"] / "result.json"
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    if (
        result.get("status") != "completed"
        or result.get("request_sha256") != request_sha
        or result.get("checkpoint_sha256") != job["checkpoint_sha256"]
        or result.get("config_sha256") != job["config_sha256"]
    ):
        raise ValueError("Existing source result differs from the frozen request")
    for entry in result["artifacts"].values():
        if digest(Path(entry["path"])) != entry["sha256"]:
            raise ValueError("Completed source-stage evidence changed")
    evaluation = json.loads(Path(result["artifacts"]["evaluation"]["path"]).read_text())
    performance = json.loads(Path(result["artifacts"]["performance"]["path"]).read_text())
    check_evidence(
        request, job, evaluation, performance, result["artifacts"]["evaluation"]["sha256"]
    )
    return result


def check_evidence(
    request: dict, job: dict, evaluation: dict, performance: dict, evaluation_sha: str
) -> None:
    metadata = evaluation.get("config", {}).get("evaluation", {})
    if (
        evaluation.get("git_sha") != request["code_sha"]
        or evaluation.get("git_dirty") is not False
        or evaluation.get("seed") != 0
        or evaluation.get("stage") != f"eval:{job['dataset']}:val"
    ):
        raise ValueError("Fresh source evaluation provenance mismatch")
    if (
        evaluation.get("dataset_sizes", {}).get("eval") != job["expected_images"]
        or metadata.get("split") != "val"
        or metadata.get("deterministic") is not True
        or metadata.get("weights") not in ("raw", "ema")
        or metadata.get("tta", {}).get("enabled") is not False
        or metadata.get("data", {}).get("limit") is not None
        or metadata.get("data", {}).get("name") != job["evaluation_data"]["dataset"]
        or metadata.get("data", {}).get("root") != job["evaluation_data"]["root"]
        or metadata.get("data", {}).get("split_file") != job["evaluation_data"].get("split_file")
    ):
        raise ValueError(
            "Source evaluation must cover full native validation with deterministic auto weights"
        )
    metrics = evaluation.get("metrics", {})
    if (
        set(metrics.get("per_class_iou", {})) != set(job["class_names"])
        or not isinstance(metrics.get("miou"), (int, float))
        or not math.isfinite(metrics["miou"])
    ):
        raise ValueError("Source evaluation lacks its full native class metrics")
    source = performance.get("source", {})
    contract = performance.get("contract", {})
    if (
        performance.get("status") != "complete"
        or source.get("checkpoint_sha256") != job["checkpoint_sha256"]
        or source.get("config_sha256") != job["config_sha256"]
        or source.get("result_sha256") != evaluation_sha
        or source.get("weights") != metadata["weights"]
    ):
        raise ValueError("Source profile does not match the fresh evaluation weight bank")
    if (
        contract.get("precision") != "bf16_autocast"
        or contract.get("input_shape_nchw") != [1, 3, 1024, 1024]
        or contract.get("warmup_iterations") != 20
        or contract.get("measured_iterations") != 100
    ):
        raise ValueError("Source profile differs from the frozen deployment contract")
    measurements = performance.get("measurements", {})
    fps = measurements.get("latency", {}).get("fps")
    if (
        not isinstance(fps, (int, float))
        or not math.isfinite(fps)
        or fps <= 0
        or type(measurements.get("peak_reserved_bytes")) is not int
        or measurements["peak_reserved_bytes"] <= 0
    ):
        raise ValueError("Source profile lacks measured FPS and allocator memory")


def evaluate_job(request_path: Path, job_name: str, gpu: int, repo: Path, python: str) -> dict:
    request, policy, request_sha = validate_request(request_path, repo)
    job = next(job for job in request["jobs"] if job["name"] == job_name)
    gpu_policy.assert_env(policy, gpu)
    existing = verified_result(request, job, request_sha)
    if existing is not None:
        return existing
    verify_source(job)
    directory = Path(request["output_root"]) / job_name
    directory.mkdir(parents=True, exist_ok=True)
    evaluation_path, profile_path = directory / "evaluation.json", directory / "performance.json"
    evaluation_command = [
        python,
        "-m",
        "segmentary.eval",
        job["config"],
        "--ckpt",
        job["checkpoint"],
        "--auto-weights",
        "--deterministic",
        "--split",
        "val",
        "--out",
        str(evaluation_path),
    ]
    source_data = yaml.safe_load(Path(job["config"]).read_text())["stages"][-1]["data"][0]
    override = job["evaluation_data"]
    evaluation_command.extend(
        [
            "--dataset",
            override["dataset"],
            "--root",
            override["root"],
            "--loader-options",
            json.dumps(source_data.get("loader_options") or {}),
        ]
    )
    if source_data.get("loader") is not None:
        evaluation_command.extend(["--loader", source_data["loader"]])
    if source_data.get("mapping") is not None:
        evaluation_command.extend(["--mapping", source_data["mapping"]])
    if override.get("split_file") is not None:
        evaluation_command.extend(["--split-file", override["split_file"]])
    if source_data.get("variant") is not None:
        evaluation_command.extend(["--variant", str(source_data["variant"])])
    subprocess.run(evaluation_command, cwd=repo, check=True)
    performance_command = [
        python,
        "-m",
        "segmentary.performance",
        job["config"],
        "--model-id",
        job["model"],
        "--measured-job-id",
        job_name,
        "--applies-to",
        job_name,
        "--ckpt",
        job["checkpoint"],
        "--result",
        str(evaluation_path),
        "--out",
        str(profile_path),
        "--expected-git-sha",
        request["code_sha"],
        "--expected-result-git-sha",
        request["code_sha"],
        "--expected-result-stage",
        f"eval:{job['dataset']}:val",
        "--expected-seed",
        "0",
        "--checkpoint-global-step",
        str(job["checkpoint_global_step"]),
        "--auto-weights",
        "--height",
        "1024",
        "--width",
        "1024",
        "--warmup",
        "20",
        "--iterations",
        "100",
    ]
    subprocess.run(performance_command, cwd=repo, check=True)
    evaluation, performance = (
        json.loads(path.read_text()) for path in (evaluation_path, profile_path)
    )
    evaluation_sha = digest(evaluation_path)
    check_evidence(request, job, evaluation, performance, evaluation_sha)
    result = {
        "status": "completed",
        "request_sha256": request_sha,
        "config_sha256": job["config_sha256"],
        "checkpoint_sha256": job["checkpoint_sha256"],
        "finished_at": now(),
        "artifacts": {
            "evaluation": {"path": str(evaluation_path), "sha256": evaluation_sha},
            "performance": {"path": str(profile_path), "sha256": digest(profile_path)},
        },
    }
    write(directory / "result.json", result)
    return result


def build_report(request: dict, request_sha: str, *, write_output: bool = True) -> dict:
    models = []
    completed_at = []
    for model in request["models"]:
        stages = []
        for stage in STAGES:
            job = next(
                job for job in request["jobs"] if job["model"] == model and job["stage"] == stage
            )
            result = verified_result(request, job, request_sha)
            if result is None:
                raise ValueError("Source-stage report requires all sixteen verified results")
            completed_at.append(result["finished_at"])
            evaluation = json.loads(Path(result["artifacts"]["evaluation"]["path"]).read_text())
            performance = json.loads(Path(result["artifacts"]["performance"]["path"]).read_text())
            stages.append(
                {
                    "stage": stage,
                    "dataset": job["dataset"],
                    "split": "val",
                    "source_seed": 0,
                    "taxonomy": job["taxonomy"],
                    "class_names": job["class_names"],
                    "metrics": evaluation,
                    "performance": performance,
                    "checkpoint": {
                        "path": job["checkpoint"],
                        "sha256": job["checkpoint_sha256"],
                        "global_step": job["checkpoint_global_step"],
                    },
                    "config": {"path": job["config"], "sha256": job["config_sha256"]},
                    "evaluation_receipt": result["artifacts"]["evaluation"],
                    "performance_receipt": result["artifacts"]["performance"],
                    "training_receipt": {
                        "path": job["training_receipt"]["path"],
                        "sha256": job["training_receipt"]["sha256"],
                    },
                    "training": job["training_receipt"]["record"],
                    "public_pretraining": job["public_pretraining"],
                    "evaluation_data": job["evaluation_data"],
                }
            )
        models.append({"model": model, "stages": stages})
    report = {
        "schema_version": 1,
        "request_sha256": request_sha,
        "code_sha": request["code_sha"],
        "generated_at": max(completed_at),
        "source_seed": 0,
        "evaluation_weight_policy": "fresh auto bank, shared exactly with the deployment profile",
        "stage_comparison_scope": "native datasets and label spaces differ",
        "models": models,
    }
    if write_output:
        path = Path(request["output_root"]) / "source-stage-reports.json"
        if path.exists():
            if json.loads(path.read_text()) != report:
                raise ValueError("Existing aggregate differs from its verified frozen evidence")
        else:
            write(path, report)
    return report


def load_verified_report(request_path: Path, repo: Path) -> dict:
    """Read the aggregate after independently verifying its entire frozen job set."""
    request, _policy, request_sha = validate_request(
        request_path.resolve(), repo, verify_code=False
    )
    path = Path(request["output_root"]) / "source-stage-reports.json"
    report = json.loads(path.read_text())
    if report != build_report(request, request_sha, write_output=False):
        raise ValueError("Source-stage aggregate differs from verified job evidence")
    return report


def run(args: argparse.Namespace) -> int:
    request_path = args.request.resolve()
    request, policy, request_sha = validate_request(request_path, args.repo)
    output = Path(request["output_root"])
    pending: queue.Queue = queue.Queue()
    states = {}
    for job in request["jobs"]:
        complete = verified_result(request, job, request_sha) is not None
        states[job["name"]] = {"status": "completed" if complete else "queued"}
        if not complete:
            pending.put(job)
    mutex, stop = threading.Lock(), threading.Event()

    def update(name: str, **values) -> None:
        with mutex:
            states[name].update(values)
            write(
                output / "runner-status.json",
                {
                    "request_sha256": request_sha,
                    "updated_at": now(),
                    "jobs": states,
                    "stopping": stop.is_set(),
                },
            )

    def worker(gpu: int) -> None:
        entry = gpu_policy.require_allowed(policy, gpu)
        while not stop.is_set() and not pending.empty():
            if not idle_snapshot(policy)[gpu]:
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
                command = [
                    args.python,
                    "-u",
                    str(args.repo / "scripts/evaluate_rad_source_stages.py"),
                    "--request",
                    str(request_path),
                    "--repo",
                    str(args.repo),
                    "--python",
                    args.python,
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
                log = output / "logs" / (job["name"] + ".log")
                log.parent.mkdir(parents=True, exist_ok=True)
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
                        )
                        while process.poll() is None:
                            if stop.wait(args.poll_seconds):
                                stop_child(process)
                                raise RuntimeError("Source-stage runner stopped")
                            gpu_policy.assert_pid_on_uuid(process.pid, entry["uuid"])
                        if process.returncode or verified_result(request, job, request_sha) is None:
                            raise RuntimeError(f"Source-stage child failed; see {log}")
                    update(job["name"], status="completed", finished_at=now())
                except BaseException as error:
                    if process is not None:
                        stop_child(process)
                    update(job["name"], status="failed", error=str(error), finished_at=now())
                    if isinstance(error, gpu_policy.GpuPolicyError):
                        stop.set()
                finally:
                    pending.task_done()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    with exclusive_locks([output / "locks/runner.lock"]) as acquired:
        if not acquired:
            raise RuntimeError("This source-stage request already has a runner")
        with ThreadPoolExecutor(max_workers=len(policy["allowed"])) as executor:
            futures = [executor.submit(worker, gpu) for gpu in gpu_policy.allowed_indices(policy)]
            try:
                for future in as_completed(futures):
                    future.result()
            except BaseException:
                stop.set()
                raise
        if any(state["status"] != "completed" for state in states.values()):
            return 1
        build_report(request, request_sha)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--lock-root", type=Path, default=Path("/data/izadia1/projects/segmentary-runs/.gpu-locks")
    )
    parser.add_argument("--poll-seconds", type=float, default=3)
    parser.add_argument("--job")
    parser.add_argument("--gpu", type=int)
    args = parser.parse_args()
    args.repo = args.repo.resolve()
    if args.poll_seconds <= 0 or (args.job is None) != (args.gpu is None):
        parser.error("Positive polling and paired --job/--gpu arguments are required")
    if args.job is not None:
        evaluate_job(args.request.resolve(), args.job, args.gpu, args.repo, args.python)
        return
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
