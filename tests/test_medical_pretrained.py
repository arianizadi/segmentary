"""nnFoundation route: runtime binding, tensor-level transfer records, and a CPU end-to-end run.

The end-to-end tests need nnU-Net master (``DynamicPretrainedTrainer``); they run
in a fresh interpreter so nnU-Net's path variables point at a temporary tree.
``SEGMENTARY_NNFOUNDATION_CHECKPOINT`` and ``SEGMENTARY_TASK07_PLAN`` enable the
real-checkpoint check (about 1 GB of CPU memory, no GPU).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from torch import nn

from segmentary.medical import nnunet_pretrained as p

ROOT = Path(__file__).resolve().parents[1]
MASTER = importlib.util.find_spec("nnunetv2") is not None and (
    importlib.util.find_spec("nnunetv2.training.nnUNetTrainer.pretraining") is not None
)
needs_master = pytest.mark.skipif(not MASTER, reason="needs nnU-Net master (pretraining trainers)")


class _Block(nn.Module):
    def __init__(self, kernel: tuple[int, int, int]) -> None:
        super().__init__()
        self.conv = nn.Conv3d(2, 2, kernel, padding=tuple(k // 2 for k in kernel))
        self.all_modules = nn.Sequential(self.conv)  # aliases, as in nnU-Net's conv blocks


class _Encoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.stem = _Block((1, 3, 3))
        self.stages = nn.ModuleList([_Block((3, 3, 3)), _Block((3, 3, 3))])


class _Decoder(nn.Module):
    def __init__(self, encoder: _Encoder) -> None:
        super().__init__()
        self.encoder = encoder  # aliases encoder.* as decoder.encoder.*
        self.head = nn.Conv3d(2, 3, 1)


class _Net(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = _Encoder()
        self.decoder = _Decoder(self.encoder)


def _transfer(net: _Net, checkpoint: dict, *, load: bool = True) -> tuple[dict, dict, dict]:
    state = net.state_dict()
    groups = p._storage_groups(state)
    before = {k: v.detach().clone() for k, v in state.items()}
    if load:
        with torch.no_grad():
            net.encoder.stem.conv.weight.copy_(
                checkpoint["encoder.stem.conv.weight"].mean(2, keepdim=True)
            )
            net.encoder.stem.conv.bias.copy_(checkpoint["encoder.stem.conv.bias"])
            for key in ("weight", "bias"):
                getattr(net.encoder.stages[0].conv, key).copy_(
                    checkpoint[f"encoder.stages.0.conv.{key}"]
                )
    return before, net.state_dict(), groups


def _checkpoint() -> dict:
    torch.manual_seed(1)
    return {
        "encoder.stem.conv.weight": torch.randn(2, 2, 3, 3, 3),
        "encoder.stem.conv.bias": torch.randn(2),
        "encoder.stages.0.conv.weight": torch.randn(2, 2, 3, 3, 3),
        "encoder.stages.0.conv.bias": torch.randn(2),
        "decoder.mae.weight": torch.randn(4),
    }


def test_transfer_record_lists_copied_adapted_and_initial_tensors_once():
    torch.manual_seed(0)
    net, checkpoint = _Net(), _checkpoint()
    before, after, groups = _transfer(net, checkpoint)
    record = p.classify_transfer(
        before,
        after,
        checkpoint,
        groups,
        allowed_random_prefixes=["decoder.", "encoder.stages.1."],
    )
    assert record["copied"] == [
        "encoder.stages.0.conv.bias",
        "encoder.stages.0.conv.weight",
        "encoder.stem.conv.bias",
    ]
    assert record["adapted"] == [
        {
            "name": "encoder.stem.conv.weight",
            "from_shape": [2, 2, 3, 3, 3],
            "to_shape": [2, 2, 1, 3, 3],
            "rule": "mean over axes [2]",
        }
    ]
    assert record["random"] == [
        "decoder.head.bias",
        "decoder.head.weight",
        "encoder.stages.1.conv.bias",
        "encoder.stages.1.conv.weight",
    ]
    # all_modules.0.* and decoder.encoder.* name the same tensors and are not counted again.
    assert "encoder.stem.all_modules.0.weight" in record["aliases"]
    assert "decoder.encoder.stages.0.conv.weight" in record["aliases"]
    assert record["parameters"] == {"copied": 112, "adapted": 36, "random": 119}
    assert record["checkpoint_tensors_unused"] == ["decoder.mae.weight"]


def test_transfer_record_fails_closed():
    torch.manual_seed(0)
    checkpoint = _checkpoint()
    allowed = ["decoder.", "encoder.stages.1."]
    net = _Net()
    before, after, groups = _transfer(net, checkpoint)
    with pytest.raises(ValueError, match="initialisation outside"):
        p.classify_transfer(before, after, checkpoint, groups, allowed_random_prefixes=["decoder."])
    with pytest.raises(ValueError, match="initialisation outside"):
        p.classify_transfer(before, after, checkpoint, groups, allowed_random_prefixes=[])
    with torch.no_grad():
        net.decoder.head.weight.add_(1)
    with pytest.raises(ValueError, match="changed although"):
        p.classify_transfer(
            before, net.state_dict(), checkpoint, groups, allowed_random_prefixes=allowed
        )
    net = _Net()
    before, after, groups = _transfer(net, checkpoint, load=False)
    with pytest.raises(ValueError, match="differs from the checkpoint"):
        p.classify_transfer(before, after, checkpoint, groups, allowed_random_prefixes=allowed)
    net = _Net()
    before, after, groups = _transfer(net, checkpoint)
    with torch.no_grad():
        net.encoder.stem.conv.weight.copy_(
            checkpoint["encoder.stem.conv.weight"].sum(2, keepdim=True)
        )
    with pytest.raises(ValueError, match="kernel adaptation"):
        p.classify_transfer(
            before, net.state_dict(), checkpoint, groups, allowed_random_prefixes=allowed
        )
    with pytest.raises(ValueError, match="No checkpoint tensor"):
        p.classify_transfer(before, before, {}, groups, allowed_random_prefixes=[""])


def test_vendor_loader_reads_only_the_verified_bytes(tmp_path):
    path = tmp_path / "checkpoint.pth"
    buffer = io.BytesIO()
    torch.save({"value": torch.ones(2)}, buffer)
    verified = buffer.getvalue()
    torch.save({"value": torch.zeros(2)}, path)  # the file changed after hashing
    with p._serve_verified_bytes(str(path), verified):
        assert torch.equal(torch.load(str(path), weights_only=True)["value"], torch.ones(2))
    assert torch.equal(torch.load(str(path), weights_only=True)["value"], torch.zeros(2))


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _source(tmp_path: Path) -> tuple[Path, Path, str]:
    source = tmp_path / "nnUNet"
    (source / "nnunetv2" / "sub").mkdir(parents=True)
    (source / "nnunetv2" / "__init__.py").write_text("")
    (source / "nnunetv2" / "sub" / "module.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    _git(source, "add", ".")
    _git(source, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-qm", "x")
    installed = tmp_path / "site-packages" / "nnunetv2"
    shutil.copytree(source / "nnunetv2", installed)
    return source, installed, _git(source, "rev-parse", "HEAD")


def _package(source: Path, installed: Path, **direct) -> dict:
    url = {"url": source.as_uri(), "dir_info": {}, **direct}
    return {
        "direct_url": json.dumps(url),
        "installed_python_tree_sha256": p.python_tree_sha256(installed)[0],
    }


def test_installed_nnunet_must_equal_a_clean_checkout_of_its_commit(tmp_path):
    source, installed, commit = _source(tmp_path)
    proof = p._source_commit(_package(source, installed), "nnunetv2")
    assert proof["commit"] == commit
    assert proof["proof"] == "clean_checkout_python_tree_equals_installed"
    (installed / "sub" / "module.py").write_text("VALUE = 2\n")
    with pytest.raises(RuntimeError, match="differs from its clean source"):
        p._source_commit(_package(source, installed), "nnunetv2")
    (installed / "sub" / "module.py").write_text("VALUE = 1\n")
    package = _package(source, installed)
    (source / "untracked.txt").write_text("dirty")
    with pytest.raises(RuntimeError, match="differs from its clean source"):
        p._source_commit(_package(source, installed), "nnunetv2")
    with pytest.raises(RuntimeError, match="non-editable"):
        p._source_commit(_package(source, installed, dir_info={"editable": True}), "nnunetv2")
    vcs = {
        **package,
        "direct_url": json.dumps({"url": "git+https://x", "vcs_info": {"commit_id": "a" * 40}}),
    }
    assert p._source_commit(vcs, "nnunetv2")["commit"] == "a" * 40
    with pytest.raises(RuntimeError, match="direct_url"):
        p._source_commit({"direct_url": None}, "nnunetv2")


def test_runtime_identity_hashes_pip_freeze_and_reads_the_source_commit(tmp_path, monkeypatch):
    source, installed, commit = _source(tmp_path)
    freeze = "nnunetv2 @ file:///x\ntorch==2.11.0\n"
    packages = {
        "nnunetv2": {"version": "2.8.1", **_package(source, installed)},
        "dynamic_network_architectures": {"version": "0.4.4", "direct_url": None},
    }
    calls = []
    real_run = subprocess.run

    def run(argv, **kwargs):
        if argv[0] == "git":
            return real_run(argv, **kwargs)
        calls.append((argv, kwargs["env"]))
        stdout = freeze if "freeze" in argv else json.dumps(packages)
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(p.subprocess, "run", run)
    identity = p.runtime_identity("/env/bin/python", {"PYTHONPATH": "src"})
    assert identity["pip_freeze_sha256"] == hashlib.sha256(freeze.encode()).hexdigest()
    assert identity["nnunetv2_commit"] == commit
    assert [argv[1:4] for argv, _ in calls] == [
        ["-m", "pip", "--disable-pip-version-check"],
        ["-c", p._TREE_PROBE],
    ]
    assert all(env == {"PYTHONPATH": "src"} for _, env in calls)


def test_trainer_is_defined_lazily_and_named_for_the_allowlist():
    from segmentary.medical import backend as b

    assert p.TRAINER == b.PRETRAINED_TRAINER and p.TRAINER in b.SEGMENTARY_TRAINERS
    assert p.RUNTIME == b.NNSSL_RUNTIME
    assert "nnunet_pretrained.py" in b._code_identity()
    with pytest.raises(AttributeError):
        p.__getattr__("Other")


E2E = r"""
import hashlib, io, json, os, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np, nibabel as nib, torch
from segmentary.medical import backend as b
from segmentary.medical import nnunet_pretrained as p
from segmentary.medical.recipe_plan import transfer_plan

