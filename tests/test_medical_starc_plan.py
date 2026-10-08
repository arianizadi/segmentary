"""STAR-C arms in the warm-start and round-2 region planners, rechecked by the runner."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from segmentary.medical.recipe_plan import (
    STARC_TARGET_METHOD,
    STARC_TARGET_SCHEMA,
    validate_starc_inference,
)
from test_medical_round2_plan import SEED_FOLDS, planner
from test_medical_round2_plan import inputs as round2_inputs  # noqa: F401  (fixture)
from test_medical_seed_folds_plan import _source_workspace, runner
from test_medical_seed_folds_plan import inputs as seed_inputs  # noqa: F401  (fixture)

DATA = "nnUNetPlans_3d_fullres"
sha256 = planner.sha256_file


def _targets(root: Path, inputs: dict, segmentations: dict[str, str]) -> str:
    root.mkdir(parents=True)
    cases = {}
    for case, digest in segmentations.items():
        (root / f"{case}.npz").write_bytes(f"{case} rays".encode())
        cases[case] = {
            "segmentation": f"{case}_seg.b2nd",
            "segmentation_sha256": digest,
            "sha256": sha256(root / f"{case}.npz"),
            "components": 1,
        }
    plan = (
        inputs["reference_workspace"]
        / "nnUNet_preprocessed/Dataset707_Pancreas/nnUNetResEncUNetLPlans.json"
    )
    manifest = {
        "schema": STARC_TARGET_SCHEMA,
        **copy.deepcopy(STARC_TARGET_METHOD),
        "plans_sha256": sha256(plan),
        "configuration": "3d_fullres",
        "data_identifier": DATA,
        "spacing": [2.5, 0.8125, 0.8125],
        "lesion_labels": [2],
        "rays": 96,
        "code": {},
        "forbidden_cases_checked": {"sha256": sha256(inputs["splits"]), "key": "test"},
        "cases": cases,
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return sha256(root / "manifest.json")


@pytest.fixture
def starc_inputs(round2_inputs, tmp_path):  # noqa: F811
    """The round-2 reference plus a data folder in its plan binding, and matching targets."""
    reference = round2_inputs["reference_workspace"]
    plan_path = reference / "nnUNet_preprocessed/Dataset707_Pancreas/nnUNetResEncUNetLPlans.json"
    plan = json.loads(plan_path.read_text())
    plan["configurations"]["3d_fullres"]["data_identifier"] = DATA
    plan_path.write_text(json.dumps(plan))
    split = json.loads(round2_inputs["splits"].read_text())
    record = json.loads((reference / "plan-binding.json").read_text())
    record["files"][plan_path.name] = sha256(plan_path)
    segmentations = {}
    for case in split["train"] + split["val"]:
        segmentations[case] = f"{abs(hash(case)) % 10**12:064d}"
        record["files"][f"{DATA}/{case}_seg.b2nd"] = segmentations[case]
    (reference / "plan-binding.json").write_text(json.dumps(record))
    targets = tmp_path / "starc-targets"
    digest = _targets(targets, round2_inputs, segmentations)
    return {**round2_inputs, "starc_targets": targets, "starc_targets_sha256": digest}


@pytest.fixture
def warm(starc_inputs, tmp_path):
    wave = tmp_path / "wave1" / "runs"
    for fold in (0, 1):
        _source_workspace(wave, starc_inputs, fold, 0)
    pattern = str(
        wave / "nnunet_resenc_l-fold{fold}-seed{seed}/nnUNet_results/Dataset707_Pancreas/"
        "nnUNetTrainer__nnUNetResEncUNetLPlans__3d_fullres/fold_{fold}/checkpoint_final.pth"
    )
    return {
        **starc_inputs,
        "campaign_dir": tmp_path / "task07-starc-warm",
        "arms": ["A=resenc", "S=starc", "F=starc:frozen", "X=starc:aux_only"],
        "runs": ["2:0:0:A", "3:0:0:S", "4:0:0:F", "5:0:0:X", "6:1:0:S"],
        "init_checkpoint_pattern": pattern,
    }


def test_warm_start_starc_arms_bind_trainer_prefix_options_and_targets(warm):
    spec = SEED_FOLDS.plan_warm_start(**warm)
    protocol = spec["protocol"]
    assert protocol["starc_targets"]["manifest_sha256"] == warm["starc_targets_sha256"]
    split = json.loads(warm["splits"].read_text())
    assert protocol["starc_targets"]["cases"] == len(split["train"]) + len(split["val"]) == 239
    assert protocol["pilot"]["trainer"] == ["nnUNetTrainerFinetune", "nnUNetTrainerStarCFinetune"]
    modes = {}
    for run in spec["runs"]:
        recipe = json.loads(Path(run["config"]).read_text())
        arm = run["id"].split("-")[1]
        assert run["comparison_group"].startswith(f"warm_start_fold{recipe['fold']}_seed0_")
        if arm == "A":
            assert recipe["trainer"] == "nnUNetTrainerFinetune"
            assert recipe["starc_options"] is None and recipe["starc_targets"] is None
            continue
        assert run["id"].startswith("nnunet_planned_starc-")
        assert recipe["architecture"] == "starc"
        assert recipe["trainer"] == "nnUNetTrainerStarCFinetune"
        assert recipe["init_allowed_missing_prefixes"] == ["starc."]
        assert recipe["starc_targets"] == str(warm["starc_targets"].resolve())
        assert recipe["starc_targets_manifest_sha256"] == warm["starc_targets_sha256"]
        assert recipe["starc_inference"] == validate_starc_inference(None)
        modes[arm] = (recipe["starc_options"]["fusion"], recipe["starc_options"]["freeze_backbone"])
    assert modes == {"S": ("gated", False), "F": ("gated", True), "X": ("aux_only", False)}
    runner.load_spec(warm["campaign_dir"] / "campaign.json")


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"starc_targets": None, "starc_targets_sha256": None}, "--starc-targets"),
        ({"starc_targets_sha256": "0" * 64}, "Content hash"),
        ({"arms": ["S=starc:robust"], "runs": ["2:0:0:S"]}, "modes"),
        ({"arms": ["A=resenc"], "runs": ["2:0:0:A"]}, "only to starc arms"),
    ],
)
def test_warm_start_starc_planning_fails_closed(warm, changes, message):
    with pytest.raises(ValueError, match=message):
        SEED_FOLDS.plan_warm_start(**{**warm, **changes})
    assert not warm["campaign_dir"].exists()


def test_warm_start_refuses_targets_from_other_segmentations(warm):
    manifest = json.loads((warm["starc_targets"] / "manifest.json").read_text())
    case = next(iter(manifest["cases"]))
    manifest["cases"][case]["segmentation_sha256"] = "1" * 64
    (warm["starc_targets"] / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="another segmentation"):
        SEED_FOLDS.plan_warm_start(
            **{**warm, "starc_targets_sha256": sha256(warm["starc_targets"] / "manifest.json")}
        )


@pytest.mark.parametrize(
    "tamper, message",
    [
        (lambda r: r["starc_options"].update(ray_weight=1.0), "warm-start plan"),
        (lambda r: r.update(starc_targets_manifest_sha256="0" * 64), "warm-start plan"),
        (lambda r: r.update(trainer="nnUNetTrainerFinetune"), "warm-start plan"),
        (lambda r: r.update(starc_inference={"two_pass": False}), "warm-start plan"),
    ],
)
def test_runner_rechecks_starc_warm_start_recipes(warm, tamper, message):
    spec = SEED_FOLDS.plan_warm_start(**warm)
    run = next(run for run in spec["runs"] if "-S-fold0" in run["id"])
    path = Path(run["config"])
    recipe = json.loads(path.read_text())
    tamper(recipe)
    path.write_text(json.dumps(recipe))
    with pytest.raises(ValueError, match=message):
        runner.load_spec(warm["campaign_dir"] / "campaign.json")


def test_runner_rehashes_the_target_manifest(warm):
    SEED_FOLDS.plan_warm_start(**warm)
    manifest = warm["starc_targets"] / "manifest.json"
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(ValueError, match="target manifest changed"):
        runner.load_spec(warm["campaign_dir"] / "campaign.json")


def test_region_starc_arms_train_the_star_trainer_on_region_heads(starc_inputs, tmp_path):
    campaign = tmp_path / "task07-z2-starc"
    spec = planner.plan_regions(
        **{**starc_inputs, "campaign_dir": campaign},
        arms=["Z2=resenc", "Z2S=starc", "Z2X=starc:aux_only"],
        runs=["2:0:0:Z2", "3:0:0:Z2S", "4:0:0:Z2X"],
    )
    recipes = {run["id"]: json.loads(Path(run["config"]).read_text()) for run in spec["runs"]}
    plain = recipes["nnunet_resenc_l-Z2-fold0-seed0"]
    assert plain["trainer"] == "nnUNetTrainer" and plain["starc_options"] is None
    for name, fusion in (("Z2S", "gated"), ("Z2X", "aux_only")):
        recipe = recipes[f"nnunet_planned_starc-{name}-fold0-seed0"]
        assert recipe["trainer"] == "nnUNetTrainerStarC" and recipe["purpose"] == "baseline"
        assert recipe["initialization"] == "scratch" and recipe["output_mode"] == "regions"
        assert recipe["starc_options"]["fusion_channels"] == [0, 1]
        assert recipe["starc_options"]["fusion"] == fusion
        assert recipe["starc_targets_manifest_sha256"] == starc_inputs["starc_targets_sha256"]
    assert {run["comparison_group"] for run in spec["runs"]} == {
        "regions_fold0_seed0_scratch_250000_steps"
    }
    runner.load_spec(campaign / "campaign.json")
    path = Path(spec["runs"][1]["config"])
    recipe = json.loads(path.read_text())
    recipe["trainer"] = "nnUNetTrainer"
    path.write_text(json.dumps(recipe))
    with pytest.raises(ValueError, match=r"region-label plan|planned arm"):
        runner.load_spec(campaign / "campaign.json")


def test_starc_is_refused_in_the_pretrained_runtime_and_without_targets(starc_inputs, tmp_path):
    with pytest.raises(ValueError, match="no nnssl-runtime trainer"):
        planner.parse_arm("S=starc", regions=False)
    with pytest.raises(ValueError, match="--starc-targets"):
        planner.plan_regions(
            **{
                **starc_inputs,
                "campaign_dir": tmp_path / "bad",
                "starc_targets": None,
                "starc_targets_sha256": None,
            },
            arms=["S=starc"],
            runs=["2:0:0:S"],
        )
    assert not (tmp_path / "bad").exists()
