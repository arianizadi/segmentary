"""Verify mud selection, arithmetic, resource failures and collection gating."""

import subprocess

import numpy as np
import pytest
from scripts.collect_rtis_statistics import matrix_metrics, mud_counts, score_curve
from scripts.run_rtis_full_campaign import validate_collection

from segmentary.config import TrainConfig
from segmentary.curriculum import _checkpoint_callbacks
from segmentary.utils.resource_tracking import run_recorded


def test_mud_metric_controls_both_retention_and_early_stopping(tmp_path):
    cfg = TrainConfig(selection_metric="val_iou/mud-pumping", early_stopping_patience=5)
    callbacks = _checkpoint_callbacks(tmp_path, cfg)
    assert callbacks[0].monitor == callbacks[-1].monitor == "val_iou/mud-pumping"
    assert callbacks[-1].patience == 5
    assert callbacks[0].mode == callbacks[-1].mode == "max"


def test_confusion_and_score_curve_have_explicit_denominators():
    matrix = np.array([[4, 2], [1, 3]], dtype=np.int64)
    counts = mud_counts(matrix, 1)
    assert counts == {
        "tp": 3,
        "fp": 2,
        "fn": 1,
        "tn": 4,
        "support": 4,
        "predicted_pixels": 5,
        "iou": 0.5,
        "precision": 0.6,
        "recall": 0.75,
    }
    assert matrix_metrics(matrix, ["other", "mud-pumping"])["per_class_iou"]["mud-pumping"] == 0.5
    positive = np.zeros(1001, np.int64)
    negative = positive.copy()
    positive[500] = 3
    positive[100] = 1
    negative[800] = 2
    negative[0] = 4
    threshold = score_curve(positive, negative)[50]
    assert threshold == {
        "threshold": 0.5,
        "tp": 3,
        "fp": 2,
        "fn": 1,
        "precision": 0.6,
        "recall": 0.75,
    }


@pytest.mark.parametrize("exit_code", [0, 3])
def test_failed_subprocess_still_has_durable_full_timing(tmp_path, monkeypatch, exit_code):
    import json
    import os
    import sys

    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "100, 50, 90, 40")
    records = tmp_path / "attempts"
    with (tmp_path / "log.txt").open("w") as log:
        args = ([sys.executable, "-c", f"raise SystemExit({exit_code})"],)
        kwargs = {
            "cwd": tmp_path,
            "env": {**os.environ, "CUDA_VISIBLE_DEVICES": "0"},
            "stdout": log,
            "records": records,
            "phase": "training",
        }
        if exit_code:
            with pytest.raises(subprocess.CalledProcessError):
                run_recorded(*args, **kwargs)
        else:
            run_recorded(*args, **kwargs)
    record = json.loads(next(records.glob("*.json")).read_text())
    assert record["status"] == ("failed" if exit_code else "completed")
    assert record["returncode"] == exit_code
    assert record["wall_clock_s"] > 0


def test_run_recorded_kills_child_on_foreign_gpu_context_and_records_uuid(tmp_path, monkeypatch):
    import json
    import os
    import sys

    from segmentary.gpu_policy import GpuPolicyError
    from segmentary.utils import resource_tracking

    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "100, 50, 90, 40")
    seen = []

    def on_wrong_gpu(pid, uuid):
        seen.append((pid, uuid))
        raise GpuPolicyError(f"Process {pid} has a context on GPU-bad, not {uuid}")

    monkeypatch.setattr(resource_tracking, "assert_pid_on_uuid", on_wrong_gpu)
    records = tmp_path / "attempts"
    with (tmp_path / "log.txt").open("w") as log:
        with pytest.raises(GpuPolicyError, match="GPU-bad"):
            resource_tracking.run_recorded(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                cwd=tmp_path,
                env={**os.environ, "CUDA_VISIBLE_DEVICES": "2"},
                stdout=log,
                records=records,
                phase="training",
                expected_gpu_uuid="GPU-good",
            )
    record = json.loads(next(records.glob("*.json")).read_text())
    assert seen == [(record["pid"], "GPU-good")]
    assert record["gpu_uuid"] == "GPU-good"
    assert record["status"] == "failed"
    assert record["returncode"] not in (None, 0)
    assert "GPU-bad" in record["gpu_policy_violation"]
    assert record["wall_clock_s"] < 30


