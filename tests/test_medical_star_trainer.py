"""STAR-C trainer pieces against the real nnU-Net 2.8.1 pipeline (backend interpreter).

- the recorded augmentation frame equals what nnU-Net's own spatial and mirror
  transforms do (coordinate ramps pushed through them), in dummy-2D and 3D mode;
- ``StarCDataLoader`` returns exactly the official loader's data and targets,
  plus STAR-C targets that follow the augmented patch;
- the two-pass predictor's tile instances mirror correctly;
- an end-to-end CPU smoke (synthetic data, offline targets, training, two-pass
  inference) through ``scripts/starc_cpu_smoke.py`` in a fresh process.
"""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

pytest.importorskip("nnunetv2")
pytest.importorskip("batchgeneratorsv2")
pytest.importorskip("blosc2")

from batchgeneratorsv2.transforms.spatial.mirroring import MirrorTransform
from batchgeneratorsv2.transforms.spatial.spatial import SpatialTransform
from batchgeneratorsv2.transforms.utils.compose import ComposeTransforms
from batchgeneratorsv2.transforms.utils.pseudo2d import (
    Convert2DTo3DTransform,
    Convert3DTo2DTransform,
)
from batchgeneratorsv2.transforms.utils.random import RandomTransform
from nnunetv2.training.data_augmentation.compute_initial_patch_size import get_patch_size
from nnunetv2.training.dataloading.data_loader import nnUNetDataLoader
from nnunetv2.training.dataloading.nnunet_dataset import nnUNetDatasetBlosc2
from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer
from nnunetv2.utilities.label_handling.label_handling import LabelManager

from segmentary.medical import star_completion as sc
from segmentary.medical.nnunet_star_trainer import (
    FRAMES_KEY,
    RecordingMirrorTransform,
    RecordingSpatialTransform,
    StarCDataLoader,
    StarCPredictor,
    enable_frame_recording,
    nnUNetTrainerStarC,
    target_rng,
)

ROOT = Path(__file__).resolve().parents[1]
SPACING = (2.5, 0.8125, 0.8125)
GEOMETRIC = (Convert3DTo2DTransform, Convert2DTo3DTransform, SpatialTransform, MirrorTransform)


@pytest.fixture(autouse=True)
def bounded_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(4)
    yield
    torch.set_num_threads(previous)


def _augmentation(patch, *, dummy_2d, deep_supervision=None):
    rotation = (-math.pi, math.pi) if dummy_2d else (-math.pi / 6, math.pi / 6)
    initial = get_patch_size(patch, rotation, rotation, rotation, (0.85, 1.25))
    if dummy_2d:
        initial[0] = patch[0]
    transforms = nnUNetTrainer.get_training_transforms(
        patch,
        rotation,
        deep_supervision,
        (0, 1, 2),
        dummy_2d,
        use_mask_for_norm=[False],
        is_cascaded=False,
        foreground_labels=[1, 2],
        regions=None,
        ignore_label=None,
    )
    return [int(v) for v in initial], transforms


@pytest.mark.parametrize("dummy_2d", [True, False])
@pytest.mark.parametrize("forced", [True, False])
def test_recorded_frame_equals_nnunet_spatial_and_mirror_transforms(dummy_2d, forced):
    patch = (16, 96, 80) if dummy_2d else (40, 48, 48)
    initial, transforms = _augmentation(patch, dummy_2d=dummy_2d)
    geometric = [t for t in transforms.transforms if isinstance(t, GEOMETRIC)]
    for transform in geometric:
        if forced and isinstance(transform, SpatialTransform):
            transform.p_rotation = transform.p_scaling = 1.0
    compose = enable_frame_recording(ComposeTransforms(geometric))
    assert any(isinstance(t, RecordingSpatialTransform) for t in compose.transforms)
    assert any(isinstance(t, RecordingMirrorTransform) for t in compose.transforms)
    ramps = np.stack(np.meshgrid(*[np.arange(n) for n in initial], indexing="ij")).astype(
        np.float32
    )
    grid = np.stack(np.meshgrid(*[np.arange(n) for n in patch], indexing="ij"), -1).reshape(-1, 3)
    checked = 0
    for trial in range(10):
        torch.manual_seed(trial)
        np.random.seed(trial)
        records: list = []
        out = compose(
            image=torch.from_numpy(ramps.copy()),
            segmentation=torch.zeros((1, *initial), dtype=torch.int16),
            starc_frames=records,
        )
        frame = sc.compose_patch_frame([0, 0, 0], records)
        mapped = frame.to_volume(grid)
        inside = np.all((mapped >= 0) & (mapped <= np.asarray(initial) - 1), axis=1)
        assert inside.mean() > 0.5
        image = out["image"].numpy().reshape(3, -1).T
        error = np.abs(image[inside] - mapped[inside]).max()
        assert error < 0.02, (trial, records)
        checked += int(inside.sum())
    assert checked > 0


