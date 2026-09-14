"""New center distributions, paired augmentation, and opt-in recipe contracts."""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from segmentary.medical.torch_augmentation import augment_patch
from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import sample_patch
from segmentary.medical.torch_sampling import _background_center


def _data():
    label = np.zeros((10, 10, 10), dtype=np.uint8)
    label.flat[800:950] = 1
    label.flat[950:] = 2
    return {
        "image": label.astype(np.float32) / 2,
        "label": label,
        "foreground_coordinates": {c: np.argwhere(label == c) for c in (1, 2)},
    }


def _config(tmp_path, **kwargs):
    return TorchConfig(str(tmp_path), gpu="cpu", patch_size=(1, 1, 1), augment=False, **kwargs)


@pytest.mark.parametrize(
    "options",
    [
        {"foreground_probability": None},
        {"center_probabilities": (0.25, 0.25, 0.5)},
        {"class_center_weights": (1, 1, 5)},
        {"foreground_probability": None, "center_probabilities": (0, 0, 0)},
        {"foreground_probability": None, "center_probabilities": (1, 1, 1)},
        {"foreground_probability": None, "center_probabilities": (-0.25, 0.75, 0.5)},
        {"foreground_probability": None, "class_center_weights": (0, 0, 0)},
        {"foreground_probability": None, "class_center_weights": (1, float("inf"), 5)},
        {"foreground_probability": None, "class_center_weights": (1, float("nan"), 5)},
        {"foreground_probability": None, "class_center_weights": (1, True, 5)},
        {"foreground_probability": None, "class_center_weights": (1, 5)},
        {
            "foreground_probability": None,
            "center_probabilities": (0.25, 0.25, 0.5),
            "class_center_weights": (1, 1, 5),
        },
        {"rotation_probability": -0.1},
        {"rotation_probability": True},
        {"rotation_probability": 1.1},
        {"rotation_probability": 0.25, "augment": False},
        {"rotation_probability": 0.25, "spacing_mm": (0.75, 1.5, 2.5)},
        {"rotation_degrees": (-181, 10)},
        {"rotation_degrees": (15, -15)},
        {"rotation_degrees": (15,)},
        {"rotation_degrees": None},
        {"rotation_padding_value": -0.1},
        {"rotation_padding_value": 1.1},
        {"intensity_scale_probability": 1.1},
        {"intensity_scale_probability": 0.5, "augment": False},
        {"intensity_scale_range": (1, 0.9)},
        {"intensity_scale_range": (0, 1)},
        {"intensity_scale_range": (0.9, float("nan"))},
    ],
)
def test_invalid_opt_in_recipes_fail_before_training(tmp_path, options):
    with pytest.raises(ValueError):
        TorchConfig(str(tmp_path), **options)


def test_recipe_serialization_preserves_declared_values_and_disabled_defaults(tmp_path):
    config = TorchConfig(str(tmp_path))
    assert config.foreground_probability == 0.5
    assert config.center_probabilities is config.class_center_weights is None
    assert config.rotation_probability == config.intensity_scale_probability == 0
    assert TorchConfig(**json.loads(json.dumps(dataclasses.asdict(config)))) == config
    weighted = dataclasses.replace(
        config, foreground_probability=None, class_center_weights=[1, 1, 5]
    )
    assert weighted.class_center_weights == (1, 1, 5)
    assert TorchConfig(**json.loads(json.dumps(dataclasses.asdict(weighted)))) == weighted


