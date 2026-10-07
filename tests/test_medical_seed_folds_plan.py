"""Seed/fold campaigns pin each run to an allowed GPU on one frozen nnU-Net plan."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from segmentary.gpu_policy import GpuPolicyError
from test_medical_strong_recipe_plan import build_inputs

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "seed_folds_planner_test", ROOT / "scripts/plan_medical_seed_folds.py"
)
assert SPEC is not None and SPEC.loader is not None
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "seed_folds_runner_test", ROOT / "scripts/run_medical_campaign.py"
)
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)

WAVE = ["2:0:0", "3:0:1", "4:0:2", "5:0:3", "6:1:0", "7:2:0", "8:3:0", "9:4:0"]


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    values = build_inputs(tmp_path, monkeypatch)
    values.pop("gpus")
    metadata = json.loads(values["manifest"].read_text())
    monkeypatch.setattr(planner, "load_manifest", lambda path, verify_files: metadata)
    monkeypatch.setattr(planner, "validate_splits", lambda *_: None)
    monkeypatch.setattr(planner, "validate_cv_splits", lambda *_: None)
    split = json.loads(values["splits"].read_text())
    development = split["train"] + split["val"]
    folds = [{"fold": 0, "train": split["train"], "val": split["val"]}]
    for fold in range(1, 5):
        val = split["train"][fold - 1 :: 4]
        folds.append({"fold": fold, "train": [c for c in development if c not in val], "val": val})
    cv = tmp_path / "cv.json"
    cv.write_text(
        json.dumps(
            {
                "fingerprint": "cv",
                "base_splits_sha256": planner.sha256_file(values["splits"]),
                "folds": folds,
            }
        )
    )
    values.update(campaign_dir=tmp_path / "task07-wave1", cv_splits=cv, runs=list(WAVE))
    return values


def test_wave_runs_are_pinned_to_their_gpu_fold_and_seed(inputs):
    spec = planner.plan_campaign(**inputs)
    assert spec["gpus"] == [str(gpu) for gpu in range(2, 10)]
    expected = {
        planner.MODEL + f"-fold{fold}-seed{seed}": gpu
        for gpu, fold, seed in (item.split(":") for item in WAVE)
    }
    assert {run["id"]: run["gpu"] for run in spec["runs"]} == expected
    for run in spec["runs"]:
        recipe = json.loads(Path(run["config"]).read_text())
        gpu, fold, seed = run["gpu"], recipe["fold"], recipe["seed"]
        assert run["id"] == f"nnunet_resenc_l-fold{fold}-seed{seed}"
        assert recipe["gpu"] == gpu
        assert recipe["cv_splits"] == str(inputs["cv_splits"])
        assert recipe["cv_splits_sha256"] == planner.sha256_file(inputs["cv_splits"])
        assert recipe["use_mirroring"] is False and recipe["tile_step_size"] == 0.5
        assert recipe["workers"] == 4 and recipe["purpose"] == "baseline"
        assert recipe["architecture"] == "resenc" and recipe["resenc"] == "L"
        assert recipe["reference_workspace"] == str(inputs["reference_workspace"])
        assert recipe["num_epochs"] is None
    assert spec["protocol"]["primary_checkpoint"] == "checkpoint_final.pth"
    runner.load_spec(inputs["campaign_dir"] / "campaign.json")


@pytest.mark.parametrize(
    "runs, error",
    [
        (["1:0:0"], GpuPolicyError),
        (["0:1:0", "2:0:0"], GpuPolicyError),
        (["2:0:0", "3:0:0"], ValueError),
        (["2:0"], ValueError),
        (["2:5:0"], ValueError),
    ],
)
def test_invalid_or_forbidden_runs_create_nothing(inputs, runs, error):
    with pytest.raises(error):
        planner.plan_campaign(**{**inputs, "runs": runs})
    assert not inputs["campaign_dir"].exists()


def test_cv_manifest_from_another_split_is_rejected(inputs):
    cv = json.loads(inputs["cv_splits"].read_text())
    cv["base_splits_sha256"] = "0" * 64
    inputs["cv_splits"].write_text(json.dumps(cv))
    with pytest.raises(ValueError, match="different split file"):
        planner.plan_campaign(**inputs)
    assert not inputs["campaign_dir"].exists()


@pytest.mark.parametrize(
    "tamper, message",
    [
        (lambda c, r, s: c.write_text(c.read_text() + " "), "cross-validation manifest changed"),
        (lambda c, r, s: r.update(tile_step_size=0.25), "differs from the seed/fold plan"),
        (lambda c, r, s: r.update(use_mirroring=True), "differs from the seed/fold plan"),
        (lambda c, r, s: r.update(reference_plan_binding_sha256="0" * 64), "seed/fold plan"),
        (lambda c, r, s: r.update(seed=7), "differs from the seed/fold plan"),
        (lambda c, r, s: r.update(cv_splits_sha256="0" * 64), "differs from the seed/fold plan"),
        (lambda c, r, s: s["protocol"].update(cv_fingerprint="other"), "not the planned one"),
        (lambda c, r, s: s["protocol"].update(splits_sha256="0" * 64), "changed after planning"),
    ],
)
def test_runner_rechecks_the_seed_fold_plan_at_launch(inputs, tamper, message):
    planner.plan_campaign(**inputs)
    spec_path = inputs["campaign_dir"] / "campaign.json"
    spec = json.loads(spec_path.read_text())
    recipe_path = Path(spec["runs"][4]["config"])
    recipe = json.loads(recipe_path.read_text())
    tamper(inputs["cv_splits"], recipe, spec)
    recipe_path.write_text(json.dumps(recipe))
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match=message):
        runner.load_spec(spec_path)


def test_two_digit_folds_parse_for_larger_manifests():
    assert planner.parse_arm("2:12:3") == ("2", 12, 3)
    with pytest.raises(ValueError):
        planner.parse_arm("2:01:3")
