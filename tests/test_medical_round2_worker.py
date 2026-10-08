"""The plan-stage adaptation worker on real nnU-Net preprocessing (CPU, tiny volumes).

Region mode runs in the nnU-Net 2.8.1 backend environment; the nnssl branch
(sampling-location store and ``plan_like_dynamic``) runs in nnU-Net master. Each
test skips in the other environment. The worker runs in process; only the stage
launcher is replaced, so the orchestrator's own checks are the real ones.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
import pickle
import shutil
from pathlib import Path

import numpy as np
import pytest

from segmentary.medical import backend as b
from segmentary.medical import nnunet_reference
from test_medical_backend import prepared as prepared_backend  # noqa: F401  (fixture)
from test_medical_regions import _case, _plans

HAS_NNUNET = importlib.util.find_spec("nnunetv2") is not None
MASTER = HAS_NNUNET and importlib.util.find_spec("nnunetv2.preprocessing.sampling_locations")
OFFICIAL = HAS_NNUNET and not MASTER
RESENC = {
    "network_class_name": "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet",
    "_kw_requires_import": ["conv_op", "norm_op", "dropout_op", "nonlin"],
    "arch_kwargs": {
        "conv_bias": True,
        "conv_op": "torch.nn.modules.conv.Conv3d",
        "dropout_op": None,
        "dropout_op_kwargs": None,
        "features_per_stage": [4, 8, 16, 16, 16],
        "kernel_sizes": [[1, 3, 3]] + [[3, 3, 3]] * 4,
        "n_blocks_per_stage": [1, 1, 2, 2, 2],
        "n_conv_per_stage_decoder": [1, 1, 1, 1],
        "n_stages": 5,
        "nonlin": "torch.nn.LeakyReLU",
        "nonlin_kwargs": {"inplace": True},
        "norm_op": "torch.nn.modules.instancenorm.InstanceNorm3d",
        "norm_op_kwargs": {"affine": True, "eps": 1e-05},
        "strides": [[1, 1, 1], [1, 2, 2], [2, 2, 2], [2, 2, 2], [1, 2, 2]],
    },
}


@pytest.fixture(autouse=True)
def simulated_gpu_allocation(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2")


def _reference_cache(original: b.NNUNetConfig, tmp_path: Path) -> tuple[str, dict, dict]:
    """Real nnU-Net preprocessing of two tiny cases, frozen like a Wave 1 reference."""
    from nnunetv2.preprocessing.preprocessors.default_preprocessor import DefaultPreprocessor
    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager

    plan = _plans()
    plan["dataset_name"] = original.dataset
    plan["configurations"]["3d_fullres"]["architecture"] = copy.deepcopy(RESENC)
    cache = original.preprocessed
    dataset = b._json(original.root / "nnUNet_raw" / original.dataset / "dataset.json")
    manager = PlansManager(plan)
    data = cache / "nnUNetPlans_3d_fullres"
    data.mkdir(parents=True)
    (cache / "gt_segmentations").mkdir()
    for index, case in enumerate(("train_a", "val_b")):
        image, label = _case(tmp_path / f"source-{index}")
        DefaultPreprocessor().run_case_save(
            str(data / case),
            [str(image)],
            str(label),
            manager,
            manager.get_configuration("3d_fullres"),
            dataset,
        )
        shutil.copyfile(label, cache / "gt_segmentations" / f"{case}.nii.gz")
    b._atomic_json(cache / "nnUNetResEncUNetLPlans.json", plan)
    b._atomic_json(cache / "dataset.json", dataset)
    b._atomic_json(cache / "dataset_fingerprint.json", {})
    index = {str(p.relative_to(cache)): b._sha(p) for p in sorted(cache.rglob("*")) if p.is_file()}
    b._atomic_json(original.root / "plan-binding.json", {"files": index})
    return b._sha(original.root / "plan-binding.json"), index, plan


@pytest.fixture
def real_reference(prepared_backend, monkeypatch, tmp_path):  # noqa: F811
    original, _, _, manifest, splits = prepared_backend
    sha, index, _ = _reference_cache(original, tmp_path)

    def import_reference(config):
        for relative in index:
            if relative != "splits_final.json":
                target = config.preprocessed / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original.preprocessed / relative, target)
        return {"weights_imported": False}

    def make(name: str, **changes):
        config = dataclasses.replace(
            original,
            workspace=str(tmp_path / name),
            reference_workspace=original.workspace,
            reference_plan_binding_sha256=sha,
            deterministic=False,
            workers=2,
            **changes,
        )
        b.prepare_dataset(manifest, splits, config)
        for variable in ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"):
            monkeypatch.setenv(variable, str(config.root / variable))
        return config

    def run(config, action, payload, *, gpu=False):
        assert (action, payload, gpu) == ("plan", {"adapt_reference": True}, False)
        b._adapt_reference_worker(config)
        return {"action": "plan", "status": "completed", "in_process": True}

    monkeypatch.setattr(nnunet_reference, "import_reference", import_reference)
    monkeypatch.setattr(b, "_run", run)
    return make, index, original


@pytest.mark.skipif(not OFFICIAL, reason="needs the nnU-Net 2.8.1 backend environment")
@pytest.mark.parametrize("architecture", ["resenc", "hrc"])
def test_region_worker_rewrites_only_sampling_keys_on_real_arrays(real_reference, architecture):
    make, index, original = real_reference
    extra = {}
    if architecture == "hrc":
        extra = {
            "architecture": "hrc",
            "hrc_options": {"output_mode": "regions", "host_channels": [0], "lesion_channels": [1]},
        }
    config = make(f"regions-{architecture}", output_mode="regions", **extra)
    b.plan_and_preprocess(config)
    record = b._json(config.root / "reference-adaptation.json")
    worker = record["worker"]["regions"]
    assert worker["label_mode_reference_reproduced"] == 2
    assert worker["label_keys"] == [1, 2] and worker["region_keys"] == [[1, 2], [2]]
    files = b._plan_binding(config)["files"]
    data = config.preprocessed / "nnUNetPlans_3d_fullres"
    for case in ("train_a", "val_b"):
        for suffix in (".b2nd", "_seg.b2nd"):
            relative = f"nnUNetPlans_3d_fullres/{case}{suffix}"
            assert files[relative] == index[relative]
        reference = pickle.loads(
            (original.preprocessed / f"nnUNetPlans_3d_fullres/{case}.pkl").read_bytes()
        )
        regions = pickle.loads((data / f"{case}.pkl").read_bytes())
        assert set(reference["class_locations"]) == {1, 2}
        assert set(regions["class_locations"]) == {(1, 2), (2,)}

        # Tiny cases are sampled exhaustively: the region pancreas key holds every
        # pancreas and mass voxel, the label key 1 only the non-mass ones.
        def rows(values):
            return sorted(map(tuple, np.asarray(values).tolist()))

        assert rows(regions["class_locations"][(1, 2)]) == sorted(
            rows(reference["class_locations"][1]) + rows(reference["class_locations"][2])
        )
        assert rows(regions["class_locations"][(2,)]) == rows(reference["class_locations"][2])
    if architecture == "hrc":
        outputs = b._json(config.root / "recipe-transfer.json")["changes"]["hrc_outputs"]
        assert outputs == {"output_mode": "regions", "host": ["pancreas"], "lesion": ["mass"]}


def _nnssl_checkpoint(tmp_path: Path) -> tuple[str, str]:
    import torch
    from nnunetv2.utilities.get_network_from_plans import get_network_from_plans

    pretrained = copy.deepcopy(RESENC)
    kwargs = pretrained["arch_kwargs"]
    kwargs.update(
        n_stages=4,
        features_per_stage=[4, 8, 16, 16],
        kernel_sizes=[[3, 3, 3]] * 4,
        strides=kwargs["strides"][:4],
        n_blocks_per_stage=[1, 1, 2, 2],
        n_conv_per_stage_decoder=[1, 1, 1],
    )
    network = get_network_from_plans(
        pretrained["network_class_name"],
        kwargs,
        pretrained["_kw_requires_import"],
        1,
        3,
        allow_init=True,
        deep_supervision=True,
    )
    path = tmp_path / "models" / "checkpoint_final.pth"
    path.parent.mkdir()
    torch.save(
        {
            "network_weights": network.state_dict(),
            "citations": [],
            "nnssl_adaptation_plan": {
                "architecture_plans": {"arch_class_name": "ResEncL"},
                "pretrain_num_input_channels": 1,
                "pretrain_plan": {"configurations": {"onemmiso": {"patch_size": [16, 16, 16]}}},
                "recommended_downstream_patchsize": [16, 16, 16],
                "key_to_encoder": "encoder.stages",
                "key_to_stem": "encoder.stem",
                "keys_to_in_proj": [
                    "encoder.stem.convs.0.conv",
                    "encoder.stem.convs.0.all_modules.0",
                ],
                "key_to_lpe": None,
            },
        },
        path,
    )
    return str(path), b._sha(path)


@pytest.mark.skipif(not MASTER, reason="needs the nnU-Net master (nnssl) environment")
@pytest.mark.parametrize("architecture", ["resenc", "hrc"])
def test_nnssl_worker_builds_the_store_and_dynamic_plan_on_real_arrays(
    real_reference, tmp_path, architecture
):
    make, index, _ = real_reference
    checkpoint, digest = _nnssl_checkpoint(tmp_path)
    allowed = ["decoder.", "encoder.stages.4."] + (["hrc."] if architecture == "hrc" else [])
    config = make(
        f"nnssl-{architecture}",
        architecture=architecture,
        backend_runtime=b.NNSSL_RUNTIME,
        runtime_freeze_sha256="f" * 64,
        nnunet_commit="c" * 40,
        pretrained_plan_name="tiny",
        trainer=b.PRETRAINED_TRAINER,
        purpose="finetune",
        num_epochs=3,
        initialization="pretrained",
        init_checkpoint=checkpoint,
        init_checkpoint_sha256=digest,
        init_allowed_missing_prefixes=allowed,
    )
    result = b.plan_and_preprocess(config)
    files = b._plan_binding(config)["files"]
    assert result["plan_sha256"] == files["ptPlans_dynamic__tiny.json"]
    for relative, digest_ in index.items():
        if relative.endswith((".b2nd", ".pkl", ".nii.gz")):
            assert files[relative] == digest_
    store = [name for name in files if "/fg_sampling/" in name]
    assert any(name.endswith("meta.json") for name in store)
    record = b._json(config.root / "reference-adaptation.json")
    assert record["pretrain_info"]["checkpoint_path"] == checkpoint
    assert record["sampling_store_files"] == len(store)
    plan = b._json(config.preprocessed / "ptPlans_dynamic__tiny.json")
    assert list(plan["configurations"]) == ["3d_fullres"]
    name = plan["configurations"]["3d_fullres"]["architecture"]["network_class_name"]
    assert name.endswith("HRCResEncUNet" if architecture == "hrc" else "ResidualEncoderUNet")
    assert json.loads((config.root / "reference-adaptation-worker.json").read_text())["nnssl"]
