"""Source-stage evaluation uses mocked GPU children and byte-bound native receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
from pathlib import Path

import pytest
import yaml
from scripts import evaluate_rad_source_stages as stages

from helpers_gpu_policy import make_policy


def bind_request(path, request):
    stages.write(path, request)
    campaign_path = Path(request["campaign_json"])
    campaign = json.loads(campaign_path.read_text())
    protocol = {
        "source_stage_reports": {"spec": str(path.resolve()), "spec_sha256": stages.digest(path)}
    }
    campaign["research_protocol"] = protocol
    campaign["research_protocol_sha256"] = hashlib.sha256(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    stages.write(campaign_path, campaign)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    policy = make_policy(list(range(10)))
    campaign = tmp_path / "campaign.json"
    stages.write(
        campaign,
        {
            "code_sha": "a" * 40,
            "gpu_policy": policy,
            "gpu_policy_sha256": stages.gpu_policy.policy_sha256(policy),
        },
    )
    jobs = []
    models = [f"model_{index}" for index in range(8)]
    for model in models:
        for stage, (dataset, count) in stages.STAGES.items():
            directory = tmp_path / "original" / model / stage
            directory.mkdir(parents=True)
            config, checkpoint, receipt = (
                directory / filename for filename in ("config.yaml", "last.ckpt", "results.json")
            )
            taxonomy = "city19" if stage == "cityscapes" else "rail21"
            native_root = tmp_path / "native" / dataset
            native_root.mkdir(parents=True, exist_ok=True)
            split_file = (
                native_root / "surviving-split.json" if stage == "cityscapes_to_railsem19" else None
            )
            if split_file is not None:
                stages.write(split_file, {"val": ["native-validation"]})
            config.write_text(
                yaml.safe_dump(
                    {
                        "space": taxonomy,
                        "train": {"seed": 0},
                        "stages": [
                            {
                                "data": [
                                    {
                                        "name": dataset,
                                        "root": str(native_root),
                                        "limit": None,
                                        "loader": None,
                                        "split_file": "/retired/source/rail-split.json"
                                        if split_file
                                        else None,
                                    }
                                ]
                            }
                        ],
                    }
                )
            )
            checkpoint.write_bytes((model + stage).encode())
            training = {"stage": stage, "seed": 0, "wall_clock_s": 123, "metrics": {"miou": 0.5}}
            stages.write(receipt, training)
            jobs.append(
                {
                    "name": f"{model}--{stage}--seed-0",
                    "model": model,
                    "stage": stage,
                    "seed": 0,
                    "dataset": dataset,
                    "expected_images": count,
                    "taxonomy": taxonomy,
                    "class_names": [
                        f"class-{index}" for index in range(19 if stage == "cityscapes" else 21)
                    ],
                    "config": str(config),
                    "config_sha256": stages.digest(config),
                    "checkpoint": str(checkpoint),
                    "checkpoint_sha256": stages.digest(checkpoint),
                    "checkpoint_global_step": 40000 if stage == "cityscapes" else 20000,
                    "training_receipt": {
                        "path": str(receipt),
                        "sha256": stages.digest(receipt),
                        "record": training,
                    },
                    "public_pretraining": {"public_checkpoint": model + "-public"},
                }
            )
            jobs[-1]["evaluation_data"] = {
                "dataset": dataset,
                "root": str(native_root),
                "split_file": str(split_file) if split_file else None,
                "split_file_sha256": stages.digest(split_file) if split_file else None,
            }
    request = {
        "schema_version": 1,
        "source_stage_evaluation_authorized": True,
        "campaign_json": str(campaign),
        "output_root": str(tmp_path / "source-evaluation"),
        "code_sha": "a" * 40,
        "models": models,
        "jobs": jobs,
    }
    path = tmp_path / "request.json"
    bind_request(path, request)
    monkeypatch.setattr(stages, "verify_checkout", lambda *args: None)
    monkeypatch.setattr(stages.gpu_policy, "assert_env", lambda *args: {})
    return path, request, policy


def receipts(request, job):
    metrics = {
        "miou": 0.5,
        "per_class_iou": dict.fromkeys(job["class_names"], 0.5),
        "support": dict.fromkeys(job["class_names"], 5),
    }
    if job["stage"] == "cityscapes_to_railsem19":
        metrics["per_class_iou"][job["class_names"][-1]] = None
        metrics["support"][job["class_names"][-1]] = 0
    evaluation = {
        "git_sha": request["code_sha"],
        "git_dirty": False,
        "seed": 0,
        "stage": f"eval:{job['dataset']}:val",
        "dataset_sizes": {"eval": job["expected_images"]},
        "metrics": metrics,
        "config": {
            "evaluation": {
                "split": "val",
                "deterministic": True,
                "weights": "raw",
                "tta": {"enabled": False},
                "data": {
                    "name": job["dataset"],
                    "root": job["evaluation_data"]["root"],
                    "split_file": job["evaluation_data"].get("split_file"),
                    "limit": None,
                },
            }
        },
    }
    directory = Path(request["output_root"]) / job["name"]
    stages.write(directory / "evaluation.json", evaluation)
    performance = {
        "status": "complete",
        "measurements": {"latency": {"fps": 100.0}, "peak_reserved_bytes": 1024},
        "source": {
            "checkpoint_sha256": job["checkpoint_sha256"],
            "config_sha256": job["config_sha256"],
            "result_sha256": stages.digest(directory / "evaluation.json"),
            "weights": "raw",
        },
        "contract": {
            "precision": "bf16_autocast",
            "input_shape_nchw": [1, 3, 1024, 1024],
            "warmup_iterations": 20,
            "measured_iterations": 100,
        },
    }
    stages.write(directory / "performance.json", performance)
    return evaluation, performance


def complete(request, job, request_sha):
    receipts(request, job)
    directory = Path(request["output_root"]) / job["name"]
    result = {
        "status": "completed",
        "request_sha256": request_sha,
        "checkpoint_sha256": job["checkpoint_sha256"],
        "config_sha256": job["config_sha256"],
        "finished_at": "2026-11-17T00:00:00+00:00",
        "artifacts": {
            key: {"path": str(directory / filename), "sha256": stages.digest(directory / filename)}
            for key, filename in (
                ("evaluation", "evaluation.json"),
                ("performance", "performance.json"),
            )
        },
    }
    stages.write(directory / "result.json", result)


@pytest.mark.parametrize("index", [0, 1])
def test_child_runs_full_native_auto_evaluation_then_matching_profile_and_resumes(
    prepared, monkeypatch, index
):
    path, request, _ = prepared
    job = request["jobs"][index]
    commands = []

    def execute(command, **kwargs):
        commands.append(command)
        receipts(request, job)

    monkeypatch.setattr(stages.subprocess, "run", execute)
    result = stages.evaluate_job(path, job["name"], 0, path.parent, "python")
    assert result["status"] == "completed" and len(commands) == 2
    assert commands[0][2] == "segmentary.eval"
    assert "--auto-weights" in commands[0] and "--deterministic" in commands[0]
    assert "--limit" not in commands[0] and "--tta" not in commands[0]
    if index == 1:
        assert (
            commands[0][commands[0].index("--split-file") + 1]
            == job["evaluation_data"]["split_file"]
        )
        assert "/retired/source/rail-split.json" not in commands[0]
    assert commands[1][2] == "segmentary.performance"
    assert "--auto-weights" in commands[1] and "--deterministic" not in commands[1]
    stages.evaluate_job(path, job["name"], 0, path.parent, "python")
    assert len(commands) == 2
    Path(result["artifacts"]["evaluation"]["path"]).write_text("changed")
    with pytest.raises(ValueError, match="evidence changed"):
        stages.evaluate_job(path, job["name"], 0, path.parent, "python")


@pytest.mark.parametrize("changed_file", ["checkpoint", "split_file"])
def test_changed_source_refused_before_inference(prepared, monkeypatch, changed_file):
    path, request, _ = prepared
    job = request["jobs"][1]
    filename = (
        job["checkpoint"] if changed_file == "checkpoint" else job["evaluation_data"]["split_file"]
    )
    Path(filename).write_bytes(b"changed")
    monkeypatch.setattr(
        stages.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("source corruption must fail before GPU child"),
    )
    with pytest.raises(
        ValueError,
        match=r"Frozen source bytes changed|Pinned source validation split bytes changed",
    ):
        stages.evaluate_job(path, job["name"], 0, path.parent, "python")


def test_aggregate_is_idempotent_and_retains_native_absent_classes(prepared):
    path, request, _ = prepared
    sha = stages.digest(path)
    for job in request["jobs"]:
        complete(request, job, sha)
    stages.build_report(request, sha)
    report_path = Path(request["output_root"]) / "source-stage-reports.json"
    before = report_path.read_bytes()
    report = stages.load_verified_report(path, path.parent)
    stages.build_report(request, sha)
    assert report_path.read_bytes() == before
    assert len(report["models"]) == 8
    assert all(len(model["stages"]) == 2 for model in report["models"])
    assert (
        report["models"][0]["stages"][1]["metrics"]["metrics"]["per_class_iou"]["class-20"] is None
    )
    assert (
        report["models"][0]["stages"][0]["training"]
        == request["jobs"][0]["training_receipt"]["record"]
    )


def test_report_verification_allows_current_report_code_to_differ(prepared, monkeypatch):
    path, request, _ = prepared
    for job in request["jobs"]:
        complete(request, job, stages.digest(path))
    stages.build_report(request, stages.digest(path))

    def changed_checkout(*args):
        raise ValueError("report checkout has a new HEAD")

    monkeypatch.setattr(stages, "verify_checkout", changed_checkout)
    with pytest.raises(ValueError, match="new HEAD"):
        stages.validate_request(path, path.parent)
    assert stages.load_verified_report(path, path.parent)["code_sha"] == request["code_sha"]


@pytest.mark.parametrize("change", ["partial", "duplicate", "wrong-count", "wrong-stage"])
def test_source_request_exact_full_native_pairs(prepared, change):
    path, request, _ = prepared
    if change == "partial":
        request["jobs"].pop()
    elif change == "duplicate":
        request["jobs"][1] = request["jobs"][0]
    elif change == "wrong-count":
        request["jobs"][0]["expected_images"] = 5
    else:
        request["jobs"][0]["stage"] = "rtis"
    bind_request(path, request)
    with pytest.raises(ValueError):
        stages.validate_request(path, path.parent)


def test_scheduler_holds_shared_device_lock_through_the_whole_child(
    prepared, monkeypatch, tmp_path
):
    path, request, policy = prepared
    monkeypatch.setattr(stages, "idle_snapshot", lambda _: dict.fromkeys(range(10), True))
    mutex = threading.Lock()
    active = set()

    class Child:
        returncode = 0
        pid = 1234

        def __init__(self, command, **kwargs):
            gpu = int(command[command.index("--gpu") + 1])
            name = command[command.index("--job") + 1]
            entry = stages.gpu_policy.require_allowed(policy, gpu)
            with stages.exclusive_locks(
                stages.shared_lock_paths(tmp_path / "locks", gpu, entry["uuid"])
            ) as acquired:
                assert not acquired
            with mutex:
                assert gpu not in active
                active.add(gpu)
            assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == str(gpu)
            job = next(job for job in request["jobs"] if job["name"] == name)
            complete(request, job, stages.digest(path))
            with mutex:
                active.remove(gpu)

        def poll(self):
            return 0

    monkeypatch.setattr(stages.subprocess, "Popen", Child)
    args = argparse.Namespace(
        request=path,
        repo=path.parent,
        python="python",
        lock_root=tmp_path / "locks",
        poll_seconds=0.001,
    )
    assert stages.run(args) == 0
    assert len(stages.load_verified_report(path, path.parent)["models"]) == 8