@pytest.mark.parametrize(
    "options,expected",
    [
        ({"center_probabilities": (0.25, 0.25, 0.5)}, (0.2, 0.2875, 0.5125)),
        ({"class_center_weights": (1, 1, 1)}, (1 / 3, 1 / 3, 1 / 3)),
        ({"class_center_weights": (1, 1, 5)}, (1 / 7, 1 / 7, 5 / 7)),
    ],
)
def test_observed_center_distribution_distinguishes_uniform_from_background(
    tmp_path, options, expected
):
    data = _data()
    config = _config(tmp_path, foreground_probability=None, **options)
    rng = np.random.default_rng(501)
    counts = np.zeros(3, dtype=int)
    for _ in range(9000):
        _, target = sample_patch(data, config, rng)
        counts[int(target.item())] += 1
    np.testing.assert_allclose(counts / counts.sum(), expected, atol=0.015, rtol=0)


def test_uniform_volume_branch_can_land_on_mass_and_is_not_background_only(tmp_path):
    data = _data()
    config = _config(tmp_path, foreground_probability=None, center_probabilities=(1, 0, 0))
    rng = np.random.default_rng(0)
    encountered = set()
    for _ in range(100):
        diagnostic = {}
        _, target = sample_patch(data, config, rng, diagnostics=diagnostic)
        assert diagnostic["selected_center_class"] is None
        assert diagnostic["selected_center_branch"] == "uniform_volume"
        encountered.add(target.item())
    assert encountered == {0, 1, 2}


@pytest.mark.parametrize("mode", ["center_probabilities", "class_center_weights"])
def test_missing_weighted_classes_renormalize_and_no_remaining_class_falls_back(tmp_path, mode):
    data = _data()
    data["label"][data["label"] == 2] = 0
    data["foreground_coordinates"][2] = np.empty((0, 3), dtype=int)
    config = _config(tmp_path, foreground_probability=None, **{mode: (0, 0.3, 0.7)})
    rng = np.random.default_rng(9)
    for _ in range(10):
        diagnostic = {}
        _, target = sample_patch(data, config, rng, diagnostics=diagnostic)
        assert target.item() == 1
        assert diagnostic["missing_center_classes"] == [2]
        assert diagnostic["effective_center_probabilities"] == [0, 1, 0]
        assert not diagnostic["center_fallback"]
    config = dataclasses.replace(config, **{mode: (0, 0, 1)})
    plain_rng, audited_rng = np.random.default_rng(91), np.random.default_rng(91)
    plain = sample_patch(data, config, plain_rng)
    diagnostic = {}
    audited = sample_patch(data, config, audited_rng, diagnostics=diagnostic)
    assert diagnostic["center_fallback"]
    assert diagnostic["selected_center_branch"] == "uniform_volume"
    assert diagnostic["selected_center_class"] is None
    assert plain_rng.bit_generator.state == audited_rng.bit_generator.state
    for a, b in zip(plain, audited, strict=True):
        np.testing.assert_array_equal(a, b)


def test_exact_background_hot_path_never_scans_full_cached_volume(tmp_path, monkeypatch):
    data = _data()
    config = _config(tmp_path, foreground_probability=None, class_center_weights=(1, 0, 0))

    def forbidden(*args, **kwargs):
        raise AssertionError("Cached center sampling must not scan the full volume")

    monkeypatch.setattr(np, "argwhere", forbidden)
    monkeypatch.setattr(np, "any", forbidden)
    rng = np.random.default_rng(20)
    for _ in range(50):
        _, target = sample_patch(data, config, rng)
        assert target.item() == 0
    assert "_center_background_exclusions" not in data


def test_bounded_background_fallback_selects_each_background_rank_without_bias():
    label = np.ones((2, 3, 5), dtype=np.uint8)
    allowed = [0, 7, 8, 17, 29]
    label.flat[allowed] = 0
    label.flat[12:16] = 2
    data = {"label": label}
    coordinates = {c: np.argwhere(label == c) for c in (1, 2)}

    class RejectThenRank:
        def __init__(self, rank):
            self.rank = rank
            self.calls = 0

        def integers(self, high):
            self.calls += 1
            if self.calls <= 32:
                assert high == label.size
                return 1  # Deliberately reject a foreground location.
            assert high == len(allowed)
            return self.rank

    for rank, expected in enumerate(allowed):
        rng = RejectThenRank(rank)
        center = _background_center(data, coordinates, len(allowed), rng)
        assert np.ravel_multi_index(center, label.shape) == expected
        assert rng.calls == 33
    assert len(data["_center_background_exclusions"]) == label.size - len(allowed)


