"""Fresh same-model arms preserve the reference, identity and readable reporting."""

from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from segmentary.medical.recipe_ablation import recipe_fingerprint, scientific_recipe
from segmentary.medical.torch_config import TorchConfig

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


planner = module("ablation_planner_test", "plan_medical_recipe_ablation.py")
runner = module("ablation_runner_test", "run_medical_campaign.py")
reporter = module("ablation_reporter_test", "report_medical_campaign.py")


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    shutil.copy2(
        ROOT / "scripts/run_medical_campaign.py", source / "scripts/run_medical_campaign.py"
    )
    (source / ".gitignore").write_text("__pycache__/\n")
    subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Fixture",
        ],
        check=True,
        capture_output=True,
    )
    reference = tmp_path / "original" / "campaign.json"
    recipe = tmp_path / "original" / "recipes" / "dynunet.json"
    raw = yaml.safe_load((ROOT / "configs/medical/torch/dynunet.yaml").read_text())
    raw.update(planner.EXPECTED_CONTROL)
    raw.update(
        workspace=str(tmp_path / "original/runs/dynunet-seed0"),
        backend_python=sys.executable,
        gpu="0",
        workers=4,
        prefetch_batches=True,
    )
    # Mimic historical recipes which have no newly added optional fields.
    for field in (
        "center_probabilities",
        "class_center_weights",
        "rotation_probability",
        "rotation_degrees",
        "rotation_padding_value",
        "intensity_scale_probability",
        "intensity_scale_range",
    ):
        raw.pop(field, None)
    write(recipe, raw)
    splits = tmp_path / "data" / "splits.json"
    split_record = {
        "fingerprint": "split-hash",
        "train": [f"train-{n}" for n in range(197)],
        "val": [f"val-{n}" for n in range(42)],
        "test": [f"DO-NOT-OPEN-TEST-{n}" for n in range(42)],
    }
    write(splits, split_record)
    manifest = tmp_path / "data" / "manifest.json"
    write(manifest, {"fingerprint": "manifest-hash"})
    metadata = {
        "fingerprint": "manifest-hash",
        "grouping_status": "dataset_case_unverified",
        "cases": [
            {
                "case_id": identifier,
                "annotation_status": "labeled",
                "label": "/must-not-open/labels.nii.gz",
            }
            for key in ("train", "val", "test")
            for identifier in split_record[key]
        ],
    }

    def load(path, *, verify_files):
        assert path == manifest
        assert verify_files is False
        return metadata

    monkeypatch.setattr(planner, "load_manifest", load)
    monkeypatch.setattr(planner, "validate_splits", lambda *_: None)
    write(
        reference,
        {
            "schema_version": 1,
            "campaign_id": "original",
            "source_root": str(source),
            "source_commit": "a" * 40,
            "python": sys.executable,
            "manifest": str(manifest),
            "splits": str(splits),
            "gpus": ["0", "9"],
            "runs": [{"id": "dynunet-seed0", "config": str(recipe), "model": "dynunet"}],
            "protocol": {
                "manifest_sha256": planner.sha256_file(manifest),
                "splits_sha256": planner.sha256_file(splits),
            },
            "evaluation": {
                "bootstrap_samples": 1000,
                "seed": 0,
                "surface_tolerance_mm": 2.0,
                "review_overlays": False,
            },
        },
    )
    write(
        reference.parent / "state" / "campaign-binding.json",
        {
            "spec_sha256": planner.sha256_file(reference),
            "recipes": {"dynunet-seed0": planner.sha256_file(recipe)},
            "manifest_sha256": planner.sha256_file(manifest),
            "splits_sha256": planner.sha256_file(splits),
        },
    )
    return {
        "source_root": source,
        "campaign_dir": tmp_path / "ablation",
        "reference_campaign": reference,
        "python": Path(sys.executable),
        "cache_root": tmp_path / "cache",
        "gpus": [str(n) for n in range(1, 7)],
    }


