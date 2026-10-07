"""Host-referenced calibration statistics, deviation tensor and zero-init FiLM block."""

from __future__ import annotations

import itertools

import numpy as np
import pytest
import torch

from segmentary.medical.host_reference import (
    INTENSITY_CHANNELS,
    REFERENCE_MODES,
    HostReferenceBlock,
    annulus_stats,
    box_mean3d,
    box_sum3d,
    compute_host_reference,
    host_lesion_probabilities,
    robust_gland_stats,
)


@pytest.fixture(autouse=True)
def bounded_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


def _numpy_box_sum(values: np.ndarray, kernel) -> np.ndarray:
    """Brute-force reference: sum over the part of each centred box inside the volume."""
    result = np.zeros_like(values, dtype=np.float64)
    depth, height, width = values.shape[2:]
    rd, rh, rw = (size // 2 for size in kernel)
    for z, y, x in itertools.product(range(depth), range(height), range(width)):
        block = values[
            :,
            :,
            max(0, z - rd) : z + rd + 1,
            max(0, y - rh) : y + rh + 1,
            max(0, x - rw) : x + rw + 1,
        ]
        result[:, :, z, y, x] = block.sum(axis=(2, 3, 4))
    return result


@pytest.mark.parametrize(
    "shape, kernel",
    [
        ((2, 3, 5, 7, 6), (3, 5, 3)),
        ((1, 1, 4, 9, 9), (9, 17, 17)),  # box larger than the grid in every axis
        ((1, 2, 6, 6, 6), (1, 1, 1)),
        ((1, 1, 7, 8, 5), (1, 5, 5)),
    ],
)
def test_box_sum_matches_numpy_including_edges(shape, kernel):
    generator = np.random.default_rng(0)
    values = generator.normal(size=shape).astype(np.float32)
    expected = _numpy_box_sum(values.astype(np.float64), kernel)
    actual = box_sum3d(torch.from_numpy(values), kernel)
    assert actual.dtype == torch.float32
    # fp32 separable sums of at most 2601 unit-variance values: absolute error ~1e-5.
    np.testing.assert_allclose(actual.numpy(), expected, rtol=1e-5, atol=1e-4)
    counts = _numpy_box_sum(np.ones((1, 1, *shape[2:])), kernel)
    np.testing.assert_allclose(
        box_mean3d(torch.from_numpy(values), kernel).numpy(),
        expected / counts,
        rtol=1e-5,
        atol=1e-5,
    )


def test_box_mean_of_a_constant_is_exact_at_patch_edges():
    values = torch.full((1, 1, 5, 6, 7), 3.25)
    assert torch.allclose(box_mean3d(values, (9, 17, 17)), values, atol=1e-6, rtol=0)


@pytest.mark.parametrize("kernel", [(2, 3, 3), (3, 3), (3, 3, 0), (3.0, 3, 3)])
def test_box_kernels_must_be_odd_positive_triples(kernel):
    with pytest.raises(ValueError):
        box_sum3d(torch.zeros(1, 1, 4, 4, 4), kernel)


def _contaminated(gap: float, sd: float, fraction: float = 0.1, n: int = 40000, seed: int = 0):
    generator = torch.Generator().manual_seed(seed)
    lesion = int(n * fraction)
    parenchyma = 100 + sd * torch.randn(n - lesion, generator=generator)
    mass = 100 - gap + sd * torch.randn(lesion, generator=generator)
    values = torch.cat([parenchyma, mass]).view(1, 1, 1, 1, n)
    return values, torch.ones_like(values)


def test_irls_recovers_uncontaminated_location():
    values, weights = _contaminated(0, 15, fraction=0)
    mean, variance = robust_gland_stats(values, weights, sigma0=5.0)
    assert abs(mean.item() - 100) < 0.3
    # The Huber-weighted second moment is not consistency-corrected.
    assert 13 < variance.sqrt().item() < 15.5


def test_irls_with_ten_percent_contamination():
    # At the median Task07 lesion-parenchyma gap (9.2 HU) every estimate is within 1 HU.
    values, weights = _contaminated(9.2, 10, n=200000)
    mean, _ = robust_gland_stats(values, weights, sigma0=5.0)
    assert abs(mean.item() - 100) < 1.0
    # For a strongly contrasting 60 HU lesion the plain mean is off by ~6 HU.
    # Monotone Huber (k=1.5) roughly halves that bias; the redescending Tukey
    # option removes it. Huber cannot reach 1 HU here: its bias is bounded by
    # about eps * k * sigma / (1 - eps).
    values, weights = _contaminated(60, 10)
    plain, _ = robust_gland_stats(values, weights, sigma0=5.0, iterations=0)
    huber, _ = robust_gland_stats(values, weights, sigma0=5.0)
    tukey, _ = robust_gland_stats(values, weights, sigma0=5.0, loss="tukey", k=4.685)
    assert abs(plain.item() - 100) > 5.5
    assert abs(huber.item() - 100) < 0.55 * abs(plain.item() - 100)
    assert abs(tukey.item() - 100) < 1.0


def test_gland_prior_defines_empty_patches_and_vanishes_for_real_glands():
    values = torch.randn(2, 1, 4, 8, 8) + 1.5
    empty = torch.zeros_like(values)
    mean, variance = robust_gland_stats(
        values, empty, sigma0=0.07, prior_mean=0.0, prior_var=1.0, prior_cells=10.0
    )
    assert torch.allclose(mean, torch.zeros_like(mean)) and torch.allclose(
        variance, torch.ones_like(variance)
    )
    full = torch.ones_like(values) * 100  # 25,600 weighted cells versus 10 prior cells
    mean, _ = robust_gland_stats(values, full, sigma0=0.07, prior_cells=10.0, iterations=0)
    assert torch.allclose(mean.flatten(), values.mean((1, 2, 3, 4)), atol=1e-3)


@pytest.mark.parametrize("cells", [1300, 400, 100])
def test_network_gland_prior_does_not_inflate_sigma_with_partial_coverage(cells):
    """The network's prior (10 cells, 15 HU SD) keeps sigma_g at the parenchymal SD.

    A foreground-scale prior variance (71 HU SD) inflated a 12 HU gland to
    14-31 HU as gland coverage fell from 1300 to 100 cells (mean weight 0.7).
    """
    std = 71.16
    generator = torch.Generator().manual_seed(cells)
    values = ((100 + 12 * torch.randn(cells, generator=generator)) - 79.77) / std
    shaped = values.view(1, 1, 1, 1, cells), torch.full((1, 1, 1, 1, cells), 0.7)
    kwargs = {"sigma0": 5 / std, "prior_mean": 0.0}
    plain_mean, plain_var = robust_gland_stats(*shaped, **kwargs, prior_cells=0.0)
    mean, variance = robust_gland_stats(
        *shaped, **kwargs, prior_cells=10.0, prior_var=(15 / std) ** 2
    )
    # Within 10% of the prior-free estimate (was +21% to +167% with a 71 HU prior SD).
    assert variance.sqrt().item() < 1.10 * plain_var.sqrt().item()
    # The mean is shrunk toward the dataset foreground mean by at most ~2.5 HU.
    assert abs(mean.item() - plain_mean.item()) * std < 2.6
    _, inflated = robust_gland_stats(*shaped, **kwargs, prior_cells=10.0, prior_var=1.0)
    assert inflated.sqrt().item() > 1.15 * plain_var.sqrt().item()


def test_annulus_excludes_the_core_and_shrinks_toward_the_prior():
    values = torch.zeros(1, 1, 9, 17, 17)
    values[:, :, 3:6, 5:12, 5:12] = 10.0  # a lesion that fills the inner box exactly
    weights = torch.ones_like(values)
    prior = torch.zeros(1, 1, 1, 1, 1)
    mean, variance, support = annulus_stats(
        values,
        weights,
        outer=(9, 17, 17),
        inner=(3, 7, 7),
        prior_mean=prior,
        prior_var=prior,
        shrinkage=0.0,
    )
    centre = (0, 0, 4, 8, 8)
    assert mean[centre].item() == pytest.approx(0.0, abs=1e-5)
    assert variance[centre].item() == pytest.approx(0.0, abs=1e-4)
    assert support[centre].item() == pytest.approx(9 * 17 * 17 - 3 * 7 * 7)
    # No host weight anywhere: the shrunk estimate is exactly the prior.
    mean, variance, support = annulus_stats(
        values,
        torch.zeros_like(values),
        outer=(9, 17, 17),
        inner=(3, 7, 7),
        prior_mean=torch.full_like(prior, 2.0),
        prior_var=torch.full_like(prior, 0.5),
        shrinkage=50.0,
    )
    assert torch.allclose(mean, torch.full_like(mean, 2.0))
    assert torch.allclose(variance, torch.full_like(variance, 0.5))
    assert support.abs().max() == 0


def test_annulus_matches_an_explicit_weighted_ring_with_shrinkage():
    generator = torch.Generator().manual_seed(3)
    values = torch.randn(1, 2, 5, 6, 7, generator=generator)
    weights = torch.rand(1, 1, 5, 6, 7, generator=generator)
    prior_mean = torch.tensor([0.5, -0.5]).view(1, 2, 1, 1, 1)
    prior_var = torch.tensor([2.0, 3.0]).view(1, 2, 1, 1, 1)
    mean, variance, support = annulus_stats(
        values,
        weights,
        outer=(3, 5, 5),
        inner=(1, 3, 3),
        prior_mean=prior_mean,
        prior_var=prior_var,
        shrinkage=4.0,
    )
    z, y, x = 2, 1, 6
    ring = torch.zeros(5, 6, 7, dtype=torch.bool)
    ring[z - 1 : z + 2, max(0, y - 2) : y + 3, max(0, x - 2) : x + 3] = True
    ring[z, y - 1 : y + 2, x - 1 : x + 2] = False
    w = weights[0, 0][ring].double()
    for channel in range(2):
        v = values[0, channel][ring].double()
        s = w.sum()
        ring_mean = (w * v).sum() / s
        expected_mean = (s * ring_mean + 4 * prior_mean[0, channel, 0, 0, 0]) / (s + 4)
        expected_var = ((w * (v - ring_mean) ** 2).sum() + 4 * prior_var[0, channel, 0, 0, 0]) / (
            s + 4
        )
        assert mean[0, channel, z, y, x].item() == pytest.approx(expected_mean.item(), abs=1e-5)
        assert variance[0, channel, z, y, x].item() == pytest.approx(expected_var.item(), abs=1e-4)
    assert support[0, 0, z, y, x].item() == pytest.approx(w.sum().item(), abs=1e-5)


def test_region_and_softmax_probability_decoding():
    logits = torch.randn(2, 3, 2, 3, 4)
    host, lesion = host_lesion_probabilities(
        logits, output_mode="softmax", host_channels=[1], lesion_channels=[2]
    )
    probabilities = torch.softmax(logits, 1)
    assert torch.allclose(host, probabilities[:, 1:2]) and torch.allclose(
        lesion, probabilities[:, 2:3]
    )
    regions = torch.randn(2, 2, 2, 3, 4)
    host, lesion = host_lesion_probabilities(
        regions, output_mode="regions", host_channels=[0], lesion_channels=[1]
    )
    whole, mass = torch.sigmoid(regions[:, :1]), torch.sigmoid(regions[:, 1:])
    assert torch.allclose(host, whole * (1 - mass)) and torch.allclose(lesion, mass)
    with pytest.raises(ValueError):
        host_lesion_probabilities(
            regions, output_mode="regions", host_channels=[0, 1], lesion_channels=[1]
        )


def _reference(mode: str, image: torch.Tensor, host: torch.Tensor, lesion: torch.Tensor):
    return compute_host_reference(
        image,
        host,
        lesion,
        mode=mode,
        sigma0=0.07,
        outer=(3, 5, 5),
        inner=(1, 3, 3),
        shrinkage=50.0,
        gland_prior_cells=10.0,
        gland_prior_var=(15 / 71.16) ** 2,
        robust_loss="huber",
        robust_k=1.5,
        iterations=3,
    )


def _inputs(seed: int = 0):
    generator = torch.Generator().manual_seed(seed)
    features = torch.randn(2, 8, 4, 16, 16, generator=generator)
    image = torch.randn(2, 1, 4, 16, 16, generator=generator)
    stats_image = torch.nn.functional.avg_pool3d(image, (2, 4, 4))
    host = torch.rand(2, 1, 2, 4, 4, generator=generator)
    lesion = torch.rand(2, 1, 2, 4, 4, generator=generator) * (1 - host)
    return features, image, stats_image, host, lesion


@pytest.mark.parametrize("mode", REFERENCE_MODES)
def test_zero_initialised_block_is_an_exact_identity_and_masks_ablations(mode):
    features, image, stats_image, host, lesion = _inputs()
    block = HostReferenceBlock(
        8, reference_mode=mode, sigma0=0.07, outer_box=(3, 5, 5), inner_box=(1, 3, 3)
    )
    reference = _reference(mode, stats_image, host, lesion)
    output = block(features, image, reference, (2, 4, 4))
    assert torch.equal(output, features)
    deviation = block.deviation(features, image, reference, (2, 4, 4))
    assert deviation.shape == (2, INTENSITY_CHANNELS + 16, 4, 16, 16)
    assert torch.isfinite(deviation).all()
    intensity, feature = deviation[:, :INTENSITY_CHANNELS], deviation[:, INTENSITY_CHANNELS:]
    assert (intensity.abs().sum() == 0) == (mode in {"features_only", "none"})
    assert (feature.abs().sum() == 0) == (mode in {"hu_only", "none"})
    gland = deviation[:, 4:6]
    assert (gland.abs().sum() == 0) == (mode in {"local_only", "features_only", "none"})
    if mode == "gland_only":
        assert torch.allclose(reference.local_mean, reference.gland_mean.expand_as(stats_image))
    if mode == "unmasked_lcn":
        assert torch.equal(reference.weights, torch.ones_like(reference.weights))


def test_trained_film_changes_features_and_autocast_gradients_are_finite():
    features, image, stats_image, host, lesion = _inputs(1)
    features.requires_grad_(True)
    block = HostReferenceBlock(8, sigma0=0.07)
    torch.nn.init.normal_(block.film.weight, std=0.1)
    reference = _reference("robust", stats_image, host, lesion)
    with torch.autocast("cpu", dtype=torch.bfloat16):
        output = block(features, image, reference, (2, 4, 4))
    assert not torch.equal(output.float(), features)
    output.float().square().mean().backward()
    for name, parameter in block.named_parameters():
        assert parameter.grad is not None and torch.isfinite(parameter.grad).all(), name
    assert features.grad is not None and torch.isfinite(features.grad).all()
    # Reference statistics stay fp32 under autocast.
    assert reference.local_mean.dtype == torch.float32


def test_reference_weights_are_detached_from_the_probabilities():
    _, _, stats_image, host, lesion = _inputs(2)
    host.requires_grad_(True)
    reference = _reference("robust", stats_image, host, lesion)
    assert not reference.weights.requires_grad and not reference.local_mean.requires_grad


def test_invalid_block_settings_fail_closed():
    with pytest.raises(ValueError):
        HostReferenceBlock(8, reference_mode="median", sigma0=0.07)
    with pytest.raises(ValueError):
        HostReferenceBlock(8, sigma0=0.0)
    with pytest.raises(ValueError):
        HostReferenceBlock(8, sigma0=0.07, smoothing_box=(1, 4, 5))