def test_run_recorded_keeps_child_alive_through_transient_inspection_failures(
    tmp_path, monkeypatch
):
    """A slow nvidia-smi/ps is not a violation: record it and keep polling."""
    import json
    import os
    import sys

    from segmentary.gpu_policy import GpuInspectionError
    from segmentary.utils import resource_tracking

    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "100, 50, 90, 40")
    checks = []

    def flaky(pid, uuid):
        checks.append(pid)
        if len(checks) <= 2:
            raise GpuInspectionError("Could not list GPU compute processes: timeout")

    monkeypatch.setattr(resource_tracking, "assert_pid_on_uuid", flaky)
    records = tmp_path / "attempts"
    with (tmp_path / "log.txt").open("w") as log:
        resource_tracking.run_recorded(
            [sys.executable, "-c", "import time; time.sleep(12)"],
            cwd=tmp_path,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "2"},
            stdout=log,
            records=records,
            phase="training",
            expected_gpu_uuid="GPU-good",
        )
    record = json.loads(next(records.glob("*.json")).read_text())
    assert record["status"] == "completed" and record["returncode"] == 0
    assert "gpu_policy_violation" not in record
    assert len(record["policy_check_errors"]) == 2
    assert len(checks) >= 3


def test_run_recorded_fails_closed_after_sustained_inspection_outage(tmp_path, monkeypatch):
    import json
    import os
    import sys

    from segmentary.gpu_policy import GpuInspectionError, GpuPolicyError
    from segmentary.utils import resource_tracking

    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "100, 50, 90, 40")

    def down(pid, uuid):
        raise GpuInspectionError("Could not list processes: ps missing")

    monkeypatch.setattr(resource_tracking, "assert_pid_on_uuid", down)
    records = tmp_path / "attempts"
    with (tmp_path / "log.txt").open("w") as log:
        with pytest.raises(GpuPolicyError, match="could not be verified for 2 consecutive"):
            resource_tracking.run_recorded(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                cwd=tmp_path,
                env={**os.environ, "CUDA_VISIBLE_DEVICES": "2"},
                stdout=log,
                records=records,
                phase="training",
                expected_gpu_uuid="GPU-good",
                max_unverified_checks=2,
            )
    record = json.loads(next(records.glob("*.json")).read_text())
    assert record["status"] == "failed" and record["returncode"] not in (None, 0)
    assert "ps missing" in record["gpu_policy_violation"]
    assert len(record["policy_check_errors"]) == 2
    assert record["wall_clock_s"] < 30


def test_run_recorded_queries_telemetry_by_uuid_when_known(tmp_path, monkeypatch):
    import os
    import sys

    from segmentary.utils import resource_tracking

    commands = []
    monkeypatch.setattr(
        subprocess, "check_output", lambda cmd, *a, **k: commands.append(cmd) or "1, 2, 3, 4"
    )
    monkeypatch.setattr(resource_tracking, "assert_pid_on_uuid", lambda pid, uuid: None)
    with (tmp_path / "log.txt").open("w") as log:
        resource_tracking.run_recorded(
            [sys.executable, "-c", "pass"],
            cwd=tmp_path,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "2"},
            stdout=log,
            records=tmp_path / "attempts",
            phase="training",
            expected_gpu_uuid="GPU-good",
        )
    assert all("--id=GPU-good" in cmd for cmd in commands)