def test_six_fresh_arms_preserve_original_recipe_and_separate_identities(inputs):
    before = {
        path: path.read_bytes() for path in inputs["reference_campaign"].parent.rglob("*.json")
    }
    spec = planner.plan_ablation(**inputs)
    assert len(spec["runs"]) == 6
    assert spec["gpus"] == ["1", "2", "3", "4", "5", "6"]
    assert len({run["id"] for run in spec["runs"]}) == 6
    assert len({run["workspace"] for run in spec["runs"]}) == 6
    configs = {run["id"]: json.loads(Path(run["config"]).read_text()) for run in spec["runs"]}
    control = configs["dynunet-control-seed0"]
    old = json.loads(next(path for path in before if path.name == "dynunet.json").read_text())
    old_resolved = json.loads(json.dumps(dataclasses.asdict(TorchConfig(**old))))
    assert scientific_recipe(control) == scientific_recipe(old_resolved)
    for run in spec["runs"]:
        config = configs[run["id"]]
        assert run["model"] == config["model"] == "dynunet"
        assert config["epochs"] * config["steps_per_epoch"] == 10000
        assert config["batch_size"] == 8
        assert config["patch_size"] == [96, 96, 96]
        assert not Path(run["workspace"]).exists()
        assert config["initialization"] == "scratch"
        arm = spec["protocol"]["recipe_ablation"]["arms"][run["id"]]
        assert recipe_fingerprint({**control, **arm["changes_from_control"]}) == recipe_fingerprint(
            config
        )
    assert not inputs["cache_root"].exists()
    assert all(path.read_bytes() == contents for path, contents in before.items())
    assert runner.load_spec(inputs["campaign_dir"] / "campaign.json") == spec


def test_explicit_seeds_get_separate_controls_and_comparison_groups(inputs):
    spec = planner.plan_ablation(**inputs, seeds=[0, 2])
    assert len(spec["runs"]) == 12
    assert len({run["comparison_group"] for run in spec["runs"]}) == 2
    for run in spec["runs"]:
        config = json.loads(Path(run["config"]).read_text())
        arm = spec["protocol"]["recipe_ablation"]["arms"][run["id"]]
        assert arm["control_run_id"] == f"dynunet-control-seed{config['seed']}"
    runner.load_spec(inputs["campaign_dir"] / "campaign.json")


