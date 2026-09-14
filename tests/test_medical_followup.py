"""Budget/grid experiments preserve references and reject scientific drift."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from segmentary.medical.followup import ARMS, validate_declared_followup
from segmentary.medical.recipe_ablation import recipe_fingerprint, scientific_recipe

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


planner = module("followup_planner_test", ROOT / "scripts/plan_medical_followup.py")
ablation_tests = module(
    "followup_reference_fixture", ROOT / "tests/test_medical_recipe_ablation.py"
)
runner = module("followup_runner_test", ROOT / "scripts/run_medical_campaign.py")
reporter = module("followup_reporter_test", ROOT / "scripts/report_medical_campaign.py")


def write(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    # Reuse the existing frozen-reference fixture, not production dataset payloads.
    values = ablation_tests.inputs.__wrapped__(tmp_path, monkeypatch)
    monkeypatch.setattr(planner, "load_manifest", ablation_tests.planner.load_manifest)
    monkeypatch.setattr(planner, "validate_splits", ablation_tests.planner.validate_splits)
    monkeypatch.setattr(planner, "_runtime_record", lambda *_: {"python": "3.11.1", "packages": {}})
    for relative in (
        "scripts/plan_medical_followup.py",
        "src/segmentary/medical/followup.py",
        "src/segmentary/medical/torch_config.py",
        "src/segmentary/medical/torch_cache.py",
    ):
        destination = values["source_root"] / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    subprocess.run(
        ["git", "-C", str(values["source_root"]), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(values["source_root"]),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Follow-up fixture",
        ],
        check=True,
        capture_output=True,
    )
    values["reference_run_id"] = "dynunet-seed0"
    values["gpus"] = ["1", "2", "3"]
    return values


def configs(spec):
    return {run["id"]: json.loads(Path(run["config"]).read_text()) for run in spec["runs"]}


def test_followup_freezes_fresh_control_budget_and_equal_physical_extent(inputs):
    original = {
        path: path.read_bytes() for path in inputs["reference_campaign"].parent.rglob("*.json")
    }
    spec = planner.plan_followup(**inputs)
    recipes = configs(spec)
    assert len(spec["runs"]) == 3
    assert len({run["comparison_group"] for run in spec["runs"]}) == 3
    control = recipes["dynunet-control10k-seed0"]
    assert scientific_recipe(control) == scientific_recipe(
        planner._json_config(
            json.loads(next(path for path in original if path.name == "dynunet.json").read_text())
        )
    )
    assert recipes["dynunet-long30k-seed0"]["epochs"] == 300
    fine = recipes["dynunet-fine10k-seed0"]
    assert fine["patch_size"] == [96, 144, 144]
    assert fine["spacing_mm"] == [1.0, 1.0, 2.5]
    for arm in spec["protocol"]["followup_experiments"]["arms"].values():
        assert arm["nominal_crop_extent_mm_xyz"] == [144.0, 144.0, 240.0]
    for name, recipe in recipes.items():
        assert recipe["initialization"] == "scratch"
        assert recipe["batch_size"] == 8
        assert not Path(recipe["workspace"]).exists()
        assert recipe["cache_root"] == str(inputs["cache_root"])
        expected = ARMS[name.removeprefix("dynunet-").removesuffix("-seed0")]["changes"]
        assert recipe_fingerprint(recipe) == recipe_fingerprint({**control, **expected})
    assert all(path.read_bytes() == payload for path, payload in original.items())
    assert not inputs["cache_root"].exists()
    assert runner.load_spec(inputs["campaign_dir"] / "campaign.json") == spec


@pytest.mark.parametrize(
    "fault",
    [
        "budget",
        "geometry",
        "group",
        "declared_delta",
        "control",
        "missing_arm",
        "missing_declaration",
    ],
)
def test_frozen_declaration_rejects_drift_even_with_updated_candidate_fingerprint(inputs, fault):
    spec = planner.plan_followup(**inputs)
    recipes = configs(spec)
    declaration = spec["protocol"]["followup_experiments"]
    candidate = "dynunet-fine10k-seed0"
    if fault == "budget":
        recipes[candidate]["epochs"] = 300
    elif fault == "geometry":
        recipes[candidate]["patch_size"] = [96, 96, 96]
    elif fault == "group":
        spec["runs"][2]["comparison_group"] = spec["runs"][0]["comparison_group"]
    elif fault == "declared_delta":
        declaration["arms"][candidate]["changes_from_control"]["learning_rate"] = 1e-3
    elif fault == "control":
        recipes["dynunet-control10k-seed0"]["learning_rate"] = 1e-3
    elif fault == "missing_arm":
        recipes.pop("dynunet-long30k-seed0")
    else:
        del spec["protocol"]["followup_experiments"]
    declaration["arms"][candidate]["scientific_recipe_sha256"] = recipe_fingerprint(
        recipes[candidate]
    )
    with pytest.raises(ValueError, match="Follow-up"):
        validate_declared_followup(spec, recipes)


def test_ordinary_campaigns_are_not_reinterpreted():
    validate_declared_followup({"protocol": {}, "runs": []}, {})


def test_runtime_probe_uses_training_import_environment(tmp_path, monkeypatch):
    source = tmp_path / "source"
    observed = {}

    def run(command, **kwargs):
        observed.update(kwargs)
        assert command[0] == "/training/python"
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "python": "3.11.1",
                    "config_module": str(source / "src/segmentary/medical/torch_config.py"),
                }
            ),
        )

    monkeypatch.setattr(planner.subprocess, "run", run)
    planner._runtime_record(source, "/training/python")
    assert observed["env"]["PYTHONPATH"] == str(source / "src")
    assert observed["env"]["PYTHONNOUSERSITE"] == "1"
    assert observed["env"]["HF_HUB_OFFLINE"] == "1"


@pytest.mark.parametrize("fault", ["recipe", "group", "missing_declaration", "split"])
def test_runner_and_reporter_reject_changed_followup_before_launch(inputs, fault):
    spec = planner.plan_followup(**inputs)
    campaign = inputs["campaign_dir"] / "campaign.json"
    if fault == "recipe":
        path = Path(spec["runs"][2]["config"])
        config = json.loads(path.read_text())
        config["spacing_mm"] = [1.5, 1.5, 2.5]
        write(path, config)
    elif fault == "group":
        spec["runs"][2]["comparison_group"] = spec["runs"][0]["comparison_group"]
        write(campaign, spec)
    elif fault == "missing_declaration":
        del spec["protocol"]["followup_experiments"]
        write(campaign, spec)
    else:
        path = Path(spec["splits"])
        path.write_text(path.read_text() + "\n")
    for check in (
        lambda: runner.load_spec(campaign),
        lambda: reporter.collect(campaign, inputs["campaign_dir"] / "state"),
    ):
        with pytest.raises(ValueError, match="Follow-up"):
            check()
    assert not (inputs["campaign_dir"] / "state").exists()


def test_pending_followup_report_is_readable_and_has_no_cross_protocol_winner(inputs):
    spec = planner.plan_followup(**inputs)
    snapshot = reporter.collect(
        inputs["campaign_dir"] / "campaign.json", inputs["campaign_dir"] / "state"
    )
    files = reporter.render(snapshot)
    for run in spec["runs"]:
        assert run["id"] in files["comparison.md"]
        assert run["id"] in files["learning-curves.md"]
    assert all(row["screening_rank"] is None for row in snapshot["runs"])
    assert "must-not-open" not in "\n".join(files.values())
    assert str(inputs["campaign_dir"]) not in "\n".join(files.values())


def test_followup_has_no_ordinary_winner_even_when_complete():
    row = {
        "id": "control",
        "comparison_group": "followup",
        "followup_experiment": {"arm": "control10k"},
        "status": "completed",
        "training_complete": True,
        "scratch_origin_verified": True,
        "code_fingerprint": "source",
        "runtime_fingerprint": "runtime",
        "split_fingerprint": "split",
        "checkpoint_selection": "mass-dice",
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
    assert reporter._rank_groups([row])["followup"]["ranked"] is False


@pytest.mark.parametrize("fault", ["binding", "reference", "split", "pretrained"])
def test_planner_rejects_changed_reference(inputs, fault):
    reference = json.loads(inputs["reference_campaign"].read_text())
    if fault == "binding":
        write(inputs["reference_campaign"].parent / "state/campaign-binding.json", {})
    elif fault == "reference":
        inputs["reference_campaign"].write_text(inputs["reference_campaign"].read_text() + "\n")
    elif fault == "split":
        path = Path(reference["splits"])
        path.write_text(path.read_text() + "\n")
    else:
        path = Path(reference["runs"][0]["config"])
        recipe = json.loads(path.read_text())
        recipe["initialization"] = "pretrained"
        write(path, recipe)
    with pytest.raises(ValueError, match="frozen binding"):
        planner.plan_followup(**inputs)
    assert not inputs["campaign_dir"].exists()


def test_planner_rejects_runtime_change_before_atomic_publication(inputs, monkeypatch):
    records = iter([{"python": "3.11.1"}, {"python": "3.11.2"}])
    monkeypatch.setattr(planner, "_runtime_record", lambda *_: next(records))
    with pytest.raises(ValueError, match="runtime changed"):
        planner.plan_followup(**inputs)
    assert not inputs["campaign_dir"].exists()
    assert not list(inputs["campaign_dir"].parent.glob(".ablation.building-*"))


def test_planner_refuses_to_write_into_reference_or_cache(inputs):
    values = dict(inputs, cache_root=inputs["reference_campaign"].parent / "cache")
    with pytest.raises(ValueError, match="must be separate"):
        planner.plan_followup(**values)


def test_planner_refuses_wrong_source_implementation(inputs):
    path = inputs["source_root"] / "scripts/plan_medical_followup.py"
    path.write_text(path.read_text() + "\n# different implementation\n")
    subprocess.run(
        ["git", "-C", str(inputs["source_root"]), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(inputs["source_root"]),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Different source",
        ],
        check=True,
        capture_output=True,
    )
    with pytest.raises(ValueError, match="implementation must match"):
        planner.plan_followup(**inputs)


def test_cache_identity_reuses_coarse_grid_but_separates_fine_spacing(monkeypatch):
    from segmentary.medical import torch_cache
    from segmentary.medical.torch_config import TorchConfig

    monkeypatch.setattr(torch_cache, "_sources", lambda _: {"image": "a" * 64, "label": "b" * 64})
    monkeypatch.setattr(torch_cache.importlib.metadata, "version", lambda _: "test")
    coarse = TorchConfig(
        workspace="/unused/cache-test",
        model="dynunet",
        patch_size=(96, 96, 96),
        spacing_mm=(1.5, 1.5, 2.5),
    )
    longer = dataclasses.replace(coarse, epochs=300)
    fine = dataclasses.replace(coarse, spacing_mm=(1.0, 1.0, 2.5), patch_size=(96, 144, 144))
    assert torch_cache._identity({}, coarse) == torch_cache._identity({}, longer)
    assert torch_cache._identity({}, coarse) != torch_cache._identity({}, fine)


@pytest.mark.parametrize("experiment,count", [("deep-supervision", 2), ("recipe-explorations", 9)])
def test_requested_experiments_are_frozen_separately(inputs, experiment, count):
    spec = planner.plan_followup(**inputs, experiment=experiment)
    recipes = configs(spec)
    assert len(recipes) == count
    declaration = spec["protocol"]["followup_experiments"]
    assert len(declaration["planned_contrasts"]) == count - 1
    assert all(c["epochs"] * c["steps_per_epoch"] == 10000 for c in recipes.values())
    assert all(c["initialization"] == "scratch" and c["batch_size"] == 8 for c in recipes.values())
    assert recipes["dynunet-deep10k-seed0"]["model_options"]["deep_supervision"] is True
    assert not recipes["dynunet-control10k-seed0"]["model_options"].get("deep_supervision", False)
    if count == 9:
        assert recipes["swin_unetr-swin48-seed0"]["model"] == "swin_unetr"
        assert declaration["arms"]["dynunet-isotropic-seed0"]["nominal_crop_extent_mm_xyz"] == [
            144,
            144,
            240,
        ]
    assert runner.load_spec(inputs["campaign_dir"] / "campaign.json") == spec
    snapshot = reporter.collect(
        inputs["campaign_dir"] / "campaign.json", inputs["campaign_dir"] / "state"
    )
    assert all(row["screening_rank"] is None for row in snapshot["runs"])
    files = reporter.render(snapshot)
    assert (
        "Controlled recipe explorations" if count == 9 else "Deep supervision experiment"
    ) in files["README.md"]
    recipes["dynunet-deep10k-seed0"]["learning_rate"] *= 2
    declaration["arms"]["dynunet-deep10k-seed0"]["scientific_recipe_sha256"] = recipe_fingerprint(
        recipes["dynunet-deep10k-seed0"]
    )
    with pytest.raises(ValueError, match="differs"):
        validate_declared_followup(spec, recipes)


def test_cascade_requires_exact_development_roi_manifests(inputs):
    reference = json.loads(inputs["reference_campaign"].read_text())
    splits = json.loads(Path(reference["splits"]).read_text())
    mapping = {}
    for margin in (20, 40):
        path = inputs["campaign_dir"].parent / f"roi{margin}.json"
        write(
            path,
            {
                "schema_version": 1,
                "kind": "predicted_pancreas_native_bbox",
                "reference_labels_used": False,
                "empty_prediction_policy": "full_ct",
                "margin_mm": margin,
                "manifest_sha256": planner.sha256_file(Path(reference["manifest"])),
                "splits_sha256": planner.sha256_file(Path(reference["splits"])),
                "cases": {key: {} for key in splits["train"] + splits["val"]},
            },
        )
        mapping[str(margin)] = {"path": str(path), "sha256": planner.sha256_file(path)}
    spec = planner.plan_followup(**inputs, experiment="cascade", roi_manifests=mapping)
    recipes = configs(spec)
    assert set(recipes) == {
        "dynunet-control10k-seed0",
        "dynunet-roi20-seed0",
        "dynunet-roi40-seed0",
    }
    assert runner.load_spec(inputs["campaign_dir"] / "campaign.json") == spec
    assert recipes["dynunet-roi20-seed0"]["roi_manifest_sha256"] == mapping["20"]["sha256"]
    with Path(mapping["20"]["path"]).open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="changed"):
        validate_declared_followup(spec, recipes)