def test_frame_recording_refuses_unrecordable_pipelines():
    with pytest.raises(ValueError, match="elastic"):
        enable_frame_recording(
            ComposeTransforms([SpatialTransform((8, 8, 8), 0, False, p_elastic_deform=0.1)])
        )
    with pytest.raises(ValueError, match="nested"):
        enable_frame_recording(
            ComposeTransforms([RandomTransform(MirrorTransform((0, 1, 2)), 0.5)])
        )


def _ellipsoid(shape, centre, axes_mm):
    grids = np.meshgrid(
        *[np.arange(n) * s for n, s in zip(shape, SPACING, strict=True)], indexing="ij"
    )
    return (
        sum(
            ((g - c * s) / a) ** 2
            for g, c, s, a in zip(grids, centre, SPACING, axes_mm, strict=True)
        )
        <= 1
    )


def _dataset(folder: Path, cases: int = 3) -> list[str]:
    folder.mkdir(parents=True)
    rng = np.random.default_rng(0)
    shape = (30, 150, 130)
    names = []
    for index in range(cases):
        segmentation = np.zeros(shape, np.int8)
        segmentation[_ellipsoid(shape, (15, 75, 65), (40, 30, 40))] = 1
        for centre, radius in (((14, 70, 60), 7.0), ((18, 95, 85), 5.0))[: 1 + index % 2]:
            segmentation[_ellipsoid(shape, centre, (radius,) * 3)] = 2
        image = rng.normal(0, 0.3, shape).astype(np.float32) + segmentation
        locations = {}
        for label in (1, 2):
            points = np.argwhere(segmentation == label)
            locations[label] = np.c_[np.zeros(len(points), int), points]
        nnUNetDatasetBlosc2.save_case(
            image[None],
            segmentation[None],
            {"spacing": list(SPACING), "class_locations": locations},
            str(folder / f"case_{index}"),
            chunks=(1, *shape),
            blocks=(1, *shape),
        )
        table = sc.compute_case_targets(segmentation, SPACING, [2], sc.star_geometry(96))
        sc.save_case_targets(folder.parent / "targets" / f"case_{index}.npz", table)
        names.append(f"case_{index}")
    return names


def test_star_loader_matches_the_official_loader_and_targets_follow_the_patch(tmp_path):
    (tmp_path / "targets").mkdir()
    _dataset(tmp_path / "data")
    patch = (16, 96, 64)
    initial, transforms = _augmentation(
        patch, dummy_2d=True, deep_supervision=[[1, 1, 1], [1, 0.5, 0.5]]
    )
    labels = LabelManager({"background": 0, "pancreas": 1, "mass": 2}, regions_class_order=None)
    dataset = nnUNetDatasetBlosc2(str(tmp_path / "data"))
    builder = sc.StarTargetBuilder(
        tmp_path / "targets",
        spacing=SPACING,
        rays=96,
        patch_size=patch,
        cell_stride=(2, 4, 4),
        ray_samples=32,
        max_gt_instances=4,
        core_fraction=0.3,
        sigma_min_mm=3.0,
        sigma_fraction=0.25,
        min_ray_mm=0.5,
        max_ray_mm=90.0,
    )
    official = nnUNetDataLoader(
        dataset, 2, initial, patch, labels, 0.5, transforms=copy.deepcopy(transforms)
    )
    star = StarCDataLoader(
        dataset,
        2,
        initial,
        patch,
        labels,
        0.5,
        transforms=enable_frame_recording(copy.deepcopy(transforms)),
        star_builder=builder,
    )
    centres_checked = 0
    for trial in range(8):
        batches = []
        for loader in (official, star):
            loader.rs = np.random.RandomState(trial)
            np.random.seed(trial)
            torch.manual_seed(trial)
            batches.append(loader.generate_train_batch())
        a, b = batches
        assert list(a["keys"]) == list(b["keys"])
        assert torch.equal(a["data"], b["data"])
        assert all(torch.equal(x, y) for x, y in zip(a["target"], b["target"], strict=True))
        targets = b["starc"]
        assert targets["heatmap"].shape == (2, 1, 8, 24, 16)
        assert targets["ray_targets"].shape == (2, 36, 96)
        for sample in range(2):
            valid = targets["centre_valid"][sample]
            assert (targets["heatmap"][sample] == 1).sum() == valid.sum()
            for centre in targets["centres"][sample][valid]:
                index = tuple(
                    np.clip(np.rint(centre.numpy()).astype(int), 0, np.asarray(patch) - 1)
                )
                # Inner centres are deep inside the lesion, so augmentation keeps them mass.
                assert b["target"][0][(sample, 0, *index)] == 2
                centres_checked += 1
            mask = targets["ray_mask"][sample]
            assert torch.isfinite(targets["ray_targets"][sample][mask]).all()
    assert centres_checked > 4