def test_planning_respects_gpu_subset_without_reallocating_historical_gpus(inputs, monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2,3,4,5,6")
    assert planner.plan_ablation(**inputs)["gpus"] == inputs["gpus"]


@pytest.mark.parametrize("fault", ["recipe", "data", "missing_declaration", "forged_recipe_hash"])
def test_runner_rejects_drift_before_first_state_or_training(inputs, fault):
    spec = planner.plan_ablation(**inputs)
    spec_path = inputs["campaign_dir"] / "campaign.json"
    if fault in {"recipe", "forged_recipe_hash"}:
        run = spec["runs"][1]
        config = json.loads(Path(run["config"]).read_text())
        config["learning_rate"] *= 2
        write(Path(run["config"]), config)
        if fault == "forged_recipe_hash":
            spec["protocol"]["recipe_ablation"]["arms"][run["id"]]["scientific_recipe_sha256"] = (
                recipe_fingerprint(config)
            )
            write(spec_path, spec)
    elif fault == "data":
        Path(spec["splits"]).write_text(Path(spec["splits"]).read_text() + "\n")
    else:
        del spec["protocol"]["recipe_ablation"]
        write(spec_path, spec)
    with pytest.raises(ValueError, match="ablation"):
        runner.Campaign(spec_path, inputs["campaign_dir"] / "state")
    assert not (inputs["campaign_dir"] / "state").exists()


def test_same_model_reports_keep_all_arm_names_and_configuration_changes(inputs):
    spec = planner.plan_ablation(**inputs)
    snapshot = reporter.collect(
        inputs["campaign_dir"] / "campaign.json", inputs["campaign_dir"] / "state"
    )
    assert len(snapshot["runs"]) == 6
    assert all(
        row["model"] == "dynunet" and row["display_name"] == row["id"] for row in snapshot["runs"]
    )
    assert not snapshot["groups"][planner.GROUP]["ranked"]
    files = reporter.render(snapshot)
    for run in spec["runs"]:
        for name in (
            "README.md",
            "comparison.md",
            "learning-curves.md",
            "training-cost.md",
            "inference.md",
            "clinical-metrics.md",
        ):
            assert run["id"] in files[name]
        assert f"models/{run['id']}.md" in files
        assert f"records/{run['id']}.json" in files
    assert snapshot["runs"][1]["recipe"]["center_probabilities"] == [0.25, 0.25, 0.5]
    assert "must-not-open" not in "\n".join(files.values())
    assert str(inputs["campaign_dir"]) not in "\n".join(files.values())


def test_changed_bound_recipe_is_invalid_and_never_ranked(inputs):
    spec = planner.plan_ablation(**inputs)
    run = spec["runs"][1]
    config = json.loads(Path(run["config"]).read_text())
    config["rotation_probability"] = 0.8
    write(Path(run["workspace"]) / "binding.json", {"config": config})
    snapshot = reporter.collect(
        inputs["campaign_dir"] / "campaign.json", inputs["campaign_dir"] / "state"
    )
    assert snapshot["runs"][1]["status"] == "invalid_report"
    assert all(row["screening_rank"] is None for row in snapshot["runs"])


def test_ablation_rank_requires_recorded_matching_actual_runtime():
    row = {
        "id": "control",
        "comparison_group": "ablation",
        "recipe_ablation": {"arm": "control"},
        "status": "completed",
        "training_complete": True,
        "scratch_origin_verified": True,
        "code_fingerprint": "same-source",
        "split_fingerprint": "same-split",
        "checkpoint_selection": "same-rule",
        "selected_checkpoint_sha256": "a" * 64,
        "selected_checkpoint": "checkpoint_best.pth",
        "budget_steps": 10000,
        "completed_steps": 10000,
        "seed": 0,
        "recipe": {"batch_size": 8, "inference_batch_size": 8, "precision": "bf16", "overlap": 0.5},
        "evaluation": {
            "complete_coverage": True,
            "cohort_fingerprint": "cohort",
            "protocol_fingerprint": "eval",
            "manifest_fingerprint": "data",
            "mass": {"dice": 0.3},
        },
    }
    rows = [copy.deepcopy(row), {**copy.deepcopy(row), "id": "candidate"}]
    assert not reporter._rank_groups(rows)["ablation"]["ranked"]
    for member in rows:
        member["runtime_fingerprint"] = "matching-runtime"
    assert reporter._rank_groups(rows)["ablation"]["ranked"]
    rows[1]["runtime_fingerprint"] = "different-torch-or-scipy"
    result = reporter._rank_groups(rows)["ablation"]
    assert not result["ranked"]
    assert any("runtime differs" in reason for reason in result["reasons"])


@pytest.mark.parametrize("fault", ["dirty", "existing", "reference", "split", "seeds"])
def test_invalid_plan_does_not_publish_or_touch_existing_campaign(inputs, fault):
    if fault == "dirty":
        (inputs["source_root"] / "untracked").write_text("user work")
    elif fault == "existing":
        inputs["campaign_dir"].mkdir()
        (inputs["campaign_dir"] / "keep").write_text("user work")
    elif fault == "reference":
        path = inputs["reference_campaign"].parent / "recipes/dynunet.json"
        config = json.loads(path.read_text())
        config["epochs"] = 300
        write(path, config)
    elif fault == "split":
        reference = json.loads(inputs["reference_campaign"].read_text())
        split = json.loads(Path(reference["splits"]).read_text())
        split["test"] = []
        write(Path(reference["splits"]), split)
    else:
        inputs = copy.copy(inputs)
        inputs["seeds"] = [0, 0]
    with pytest.raises((ValueError, FileExistsError)):
        planner.plan_ablation(**inputs)
    assert not (inputs["campaign_dir"] / "campaign.json").exists()
    if fault == "existing":
        assert (inputs["campaign_dir"] / "keep").read_text() == "user work"
