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
        # The seed/fold preset is the scratch Wave 1 recipe, never a fine-tune.
        (lambda c, r, s: r.update(trainer="nnUNetTrainerFinetune"), "seed/fold plan"),
        (lambda c, r, s: r.update(initial_lr=1e-3), "seed/fold plan"),
        (lambda c, r, s: r.update(hrc_options={"levels": [2]}), "seed/fold plan"),
        (lambda c, r, s: r.update(init_allowed_missing_prefixes=["hrc."]), "seed/fold plan"),
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


def test_runner_accepts_wave1_recipes_planned_before_the_trainer_fields(inputs):
    """Recipes written by ddc615e3 lack trainer/initialization keys; absent means scratch."""
    planner.plan_campaign(**inputs)
    spec = json.loads((inputs["campaign_dir"] / "campaign.json").read_text())
    for run in spec["runs"]:
        recipe_path = Path(run["config"])
        recipe = json.loads(recipe_path.read_text())
        for key in runner.SEED_FOLDS_DEFAULTS:
            recipe.pop(key)
        recipe.pop("init_allowed_missing_prefixes")
        recipe_path.write_text(json.dumps(recipe))
    runner.load_spec(inputs["campaign_dir"] / "campaign.json")


def test_two_digit_folds_parse_for_larger_manifests():
    assert planner.parse_arm("2:12:3") == ("2", 12, 3)
    with pytest.raises(ValueError):
        planner.parse_arm("2:01:3")


# Warm-start arm sets ------------------------------------------------------------

WARM_ARMS = ["A=resenc", "B=hrc", "C=hrc:unmasked_lcn"]
WARM_RUNS = ["2:0:0:A", "3:0:0:B", "4:0:0:C", "5:1:0:A", "6:1:0:B", "7:1:0:C"]


def _source_workspace(root: Path, inputs: dict, fold: int, seed: int) -> Path:
    """A completed Wave 1 style scratch run whose final checkpoint warm-starts a fold."""
    workspace = root / f"nnunet_resenc_l-fold{fold}-seed{seed}"
    checkpoint = (
        workspace
        / "nnUNet_results/Dataset707_Pancreas/nnUNetTrainer__nnUNetResEncUNetLPlans__3d_fullres"
        / f"fold_{fold}/checkpoint_final.pth"
    )
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(f"fold {fold} seed {seed} weights".encode())
    sha = planner.sha256_file
    reference_plan = (
        inputs["reference_workspace"]
        / "nnUNet_preprocessed/Dataset707_Pancreas/nnUNetResEncUNetLPlans.json"
    )
    # Importing from a reference re-serialises the plan (sorted keys, indent 2):
    # same content, different bytes, as in every real reference-imported run.
    plan_path = workspace / "nnUNet_preprocessed/Dataset707_Pancreas/nnUNetResEncUNetLPlans.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps(json.loads(reference_plan.read_text()), sort_keys=True, indent=2)
    )
    assert sha(plan_path) != sha(reference_plan)
    files = {
        "binding.json": {
            "config": {
                "workspace": str(workspace),
                "fold": fold,
                "seed": seed,
                "architecture": "resenc",
                "resenc": "L",
                "purpose": "baseline",
                "cv_splits_sha256": sha(inputs["cv_splits"]),
                "reference_plan_binding_sha256": sha(
                    inputs["reference_workspace"] / "plan-binding.json"
                ),
            },
            "initialization": "scratch",
            "manifest_sha256": sha(inputs["manifest"]),
            "splits_sha256": sha(inputs["splits"]),
        },
        "checkpoint-index.json": {"checkpoint_final.pth": {"sha256": sha(checkpoint)}},
        "training-result.json": {"completed": True, "epochs": 1000},
        "plan-binding.json": {"files": {"nnUNetResEncUNetLPlans.json": sha(plan_path)}},
    }
    for name, value in files.items():
        (workspace / name).write_text(json.dumps(value))
    return checkpoint


@pytest.fixture
def warm_inputs(inputs, tmp_path):
    wave = tmp_path / "wave1" / "runs"
    for fold in (0, 1):
        _source_workspace(wave, inputs, fold, 0)
    pattern = str(
        wave / "nnunet_resenc_l-fold{fold}-seed{seed}/nnUNet_results/Dataset707_Pancreas/"
        "nnUNetTrainer__nnUNetResEncUNetLPlans__3d_fullres/fold_{fold}/checkpoint_final.pth"
    )
    return {
        **inputs,
        "campaign_dir": tmp_path / "task07-warm-start",
        "arms": list(WARM_ARMS),
        "runs": list(WARM_RUNS),
        "init_checkpoint_pattern": pattern,
    }


