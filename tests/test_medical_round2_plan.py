"""Round-2 planners: Z2 region labels and the Z4 nnFoundation pair, rechecked by the runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from segmentary.medical import nnunet_pretrained
from test_medical_seed_folds_plan import inputs as seed_inputs  # noqa: F401  (fixture)
from test_medical_seed_folds_plan import runner

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "round2_planner_test", ROOT / "scripts/plan_medical_round2_arms.py"
)
assert SPEC is not None and SPEC.loader is not None
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)
SEED_FOLDS = sys.modules["scripts.plan_medical_seed_folds"]
FREEZE, COMMIT = "e" * 64, "d" * 40
RESENC_L_ARCH = {
    "network_class_name": "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet",
    "arch_kwargs": {"n_stages": 7},
}


@pytest.fixture
def inputs(seed_inputs, monkeypatch):  # noqa: F811
    metadata = json.loads(seed_inputs["manifest"].read_text())
    monkeypatch.setattr(SEED_FOLDS, "load_manifest", lambda path, verify_files: metadata)
    monkeypatch.setattr(SEED_FOLDS, "validate_splits", lambda *_: None)
    monkeypatch.setattr(SEED_FOLDS, "validate_cv_splits", lambda *_: None)
    # The real Wave 1 plan declares its 7-stage architecture; rebind the fixture plan.
    reference = seed_inputs["reference_workspace"]
    plan_path = reference / "nnUNet_preprocessed/Dataset707_Pancreas/nnUNetResEncUNetLPlans.json"
    plan = json.loads(plan_path.read_text())
    plan["configurations"]["3d_fullres"]["architecture"] = RESENC_L_ARCH
    plan_path.write_text(json.dumps(plan))
    binding = json.loads((reference / "plan-binding.json").read_text())
    binding["files"][plan_path.name] = planner.sha256_file(plan_path)
    (reference / "plan-binding.json").write_text(json.dumps(binding))
    values = {k: v for k, v in seed_inputs.items() if k != "runs"}
    return values


def test_region_arms_bind_the_ordered_task07_regions_on_gpus_2_to_9(inputs, tmp_path):
    campaign = tmp_path / "task07-z2"
    spec = planner.plan_regions(
        **{**inputs, "campaign_dir": campaign},
        arms=["Z2=resenc", "Z2HRC=hrc"],
        runs=["2:0:0:Z2", "3:0:0:Z2HRC", "9:4:0:Z2"],
    )
    assert spec["protocol"]["preset"] == planner.REGIONS_PRESET
    assert spec["gpus"] == ["2", "3", "9"]
    groups = {}
    for run in spec["runs"]:
        recipe = json.loads(Path(run["config"]).read_text())
        assert recipe["output_mode"] == "regions"
        assert recipe["label_regions"] == [["pancreas", [1, 2]], ["mass", [2]]]
        assert recipe["regions_class_order"] == [1, 2]
        assert recipe["purpose"] == "baseline" and recipe["trainer"] == "nnUNetTrainer"
        assert recipe["initialization"] == "scratch" and recipe["num_epochs"] is None
        assert recipe["backend_runtime"] == "nnunet-2.8.1"
        assert recipe["reference_workspace"] == str(inputs["reference_workspace"])
        if "Z2HRC" in run["id"]:
            assert run["id"] == "nnunet_planned_hrc-Z2HRC-fold0-seed0"
            options = recipe["hrc_options"]
            assert (
                options["output_mode"],
                options["host_channels"],
                options["lesion_channels"],
            ) == (
                "regions",
                [0],
                [1],
            )
        else:
            assert recipe["architecture"] == "resenc" and recipe["hrc_options"] is None
        groups.setdefault(run["comparison_group"], []).append(run["id"])
    assert set(groups) == {
        "regions_fold0_seed0_scratch_250000_steps",
        "regions_fold4_seed0_scratch_250000_steps",
    }
    runner.load_spec(campaign / "campaign.json")


@pytest.mark.parametrize(
    "runs, error",
    [
        (["1:0:0:Z2"], "GPUs 2-9"),
        (["0:0:0:Z2"], "GPUs 2-9"),
        (["10:0:0:Z2"], "GPUs 2-9"),
        (["2:0:0:Z9"], "undeclared arm"),
        (["2:0:0:Z2", "3:0:0:Z2"], "exactly once"),
        (["2:0:0"], "GPU:FOLD:SEED:ARM"),
    ],
)
def test_round2_runs_fail_closed_before_planning(inputs, tmp_path, runs, error):
    campaign = tmp_path / "bad"
    with pytest.raises(ValueError, match=error):
        planner.plan_regions(**{**inputs, "campaign_dir": campaign}, runs=runs)
    assert not campaign.exists()


@pytest.mark.parametrize(
    "change, message",
    [
        ({"output_mode": "labels", "label_regions": None, "regions_class_order": None}, "region"),
        ({"label_regions": [["mass", [2]], ["pancreas", [1, 2]]]}, "region"),
        ({"purpose": "pilot", "num_epochs": 100}, "region"),
        ({"gpu": "0"}, "planned arm"),
    ],
)
def test_runner_rechecks_the_region_plan(inputs, tmp_path, change, message):
    campaign = tmp_path / "task07-z2"
    spec = planner.plan_regions(**{**inputs, "campaign_dir": campaign}, runs=["2:0:0:Z2"])
    path = Path(spec["runs"][0]["config"])
    path.write_text(json.dumps({**json.loads(path.read_text()), **change}))
    with pytest.raises(ValueError, match=message):
        runner.load_spec(campaign / "campaign.json")


@pytest.fixture
def pretrained(inputs, tmp_path, monkeypatch):
    checkpoint = tmp_path / "models" / "checkpoint_final.pth"
    checkpoint.parent.mkdir()
    checkpoint.write_bytes(b"nnFoundation encoder")
    probes = []

    def runtime_identity(python, environment):
        probes.append((python, environment["CUDA_VISIBLE_DEVICES"]))
        return {
            "pip_freeze_sha256": FREEZE,
            "nnunetv2_commit": COMMIT,
            "packages": {"nnunetv2": {"version": "2.8.1"}},
            "sources": {"nnunetv2": {"commit": COMMIT}},
        }

    monkeypatch.setattr(nnunet_pretrained, "runtime_identity", runtime_identity)
    return {
        **inputs,
        "campaign_dir": tmp_path / "task07-z4",
        "init_checkpoint": checkpoint,
        "init_checkpoint_sha256": planner.sha256_file(checkpoint),
        "runtime_freeze_sha256": FREEZE,
        "nnunet_commit": COMMIT,
        "runs": ["2:0:0:Z4", "3:0:0:Z4HRC", "4:1:0:Z4", "5:1:0:Z4HRC"],
        "_probes": probes,
    }


def test_pretrained_pair_binds_runtime_checkpoint_and_tensor_allowlist(pretrained):
    probes = pretrained.pop("_probes")
    spec = planner.plan_pretrained(**pretrained)
    assert probes == [(str(pretrained["nnunet_python"]), "")]
    protocol = spec["protocol"]
    assert protocol["preset"] == planner.PRETRAINED_PRESET
    assert protocol["pretrained"]["runtime_freeze_sha256"] == FREEZE
    assert protocol["pretrained"]["nnunet_commit"] == COMMIT
    assert protocol["finetune"]["optimizer_steps"] == 75000
    assert protocol["finetune"]["warmup_epochs"] == 15
    groups = {}
    for run in spec["runs"]:
        recipe = json.loads(Path(run["config"]).read_text())
        assert recipe["backend_runtime"] == "nnunet-master-nnssl"
        assert recipe["backend_python"] == str(pretrained["nnunet_python"])
        assert recipe["runtime_freeze_sha256"] == FREEZE and recipe["nnunet_commit"] == COMMIT
        assert recipe["pretrained_plan_name"] == "nnFoundationCNN_8edba046"
        assert recipe["trainer"] == "nnUNetTrainerPretrainedDS" and recipe["purpose"] == "finetune"
        assert recipe["initialization"] == "pretrained"
        assert recipe["init_checkpoint"] == str(pretrained["init_checkpoint"])
        assert recipe["init_checkpoint_sha256"] == pretrained["init_checkpoint_sha256"]
        assert recipe["num_epochs"] == 300 and recipe["initial_lr"] == 1e-3
        assert recipe["output_mode"] == "labels" and recipe["use_mirroring"] is False
        expected = ["decoder.", "encoder.stages.6."]
        if recipe["architecture"] == "hrc":
            expected = ["decoder.", "encoder.stages.6.", "hrc."]
            assert recipe["hrc_options"]["output_mode"] == "softmax"
        assert recipe["init_allowed_missing_prefixes"] == expected
        groups.setdefault(run["comparison_group"], set()).add(recipe["architecture"])
    # Never ranked against scratch: a pretrained-nnfoundation group per fold and seed.
    assert groups == {
        "pretrained-nnfoundation_fold0_seed0_75000_steps": {"resenc", "hrc"},
        "pretrained-nnfoundation_fold1_seed0_75000_steps": {"resenc", "hrc"},
    }
    assert {runner.group_initialization(group) for group in groups} == {"pretrained"}
    runner.load_spec(pretrained["campaign_dir"] / "campaign.json")


@pytest.mark.parametrize(
    "change, message",
    [
        ({"runtime_freeze_sha256": "0" * 64}, "pip freeze"),
        ({"nnunet_commit": "0" * 40}, "commit"),
        ({"init_checkpoint_sha256": "0" * 64}, "SHA256"),
        ({"runs": ["1:0:0:Z4"]}, "GPUs 2-9"),
        ({"num_epochs": 0}, "positive"),
    ],
)
def test_pretrained_planner_refuses_drift(pretrained, change, message):
    pretrained.pop("_probes")
    with pytest.raises(ValueError, match=message):
        planner.plan_pretrained(**{**pretrained, **change})
    assert not pretrained["campaign_dir"].exists()


def test_runner_rechecks_the_pretrained_plan_and_checkpoint(pretrained):
    pretrained.pop("_probes")
    spec = planner.plan_pretrained(**pretrained)
    campaign = pretrained["campaign_dir"] / "campaign.json"
    path = Path(spec["runs"][0]["config"])
    original = path.read_text()
    for change in (
        {"init_allowed_missing_prefixes": ["decoder.", "encoder."]},
        {"runtime_freeze_sha256": "0" * 64},
        {"num_epochs": 1000},
        {"backend_runtime": "nnunet-2.8.1"},
    ):
        path.write_text(json.dumps({**json.loads(original), **change}))
        with pytest.raises(ValueError, match="pretrained plan"):
            runner.load_spec(campaign)
    path.write_text(original)
    record = json.loads(campaign.read_text())
    record["runs"][0]["comparison_group"] = "nnunet_resenc_l_fold0_scratch"
    campaign.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="comparison_group"):
        runner.load_spec(campaign)
    record["runs"][0]["comparison_group"] = spec["runs"][0]["comparison_group"]
    campaign.write_text(json.dumps(record))
    runner.load_spec(campaign)
    pretrained["init_checkpoint"].write_bytes(b"other weights")
    with pytest.raises(ValueError, match="checkpoint changed"):
        runner.load_spec(campaign)


def test_cli_plans_both_commands(inputs, tmp_path, monkeypatch, capsys):
    arguments = []
    for key in (
        "source_root",
        "python",
        "nnunet_python",
        "manifest",
        "splits",
        "cv_splits",
        "reference_workspace",
    ):
        arguments += [f"--{key.replace('_', '-')}", str(inputs[key])]
    campaign = tmp_path / "cli-z2"
    assert (
        planner.main(["regions", *arguments, "--campaign-dir", str(campaign), "--run", "2:0:0:Z2"])
        == 0
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed["campaign"] == str(campaign / "campaign.json")
    assert printed["runs"] == {"nnunet_resenc_l-Z2-fold0-seed0": "2"}