root = Path(sys.argv[1])
torch.set_num_threads(4)
dataset = "Dataset998_Tiny"
raw, pre = root / "raw" / dataset, root / "preprocessed" / dataset
for folder in (raw / "imagesTr", raw / "labelsTr", pre, root / "results"):
    folder.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(0)
for case in ("case_a", "case_b"):
    image = np.zeros((40, 40, 12), np.float32)
    image[2:-2, 2:-2, 1:-1] = rng.normal(60, 40, (36, 36, 10))
    label = np.zeros(image.shape, np.uint8)
    label[10:28, 12:30, 3:9] = 1
    label[15:22, 16:24, 4:7] = 2
    for path, values in ((raw / "imagesTr" / f"{case}_0000.nii.gz", image), (raw / "labelsTr" / f"{case}.nii.gz", label)):
        volume = nib.Nifti1Image(values, np.diag([0.8, 0.8, 2.5, 1.0]))
        volume.header.set_xyzt_units("mm")
        nib.save(volume, path)
labels = {"background": 0, "pancreas": 1, "mass": 2}
dataset_json = {"channel_names": {"0": "CT"}, "labels": labels, "numTraining": 2,
                "file_ending": ".nii.gz", "overwrite_image_reader_writer": "NibabelIO"}
(raw / "dataset.json").write_text(json.dumps(dataset_json))
(pre / "dataset.json").write_text(json.dumps(dataset_json))
(pre / "splits_final.json").write_text(json.dumps([{"train": ["case_a"], "val": ["case_b"]}]))