@pytest.mark.parametrize("mode,context", [("2d", 1), ("2.5d", 5), ("3d", 1)])
def test_diagnostics_preserve_legacy_outputs_rng_and_record_padding(tmp_path, mode, context):
    data = _data()
    config = TorchConfig(
        str(tmp_path),
        gpu="cpu",
        mode=mode,
        context_slices=context,
        patch_size=(12, 13, 14) if mode == "3d" else (13, 14),
    )
    for seed in range(20):
        plain_rng, audited_rng = np.random.default_rng(seed), np.random.default_rng(seed)
        plain = sample_patch(data, config, plain_rng)
        diagnostic = {}
        audited = sample_patch(data, config, audited_rng, diagnostics=diagnostic)
        for a, b in zip(plain, audited, strict=True):
            np.testing.assert_array_equal(a, b)
        assert plain_rng.bit_generator.state == audited_rng.bit_generator.state
        expected_real_voxels = 1000 if mode == "3d" else 100
        assert (
            diagnostic["crop_padding_voxels"] == np.prod(config.patch_size) - expected_real_voxels
        )
        assert sum(diagnostic["final_label_voxels"].values()) == np.prod(config.patch_size)
        assert diagnostic["final_label_voxels"] == diagnostic["label_voxels_before_augmentation"]


@pytest.mark.parametrize("shape", [(3, 7, 7), (1, 3, 7, 7)])
def test_quarter_turn_keeps_all_context_slices_aligned_and_masks_discrete(tmp_path, shape):
    label = np.zeros(shape[1:], dtype=np.uint8)
    label[..., 1:3, 2:5] = 1
    label[..., 4, 5] = 2
    image = np.broadcast_to(label / 2, shape).astype(np.float32).copy()
    config = TorchConfig(str(tmp_path), rotation_probability=1, rotation_degrees=(90, 90))
    diagnostic = {}
    actual, target = augment_patch(image, label, config, np.random.default_rng(0), diagnostic)
    np.testing.assert_array_equal(actual, np.rot90(image, axes=(-2, -1)))
    np.testing.assert_array_equal(target, np.rot90(label, axes=(-2, -1)))
    assert set(np.unique(target)) == {0, 1, 2}
    assert actual.shape == image.shape and target.shape == label.shape
    assert diagnostic["rotation_angle_degrees"] == 90
    assert diagnostic["rotation_applied"]


def test_oblique_rotation_uses_constant_padding_and_linear_intensity_not_label_interpolation(
    tmp_path,
):
    label = np.zeros((9, 9), dtype=np.uint8)
    label[:, 4:] = 2
    image = np.broadcast_to(label[None] / 2, (5, 9, 9)).astype(np.float32).copy()
    config = TorchConfig(
        str(tmp_path),
        rotation_probability=1,
        rotation_degrees=(30, 30),
        rotation_padding_value=0.25,
    )
    actual, target = augment_patch(image, label, config, np.random.default_rng(0), {})
    assert np.all(actual[:, 0, 0] == 0.25)
    assert target[0, 0] == 0
    assert np.any((actual != 0) & (actual != 0.25) & (actual != 1))
    assert set(np.unique(target)) == {0, 2}
    for channel in actual[1:]:
        np.testing.assert_array_equal(channel, actual[0])
    np.testing.assert_array_equal(image[0], label / 2)  # Source arrays were not changed.


