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


@pytest.mark.parametrize("damage", ["none", "missing", "extra", "hash", "count", "membership"])
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