def arch(n, kernels, strides, blocks, features):
    return {"network_class_name": "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet",
            "_kw_requires_import": ["conv_op", "norm_op", "dropout_op", "nonlin"],
            "arch_kwargs": {"conv_bias": True, "conv_op": "torch.nn.modules.conv.Conv3d", "dropout_op": None,
                            "dropout_op_kwargs": None, "features_per_stage": features, "kernel_sizes": kernels,
                            "n_blocks_per_stage": blocks, "n_conv_per_stage_decoder": [1] * (n - 1),
                            "n_stages": n, "nonlin": "torch.nn.LeakyReLU", "nonlin_kwargs": {"inplace": True},
                            "norm_op": "torch.nn.modules.instancenorm.InstanceNorm3d",
                            "norm_op_kwargs": {"affine": True, "eps": 1e-05}, "strides": strides}}

strides = [[1, 1, 1], [1, 2, 2], [2, 2, 2], [2, 2, 2], [1, 2, 2]]
target = arch(5, [[1, 3, 3]] + [[3, 3, 3]] * 4, strides, [1, 1, 2, 2, 2], [4, 8, 16, 16, 16])
resample = "resample_data_or_seg_to_shape"
plan = {
    "dataset_name": dataset, "plans_name": "nnUNetResEncUNetLPlans", "image_reader_writer": "NibabelIO",
    "original_median_spacing_after_transp": [2.5, 0.8, 0.8], "original_median_shape_after_transp": [12, 40, 40],
    "transpose_forward": [0, 1, 2], "transpose_backward": [0, 1, 2], "label_manager": "LabelManager",
    "experiment_planner_used": "nnUNetPlannerResEncL",
    "foreground_intensity_properties_per_channel": {"0": {"max": 300.0, "mean": 80.0, "median": 80.0,
        "min": -100.0, "percentile_00_5": -90.0, "percentile_99_5": 210.0, "std": 70.0}},
    "configurations": {"3d_fullres": {
        "data_identifier": "nnUNetPlans_3d_fullres", "preprocessor_name": "DefaultPreprocessor",
        "batch_size": 2, "patch_size": [8, 32, 32], "median_image_size_in_voxels": [12, 40, 40],
        "spacing": [2.5, 0.8, 0.8], "normalization_schemes": ["CTNormalization"], "use_mask_for_norm": [False],
        "resampling_fn_data": resample, "resampling_fn_seg": resample, "resampling_fn_probabilities": resample,
        "resampling_fn_data_kwargs": {"is_seg": False, "order": 3, "order_z": 0, "force_separate_z": None},
        "resampling_fn_seg_kwargs": {"is_seg": True, "order": 1, "order_z": 0, "force_separate_z": None},
        "resampling_fn_probabilities_kwargs": {"is_seg": False, "order": 1, "order_z": 0, "force_separate_z": None},
        "batch_dice": False, "architecture": target}},
}
from nnunetv2.preprocessing.preprocessors.default_preprocessor import DefaultPreprocessor
from nnunetv2.preprocessing.sampling_locations.extract_sampling_locations import extract_sampling_locations_dataset
from nnunetv2.experiment_planning.like_nnssl import plan_like_dynamic
from nnunetv2.utilities.get_network_from_plans import get_network_from_plans
from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
from nnunetv2.imageio.nibabel_reader_writer import NibabelIO