def test_wave1_checkpoint_pattern_is_the_documented_layout():
    assert planner.WAVE1_CHECKPOINTS.format(fold=3, seed=0) == (
        "/data/izadia1/projects/segmentary-runs/pancreas/task07-wave1-20261007/runs/"
        "nnunet_resenc_l-fold3-seed0/nnUNet_results/Dataset707_Pancreas/"
        "nnUNetTrainer__nnUNetResEncUNetLPlans__3d_fullres/fold_3/checkpoint_final.pth"
    )


def test_warm_start_arms_initialise_from_their_own_fold_and_bind_its_sha(warm_inputs):
    spec = planner.plan_warm_start(**warm_inputs)
    protocol = spec["protocol"]
    assert protocol["preset"] == planner.WARM_START_PRESET
    assert protocol["pilot"]["optimizer_steps"] == 37500
    groups = {}
    for run in spec["runs"]:
        recipe = json.loads(Path(run["config"]).read_text())
        fold, seed = recipe["fold"], recipe["seed"]
        bound = protocol["initial_checkpoints"][f"fold{fold}-seed{seed}"]
        assert recipe["init_checkpoint"] == bound["path"]
        assert f"fold_{fold}/checkpoint_final.pth" in bound["path"]
        assert f"fold{fold}-seed{seed}" in bound["path"]
        assert recipe["init_checkpoint_sha256"] == planner.sha256_file(Path(bound["path"]))
        assert recipe["initialization"] == "warm_start" and recipe["purpose"] == "pilot"
        assert recipe["trainer"] == "nnUNetTrainerFinetune" and recipe["initial_lr"] == 1e-3
        assert recipe["num_epochs"] == 150 and recipe["num_iterations_per_epoch"] is None
        arm = run["id"].split("-")[1]
        if arm == "A":
            assert recipe["architecture"] == "resenc" and recipe["hrc_options"] is None
            assert recipe["init_allowed_missing_prefixes"] == []
        else:
            assert recipe["architecture"] == "hrc"
            assert recipe["init_allowed_missing_prefixes"] == ["hrc."]
            mode = "unmasked_lcn" if arm == "C" else "robust"
            assert recipe["hrc_options"]["reference_mode"] == mode
        groups.setdefault(run["comparison_group"], set()).add(arm)
    assert groups == {
        "warm_start_fold0_seed0_37500_steps": {"A", "B", "C"},
        "warm_start_fold1_seed0_37500_steps": {"A", "B", "C"},
    }
    runner.load_spec(warm_inputs["campaign_dir"] / "campaign.json")


def test_warm_start_planner_refuses_missing_or_foreign_checkpoints(warm_inputs, tmp_path):
    missing = {**warm_inputs, "runs": ["2:2:0:A"]}
    with pytest.raises(ValueError, match="does not exist"):
        planner.plan_warm_start(**missing)
    # A fold-1 run pointed at fold 0's checkpoint would leak fold-1 validation cases.
    crossed = {
        **warm_inputs,
        "init_checkpoint_pattern": warm_inputs["init_checkpoint_pattern"].replace(
            "fold{fold}-seed", "fold0-seed"
        ),
    }
    with pytest.raises(ValueError, match="fold_1/checkpoint_final"):
        planner.plan_warm_start(**crossed)
    checkpoint = Path(warm_inputs["init_checkpoint_pattern"].format(fold=1, seed=0))
    workspace = checkpoint.parents[4]
    plan_path = workspace / "nnUNet_preprocessed/Dataset707_Pancreas/nnUNetResEncUNetLPlans.json"
    original_plan = plan_path.read_text()
    changed = json.loads(original_plan)
    changed["configurations"]["3d_fullres"]["batch_size"] = 3
    plan_path.write_text(json.dumps(changed, sort_keys=True, indent=2))
    original_plan_binding = (workspace / "plan-binding.json").read_text()
    plan_binding = json.loads(original_plan_binding)
    with pytest.raises(ValueError, match="plan changed after planning"):
        planner.plan_warm_start(**warm_inputs)
    plan_binding["files"]["nnUNetResEncUNetLPlans.json"] = planner.sha256_file(plan_path)
    (workspace / "plan-binding.json").write_text(json.dumps(plan_binding))
    with pytest.raises(ValueError, match="different nnU-Net plan"):
        planner.plan_warm_start(**warm_inputs)
    plan_path.write_text(original_plan)
    (workspace / "plan-binding.json").write_text(original_plan_binding)
    binding = json.loads((workspace / "binding.json").read_text())
    binding["config"]["reference_plan_binding_sha256"] = "0" * 64
    (workspace / "binding.json").write_text(json.dumps(binding))
    with pytest.raises(ValueError, match="different nnU-Net plan"):
        planner.plan_warm_start(**warm_inputs)
    checkpoint.write_bytes(b"replaced after the index was written")
    with pytest.raises(ValueError, match="checkpoint index"):
        planner.plan_warm_start(**warm_inputs)
    assert not warm_inputs["campaign_dir"].exists()


