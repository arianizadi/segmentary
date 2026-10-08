"""Backend contracts for STAR-C (``architecture: starc``): options, trainers, targets, predictor."""

from __future__ import annotations

import copy
import json
import sys
import types
from pathlib import Path

import pytest

from segmentary.medical import backend as b
from segmentary.medical.recipe_plan import (
    STARC_CLASS,
    STARC_TARGET_METHOD,
    STARC_TARGET_SCHEMA,
    validate_starc_inference,
    validate_starc_options,
)
from test_medical_backend import prepared as prepared_backend  # noqa: F401  (fixture)
from test_medical_backend_round2 import (
    frozen,  # noqa: F401  (fixture)
    simulated_gpu_allocation,  # noqa: F401  (autouse)
)
from test_medical_recipe_plan import plan as official_plan  # noqa: F401  (fixture)

CASES = ("train_a", "val_b")
DATA = "nnUNetPlans_3d_fullres"


def _targets(root: Path, *, splits: Path, plans_sha256: str, segmentations: dict) -> dict:
    """A precompute-shaped target folder for ``segmentations`` (case -> (file, sha256))."""
    root.mkdir(parents=True)
    cases = {}
    for case, (name, digest) in segmentations.items():
        (root / f"{case}.npz").write_bytes(f"{case} rays".encode())
        cases[case] = {
            "segmentation": name,
            "segmentation_sha256": digest,
            "sha256": b._sha(root / f"{case}.npz"),
            "components": 1,
        }
    manifest = {
        "schema": STARC_TARGET_SCHEMA,
        **copy.deepcopy(STARC_TARGET_METHOD),
        "plans_sha256": plans_sha256,
        "configuration": "3d_fullres",
        "data_identifier": DATA,
        "spacing": [2.5, 0.8125, 0.8125],
        "lesion_labels": [2],
        "rays": 96,
        "code": {"star_completion.py": "0" * 64},
        "forbidden_cases_checked": {"file": str(splits), "sha256": b._sha(splits), "key": "test"},
        "cases": cases,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def _rewrite(root: Path, change) -> str:
    manifest = json.loads((root / "manifest.json").read_text())
    change(manifest)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return b._sha(root / "manifest.json")


def _starc(tmp_path: Path, **changes) -> dict:
    targets = tmp_path / "targets"
    targets.mkdir(exist_ok=True)
    (targets / "manifest.json").write_text("{}")
    return {
        "architecture": "starc",
        "trainer": b.STARC_TRAINER,
        "starc_targets": str(targets),
        "starc_targets_manifest_sha256": b._sha(targets / "manifest.json"),
        "reference_workspace": str(tmp_path / "reference"),
        "reference_plan_binding_sha256": "a" * 64,
        **changes,
    }


def test_starc_binds_complete_options_inference_and_targets(tmp_path):
    config = b.NNUNetConfig(str(tmp_path / "run"), **_starc(tmp_path))
    assert config.starc_options == validate_starc_options(None)
    assert config.starc_inference == validate_starc_inference(None)
    assert config.architecture_options is config.starc_options
    assert config.model == "nnunet_planned_starc" and config.purpose == "baseline"
    assert config.model_folder.name == "nnUNetTrainerStarC__nnUNetResEncUNetLPlans__3d_fullres"
    # A full-budget STAR-C baseline keeps the official recipe; only its trainer adds losses.
    assert config.trainer == b.STARC_TRAINER and config.initial_lr is None
    pilot = b.NNUNetConfig(
        str(tmp_path / "pilot"),
        **_starc(
            tmp_path,
            trainer=b.STARC_FINETUNE_TRAINER,
            purpose="pilot",
            num_epochs=150,
            initialization="warm_start",
            init_checkpoint=str(tmp_path / "ckpt.pth"),
            init_checkpoint_sha256="b" * 64,
            init_allowed_missing_prefixes=["starc."],
            starc_options={"freeze_backbone": True},
            starc_inference={"nms_radius_mm": 4},
        ),
    )
    assert pilot.starc_options["freeze_backbone"] is True
    assert pilot.starc_inference["nms_radius_mm"] == 4.0


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"deterministic": True}, "deterministic"),
        ({"trainer": "nnUNetTrainer"}, "trains with one of"),
        ({"trainer": b.STARC_FINETUNE_TRAINER}, "non-scratch pilot"),
        ({"initial_lr": 1e-3}, "official initial learning rate"),
        ({"starc_options": {"ray_weight": -1}}, "Invalid STAR-C"),
        ({"starc_options": {"bogus": 1}}, "Unknown STAR-C"),
        ({"starc_options": {"freeze_backbone": True}}, "freeze_backbone"),
        ({"starc_inference": {"two_pass": "yes"}}, "two_pass"),
        ({"starc_targets": "relative/targets"}, "absolute starc_targets"),
        ({"starc_targets_manifest_sha256": None}, "starc_targets_manifest_sha256"),
        ({"reference_workspace": None, "reference_plan_binding_sha256": None}, "reference"),
        ({"output_mode": "regions"}, "fusion_channels"),
    ],
)
def test_starc_config_fails_closed(tmp_path, changes, message):
    with pytest.raises(ValueError, match=message):
        b.NNUNetConfig(str(tmp_path / "run"), **_starc(tmp_path, **changes))