# A 4-stage, all-3x3x3 "pretrained" ResEnc whose weights differ from any initialisation.
pretrained = arch(4, [[3, 3, 3]] * 4, strides[:4], [1, 1, 2, 2], [4, 8, 16, 16])
torch.manual_seed(123)
source = get_network_from_plans(pretrained["network_class_name"], pretrained["arch_kwargs"],
                                pretrained["_kw_requires_import"], 1, 3, allow_init=True, deep_supervision=True)
with torch.no_grad():  # perturb each tensor once, so aliased names stay one tensor
    for value in source.parameters():
        value.add_(0.01 * torch.randn_like(value))
weights = source.state_dict()
checkpoint = root / "pretrained" / "checkpoint_final.pth"
checkpoint.parent.mkdir()
torch.save({"network_weights": weights, "citations": [], "nnssl_adaptation_plan": {
    "architecture_plans": {"arch_class_name": "ResEncL"}, "pretrain_num_input_channels": 1,
    "pretrain_plan": {"configurations": {"onemmiso": {"patch_size": [16, 16, 16]}}},
    "recommended_downstream_patchsize": [16, 16, 16], "key_to_encoder": "encoder.stages",
    "key_to_stem": "encoder.stem", "keys_to_in_proj": ["encoder.stem.convs.0.conv", "encoder.stem.convs.0.all_modules.0"],
    "key_to_lpe": None}}, checkpoint)
digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()

out = {}
networks = {}
for name, options in (("resenc", None), ("hrc", {"outer_box": [3, 5, 5], "inner_box": [1, 3, 3]})):
    for stale in pre.glob("*.json"):
        if stale.name.startswith(("nnUNetResEncUNetLPlans", "ptPlans")):
            stale.unlink()
    frozen, _ = transfer_plan(plan, name, options) if name == "hrc" else (plan, None)
    (pre / "nnUNetResEncUNetLPlans.json").write_text(json.dumps(frozen))
    if not (pre / "nnUNetPlans_3d_fullres").exists():
        DefaultPreprocessor().run(998, "3d_fullres", "nnUNetResEncUNetLPlans", 1)
    extract_sampling_locations_dataset(998, "nnUNetResEncUNetLPlans", ("3d_fullres",), num_processes=1,
                                       overwrite=True, show_progress_bar=False)
    plan_like_dynamic(998, f"tiny_{name}", str(checkpoint), plans_identifier="nnUNetResEncUNetLPlans", num_processes=1)
    plans = json.loads((pre / f"ptPlans_dynamic__tiny_{name}.json").read_text())
    kept = {k: v for k, v in plans.items() if k not in ("pretrain_info", "plans_name")}
    reference = {k: v for k, v in frozen.items() if k != "plans_name"}
    assert kept == reference, "plan_like_dynamic changed the frozen plan"
    cls = getattr(p, p.TRAINER)
    # As the backend's _build_trainer does (nnU-Net's CLI injects this runtime flag).
    trainer = cls({**plans, "continue_training": False}, "3d_fullres", 0, dataset_json,
                  device=torch.device("cpu"))
    trainer.num_epochs, trainer.initial_lr = 20, 2e-3
    torch.manual_seed(0)
    trainer.initialize()
    allowed = ["decoder.", "encoder.stages.4."] + (["hrc."] if name == "hrc" else [])
    config = SimpleNamespace(init_checkpoint=str(checkpoint), init_checkpoint_sha256=digest,
                             init_allowed_missing_prefixes=allowed, initialization="pretrained")
    record = p.load_pretrained_encoder(trainer, config)
    net = trainer.network
    networks[name] = {k: v.detach().clone() for k, v in net.state_dict().items()}
    net.train()
    x = torch.randn(2, 1, 8, 32, 32)
    ds = net(x)
    scales = trainer._get_deep_supervision_scales()
    targets = [torch.randint(0, 3, (2, 1, *[int(round(s * d)) for s, d in zip(scale, (8, 32, 32))])).float() for scale in scales]
    losses = [float(trainer.train_step({"data": x, "target": targets})["loss"]) for _ in range(2)]
    trainer.set_deep_supervision_enabled(False)
    single = net(x)
    trainer.set_deep_supervision_enabled(True)
    trainer.save_checkpoint(str(Path(trainer.output_folder) / "checkpoint_final.pth"))
    model = Path(trainer.output_folder_base)
    (model / "plans.json").write_text(json.dumps(plans))
    (model / "dataset.json").write_text(json.dumps(dataset_json))
    predictor = nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=False,
                                perform_everything_on_device=False, device=torch.device("cpu"), allow_tqdm=False)
    b.initialize_predictor(predictor, model, 0, "checkpoint_final.pth", p.TRAINER)
    image, properties = NibabelIO().read_images([str(raw / "imagesTr" / "case_b_0000.nii.gz")])
    segmentation = predictor.predict_single_npy_array(image, properties, None, None, False)
    out[name] = {
        "network_class": type(net).__name__,
        "deep_supervision_outputs": [list(o.shape) for o in ds],
        "single_output": list(single.shape),
        "loss_class": type(trainer.loss).__name__,
        "losses": losses,
        "num_epochs": trainer.num_epochs, "initial_lr": trainer.initial_lr,
        "warmup": trainer.warmup_duration_whole_net,
        "scheduler": type(trainer.lr_scheduler).__name__,
        "record": {k: record[k] for k in ("copied", "adapted", "random", "parameters", "allowed_random_prefixes",
                                          "checkpoint_tensors_unused", "initialization", "external_weight_loads")},
        "prediction_shape": list(segmentation.shape), "image_shape": list(image.shape[1:]),
        "prediction_values": sorted(int(v) for v in np.unique(segmentation)),
        "predictor_network": type(predictor.network).__name__,
    }