def test_collect_job_child_env_comes_from_policy(tmp_path, monkeypatch):
    import os
    import sys
    from types import SimpleNamespace

    from scripts import run_rtis_full_campaign as full

    from helpers_gpu_policy import uuid_of, write_campaign
    from segmentary import gpu_policy

    campaign = write_campaign(tmp_path, jobs=["job"], collection_contract="x")
    config = tmp_path / "job.yaml"
    config.write_text("job")
    job = {"name": "job", "config": str(config)}
    monkeypatch.setitem(
        sys.modules,
        "scripts.collect_rtis_statistics",
        SimpleNamespace(validate_dataset=lambda *a: None),
    )
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda layers: None)
    )
    monkeypatch.setattr(full.runtime, "run_job", lambda *a: None)
    full.runtime.write(tmp_path / "state/job.json", {"name": "job", "status": "collecting"})
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(os, "environ", {"CUDA_VISIBLE_DEVICES": "0,1,2,3", "HOME": "/h"})
    captured = []

    def recorded(command, **kwargs):
        captured.append(kwargs)
        raise RuntimeError("stop")

    monkeypatch.setattr(full, "run_recorded", recorded)
    with pytest.raises(RuntimeError, match="stop"):
        full.collect_job(tmp_path, tmp_path, job, 3, campaign)
    expected = gpu_policy.child_env(
        {
            **os.environ,
            "PYTHONPATH": str(tmp_path / "src"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "OMP_NUM_THREADS": "4",
        },
        campaign["gpu_policy"],
        3,
        tmp_path / "campaign.json",
    )
    assert captured[0]["env"] == expected
    assert captured[0]["expected_gpu_uuid"] == uuid_of(3)
    assert full.runtime.read(tmp_path / "state/job.json")["gpu_uuid"] == uuid_of(3)
    with pytest.raises(gpu_policy.GpuPolicyError):
        full.collect_job(tmp_path, tmp_path, job, 1, campaign)
    with pytest.raises(gpu_policy.GpuPolicyError):
        full.run_job(tmp_path, tmp_path, job, 0, campaign)
    assert not (tmp_path / "job-attempts").exists()


def test_profile_watch_only_locks_and_measures_allowed_gpus(tmp_path, monkeypatch):
    import os

    from scripts import profile_rtis_campaign as profile

    from helpers_gpu_policy import patch_live, uuid_of, write_campaign

    campaign = write_campaign(tmp_path, jobs=["job"])
    (tmp_path / "state/job.json").write_text('{"name": "job", "status": "completed"}')
    monkeypatch.setattr(profile.runtime, "verify_frozen", lambda *a: campaign)
    patch_live(monkeypatch, compute_apps=[(1, uuid_of(2)), (2, uuid_of(0))])
    monkeypatch.setattr(os, "environ", {"CUDA_VISIBLE_DEVICES": "0,1,2,3"})
    locked, runs = [], []
    original = profile.runtime.lock

    def lock(path):
        locked.append(path.name)
        return original(path)

    def run(command, **kwargs):
        runs.append(kwargs["env"])
        (tmp_path / "STOP_PERFORMANCE").touch()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(profile.runtime, "lock", lock)
    monkeypatch.setattr(profile.subprocess, "run", run)
    monkeypatch.setattr(profile.time, "sleep", lambda s: None)
    (tmp_path / "service-logs").mkdir()
    profile.watch(tmp_path, tmp_path)
    assert "gpu-0.lock" not in locked and "gpu-1.lock" not in locked
    assert locked == ["performance.lock", "gpu-2.lock", "gpu-3.lock"]
    assert len(runs) == 1
    assert runs[0]["CUDA_VISIBLE_DEVICES"] == "3"
    assert runs[0]["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"


def test_partial_diagnostics_cannot_be_called_complete():
    with pytest.raises(RuntimeError, match="Incomplete"):
        validate_collection({}, {"test_evaluated": False, "smoke_limit": 2}, {}, [])
    with pytest.raises(RuntimeError, match="Missing train"):
        validate_collection(
            {},
            {"test_evaluated": False, "standalone_confusion_exact_match": True, "results": {}},
            {},
            [],
        )


@pytest.mark.parametrize("train_count", [205, 220, 7])
def test_collection_coverage_uses_manifest_counts(train_count):
    from scripts.collect_rtis_statistics import validate_split_coverage

    splits = {"train": list(range(train_count)), "val": list(range(37))}
    results = {
        key: {"images": train_count if key.endswith("train") else 37}
        for key in ("best-auto-train", "best-auto-val", "best-alternate-val", "final-auto-val")
    }
    validate_split_coverage(results, splits)
    results["best-auto-train"]["images"] -= 1
    with pytest.raises(RuntimeError, match=f"expected {train_count} images, got {train_count - 1}"):
        validate_split_coverage(results, splits)


@pytest.mark.parametrize(
    "damage",
    [
        "none",
        "missing",
        "extra",
        "hash",
        "count",
        "membership",
        "class",
        "image_dimensions",
        "mask_dimensions",
    ],
)
def test_preflight_fails_loudly_for_dataset_drift(tmp_path, monkeypatch, damage):
    import hashlib
    import json
    from types import SimpleNamespace

    from PIL import Image
    from scripts import collect_rtis_statistics as collector

    samples = []
    splits = {}
    for split in ("train", "val", "test"):
        for kind in ("images", "masks"):
            (tmp_path / kind / split).mkdir(parents=True)
        image_path = tmp_path / "images" / split / (split + ".png")
        Image.new("RGB", (2, 2)).save(image_path)
        Image.new("L", (2, 2)).save(tmp_path / "masks" / split / (split + ".png"))
        samples.append(
            {
                "key": split,
                "split": split,
                "image_extension": ".png",
                "width": 2,
                "height": 2,
                "image_sha256": collector.runtime.digest(image_path),
                "mask_sha256": hashlib.sha256(bytes(4)).hexdigest(),
            }
        )
        splits[split] = [split]
    if damage == "membership":
        splits["train"] = ["wrong-key"]
    if damage == "class":
        Image.new("L", (2, 2), 3).save(tmp_path / "masks/train/train.png")
        samples[0]["mask_sha256"] = hashlib.sha256(bytes([3] * 4)).hexdigest()
    if damage == "image_dimensions":
        Image.new("RGB", (3, 2)).save(tmp_path / "images/train/train.png")
        samples[0]["image_sha256"] = collector.runtime.digest(tmp_path / "images/train/train.png")
    if damage == "mask_dimensions":
        Image.new("L", (3, 2)).save(tmp_path / "masks/train/train.png")
    (tmp_path / "audit").mkdir()
    (tmp_path / "audit/samples.json").write_text(json.dumps(samples))
    (tmp_path / "splits.json").write_text(json.dumps(splits))
    config = tmp_path / "config.yaml"
    config.write_text("test")
    job = {"config": str(config), "config_sha256": collector.runtime.digest(config)}
    campaign = {
        "split_sha256": collector.runtime.digest(tmp_path / "splits.json"),
        "dataset_audit_sha256": collector.runtime.digest(tmp_path / "audit/samples.json"),
        "dataset_sizes": {"train": 1, "val": 1, "test": 1},
    }
    cfg = SimpleNamespace(
        stages=[SimpleNamespace(data=[SimpleNamespace(root=tmp_path)])],
        taxonomy_root="unused",
        space="test",
    )
    monkeypatch.setattr(collector, "load_space", lambda *a: SimpleNamespace(num_classes=2))
    if damage == "missing":
        (tmp_path / "images/train/train.png").unlink()
    elif damage == "extra":
        (tmp_path / "images/train/extra.png").write_bytes(b"extra")
    elif damage == "hash":
        Image.new("RGB", (2, 2), "red").save(tmp_path / "images/train/train.png")
    elif damage == "count":
        campaign["dataset_sizes"]["train"] = 220
    if damage == "none":
        collector.validate_dataset(tmp_path, job, cfg, campaign)
    else:
        with pytest.raises(RuntimeError):
            collector.validate_dataset(tmp_path, job, cfg, campaign)


def test_collection_main_preserves_manifest_across_all_passes(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from scripts import collect_rtis_statistics as collector

    anchor = {"path": str(tmp_path / "best.ckpt"), "sha256": "expected"}
    state = {
        "checkpoints": {"best": anchor, "final": anchor},
        "evaluation": {"metrics": {"confusion": [[1]]}},
    }
    cfg = SimpleNamespace(model=None, train=SimpleNamespace(seed=0), taxonomy_root=None, space=None)
    monkeypatch.setattr(sys, "argv", ["collector", "--campaign", str(tmp_path), "--job", "job"])
    monkeypatch.setattr(
        collector.runtime,
        "read",
        lambda path: (
            {"jobs": [{"name": "job", "config": "unused"}]}
            if str(path).endswith("plan.json")
            else state
        ),
    )
    monkeypatch.setattr(collector.runtime, "digest", lambda path: "expected")
    writes = []
    monkeypatch.setattr(collector.runtime, "write", lambda path, payload: writes.append(payload))
    monkeypatch.setattr(collector, "load_experiment", lambda *a: cfg)
    monkeypatch.setattr(
        collector, "load_space", lambda *a: SimpleNamespace(names=["class"], num_classes=1)
    )
    monkeypatch.setattr(
        collector,
        "validate_dataset",
        lambda *a: ({"train": list(range(205)), "val": list(range(37))}, []),
    )

    class Model:
        def cuda(self):
            return self

        def eval(self):
            return self

    monkeypatch.setattr(collector, "build_model", lambda *a: Model())
    monkeypatch.setattr(collector, "ema_evaluation_safe", lambda *a: True)
    monkeypatch.setattr(collector, "load_configured_checkpoint", lambda model, *a: model)
    monkeypatch.setattr(collector, "seed_everything", lambda *a, **k: None)
    monkeypatch.setattr(
        collector,
        "collect",
        lambda model, cfg, samples, split, *a: {
            "images": 205 if split == "train" else 37,
            "metrics": {"confusion": [[1]]},
        },
    )
    collector.main()
    assert writes[-1]["standalone_confusion_exact_match"] is True
    assert len(writes[-1]["results"]) == 4
