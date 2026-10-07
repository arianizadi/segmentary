"""Read-only probability export: verification, case selection and a real nnU-Net round trip."""

from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from segmentary.medical import backend as b
from test_medical_backend import fake_checkpoint, fake_plan, prepared  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "probability_export_test", ROOT / "scripts/predict_medical_probabilities.py"
)
assert SPEC is not None and SPEC.loader is not None
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


@pytest.fixture(autouse=True)
def simulated_gpu_allocation(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2")


@pytest.fixture
def trained(prepared, tmp_path):  # noqa: F811
    config = prepared[0]
    fake_plan(config)
    _set_network(config, "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet")
    fake_checkpoint(config, "checkpoint_final.pth")
    b._atomic_json(config.root / "training-result.json", {"completed": True})
    (config.root / ".stage.lock").touch()
    recipe = tmp_path / "recipe.json"
    recipe.write_text(json.dumps({"workspace": config.workspace}))
    campaign = tmp_path / "campaign.json"
    campaign.write_text(json.dumps({"runs": [{"id": "run-a", "config": str(recipe)}]}))
    runtime = b._runtime(config)
    return config, campaign, runtime


def _set_network(config, network_class: str) -> None:
    """Give the fake plan an architecture and re-freeze its plan-binding hash."""
    plan_path = config.preprocessed / f"{config.plans}.json"
    plan = b._json(plan_path)
    plan["configurations"]["3d_fullres"]["architecture"] = {"network_class_name": network_class}
    b._atomic_json(plan_path, plan)
    if config.model_folder.is_dir():
        b._atomic_json(config.model_folder / "plans.json", plan)
    record = b._json(config.root / "plan-binding.json")
    record["files"][f"{config.plans}.json"] = b._sha(plan_path)
    b._atomic_json(config.root / "plan-binding.json", record)


def _member(trained):
    _, campaign, runtime = trained
    return exporter.verify_member(campaign, "run-a", "checkpoint_final.pth", runtime=runtime)


def test_member_verification_binds_checkpoint_plan_and_files(trained):
    config = trained[0]
    member = _member(trained)
    assert member["checkpoint_sha256"] == b._sha(config.fold_folder / "checkpoint_final.pth")
    assert member["trainer"] == "nnUNetTrainer" and member["network_source_bound"] is False
    assert member["guarded_files"]["fold_0/checkpoint_final.pth"] == member["checkpoint_sha256"]
    assert set(member["guarded_files"]) == {
        "plans.json",
        "dataset.json",
        "fold_0/checkpoint_final.pth",
    }
    with pytest.raises(ValueError, match="Export checkpoint"):
        exporter.verify_member(trained[1], "run-a", "checkpoint_latest.pth", runtime=trained[2])
    with pytest.raises(ValueError, match="exactly one run"):
        exporter.verify_member(trained[1], "run-b", "checkpoint_final.pth", runtime=trained[2])
    with pytest.raises(ValueError, match="environment"):
        exporter.verify_member(trained[1], "run-a", "checkpoint_final.pth", runtime={"other": 1})


@pytest.mark.parametrize("target", ["checkpoint", "plans", "training"])
def test_member_verification_refuses_changed_records(trained, target):
    config = trained[0]
    if target == "checkpoint":
        (config.fold_folder / "checkpoint_final.pth").write_bytes(b"other weights")
    elif target == "plans":
        b._atomic_json(config.model_folder / "plans.json", {"configurations": {}})
    else:
        b._atomic_json(config.root / "training-result.json", {"completed": False})
    with pytest.raises(ValueError):
        _member(trained)


def test_segmentary_networks_require_their_training_source(trained, monkeypatch):
    _set_network(trained[0], "segmentary.medical.nnunet_architectures.HRCResEncUNet")
    assert _member(trained)["network_source_bound"] is True
    current = b._code_identity()
    monkeypatch.setattr(
        exporter.b, "_code_identity", lambda: {**current, "host_reference.py": "edited"}
    )
    with pytest.raises(ValueError, match="network source"):
        _member(trained)


def test_case_selection_is_out_of_fold_and_never_test_or_training(trained):
    member = _member(trained)
    cases = exporter.select_cases([member], "val")
    assert [case["case_id"] for case in cases] == ["val_b"]
    assert set(cases[0]) == {"case_id", "image", "image_sha256"}
    assert [c["case_id"] for c in exporter.select_cases([member], "unlabeled")] == ["unknown_d"]
    with pytest.raises(ValueError, match="test access"):
        exporter.select_cases([member], "test")
    swapped = copy.deepcopy(member)
    swapped["run_id"] = "swapped"
    splits = b._json(Path(member["splits_path"]))
    other = Path(member["splits_path"]).with_name("swapped-splits.json")
    b._atomic_json(other, {**splits, "train": splits["val"], "val": splits["train"]})
    swapped.update(splits_path=str(other), splits_sha256=b._sha(other))
    with pytest.raises(ValueError, match="different manifests or splits"):
        exporter.select_cases([member, swapped], "val")
    swapped["splits_sha256"] = member["splits_sha256"]
    with pytest.raises(ValueError):
        exporter.select_cases([member, swapped], "val")


def test_export_refuses_unsafe_outputs_devices_and_gpus(trained, tmp_path):
    member = _member(trained)
    settings = {
        "partition": "val",
        "device": "cpu",
        "gpu": None,
        "mirroring": False,
        "tile_step_size": 0.5,
        "workers": 1,
        "backend_python": "/unused/python",
    }
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        exporter.export([member], output=existing, **settings)
    with pytest.raises(ValueError, match="outside"):
        exporter.export([member], output=Path(member["workspace"]) / "probabilities", **settings)
    for device, gpu in (("cuda", None), ("cpu", "2"), ("gpu", None)):
        with pytest.raises(ValueError, match="device"):
            exporter.export(
                [member], output=tmp_path / "out", **{**settings, "device": device, "gpu": gpu}
            )
    for gpu in ("0", "1"):
        with pytest.raises(ValueError):
            exporter.export(
                [member], output=tmp_path / "out", **{**settings, "device": "cuda", "gpu": gpu}
            )
    with pytest.raises(ValueError, match="once"):
        exporter.export([member, member], output=tmp_path / "out", **settings)
    assert not (tmp_path / "out").exists()


def test_export_copies_verified_models_and_never_locks_the_workspace(trained, tmp_path):
    member = _member(trained)
    output = tmp_path / "export"
    # A runner's predict stage holds the stage lock exclusively; copying must not
    # contend for it (an exporter lock would make that stage fail).
    with b._lock(Path(member["workspace"]) / ".stage.lock"):
        target = exporter.copy_model(member, output)
    assert target == output / "models/run-a" / Path(member["model_folder"]).name
    for relative, digest in member["guarded_files"].items():
        assert b._sha(target / relative) == digest
    source = Path(member["model_folder"]) / "fold_0/checkpoint_final.pth"
    source.write_bytes(b"changed after verification")
    with pytest.raises(ValueError, match="changed after verification"):
        exporter.copy_model(member, tmp_path / "second")


# Real nnU-Net 2.8.1 round trip (backend environment only) ---------------------

STD = 71.16236877441406


def _tiny_plan() -> dict:
    return {
        "dataset_name": "Dataset707_Pancreas",
        "plans_name": "nnUNetResEncUNetLPlans",
        "original_median_spacing_after_transp": [2.5, 0.8125, 0.8125],
        "original_median_shape_after_transp": [16, 64, 64],
        "image_reader_writer": "NibabelIO",
        "transpose_forward": [0, 1, 2],
        "transpose_backward": [0, 1, 2],
        "experiment_planner_used": "nnUNetPlannerResEncL",
        "label_manager": "LabelManager",
        "foreground_intensity_properties_per_channel": {
            "0": {
                "max": 3071.0,
                "mean": 79.77403259277344,
                "median": 85.0,
                "min": -998.0,
                "percentile_00_5": -92.0,
                "percentile_99_5": 215.0,
                "std": STD,
            }
        },
        "configurations": {
            "3d_fullres": {
                "data_identifier": "nnUNetPlans_3d_fullres",
                "preprocessor_name": "DefaultPreprocessor",
                "batch_size": 2,
                "patch_size": [16, 64, 64],
                "median_image_size_in_voxels": [16.0, 64.0, 64.0],
                "spacing": [2.5, 0.8125, 0.8125],
                "normalization_schemes": ["CTNormalization"],
                "use_mask_for_norm": [False],
                "resampling_fn_data": "resample_data_or_seg_to_shape",
                "resampling_fn_seg": "resample_data_or_seg_to_shape",
                "resampling_fn_data_kwargs": {
                    "is_seg": False,
                    "order": 3,
                    "order_z": 0,
                    "force_separate_z": None,
                },
                "resampling_fn_seg_kwargs": {
                    "is_seg": True,
                    "order": 1,
                    "order_z": 0,
                    "force_separate_z": None,
                },
                "resampling_fn_probabilities": "resample_data_or_seg_to_shape",
                "resampling_fn_probabilities_kwargs": {
                    "is_seg": False,
                    "order": 1,
                    "order_z": 0,
                    "force_separate_z": None,
                },
                "architecture": {
                    "network_class_name": "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet",
                    "arch_kwargs": {
                        "n_stages": 5,
                        "features_per_stage": [4, 8, 8, 8, 8],
                        "conv_op": "torch.nn.modules.conv.Conv3d",
                        "kernel_sizes": [[1, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3]],
                        "strides": [[1, 1, 1], [1, 2, 2], [2, 2, 2], [2, 2, 2], [1, 2, 2]],
                        "n_blocks_per_stage": [1, 1, 1, 1, 1],
                        "n_conv_per_stage_decoder": [1, 1, 1, 1],
                        "conv_bias": True,
                        "norm_op": "torch.nn.modules.instancenorm.InstanceNorm3d",
                        "norm_op_kwargs": {"eps": 1e-05, "affine": True},
                        "dropout_op": None,
                        "dropout_op_kwargs": None,
                        "nonlin": "torch.nn.LeakyReLU",
                        "nonlin_kwargs": {"inplace": True},
                    },
                    "_kw_requires_import": ["conv_op", "norm_op", "dropout_op", "nonlin"],
                },
                "batch_dice": False,
            }
        },
    }


DATASET = {
    "channel_names": {"0": "CT"},
    "labels": {"background": 0, "pancreas": 1, "mass": 2},
    "numTraining": 2,
    "file_ending": ".nii.gz",
    "overwrite_image_reader_writer": "NibabelIO",
}


def _model_folder(root: Path, trainer: str, plan: dict, weights: dict) -> Path:
    import torch

    folder = root / trainer / f"{trainer}__nnUNetResEncUNetLPlans__3d_fullres"
    (folder / "fold_0").mkdir(parents=True)
    (folder / "plans.json").write_text(json.dumps(plan))
    (folder / "dataset.json").write_text(json.dumps(DATASET))
    torch.save(
        {
            "network_weights": weights,
            "trainer_name": trainer,
            "init_args": {"configuration": "3d_fullres"},
            "inference_allowed_mirroring_axes": (0, 1, 2),
        },
        folder / "fold_0" / "checkpoint_final.pth",
    )
    return folder


def test_probability_round_trip_official_and_manual_hrc_loaders_agree(tmp_path, monkeypatch):
    """ResEnc via nnU-Net's own loader and zero-FiLM HRC via the manual loader give
    the same native probabilities; the ensemble of identical members is unchanged."""
    pytest.importorskip("nnunetv2")
    nib = pytest.importorskip("nibabel")
    import torch
    from nnunetv2.utilities.get_network_from_plans import get_network_from_plans

    from segmentary.medical.recipe_plan import transfer_plan

    plan = _tiny_plan()
    architecture = plan["configurations"]["3d_fullres"]["architecture"]
    torch.manual_seed(0)
    network = get_network_from_plans(
        architecture["network_class_name"],
        architecture["arch_kwargs"],
        architecture["_kw_requires_import"],
        1,
        3,
        deep_supervision=False,
    )
    with torch.no_grad():  # make the logits informative rather than near-uniform
        for parameter in network.decoder.seg_layers.parameters():
            parameter.mul_(20)
    weights = network.state_dict()
    hrc_plan, _ = transfer_plan(plan, "hrc")
    hrc_architecture = hrc_plan["configurations"]["3d_fullres"]["architecture"]
    hrc_network = get_network_from_plans(
        hrc_architecture["network_class_name"],
        hrc_architecture["arch_kwargs"],
        hrc_architecture["_kw_requires_import"],
        1,
        3,
        deep_supervision=False,
    )
    # A warm-started HRC checkpoint: ResEnc weights plus zero-FiLM HRC modules.
    missing = hrc_network.load_state_dict(weights, strict=False).missing_keys
    assert missing and all(key.startswith("hrc.") for key in missing)
    official = _model_folder(tmp_path / "models", "nnUNetTrainer", plan, weights)
    manual = _model_folder(
        tmp_path / "models", "nnUNetTrainerFinetune", hrc_plan, hrc_network.state_dict()
    )
    image = tmp_path / "images" / "case_a.nii.gz"
    image.parent.mkdir()
    volume = np.random.default_rng(0).normal(80, 60, size=(72, 56, 20)).astype(np.float32)
    nifti = nib.Nifti1Image(volume, np.diag([0.8125, 0.8125, 2.5, 1.0]))
    nifti.header.set_xyzt_units("mm")
    nib.save(nifti, image)
    output = tmp_path / "export"
    output.mkdir()
    request = {
        "members": [
            {
                "run_id": run_id,
                "model_folder": str(folder),
                "fold": 0,
                "checkpoint": "checkpoint_final.pth",
                "trainer": trainer,
            }
            for run_id, folder, trainer in (
                ("resenc", official, "nnUNetTrainer"),
                ("hrc", manual, "nnUNetTrainerFinetune"),
            )
        ],
        "cases": [{"case_id": "case_a", "image": str(image)}],
        "output": str(output),
        "device": "cpu",
        "gpu": None,
        "mirroring": True,
        "tile_step_size": 0.5,
        "workers": 1,
    }
    (output / "request.json").write_text(json.dumps(request))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    monkeypatch.setenv("nnUNet_compile", "false")
    exporter._worker(str(output / "request.json"))
    loaded = {
        name: np.load(output / name / "case_a.npz")["probabilities"]
        for name in ("members/resenc", "members/hrc", "ensemble")
    }
    first = loaded["members/resenc"]
    assert first.shape == (3, 20, 56, 72)
    np.testing.assert_allclose(first.sum(0), 1.0, atol=1e-3)
    np.testing.assert_array_equal(loaded["members/hrc"], first)
    np.testing.assert_allclose(loaded["ensemble"], first.astype(np.float32), atol=1e-6)
    segmentation = np.asarray(nib.load(output / "members/hrc/case_a.nii.gz").dataobj)
    assert segmentation.shape == volume.shape
    np.testing.assert_array_equal(segmentation.transpose(2, 1, 0), first.argmax(0))
    assert len(np.unique(segmentation)) > 1


def test_member_record_round_trips_through_json(trained):
    member = _member(trained)
    assert json.loads(json.dumps(member)) == member
    assert dataclasses.asdict(trained[0])["trainer"] == "nnUNetTrainer"