shared = [k for k in networks["resenc"] if k in networks["hrc"]]
out["paired_equal_at_step0"] = all(torch.equal(networks["resenc"][k], networks["hrc"][k]) for k in shared)
out["hrc_only"] = sorted({k.split(".")[0] for k in networks["hrc"] if k not in networks["resenc"]})
print("E2E_RESULT " + json.dumps(out))
"""


def _run_e2e(tmp_path: Path) -> dict:
    env = dict(os.environ) | {
        "nnUNet_raw": str(tmp_path / "raw"),
        "nnUNet_preprocessed": str(tmp_path / "preprocessed"),
        "nnUNet_results": str(tmp_path / "results"),
        "nnUNet_compile": "false",
        "nnUNet_n_proc_DA": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]),
    }
    completed = subprocess.run(
        [sys.executable, "-c", E2E, str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.startswith("E2E_RESULT ")]
    assert completed.returncode == 0 and lines, completed.stdout[-3000:] + completed.stderr[-6000:]
    return json.loads(lines[-1].removeprefix("E2E_RESULT "))


@needs_master
def test_pretrained_resenc_and_hrc_train_load_and_predict_on_cpu(tmp_path):
    result = _run_e2e(tmp_path)
    for name, network in (("resenc", "ResidualEncoderUNet"), ("hrc", "HRCResEncUNet")):
        run = result[name]
        assert run["network_class"] == network and run["predictor_network"] == network
        # Deep supervision is on and its toggle works (the vendor trainer disables both).
        assert run["deep_supervision_outputs"] == [
            [2, 3, 8, 32, 32],
            [2, 3, 8, 16, 16],
            [2, 3, 4, 8, 8],
            [2, 3, 2, 4, 4],
        ]
        assert run["single_output"] == [2, 3, 8, 32, 32]
        assert run["loss_class"] == "DeepSupervisionWrapper"
        assert all(loss == loss and abs(loss) < 1e3 for loss in run["losses"])
        # Budget and learning rate come from the bound config; warm-up keeps 50/1000.
        assert (run["num_epochs"], run["initial_lr"], run["warmup"]) == (20, 2e-3, 1)
        assert run["scheduler"] == "Lin_incr_LRScheduler"
        record = run["record"]
        assert record["initialization"] == "pretrained" and record["external_weight_loads"] == 1
        adapted = {item["name"] for item in record["adapted"]}
        assert adapted == {
            "encoder.stem.convs.0.conv.weight",
            "encoder.stages.0.blocks.0.conv1.conv.weight",
            "encoder.stages.0.blocks.0.conv2.conv.weight",
        }
        assert all(item["rule"] == "mean over axes [2]" for item in record["adapted"])
        assert all(not k.startswith(("decoder.", "hrc.")) for k in record["copied"])
        assert any(k.startswith("encoder.stages.3.") for k in record["copied"])
        assert {k.split(".")[0] for k in record["random"]} <= {"decoder", "encoder", "hrc"}
        assert all(
            k.startswith(("decoder.", "hrc.", "encoder.stages.4.")) for k in record["random"]
        )
        assert any(k.startswith("encoder.stages.4.") for k in record["random"])
        assert ("hrc" in {k.split(".")[0] for k in record["random"]}) is (name == "hrc")
        assert all(k.startswith("decoder.") for k in record["checkpoint_tensors_unused"])
        assert run["prediction_shape"] == run["image_shape"]
        assert set(run["prediction_values"]) <= {0, 1, 2}
    # Same seed: the paired arms differ only by the zero-initialised HRC modules.
    assert result["paired_equal_at_step0"] is True
    assert result["hrc_only"] == ["hrc"]


REAL = r"""
import hashlib, io, json, sys
from types import SimpleNamespace
import torch
from nnunetv2.training.nnUNetTrainer.pretraining.dynamicPretrainedTrainer import DynamicPretrainedTrainer
from nnunetv2.utilities.get_network_from_plans import get_network_from_plans
from segmentary.medical import nnunet_pretrained as p
from segmentary.medical.recipe_plan import transfer_plan