@pytest.mark.parametrize(
    "arms, runs",
    [
        (["A=resenc", "A=hrc"], ["2:0:0:A"]),
        (["A=resenc:robust"], ["2:0:0:A"]),
        (["A=unet"], ["2:0:0:A"]),
        (["A=resenc"], ["2:0:0:B"]),
        (["A=resenc"], ["2:0:0:A", "3:0:0:A"]),
        (["A=resenc"], ["1:0:0:A"]),
    ],
)
def test_warm_start_arm_declarations_fail_closed(warm_inputs, arms, runs):
    with pytest.raises((ValueError, GpuPolicyError)):
        planner.plan_warm_start(**{**warm_inputs, "arms": arms, "runs": runs})
    assert not warm_inputs["campaign_dir"].exists()


@pytest.mark.parametrize(
    "tamper, message",
    [
        (lambda r, s, c: c.write_bytes(b"different weights"), "changed or is missing"),
        (lambda r, s, c: r.update(init_checkpoint_sha256="0" * 64), "warm-start plan"),
        (lambda r, s, c: r.update(num_epochs=1000), "warm-start plan"),
        (lambda r, s, c: r.update(initial_lr=1e-2), "warm-start plan"),
        (lambda r, s, c: r.update(init_allowed_missing_prefixes=["decoder."]), "warm-start"),
        (lambda r, s, c: r.update(hrc_options=None, architecture="resenc"), "model disagrees"),
        (lambda r, s, c: s["runs"][1].update(comparison_group="warm_start_other"), "warm-start"),
        (lambda r, s, c: s["runs"][1].update(comparison_group="scratch_fold0"), "tagged"),
    ],
)
def test_runner_rechecks_the_warm_start_plan_and_checkpoints(warm_inputs, tamper, message):
    planner.plan_warm_start(**warm_inputs)
    spec_path = warm_inputs["campaign_dir"] / "campaign.json"
    spec = json.loads(spec_path.read_text())
    recipe_path = Path(spec["runs"][1]["config"])
    recipe = json.loads(recipe_path.read_text())
    tamper(recipe, spec, Path(recipe["init_checkpoint"]))
    recipe_path.write_text(json.dumps(recipe))
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match=message):
        runner.load_spec(spec_path)


def test_scratch_runs_may_not_join_a_warm_start_group(inputs):
    planner.plan_campaign(**inputs)
    spec_path = inputs["campaign_dir"] / "campaign.json"
    spec = json.loads(spec_path.read_text())
    spec["runs"][0]["comparison_group"] = "warm_start_fold0_seed0_37500_steps"
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="tagged"):
        runner.load_spec(spec_path)
    assert runner.group_initialization("pretrained_fold0") == "pretrained"
    assert runner.group_initialization("nnunet_resenc_l_fold0_scratch_250000_steps") == "scratch"
    with pytest.raises(ValueError):
        runner.group_initialization("warm_start_pretrained")


def test_runner_verifies_the_initial_checkpoint_before_training(warm_inputs):
    spec = planner.plan_warm_start(**warm_inputs)
    run = spec["runs"][1]
    state = {"config": run["config"], "workspace": run["workspace"]}
    runner.Campaign.check_initial_checkpoint(None, state)  # bound sha matches
    recipe = json.loads(Path(run["config"]).read_text())
    assert runner.origin_record_name(recipe) == "initialization-origin.json"
    assert runner.origin_record_name({"initialization": "scratch"}) == "scratch-origin.json"
    Path(recipe["init_checkpoint"]).write_bytes(b"swapped weights")
    with pytest.raises(ValueError, match="changed or is missing"):
        runner.Campaign.check_initial_checkpoint(None, state)
    binding = runner.initial_checkpoints(spec)
    assert binding[run["id"]] == {
        "path": recipe["init_checkpoint"],
        "sha256": recipe["init_checkpoint_sha256"],
    }