def test_starc_targets_must_live_outside_both_workspaces(tmp_path):
    for inside in (tmp_path / "run" / "targets", tmp_path / "reference" / "targets"):
        with pytest.raises(ValueError, match="outside"):
            b.NNUNetConfig(str(tmp_path / "run"), **_starc(tmp_path, starc_targets=str(inside)))


def test_frozen_aux_only_and_starc_fields_elsewhere_are_refused(tmp_path):
    warm = {
        "trainer": b.STARC_FINETUNE_TRAINER,
        "purpose": "pilot",
        "initialization": "warm_start",
        "init_checkpoint": str(tmp_path / "ckpt.pth"),
        "init_checkpoint_sha256": "b" * 64,
    }
    with pytest.raises(ValueError, match="gated fusion"):
        b.NNUNetConfig(
            str(tmp_path / "run"),
            **_starc(
                tmp_path, **warm, starc_options={"freeze_backbone": True, "fusion": "aux_only"}
            ),
        )
    with pytest.raises(ValueError, match="need starc"):
        b.NNUNetConfig(str(tmp_path / "run"), starc_options={})
    with pytest.raises(ValueError, match="architecture=starc only"):
        b.NNUNetConfig(str(tmp_path / "run"), trainer=b.STARC_TRAINER, purpose="smoke")
    with pytest.raises(ValueError, match=r"nnssl runtime|trains with one of"):
        b.NNUNetConfig(
            str(tmp_path / "run"),
            **_starc(
                tmp_path,
                backend_runtime=b.NNSSL_RUNTIME,
                runtime_freeze_sha256="f" * 64,
                nnunet_commit="c" * 40,
                pretrained_plan_name="nnFoundationCNN_8edba046",
            ),
        )


def test_region_starc_declares_region_heads(tmp_path):
    config = b.NNUNetConfig(
        str(tmp_path / "run"),
        **_starc(tmp_path, output_mode="regions", starc_options={"fusion_channels": [0, 1]}),
    )
    assert config.starc_options["fusion_channels"] == [0, 1]
    assert config.regions_class_order == [1, 2]


def test_starc_trainers_resolve_from_their_own_module(monkeypatch):
    module = types.ModuleType("segmentary.medical.nnunet_star_trainer")
    for name in b.STARC_TRAINERS:
        setattr(module, name, type(name, (), {}))
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(sys.modules["segmentary.medical"], "nnunet_star_trainer", module, False)
    for name in b.STARC_TRAINERS:
        assert b._trainer_class(name) is getattr(module, name)
    assert b.STARC_TRAINERS <= b.SEGMENTARY_TRAINERS <= b.TRAINERS


def test_build_predictor_uses_the_two_pass_predictor_with_bound_settings(monkeypatch):
    module = types.ModuleType("segmentary.medical.nnunet_star_trainer")

    class StarCPredictor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module.StarCPredictor = StarCPredictor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(sys.modules["segmentary.medical"], "nnunet_star_trainer", module, False)
    predictor = b.build_predictor("starc", {"nms_radius_mm": 4}, tile_step_size=0.5)
    assert predictor.kwargs == {
        "tile_step_size": 0.5,
        "star_two_pass": True,
        "nms_radius_mm": 4.0,
        "max_case_instances": 32,
    }
    with pytest.raises(ValueError, match="starc only"):
        b.build_predictor("resenc", {"two_pass": True})


# ---- prepare and plan from the frozen reference --------------------------------------------


@pytest.fixture
def starc(frozen, prepared_backend, tmp_path):  # noqa: F811
    *_, splits = prepared_backend
    segmentations = {
        case: (f"{case}_seg.b2nd", frozen.index[f"{DATA}/{case}_seg.b2nd"]) for case in CASES
    }
    root = tmp_path / "starc-targets"
    _targets(
        root,
        splits=splits,
        plans_sha256=frozen.index["nnUNetResEncUNetLPlans.json"],
        segmentations=segmentations,
    )

    def make(name: str, **changes):
        options = {
            "architecture": "starc",
            "trainer": b.STARC_TRAINER,
            "starc_targets": str(root),
            "starc_targets_manifest_sha256": b._sha(root / "manifest.json"),
        }
        return frozen.make(name, **{**options, **changes})

    return types.SimpleNamespace(make=make, root=root, frozen=frozen)