def test_intensity_scale_uses_shared_factor_without_clipping_or_changing_labels(tmp_path):
    image = np.linspace(0, 1, 75, dtype=np.float32).reshape(3, 5, 5)
    label = np.zeros((5, 5), dtype=np.uint8)
    label[1:4, 2] = 2
    config = TorchConfig(
        str(tmp_path), intensity_scale_probability=1, intensity_scale_range=(1.1, 1.1)
    )
    diagnostic = {}
    actual, target = augment_patch(image, label, config, np.random.default_rng(8), diagnostic)
    np.testing.assert_array_equal(actual, image * np.float32(1.1))
    np.testing.assert_array_equal(target, label)
    assert actual.max() > 1
    assert image.max() == 1
    assert diagnostic["intensity_scale_factor"] == 1.1
    assert diagnostic["intensity_scale_applied"] and not diagnostic["rotation_applied"]


def test_disabled_augmentations_do_not_advance_generator_or_copy_inputs(tmp_path):
    image = np.ones((3, 5, 5), dtype=np.float32)
    label = np.ones((5, 5), dtype=np.uint8)
    rng = np.random.default_rng(90)
    state = json.dumps(rng.bit_generator.state, sort_keys=True)
    actual, target = augment_patch(image, label, TorchConfig(str(tmp_path)), rng, {})
    assert actual is image and target is label
    assert json.dumps(rng.bit_generator.state, sort_keys=True) == state


@pytest.mark.parametrize("mode,context", [("2d", 1), ("2.5d", 5), ("3d", 1)])
def test_augmented_sampler_resumes_exactly_and_diagnostics_leave_its_rng_unchanged(
    tmp_path, mode, context
):
    data = _data()
    config = TorchConfig(
        str(tmp_path),
        gpu="cpu",
        mode=mode,
        context_slices=context,
        patch_size=(7, 8, 9) if mode == "3d" else (8, 9),
        foreground_probability=None,
        class_center_weights=(1, 1, 5),
        rotation_probability=0.25,
        intensity_scale_probability=0.5,
    )
    rng = np.random.default_rng(13)
    for _ in range(7):
        sample_patch(data, config, rng)
    saved = json.loads(json.dumps(rng.bit_generator.state))
    expected = [sample_patch(data, config, rng) for _ in range(20)]
    resumed = np.random.default_rng()
    resumed.bit_generator.state = saved
    for image, label in expected:
        diagnostic = {}
        actual, target = sample_patch(data, config, resumed, diagnostics=diagnostic)
        np.testing.assert_array_equal(actual, image)
        np.testing.assert_array_equal(target, label)
        assert actual.flags.c_contiguous and target.flags.c_contiguous
        assert actual.dtype == np.float32 and target.dtype == np.int64
        assert -15 <= diagnostic["rotation_angle_degrees"] <= 15
        assert 0.9 <= diagnostic["intensity_scale_factor"] <= 1.1
    assert rng.bit_generator.state == resumed.bit_generator.state


def test_full_sampler_preserves_same_scan_context_after_rotation_and_scaling(tmp_path):
    shape = (7, 9, 9)
    image = np.broadcast_to(np.arange(7, dtype=np.float32)[:, None, None] / 10, shape).copy()
    label = np.zeros(shape, dtype=np.uint8)
    label[3, 4, 4] = 2
    image.flags.writeable = label.flags.writeable = False
    config = TorchConfig(
        str(tmp_path),
        gpu="cpu",
        mode="2.5d",
        context_slices=5,
        patch_size=(9, 9),
        foreground_probability=None,
        center_probabilities=(0, 0, 1),
        rotation_probability=1,
        rotation_degrees=(13, 13),
        intensity_scale_probability=1,
        intensity_scale_range=(1.05, 1.05),
    )
    patch, target = sample_patch({"image": image, "label": label}, config, np.random.default_rng(1))
    np.testing.assert_allclose(patch[:, 4, 4], np.arange(1, 6) / 10 * 1.05, atol=1e-7)
    assert target[4, 4] == 2
    assert patch.shape == (5, 9, 9) and target.shape == (9, 9)
