"""Parallel native interpolation preserves the exact serial probability field."""

from __future__ import annotations

import numpy as np
import pytest

from segmentary.medical.torch_geometry import native_probabilities

nib = pytest.importorskip("nibabel")


@pytest.mark.parametrize("workers", [1, 2, 3, 8])
@pytest.mark.parametrize("transform", ["anisotropic", "flipped_permuted"])
def test_parallel_backprojection_is_bitwise_serial_on_native_grid(workers, transform):
    from nibabel.processing import resample_from_to

    probabilities = np.random.default_rng(42).uniform(size=(3, 5, 7, 9)).astype(np.float32)
    probabilities /= probabilities.sum(axis=0, keepdims=True)
    processed_affine = np.diag([1.5, 2.0, 3.0, 1.0])
    native_affine = (
        np.diag([0.75, 1.0, 1.5, 1.0])
        if transform == "anisotropic"
        else np.array([[0, -1.0, 0, 12], [0, 0, 1.5, 0], [-0.75, 0, 0, 12], [0, 0, 0, 1]])
    )
    shape = (17, 13, 9)
    before = probabilities.copy()
    expected = [
        np.asarray(
            resample_from_to(
                nib.Nifti1Image(channel.transpose(2, 1, 0), processed_affine),
                (shape, native_affine),
                order=1,
                cval=0,
            ).dataobj
        )
        for channel in probabilities
    ]
    actual = native_probabilities(
        probabilities, processed_affine, shape, native_affine, workers=workers
    )
    assert len(actual) == 3
    for left, right in zip(actual, expected, strict=True):
        assert left.shape == shape
        assert left.dtype == right.dtype
        np.testing.assert_array_equal(left, right)
    np.testing.assert_array_equal(probabilities, before)
    np.testing.assert_array_equal(np.stack(actual).argmax(0), np.stack(expected).argmax(0))


@pytest.mark.parametrize("workers", [0, -1, True, 1.5])
def test_backprojection_rejects_invalid_cpu_budget(workers):
    with pytest.raises(ValueError, match="positive integer"):
        native_probabilities(
            np.zeros((3, 2, 2, 2)), np.eye(4), (2, 2, 2), np.eye(4), workers=workers
        )