def test_starc_plan_binds_the_transfer_outputs_and_verified_targets(starc):
    config = starc.make("starc")
    binding = b._json(config.root / "binding.json")
    assert binding["starc_targets"] == {
        "path": str(starc.root),
        "manifest_sha256": config.starc_targets_manifest_sha256,
    }
    starc.frozen.monkeypatch.setattr(b, "_run", lambda *a, **k: pytest.fail("worker started"))
    result = b.plan_and_preprocess(config)
    assert result["stage"]["action"] == "import_reference"
    plan = b._json(config.preprocessed / "nnUNetResEncUNetLPlans.json")
    architecture = plan["configurations"]["3d_fullres"]["architecture"]
    assert architecture["network_class_name"] == STARC_CLASS
    assert architecture["arch_kwargs"]["starc_rays"] == 96
    assert architecture["arch_kwargs"]["starc_spacing"] == [2.5, 0.8125, 0.8125]
    receipt = b._json(config.root / "recipe-transfer.json")
    changes = receipt["changes"]
    assert changes["starc_options"] == config.starc_options
    assert changes["starc_outputs"] == {
        "lesion_labels": ["mass"],
        "fusion_channels": ["pancreas", "mass"],
    }
    targets = changes["starc_targets"]
    assert targets["cases"] == 2 and targets["segmentations_equal_workspace"] is True
    assert targets["forbidden_cases_checked"]["key"] == "test"
    assert targets["computed_with_current_star_completion"] is False
    assert targets["method"]["march"] == STARC_TARGET_METHOD["march"]
    # The external targets are outside the hashed preprocessing cache.
    assert not any("starc" in name for name in b._json(config.root / "plan-binding.json")["files"])


def test_region_starc_plan_names_region_heads(starc):
    config = starc.make(
        "starc-regions", output_mode="regions", starc_options={"fusion_channels": [0, 1]}
    )
    from test_medical_backend_round2 import _region_worker

    _region_worker(starc.frozen.monkeypatch)
    b.plan_and_preprocess(config)
    changes = b._json(config.root / "recipe-transfer.json")["changes"]
    assert changes["starc_outputs"] == {
        "lesion_labels": ["mass"],
        "fusion_channels": ["pancreas", "mass"],
    }


@pytest.mark.parametrize(
    "tamper, message",
    [
        (lambda m: m.update(rays=64), "rays"),
        (lambda m: m.update(lesion_labels=[1]), "lesion_labels"),
        (lambda m: m.update(spacing=[3.0, 0.8125, 0.8125]), "spacing"),
        (lambda m: m.update(plans_sha256="0" * 64), "plans_sha256"),
        (lambda m: m.update(forbidden_cases_checked=None), "forbidden_cases_checked"),
        (lambda m: m["forbidden_cases_checked"].update(key="val"), "forbidden_cases_checked"),
        (lambda m: m["cases"].pop("val_b"), "exactly the development cases"),
        (lambda m: m["cases"].update(test_c=m["cases"]["val_b"]), "exactly the development"),
        (
            lambda m: m["cases"]["train_a"].update(segmentation_sha256="0" * 64),
            "another segmentation",
        ),
        (lambda m: m["cases"]["train_a"].update(sha256="0" * 64), "Content hash"),
        (lambda m: m["march"].update(bisections=4), "march"),
        (lambda m: m.update(crop_border_voxels=1), "crop_border_voxels"),
    ],
)
def test_starc_plan_refuses_targets_from_other_data(starc, tamper, message):
    sha = _rewrite(starc.root, tamper)
    config = starc.make("starc", starc_targets_manifest_sha256=sha)
    starc.frozen.monkeypatch.setattr(b, "_run", lambda *a, **k: pytest.fail("worker started"))
    with pytest.raises(ValueError, match=message):
        b.plan_and_preprocess(config)
    assert not (config.root / "plan-binding.json").exists()


def test_a_changed_target_manifest_fails_prepare_and_train(starc):
    config = starc.make("starc")
    assert (
        b._starc_targets_binding(config) == b._json(config.root / "binding.json")["starc_targets"]
    )
    _rewrite(starc.root, lambda m: m.update(note="edited"))
    with pytest.raises(ValueError, match="Content hash"):
        b._starc_targets_binding(config)
    with pytest.raises(ValueError, match="Content hash"):
        starc.make(
            "starc-again", starc_targets_manifest_sha256=config.starc_targets_manifest_sha256
        )
