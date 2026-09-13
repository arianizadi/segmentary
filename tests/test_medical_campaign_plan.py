"""A complete scratch comparison is frozen without launching or reading test CTs."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "plan_medical_campaign_test", ROOT / "scripts/plan_medical_campaign.py"
)
assert SPEC is not None and SPEC.loader is not None
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


def _commit(root):
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
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


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    source = tmp_path / "source"
    shutil.copytree(ROOT / "configs/medical/torch", source / "configs/medical/torch")
    (source / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts/run_medical_campaign.py", source / "scripts/run_medical_campaign.py"
    )
    subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
    (source / ".gitignore").write_text("__pycache__/\n")
    _commit(source)
    manifest, splits = tmp_path / "manifest.json", tmp_path / "splits.json"
    manifest.write_text('{"fingerprint":"manifest"}')
    splits.write_text(
        json.dumps({"fingerprint": "splits", "train": ["a"], "val": ["b"], "test": ["reserved"]})
    )
    metadata = {
        "fingerprint": "manifest",
        "grouping_status": "dataset_case_unverified",
        "cases": [
            {
                "case_id": key,
                "annotation_status": "labeled",
                "label": f"/must-not-open/{key}.nii.gz",
            }
            for key in ("a", "b", "reserved")
        ],
    }

    def load(path, *, verify_files):
        assert verify_files is False
        assert path == manifest
        return metadata

    monkeypatch.setattr(planner, "load_manifest", load)
    monkeypatch.setattr(planner, "validate_splits", lambda manifest, splits: None)
    # Preserve a venv-like interpreter path instead of resolving to its target.
    executable = tmp_path / "venv" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.symlink_to(sys.executable)
    return {
        "source_root": source,
        "campaign_dir": tmp_path / "campaign",
        "python": executable,
        "nnunet_python": Path(sys.executable),
        "manifest": manifest,
        "splits": splits,
        "cache_root": tmp_path / "cache",
        "gpus": [str(gpu) for gpu in range(10)],
        "scan_backend": "native",
    }


def test_all_28_resolved_arms_share_declared_scratch_budget_and_preserve_capacities(inputs):
    spec = planner.plan_campaign(**inputs)
    assert len(spec["runs"]) == 28
    assert spec["runs"][0]["model"] == "nnunet_resenc_l"
    assert {run["model"] for run in spec["runs"][1:]} == set(planner.TORCH_ORDER)
    assert len(spec["source_commit"]) == 40
    assert spec["python"] == str(inputs["python"])
    recipes = list((inputs["campaign_dir"] / "recipes").glob("*.json"))
    assert len(recipes) == 28
    for run in spec["runs"][1:]:
        recipe = json.loads(Path(run["config"]).read_text())
        source = yaml.safe_load(
            (inputs["source_root"] / "configs/medical/torch" / f"{run['model']}.yaml").read_text()
        )
        assert recipe["initialization"] == "scratch"
        assert recipe["epochs"] * recipe["steps_per_epoch"] == 10000
        assert recipe["batch_size"] == 8
        assert recipe["precision"] == "bf16"
        assert recipe["seed"] == 0
        assert recipe["validation_interval"] == 10
        assert recipe["inference_batch_size"] == 8
        assert recipe["prefetch_batches"] is True
        assert recipe["spacing_mm"] == [1.5, 1.5, 2.5]
        assert recipe["patch_size"] == ([96] * 3 if source["mode"] == "3d" else [256] * 2)
        assert recipe["context_slices"] == (1 if source["mode"] == "3d" else 5)
        expected_options = source["model_options"]
        if run["model"] in planner.MAMBA:
            expected_options["scan_backend"] = "native"
            expected_options["checkpoint_mamba"] = True
        assert recipe["model_options"] == expected_options
        assert run["comparison_group"] == planner.COMMON_GROUP
        assert not Path(run["workspace"]).exists()
    official = json.loads(Path(spec["runs"][0]["config"]).read_text())
    assert official["purpose"] == "baseline"
    assert official["num_epochs"] is None
    assert official["num_iterations_per_epoch"] is None
    assert spec["runs"][0]["comparison_group"] != planner.COMMON_GROUP
    assert not inputs["cache_root"].exists()
    assert not list(inputs["campaign_dir"].parent.glob("*.building-*"))


def test_dirty_source_and_existing_output_fail_without_modifying_existing_files(inputs):
    dirty = inputs["source_root"] / "untracked.txt"
    dirty.write_text("user work")
    with pytest.raises(ValueError, match="clean checkout"):
        planner.plan_campaign(**inputs)
    assert not inputs["campaign_dir"].exists()
    dirty.unlink()
    inputs["campaign_dir"].mkdir()
    marker = inputs["campaign_dir"] / "user-work.txt"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        planner.plan_campaign(**inputs)
    assert marker.read_text() == "preserve"


def test_pretrained_source_recipe_and_missing_model_fail_closed(inputs):
    path = inputs["source_root"] / "configs/medical/torch/unet_3d.yaml"
    source = yaml.safe_load(path.read_text())
    source["initialization"] = "pretrained"
    path.write_text(yaml.safe_dump(source))
    _commit(inputs["source_root"])
    with pytest.raises(ValueError, match="scratch initialization"):
        planner.plan_campaign(**inputs)
    assert not inputs["campaign_dir"].exists()
    path.unlink()
    _commit(inputs["source_root"])
    with pytest.raises(ValueError, match="exactly the declared 27"):
        planner.plan_campaign(**inputs)


def test_reserved_test_and_gpu_allocation_are_required(inputs, monkeypatch):
    splits = json.loads(inputs["splits"].read_text())
    splits["test"] = []
    inputs["splits"].write_text(json.dumps(splits))
    with pytest.raises(ValueError, match="reserved test"):
        planner.plan_campaign(**inputs)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    with pytest.raises(ValueError, match="inherited CUDA"):
        planner.plan_campaign(**inputs)
    assert not inputs["campaign_dir"].exists()
