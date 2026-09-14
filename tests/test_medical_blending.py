"""Independent overlap-add references and stable inference-only weighting."""

from __future__ import annotations

import itertools
from dataclasses import asdict

import numpy as np
import pytest
import torch
from torch import nn

from segmentary.medical.torch_blending import InferenceBlending, gaussian_weights
from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import tiled_probabilities


class LocalEdgeModel(nn.Module):
    def forward(self, x):
        axes = [torch.linspace(-1, 1, n, device=x.device).abs() for n in x.shape[2:]]
        edge = sum(torch.meshgrid(*axes, indexing="ij")) / len(axes)
        return torch.cat((x[:, :1], edge.expand_as(x[:, :1]), -x[:, :1]), dim=1)


def _reference(model, image, config, weights=None):
    """Original scalar-window accumulation; no new blending implementation used."""
    original = image.shape[1:]
    padded = np.pad(
        image,
        [(0, 0), *[(0, max(p - n, 0)) for p, n in zip(config.patch_size, original, strict=True)]],
    )
    shape = padded.shape[1:]
    total, count = np.zeros((3, *shape), np.float32), np.zeros(shape, np.float32)
    starts = []
    for n, p in zip(shape, config.patch_size, strict=True):
        last = max(0, n - p)
        starts.append(
            sorted(set(range(0, last + 1, max(1, int(p * (1 - config.overlap))))) | {last})
        )
    regions = [
        tuple(slice(x, x + p) for x, p in zip(origin, config.patch_size, strict=True))
        for origin in itertools.product(*starts)
    ]
    for offset in range(0, len(regions), config.inference_batch_size):
        batch = regions[offset : offset + config.inference_batch_size]
        inputs = np.stack([padded[(slice(None), *region)] for region in batch])
        probabilities = model(torch.from_numpy(inputs)).softmax(1).numpy()
        for region, probability in zip(batch, probabilities, strict=True):
            total[(slice(None), *region)] += (
                probability if weights is None else probability * weights[None]
            )
            count[region] += 1 if weights is None else weights
    crop = tuple(slice(0, n) for n in original)
    return (total / count[None])[(slice(None), *crop)]


@pytest.mark.parametrize(
    "shape,patch", [((7, 9), (4, 5)), ((7, 9, 8), (4, 5, 6)), ((2, 3, 2), (4, 5, 6))]
)
@pytest.mark.parametrize("batch", [1, 3])
def test_uniform_remains_bitwise_identical_to_original_algorithm(tmp_path, shape, patch, batch):
    config = TorchConfig(
        str(tmp_path),
        mode="3d" if len(shape) == 3 else "2d",
        gpu="cpu",
        patch_size=patch,
        inference_batch_size=batch,
    )
    before = asdict(config)
    image = np.random.default_rng(8).random((1, *shape), dtype=np.float32)
    model = LocalEdgeModel()
    expected = _reference(model, image, config)
    default = tiled_probabilities(model, image, config, torch.device("cpu"))
    explicit = tiled_probabilities(
        model, image, config, torch.device("cpu"), blending=InferenceBlending("uniform")
    )
    np.testing.assert_array_equal(default, expected)
    np.testing.assert_array_equal(explicit, expected)
    assert asdict(config) == before
    assert "blending" not in before


@pytest.mark.parametrize("patch", [(1, 1), (1, 4, 7), (6, 8, 10), (5, 7, 9)])
@pytest.mark.parametrize("sigma", [0.125, 0.01, 1e-300, 1.0])
def test_gaussian_is_positive_symmetric_bounded_and_immutable(patch, sigma):
    weights = gaussian_weights(patch, sigma)
    assert weights.dtype == np.float32
    assert weights.shape == patch
    assert np.isfinite(weights).all()
    assert weights.min() >= np.finfo(np.float32).eps
    assert weights.max() == 1
    assert not weights.flags.writeable
    for axis in range(len(patch)):
        np.testing.assert_array_equal(weights, np.flip(weights, axis))
    with pytest.raises(ValueError):
        weights.flat[0] = 0


def test_gaussian_formula_and_overlap_add_match_independent_manual_reference(tmp_path):
    patch = (4, 5)
    x, y = np.meshgrid(np.arange(4), np.arange(5), indexing="ij")
    weights = np.exp(-0.5 * (((x - 1.5) / (4 / 8)) ** 2 + ((y - 2) / (5 / 8)) ** 2))
    weights /= weights.max()
    weights = np.maximum(weights, np.finfo(np.float32).eps).astype(np.float32)
    np.testing.assert_allclose(gaussian_weights(patch), weights, rtol=1e-7)
    config = TorchConfig(
        str(tmp_path), gpu="cpu", mode="2d", patch_size=patch, inference_batch_size=3
    )
    image = np.random.default_rng(5).random((1, 7, 9), dtype=np.float32)
    model = LocalEdgeModel()
    actual = tiled_probabilities(
        model, image, config, torch.device("cpu"), blending=InferenceBlending("gaussian")
    )
    np.testing.assert_allclose(
        actual, _reference(model, image, config, weights), rtol=1e-6, atol=1e-7
    )
    np.testing.assert_allclose(actual.sum(axis=0), 1.0, atol=2e-7)
    uniform = tiled_probabilities(model, image, config, torch.device("cpu"))
    assert not np.allclose(actual, uniform)


@pytest.mark.parametrize("sigma", [0, -1, True, float("nan"), float("inf"), "0.125"])
def test_invalid_sigma_rejected(sigma):
    with pytest.raises(ValueError, match="finite and positive"):
        InferenceBlending("gaussian", sigma)


@pytest.mark.parametrize("patch", [(1,), (1, 2, 3, 4), (0, 2), (True, 2), (1.5, 2)])
def test_invalid_patch_rejected(patch):
    with pytest.raises(ValueError, match="patch_size"):
        gaussian_weights(patch)


def test_invalid_mode_rejected():
    with pytest.raises(ValueError, match="uniform or gaussian"):
        InferenceBlending("automatic")


@pytest.mark.parametrize("mode,context", [("3d", 1), ("2d", 1), ("2.5d", 3)])
def test_gaussian_flows_through_native_prediction_and_pipeline_without_label_access(
    tmp_path, mode, context
):
    import contextlib

    import nibabel as nib

    from segmentary.medical.torch_data import iter_predictions, predict_case

    values = np.arange(120, dtype=np.float32).reshape(5, 6, 4)
    affine = np.diag([1.5, 1.0, 2.0, 1.0])
    image = nib.Nifti1Image(values, affine)
    image.header.set_xyzt_units("mm")
    image.set_qform(affine, 1)
    image.set_sform(affine, 1)
    path = tmp_path / "image.nii.gz"
    nib.save(image, path)
    case = {"case_id": "tiny", "image": str(path), "label": "/forbidden/test_or_train_label"}
    config = TorchConfig(
        str(tmp_path / "run"),
        gpu="cpu",
        mode=mode,
        context_slices=context,
        patch_size=(3, 4, 5) if mode == "3d" else (4, 5),
        workers=2,
        hu_window=(0, 120),
        spacing_mm=(1.5, 1, 2),
        inference_batch_size=3,
    )
    model = LocalEdgeModel().train()
    blend = InferenceBlending("gaussian")
    expected = predict_case(model, case, config, torch.device("cpu"), blending=blend)
    with contextlib.closing(
        iter_predictions(model, [case], config, torch.device("cpu"), blending=blend)
    ) as results:
        actual = next(results)
    assert actual.error is None
    assert expected.shape == values.shape
    np.testing.assert_array_equal(actual.prediction, expected)
    assert model.training
