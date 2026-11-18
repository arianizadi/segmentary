"""Frozen source captures retain both metric definitions and resume by hash."""

from __future__ import annotations

import argparse
import copy
import gzip
import json
from pathlib import Path

import numpy as np
import pytest
from scripts import collect_rad_source_positive_metrics as collector
from scripts import evaluate_rad_source_stages as stages

import test_evaluate_rad_source_stages as source_tests

source_prepared = source_tests.prepared

CODE_SHA = "c" * 40


def image_matrices(job):
    classes = len(job["class_names"])
    values = np.zeros((classes, classes), dtype=np.int64)
    values[:19, :19] = np.eye(19, dtype=np.int64)
    result = {f"image-{index}": values.tolist() for index in range(job["expected_images"])}
    absent = values.copy()
    absent[0, 0] = 0
    absent[1, 1] = 0
    absent[1, 0] = 2
    result["image-0"] = absent.tolist()
    return result


@pytest.fixture
def prepared(source_prepared, monkeypatch):
    request_path, request, policy = source_prepared
    for job in request["jobs"]:
        source_tests.complete(request, job, stages.digest(request_path))
        directory = Path(request["output_root"]) / job["name"]
        evaluation = json.loads((directory / "evaluation.json").read_text())
        matrices = image_matrices(job)
        total = np.stack(list(matrices.values())).sum(0)
        evaluation["metrics"]["confusion"] = total.tolist()
        evaluation["metrics"]["support"] = {
            name: int(total[index].sum()) for index, name in enumerate(job["class_names"])
        }
        stages.write(directory / "evaluation.json", evaluation)
        performance = json.loads((directory / "performance.json").read_text())
        performance["source"]["result_sha256"] = stages.digest(directory / "evaluation.json")
        stages.write(directory / "performance.json", performance)
        result = json.loads((directory / "result.json").read_text())
        for entry in result["artifacts"].values():
            entry["sha256"] = stages.digest(Path(entry["path"]))
        stages.write(directory / "result.json", result)
    stages.build_report(request, stages.digest(request_path))
    monkeypatch.setattr(collector.gpu_policy, "assert_env", lambda *args: {})
    monkeypatch.setattr(collector.source_stages, "verify_checkout", lambda *args: None)
    args = argparse.Namespace(
        request=request_path,
        repo=request_path.parent,
        python="python",
        expected_code_sha=CODE_SHA,
        output_root=request_path.parent / "source-positive-images",
        lock_root=request_path.parent / "gpu-locks",
        poll_seconds=0.001,
        source_stage_report_sha256=stages.digest(
            Path(request["output_root"]) / "source-stage-reports.json"
        ),
        job=None,
        gpu=None,
    )
    return args, request, policy


def capture(command, request, *, change=None):
    checkpoint = command[command.index("--ckpt") + 1]
    job = next(job for job in request["jobs"] if job["checkpoint"] == checkpoint)
    old = Path(request["output_root"]) / job["name"] / "evaluation.json"
    evaluation = copy.deepcopy(json.loads(old.read_text()))
    evaluation["git_sha"] = CODE_SHA
    matrices = image_matrices(job)
    if change == "confusion":
        matrices["image-1"][0][0] += 1
    if change == "count":
        matrices.pop("image-1")
    path = Path(command[command.index("--per-image-confusions-out") + 1])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(matrices).encode(), mtime=0))
    evaluation["metrics"]["per_image_confusions"] = {
        "path": str(path),
        "sha256": stages.digest(path),
    }
    if change == "weights":
        evaluation["config"]["evaluation"]["weights"] = "ema"
    if change == "code":
        evaluation["git_sha"] = "d" * 40
    stages.write(Path(command[command.index("--out") + 1]), evaluation)