checkpoint, plan_path = sys.argv[1], sys.argv[2]
torch.set_num_threads(8)
plan = json.loads(open(plan_path).read())
data = open(checkpoint, "rb").read()
digest = hashlib.sha256(data).hexdigest()
adaptation = torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)["nnssl_adaptation_plan"]
first = list(adaptation["pretrain_plan"]["configurations"])[0]
info = {"checkpoint_path": checkpoint, "key_to_encoder": adaptation["key_to_encoder"],
        "key_to_stem": adaptation["key_to_stem"], "keys_to_in_proj": adaptation["keys_to_in_proj"],
        "key_to_lpe": adaptation["key_to_lpe"], "pt_num_in_channels": adaptation["pretrain_num_input_channels"],
        "pt_used_patchsize": adaptation["pretrain_plan"]["configurations"][first]["patch_size"]}
out = {}
for name in ("resenc", "hrc"):
    frozen = transfer_plan(plan, "hrc")[0] if name == "hrc" else plan
    arch = frozen["configurations"]["3d_fullres"]["architecture"]
    torch.manual_seed(0)
    net = get_network_from_plans(arch["network_class_name"], arch["arch_kwargs"], arch["_kw_requires_import"],
                                 1, 3, allow_init=True, deep_supervision=True)
    trainer = SimpleNamespace(
        adaptation_info=info, network=net, num_input_channels=1,
        load_pretrained_weights_dynamic=DynamicPretrainedTrainer.load_pretrained_weights_dynamic,
        configuration_manager=SimpleNamespace(network_arch_init_kwargs=arch["arch_kwargs"],
                                              patch_size=frozen["configurations"]["3d_fullres"]["patch_size"]))
    allowed = ["decoder.", "encoder.stages.6."] + (["hrc."] if name == "hrc" else [])
    config = SimpleNamespace(init_checkpoint=checkpoint, init_checkpoint_sha256=digest,
                             init_allowed_missing_prefixes=allowed, initialization="pretrained")
    record = p.load_pretrained_encoder(trainer, config)
    random_encoder = sum(net.state_dict()[k].numel() for k in record["random"] if k.startswith("encoder."))
    out[name] = {"parameters": record["parameters"], "total": sum(x.numel() for x in net.parameters()),
                 "adapted": sorted(item["name"] for item in record["adapted"]),
                 "random_encoder_parameters": random_encoder,
                 "random_prefixes": sorted({".".join(k.split(".")[:3]) if k.startswith("encoder.") else k.split(".")[0]
                                            for k in record["random"]})}
print("REAL_RESULT " + json.dumps(out))
"""


@needs_master
@pytest.mark.skipif(
    not (
        os.environ.get("SEGMENTARY_NNFOUNDATION_CHECKPOINT")
        and os.environ.get("SEGMENTARY_TASK07_PLAN")
    ),
    reason="set SEGMENTARY_NNFOUNDATION_CHECKPOINT and SEGMENTARY_TASK07_PLAN",
)
def test_real_nnfoundation_checkpoint_into_task07_resenc_l_and_hrc():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            REAL,
            os.environ["SEGMENTARY_NNFOUNDATION_CHECKPOINT"],
            os.environ["SEGMENTARY_TASK07_PLAN"],
        ],
        env=dict(os.environ) | {"CUDA_VISIBLE_DEVICES": ""},
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.startswith("REAL_RESULT ")]
    assert completed.returncode == 0 and lines, completed.stderr[-6000:]
    result = json.loads(lines[-1].removeprefix("REAL_RESULT "))
    for name in ("resenc", "hrc"):
        run = result[name]
        # The P0 check: 90.24M copied, 18.7k adapted (stem and stage 0), stage 6 random.
        assert run["parameters"]["copied"] == 90240416
        assert run["parameters"]["adapted"] == 18720
        assert run["random_encoder_parameters"] == 33189120
        assert run["adapted"] == [
            "encoder.stages.0.blocks.0.conv1.conv.weight",
            "encoder.stages.0.blocks.0.conv2.conv.weight",
            "encoder.stem.convs.0.conv.weight",
        ]
        expected = ["decoder", "encoder.stages.6"] + (["hrc"] if name == "hrc" else [])
        assert run["random_prefixes"] == expected
    assert result["resenc"]["total"] == 140989042
    assert result["hrc"]["total"] > result["resenc"]["total"]
