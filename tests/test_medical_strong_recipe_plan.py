"""A recipe transfer must preserve its cohort and plan before any work launches."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "strong_recipe_planner_test", ROOT / "scripts/plan_medical_strong_recipe.py"
)
assert SPEC is not None and SPEC.loader is not None
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


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
    manifest, splits = tmp_path / "manifest.json", tmp_path / "splits.json"
    ontology = {"background": 0, "pancreas": 1, "mass": 2}
    split_record = {
        "fingerprint": "split",
        **{
            name: [f"{name}-{index}" for index in range(count)]
            for name, count in planner.EXPECTED_COUNTS.items()
        },
    }
    metadata = {
        "fingerprint": "manifest",
        "ontology": ontology,
        "grouping_status": "dataset_case_unverified",
        "cases": [
            {
                "case_id": identifier,
                "annotation_status": "labeled",
                "image": "/DO-NOT-OPEN/ct.nii.gz",
                "label": "/DO-NOT-OPEN/mask.nii.gz",
            }
            for name in planner.EXPECTED_COUNTS
            for identifier in split_record[name]
        ],
    }
    write(manifest, metadata)
    write(splits, split_record)

    def load(path, *, verify_files):
        assert path == manifest and verify_files is False
        return metadata

    monkeypatch.setattr(planner, "load_manifest", load)
    monkeypatch.setattr(planner, "validate_splits", lambda *_: None)
    reference = tmp_path / "original"
    binding = {
        "config": {
            "workspace": str(reference),
            "resenc": "L",
            "configuration": "3d_fullres",
            "dataset_id": 707,
            "dataset_name": "Pancreas",
            "fold": 0,
            "seed": 0,
            "purpose": "baseline",
            "nnunet_version": "2.8.1",
            "use_mirroring": False,
            "tile_step_size": 0.5,
        },
        "manifest_sha256": planner.sha256_file(manifest),
        "splits_sha256": planner.sha256_file(splits),
        "planning_scope": "train_and_val_only",
        "ontology": ontology,
        "development_cases": split_record["train"] + split_record["val"],
        "held_out_cases": split_record["test"],
    }
    write(reference / "binding.json", binding)
    prepared = reference / "nnUNet_preprocessed/Dataset707_Pancreas"
    write(
        prepared / planner.METADATA_NAMES[0],
        {
            "configurations": {
                "3d_fullres": {
                    "batch_size": 2,
                    "patch_size": [56, 320, 256],
                    "spacing": [2.5, 0.8125, 0.8125],
                    "batch_dice": False,
                    "preprocessor_name": "DefaultPreprocessor",
                    "normalization_schemes": ["CTNormalization"],
                }
            },
            "foreground_intensity_properties_per_channel": {"0": {"mean": 79.77}},
        },
    )
    write(
        prepared / "splits_final.json",
        [{"train": split_record["train"], "val": split_record["val"]}],
    )
    write(prepared / "dataset.json", {"labels": ontology, "numTraining": 239})
    write(prepared / "dataset_fingerprint.json", {"scope": "239 development cases"})
    write(
        reference / "plan-binding.json",
        {
            "binding_digest": planner._digest(binding),
            "files": {
                name: planner.sha256_file(prepared / name) for name in planner.METADATA_NAMES
            },
        },
    )
    executable = tmp_path / "venv/bin/python"
    executable.parent.mkdir(parents=True)
    executable.symlink_to(sys.executable)
    return {
        "source_root": source,
        "campaign_dir": tmp_path / "strong-recipe",
        "python": executable,
        "nnunet_python": executable,
        "manifest": manifest,
        "splits": splits,
        "reference_workspace": reference,
        "gpus": ["1", "2", "3"],
    }


def test_three_architectures_preserve_full_recipe_without_touching_reference(inputs):
    reference = inputs["reference_workspace"]
    before = {path: path.read_bytes() for path in reference.rglob("*") if path.is_file()}
    spec = planner.plan_campaign(**inputs)
    assert len(spec["runs"]) == 3
    assert spec["python"] == str(inputs["python"])
    assert {run["model"] for run in spec["runs"]} == {value[0] for value in planner.ARMS.values()}
    assert {run["comparison_group"] for run in spec["runs"]} == {planner.GROUP}
    configs = [json.loads(Path(run["config"]).read_text()) for run in spec["runs"]]
    assert {config["architecture"] for config in configs} == {"resenc", "plainconv", "dynunet"}
    for config, run in zip(configs, spec["runs"], strict=True):
        assert config["seed"] == 0 and config["purpose"] == "baseline"
        assert config["reference_workspace"] == str(reference)
        assert config["reference_plan_binding_sha256"] == planner.sha256_file(
            reference / "plan-binding.json"
        )
        assert config["use_mirroring"] is False and config["tile_step_size"] == 0.5
        assert config["num_epochs"] is None and config["num_iterations_per_epoch"] is None
        assert config["backend_python"] == str(inputs["nnunet_python"])
        assert not Path(run["workspace"]).exists()
    stable = [
        {key: value for key, value in config.items() if key not in {"workspace", "architecture"}}
        for config in configs
    ]
    assert stable[0] == stable[1] == stable[2]
    assert spec["protocol"]["optimizer_steps_per_arm"] == 250000
    assert spec["protocol"]["nnunet"] == {
        "expected_default_epochs": 1000,
        "expected_default_updates_per_epoch": 250,
    }
    assert spec["protocol"]["sampled_patches_per_arm"] == 500000
    assert spec["protocol"]["maximum_concurrent_runs"] == 3
    assert spec["protocol"]["early_stopping"] is False
    assert all(path.read_bytes() == contents for path, contents in before.items())
    assert not list(inputs["campaign_dir"].parent.glob("*.building-*"))


@pytest.mark.parametrize("fault", ["binding", "plan", "source_split", "fold", "geometry", "budget"])
def test_changed_cohort_plan_and_recipe_fail_before_publication(inputs, fault):
    reference = inputs["reference_workspace"]
    binding_path, plan_binding_path = reference / "binding.json", reference / "plan-binding.json"
    binding, plan_binding = (
        json.loads(binding_path.read_text()),
        json.loads(plan_binding_path.read_text()),
    )
    prepared = reference / "nnUNet_preprocessed/Dataset707_Pancreas"
    if fault in {"binding", "budget"}:
        binding["config"]["num_epochs"] = 10
        write(binding_path, binding)
        if fault == "budget":
            plan_binding["binding_digest"] = planner._digest(binding)
    elif fault == "source_split":
        inputs["splits"].write_text(inputs["splits"].read_text() + " ")
    else:
        name = "splits_final.json" if fault == "fold" else planner.METADATA_NAMES[0]
        value = json.loads((prepared / name).read_text())
        if fault == "fold":
            value[0]["train"][0], value[0]["val"][0] = value[0]["val"][0], value[0]["train"][0]
        else:
            value["configurations"]["3d_fullres"]["patch_size"][0] = 64
        write(prepared / name, value)
        if fault != "plan":
            plan_binding["files"][name] = planner.sha256_file(prepared / name)
    write(plan_binding_path, plan_binding)
    with pytest.raises(ValueError, match="Reference"):
        planner.plan_campaign(**inputs)
    assert not inputs["campaign_dir"].exists()


@pytest.mark.parametrize(
    "gpus", [[], ["1"], ["1", "2", "2"], ["0", "1", "2", "3"], ["1", "2", "03"]]
)
def test_gpu_pool_is_explicit_bounded_and_canonical(inputs, gpus):
    with pytest.raises(ValueError, match="three distinct"):
        planner.plan_campaign(**{**inputs, "gpus": gpus})
    assert not inputs["campaign_dir"].exists()


def test_existing_output_dirty_source_and_inherited_gpu_restriction(inputs, monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2")
    with pytest.raises(ValueError, match="inherited CUDA"):
        planner.plan_campaign(**inputs)
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES")
    dirty = inputs["source_root"] / "user-change.txt"
    dirty.write_text("preserve")
    with pytest.raises(ValueError, match="clean checkout"):
        planner.plan_campaign(**inputs)
    dirty.unlink()
    inputs["campaign_dir"].mkdir()
    marker = inputs["campaign_dir"] / "user-work.txt"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        planner.plan_campaign(**inputs)
    assert marker.read_text() == "preserve"


@pytest.mark.parametrize("backend", ["torch", "nnunet"])
def test_completed_training_binds_origin_and_result_for_every_backend(tmp_path, backend):
    runner_spec = importlib.util.spec_from_file_location(
        "strong_recipe_artifact_runner_test", ROOT / "scripts/run_medical_campaign.py"
    )
    assert runner_spec is not None and runner_spec.loader is not None
    runner = importlib.util.module_from_spec(runner_spec)
    runner_spec.loader.exec_module(runner)
    names = ("checkpoint-index.json", "scratch-origin.json", "training-result.json")
    for name in names:
        write(tmp_path / name, {"identity": "scratch-run", "artifact": name})
    state = {"workspace": str(tmp_path), "backend": backend}
    instance = object.__new__(runner.Campaign)
    artifacts = instance.stage_artifacts(state, "train")
    assert artifacts == {
        str(tmp_path / name): planner.sha256_file(tmp_path / name) for name in names
    }
    write(tmp_path / "scratch-origin.json", {"identity": "different-run"})
    assert instance.stage_artifacts(state, "train") != artifacts
    (tmp_path / "training-result.json").unlink()
    with pytest.raises(FileNotFoundError):
        instance.stage_artifacts(state, "train")