def test_predictor_tile_instances_follow_mirroring():
    options = sc.network_options(sc.validate_starc_options(None))
    network = SimpleNamespace(starc=object(), starc_options=options, starc_spacing=list(SPACING))
    predictor = StarCPredictor(device=torch.device("cpu"), allow_tqdm=False)
    predictor.network = network
    radii = np.log(np.full(96, 6.0))
    predictor.star_case_detections = [
        sc.CaseDetection(np.array([20.0, 100.0, 90.0]), radii, 0.9, 1.0),
        sc.CaseDetection(np.array([20.0, 400.0, 90.0]), radii, 0.8, 1.0),  # far outside
    ]
    origin = np.array([10.0, 60.0, 50.0])
    plain = predictor.tile_instances(origin, (32, 128, 128), ())
    assert plain.centres.shape == (1, 1, 3)
    assert torch.allclose(plain.centres[0, 0], torch.tensor([10.0, 40.0, 40.0]))
    assert torch.equal(plain.transforms[0, 0], torch.eye(3))
    flipped = predictor.tile_instances(origin, (32, 128, 128), (1, 2))
    assert torch.allclose(flipped.centres[0, 0], torch.tensor([10.0, 87.0, 87.0]))
    assert torch.equal(flipped.transforms[0, 0], torch.diag(torch.tensor([1.0, -1.0, -1.0])))
    predictor.star_case_detections = []
    empty = predictor.tile_instances(origin, (32, 128, 128), ())
    assert empty.centres.shape == (1, 0, 3) and empty.log_radii.shape == (1, 0, 96)


TASK07_PLAN = {
    "dataset_name": "Dataset707_Pancreas",
    "plans_name": "nnUNetResEncUNetLPlans",
    "original_median_spacing_after_transp": [2.5, 0.8125, 0.8125],
    "original_median_shape_after_transp": [93, 512, 512],
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
            "std": 71.16236877441406,
        }
    },
    "configurations": {
        "3d_fullres": {
            "data_identifier": "nnUNetPlans_3d_fullres",
            "preprocessor_name": "DefaultPreprocessor",
            "batch_size": 2,
            "patch_size": [56, 320, 256],
            "median_image_size_in_voxels": [95.0, 512.0, 512.0],
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
            "batch_dice": False,
            "architecture": {
                "network_class_name": "dynamic_network_architectures.architectures.unet."
                "ResidualEncoderUNet",
                "arch_kwargs": {
                    "n_stages": 7,
                    "features_per_stage": [32, 64, 128, 256, 320, 320, 320],
                    "conv_op": "torch.nn.modules.conv.Conv3d",
                    "kernel_sizes": [[1, 3, 3]] + [[3, 3, 3]] * 6,
                    "strides": [
                        [1, 1, 1],
                        [1, 2, 2],
                        [2, 2, 2],
                        [2, 2, 2],
                        [2, 2, 2],
                        [1, 2, 2],
                        [1, 2, 2],
                    ],
                    "n_blocks_per_stage": [1, 3, 4, 6, 6, 6, 6],
                    "n_conv_per_stage_decoder": [1, 1, 1, 1, 1, 1],
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
        }
    },
}


def test_cpu_smoke_trains_and_predicts_end_to_end(tmp_path):
    plan_path = os.environ.get("SEGMENTARY_TASK07_PLAN")
    if not plan_path:
        plan_path = str(tmp_path / "plan.json")
        Path(plan_path).write_text(json.dumps(TASK07_PLAN))
    output = tmp_path / "smoke.json"
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "starc_cpu_smoke.py"),
            "--plan",
            plan_path,
            "--workdir",
            str(tmp_path / "work"),
            "--patch",
            "16",
            "128",
            "128",
            "--narrow",
            "--steps",
            "2",
            "--cases",
            "3",
            "--threads",
            "4",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    record = json.loads(output.read_text())
    assert record["ok"] and record["checkpoint_final"]
    assert record["star_log"] and record["two_pass"]["case_detections"] > 0