@pytest.mark.parametrize("index", [0, 1])
def test_capture_uses_native_frozen_contract_and_resumes_without_inference(
    prepared, monkeypatch, index
):
    args, request, _ = prepared
    job = request["jobs"][index]
    args.job, args.gpu = job["name"], 0
    original = Path(request["output_root"]) / job["name"] / "evaluation.json"
    original_bytes = original.read_bytes()
    commands = []

    def execute(command, **_kwargs):
        commands.append(command)
        capture(command, request)

    monkeypatch.setattr(collector.subprocess, "run", execute)
    result = collector.collect_job(args)
    assert len(commands) == 1
    command = commands[0]
    assert command[1:3] == ["-m", "segmentary.eval"]
    assert "--auto-weights" in command and "--deterministic" in command
    assert "--limit" not in command and "--tta" not in command
    if index == 1:
        assert command[command.index("--split-file") + 1] == job["evaluation_data"]["split_file"]
    assert original.read_bytes() == original_bytes
    assert result["aggregate_confusion_matches_archived"] is True
    assert result["weights"] == "raw"
    positive = result["class_positive_images"]
    assert positive["macro_scored_classes"] == 19
    assert (
        positive["per_class"][job["class_names"][0]]["positive_images"]
        == job["expected_images"] - 1
    )
    assert positive["per_class"][job["class_names"][0]]["mean_image_iou"] == 1.0
    assert positive["miou"] == pytest.approx(1 - 1 / (19 * job["expected_images"]))
    assert collector.collect_job(args) == result
    assert len(commands) == 1
    Path(result["per_image_confusions"]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        collector.collect_job(args)


@pytest.mark.parametrize("change", ["confusion", "count", "weights", "code"])
def test_capture_rejects_changed_counts_weight_bank_or_code(prepared, monkeypatch, change):
    args, request, _ = prepared
    args.job, args.gpu = request["jobs"][0]["name"], 0
    monkeypatch.setattr(
        collector.subprocess,
        "run",
        lambda command, **kwargs: capture(command, request, change=change),
    )
    with pytest.raises(ValueError):
        collector.collect_job(args)
    assert not (args.output_root / args.job / "result.json").exists()


def test_complete_parent_builds_all_sixteen_jobs_without_gpu_inspection(prepared, monkeypatch):
    args, request, _ = prepared
    monkeypatch.setattr(
        collector.subprocess, "run", lambda command, **kwargs: capture(command, request)
    )
    for job in request["jobs"]:
        args.job, args.gpu = job["name"], 0
        collector.collect_job(args)
    args.job = args.gpu = None
    monkeypatch.setattr(
        collector, "idle_snapshot", lambda *_: pytest.fail("complete captures must resume on CPU")
    )
    assert collector.run(args) == 0
    report = json.loads((args.output_root / collector.REPORT_NAME).read_text())
    assert report["metric"] == "class_positive_image_miou"
    assert report["collector_code_sha"] == CODE_SHA
    assert len(report["jobs"]) == 16
    assert {job["expected_images"] for job in report["jobs"]} == {500, 850}
    assert all(job["class_positive_images"]["macro_scored_classes"] == 19 for job in report["jobs"])
    before = (args.output_root / collector.REPORT_NAME).read_bytes()
    assert collector.run(args) == 0
    assert (args.output_root / collector.REPORT_NAME).read_bytes() == before


def test_source_hash_change_is_refused_before_capture(prepared, monkeypatch):
    args, request, _ = prepared
    args.job, args.gpu = request["jobs"][0]["name"], 0
    Path(request["jobs"][0]["checkpoint"]).write_bytes(b"changed")
    monkeypatch.setattr(
        collector.subprocess, "run", lambda *args, **kwargs: pytest.fail("frozen endpoint changed")
    )
    with pytest.raises(ValueError, match="Frozen source bytes changed"):
        collector.collect_job(args)


def test_scheduler_pins_children_and_retains_shared_locks_through_capture(prepared, monkeypatch):
    args, request, policy = prepared
    monkeypatch.setattr(collector, "idle_snapshot", lambda _: dict.fromkeys(range(10), True))
    monkeypatch.setattr(
        collector.subprocess, "run", lambda command, **kwargs: capture(command, request)
    )

    class Child:
        returncode = 0
        pid = 1234

        def __init__(self, command, **kwargs):
            gpu = int(command[command.index("--gpu") + 1])
            entry = collector.gpu_policy.require_allowed(policy, gpu)
            with collector.exclusive_locks(
                collector.shared_lock_paths(args.lock_root, gpu, entry["uuid"])
            ) as acquired:
                assert not acquired
            assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == str(gpu)
            assert kwargs["start_new_session"] is True
            assert (
                command[command.index("--source-stage-report-sha256") + 1]
                == args.source_stage_report_sha256
            )
            child_args = copy.copy(args)
            child_args.job = command[command.index("--job") + 1]
            child_args.gpu = gpu
            collector.collect_job(child_args)

        def poll(self):
            return 0

    monkeypatch.setattr(collector.subprocess, "Popen", Child)
    assert collector.run(args) == 0
    report = json.loads((args.output_root / collector.REPORT_NAME).read_text())
    assert len(report["jobs"]) == 16
