"""Capture class-positive-image source metrics from the sixteen frozen endpoints.

The CPU parent reuses the campaign's idle-GPU policy, shared locks and child UUID
monitoring. Fresh deterministic evaluations write a separate evidence tree. Each
capture must reproduce its archived native-validation confusion matrix exactly.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import queue
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
from scripts import evaluate_rad_source_stages as source_stages
from scripts.rad_paper_metrics import score_images
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

METRIC = "class_positive_image_miou"
REPORT_NAME = "source-positive-metrics.json"


def read_artifact(pointer: dict) -> dict:
    path = Path(pointer["path"])
    if digest(path) != pointer["sha256"]:
        raise ValueError(f"Source-positive artifact changed: {path}")
    return json.loads(path.read_text())


def context(request_path: Path, repo: Path, *, verify_archive: bool) -> tuple[dict, dict, dict]:
    request, policy, _ = source_stages.validate_request(request_path, repo, verify_code=False)
    archive_path = Path(request["output_root"]) / "source-stage-reports.json"
    archive = (
        source_stages.load_verified_report(request_path, repo)
        if verify_archive
        else json.loads(archive_path.read_text())
    )
    pointers = {
        "source_stage_request": {"path": str(request_path), "sha256": digest(request_path)},
        "source_stage_report": {"path": str(archive_path), "sha256": digest(archive_path)},
    }
    return request, policy, {"archive": archive, **pointers}


def archived_stage(evidence: dict, job: dict) -> dict:
    matches = [
        stage
        for model in evidence["archive"]["models"]
        if model["model"] == job["model"]
        for stage in model["stages"]
        if stage["stage"] == job["stage"]
    ]
    if len(matches) != 1:
        raise ValueError("The archived source report must contain exactly one matching stage")
    stage = matches[0]
    if (
        stage["class_names"] != job["class_names"]
        or stage["checkpoint"]["sha256"] != job["checkpoint_sha256"]
        or stage["config"]["sha256"] != job["config_sha256"]
    ):
        raise ValueError("Archived source identity differs from its frozen request")
    return stage


def evaluation_command(job: dict, directory: Path, python: str) -> list[str]:
    source_data = yaml.safe_load(Path(job["config"]).read_text())["stages"][-1]["data"][0]
    override = job["evaluation_data"]
    command = [
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
        str(directory / "evaluation.json"),
        "--per-image-confusions-out",
        str(directory / "per-image-confusion.json.gz"),
        "--dataset",
        override["dataset"],
        "--root",
        override["root"],
        "--loader-options",
        json.dumps(source_data.get("loader_options") or {}),
    ]
    for flag, value in (
        ("--loader", source_data.get("loader")),
        ("--mapping", source_data.get("mapping")),
        ("--split-file", override.get("split_file")),
        ("--variant", source_data.get("variant")),
    ):
        if value is not None:
            command.extend([flag, str(value)])
    return command


def checked_capture(
    directory: Path, job: dict, stage: dict, collector_code_sha: str
) -> tuple[dict, dict]:
    evaluation_path = directory / "evaluation.json"
    evaluation = json.loads(evaluation_path.read_text())
    original = read_artifact(stage["evaluation_receipt"])
    if (
        evaluation.get("git_sha") != collector_code_sha
        or evaluation.get("git_dirty") is not False
        or evaluation.get("seed") != 0
        or evaluation.get("stage") != f"eval:{job['dataset']}:val"
        or evaluation.get("dataset_sizes") != {"eval": job["expected_images"]}
        or evaluation.get("config") != original["config"]
    ):
        raise ValueError(
            "Fresh source capture differs from its archived native evaluation contract"
        )
    metadata = evaluation["config"]["evaluation"]
    weights = metadata["weights"]
    if metadata.get("deterministic") is not True or weights not in ("raw", "ema"):
        raise ValueError("Source capture requires the archived deterministic selected weight bank")
    pointer = evaluation["metrics"].get("per_image_confusions", {})
    expected_path = directory / "per-image-confusion.json.gz"
    if Path(pointer.get("path", "")).resolve() != expected_path.resolve():
        raise ValueError("Source capture must bind its own per-image confusion artifact")
    if digest(expected_path) != pointer.get("sha256"):
        raise ValueError("Source per-image confusion artifact changed")
    raw = json.loads(gzip.decompress(expected_path.read_bytes()))
    if not isinstance(raw, dict) or len(raw) != job["expected_images"]:
        raise ValueError("Source capture must cover every native validation image")
    classes = len(job["class_names"])
    matrices = {}
    for key, values in raw.items():
        matrix = np.asarray(values)
        if (
            not isinstance(key, str)
            or not key
            or matrix.shape != (classes, classes)
            or not np.issubdtype(matrix.dtype, np.integer)
            or bool((matrix < 0).any())
        ):
            raise ValueError("Source capture requires keyed nonnegative integer confusion matrices")
        matrices[key] = matrix.astype(np.int64)
    total = sum(matrices.values(), np.zeros((classes, classes), dtype=np.int64))
    if not np.array_equal(total, original["metrics"]["confusion"]) or not np.array_equal(
        total, evaluation["metrics"].get("confusion")
    ):
        raise ValueError(
            "Source per-image confusions must reproduce the archived aggregate exactly"
        )
    scores = score_images(matrices, job["class_names"])["class_positive_images"]
    supported = {name for name, count in original["metrics"]["support"].items() if count > 0}
    positive = {name for name, values in scores["per_class"].items() if values["positive_images"]}
    if scores["macro_scored_classes"] != 19 or positive != supported:
        raise ValueError("Each native source capture must score all nineteen supported classes")
    return evaluation, {
        "model": job["model"],
        "stage": job["stage"],
        "class_names": job["class_names"],
        "expected_images": job["expected_images"],
        "config_sha256": job["config_sha256"],
        "checkpoint_sha256": job["checkpoint_sha256"],
        "weights": weights,
        "evaluation_record": {"path": str(evaluation_path), "sha256": digest(evaluation_path)},
        "per_image_confusions": {"path": str(expected_path), "sha256": digest(expected_path)},
        "class_positive_images": scores,
        "aggregate_confusion_matches_archived": True,
    }


def completed_job(output: Path, job: dict, evidence: dict, collector_code_sha: str) -> dict | None:
    directory = output / job["name"]
    path = directory / "result.json"
    if not path.exists():
        return None
    recorded = json.loads(path.read_text())
    if (
        recorded.get("status") != "completed"
        or recorded.get("collector_code_sha") != collector_code_sha
        or recorded.get("source_stage_request") != evidence["source_stage_request"]
        or recorded.get("source_stage_report") != evidence["source_stage_report"]
    ):
        raise ValueError("Existing source-positive result has a different provenance binding")
    _evaluation, payload = checked_capture(
        directory, job, archived_stage(evidence, job), collector_code_sha
    )
    if recorded.get("job") != payload:
        raise ValueError("Existing source-positive result differs from its captured evidence")
    return payload


def collect_job(args: argparse.Namespace) -> dict:
    source_stages.verify_checkout(args.repo, args.expected_code_sha)
    request, policy, evidence = context(args.request, args.repo, verify_archive=False)
    if evidence["source_stage_report"]["sha256"] != args.source_stage_report_sha256:
        raise ValueError("Original source-stage report changed before source capture")
    job = next(job for job in request["jobs"] if job["name"] == args.job)
    gpu_policy.assert_env(policy, args.gpu)
    stage = archived_stage(evidence, job)
    existing = completed_job(args.output_root, job, evidence, args.expected_code_sha)
    if existing is not None:
        return existing
    source_stages.verify_source(job)
    directory = args.output_root / job["name"]
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(evaluation_command(job, directory, args.python), cwd=args.repo, check=True)
    _evaluation, payload = checked_capture(directory, job, stage, args.expected_code_sha)
    source_stages.verify_source(job)
    write(
        directory / "result.json",
        {
            "schema_version": 1,
            "status": "completed",
            "collector_code_sha": args.expected_code_sha,
            "source_stage_request": evidence["source_stage_request"],
            "source_stage_report": evidence["source_stage_report"],
            "job": payload,
            "completed_at": now(),
        },
    )
    return payload


def build_report(output: Path, request: dict, evidence: dict, collector_code_sha: str) -> dict:
    jobs = [completed_job(output, job, evidence, collector_code_sha) for job in request["jobs"]]
    if any(job is None for job in jobs):
        raise ValueError("Source-positive report requires all sixteen completed captures")
    report = {
        "schema_version": 1,
        "metric": METRIC,
        "source_stage_request": evidence["source_stage_request"],
        "source_stage_report": evidence["source_stage_report"],
        "collector_code_sha": collector_code_sha,
        "jobs": jobs,
    }
    path = output / REPORT_NAME
    if path.exists():
        if json.loads(path.read_text()) != report:
            raise ValueError("Existing source-positive aggregate differs from captured evidence")
    else:
        write(path, report)
    return report


def run(args: argparse.Namespace) -> int:
    source_stages.verify_checkout(args.repo, args.expected_code_sha)
    request, policy, evidence = context(args.request, args.repo, verify_archive=True)
    pending: queue.Queue = queue.Queue()
    states = {}
    for job in request["jobs"]:
        complete = (
            completed_job(args.output_root, job, evidence, args.expected_code_sha) is not None
        )
        states[job["name"]] = {"status": "completed" if complete else "queued"}
        if not complete:
            pending.put(job)
    mutex, stop = threading.Lock(), threading.Event()

    def update(name: str, **values) -> None:
        with mutex:
            states[name].update(values)
            write(
                args.output_root / "runner-status.json",
                {
                    "updated_at": now(),
                    "collector_code_sha": args.expected_code_sha,
                    "source_stage_report": evidence["source_stage_report"],
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
                    str(args.repo / "scripts/collect_rad_source_positive_metrics.py"),
                    "--request",
                    str(args.request),
                    "--repo",
                    str(args.repo),
                    "--python",
                    args.python,
                    "--output-root",
                    str(args.output_root),
                    "--expected-code-sha",
                    args.expected_code_sha,
                    "--source-stage-report-sha256",
                    evidence["source_stage_report"]["sha256"],
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
                log = args.output_root / "logs" / (job["name"] + ".log")
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
                            pid=process.pid,
                            started_at=now(),
                        )
                        while process.poll() is None:
                            if stop.wait(args.poll_seconds):
                                stop_child(process)
                                raise RuntimeError("Source-positive collector stopped")
                            gpu_policy.assert_pid_on_uuid(process.pid, entry["uuid"])
                        if (
                            process.returncode
                            or completed_job(
                                args.output_root, job, evidence, args.expected_code_sha
                            )
                            is None
                        ):
                            raise RuntimeError(f"Source-positive child failed; see {log}")
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
    with exclusive_locks([args.output_root / "locks/runner.lock"]) as acquired:
        if not acquired:
            raise RuntimeError("This source-positive output already has a collector")
        with ThreadPoolExecutor(max_workers=len(policy["allowed"])) as executor:
            futures = [executor.submit(worker, gpu) for gpu in gpu_policy.allowed_indices(policy)]
            try:
                for future in futures:
                    future.result()
            except BaseException:
                stop.set()
                raise
        if any(state["status"] != "completed" for state in states.values()):
            return 1
        build_report(args.output_root, request, evidence, args.expected_code_sha)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--expected-code-sha", required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--lock-root", type=Path, default=Path("/data/izadia1/projects/segmentary-runs/.gpu-locks")
    )
    parser.add_argument("--poll-seconds", type=float, default=3)
    parser.add_argument("--source-stage-report-sha256")
    parser.add_argument("--job")
    parser.add_argument("--gpu", type=int)
    args = parser.parse_args()
    args.repo, args.request = args.repo.resolve(), args.request.resolve()
    original_root = Path(json.loads(args.request.read_text())["output_root"]).resolve()
    args.output_root = (
        args.output_root or original_root.parent / "source-positive-images"
    ).resolve()
    if args.output_root == original_root or original_root in args.output_root.parents:
        parser.error("Source-positive captures require a separate output tree")
    if args.poll_seconds <= 0 or (args.job is None) != (args.gpu is None):
        parser.error("Positive polling and paired --job/--gpu arguments are required")
    if args.job is not None:
        if args.source_stage_report_sha256 is None:
            parser.error("A child capture requires the parent-verified source report SHA-256")
        collect_job(args)
        return
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