# ---------------------------------------------------------------------------
# Review fixes
# ---------------------------------------------------------------------------


def test_target_sampler_follows_the_legacy_position_without_advancing_it():
    legacy = np.random.RandomState(0)
    legacy.random_sample(1)  # a fresh state regenerates its key array on the first draw
    first = legacy.get_state()
    legacy.random_sample(200)  # fewer than 624 words: the key array is unchanged
    later = legacy.get_state()
    assert np.array_equal(first[1], later[1]) and first[2] != later[2]
    draws = [target_rng(state).choice(10_000, size=16, replace=False) for state in (first, later)]
    assert not np.array_equal(*draws)
    assert np.array_equal(target_rng(first).choice(10_000, 16, False), draws[0])
    np.random.seed(5)
    before = np.random.get_state()
    target_rng(np.random.get_state()).random(4)
    assert np.array_equal(np.random.get_state()[1], before[1])
    assert np.random.get_state()[2] == before[2]


def test_star_loader_refuses_a_transform_that_drops_the_frame_record(tmp_path):
    (tmp_path / "targets").mkdir()
    _dataset(tmp_path / "data", cases=1)
    patch = (16, 96, 64)
    initial, _ = _augmentation(patch, dummy_2d=True, deep_supervision=None)
    labels = LabelManager({"background": 0, "pancreas": 1, "mass": 2}, regions_class_order=None)
    builder = sc.StarTargetBuilder(
        tmp_path / "targets",
        spacing=SPACING,
        rays=96,
        patch_size=patch,
        cell_stride=(2, 4, 4),
        ray_samples=8,
        max_gt_instances=4,
        core_fraction=0.3,
        sigma_min_mm=3.0,
        sigma_fraction=0.25,
        min_ray_mm=0.5,
        max_ray_mm=90.0,
    )

    def dropping(**data):
        return {key: value for key, value in data.items() if key != FRAMES_KEY}

    loader = StarCDataLoader(
        nnUNetDatasetBlosc2(str(tmp_path / "data")),
        1,
        initial,
        patch,
        labels,
        0.5,
        transforms=dropping,
        star_builder=builder,
    )
    with pytest.raises(ValueError, match="dropped the STAR-C frame record"):
        loader.generate_train_batch()


def test_teacher_forcing_renders_at_most_max_instances_largest_first():
    options = sc.network_options(sc.validate_starc_options({"max_instances": 3}))
    network = SimpleNamespace(starc_options=options, starc_spacing=list(SPACING))
    trainer = SimpleNamespace(
        star_network=lambda: network,
        star_options=sc.training_options(
            sc.validate_starc_options({"teacher_jitter_mm": 0.0, "max_gt_instances": 16})
        ),
    )
    centres = torch.arange(2 * 16 * 3, dtype=torch.float32).reshape(2, 16, 3)
    valid = torch.zeros(2, 16, dtype=torch.bool)
    valid[0, :10] = True
    valid[1, :2] = True
    instances = nnUNetTrainerStarC.teacher_instances(
        trainer, {"centres": centres, "centre_valid": valid}
    )
    assert instances.centres.shape == (2, 3, 3) and torch.equal(instances.centres, centres[:, :3])
    assert instances.valid.tolist() == [[True, True, True], [True, True, False]]


def test_trainer_has_no_default_target_folder():
    trainer = SimpleNamespace(star_targets_dir=None)
    with pytest.raises(ValueError, match="not configured"):
        nnUNetTrainerStarC.star_targets_folder(trainer)


def test_aux_only_inference_takes_the_single_official_pass(monkeypatch):
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

    calls = []

    def official(self, data, slicers, do_on_device=True):
        calls.append(len(slicers))
        return "official"

    monkeypatch.setattr(nnUNetPredictor, "_internal_predict_sliding_window_return_logits", official)
    predictor = StarCPredictor(device=torch.device("cpu"), allow_tqdm=False)
    predictor.network = SimpleNamespace(starc=SimpleNamespace(fusion="aux_only"))
    predictor.detect_case_instances = lambda *a: pytest.fail("aux_only ran a detection pass")
    result = predictor._internal_predict_sliding_window_return_logits(torch.zeros(1), [1, 2])
    assert result == "official" and calls == [2] and predictor.star_case_detections == []
