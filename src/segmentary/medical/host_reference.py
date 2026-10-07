"""Host-referenced calibration (HRC): a lesion-excluding, contamination-resistant reference.

The network's own detached coarse probabilities give host-tissue weights
``w = p_host**2 * (1 - p_lesion)``. From them, every sample gets a robust
gland-level reference (iteratively reweighted location and scale) and a smooth
annular local reference that leaves out a lesion-sized core and shrinks toward
the gland when its support is small. The reference statistics are always
computed in fp32 with autocast disabled.

``HostReferenceBlock`` turns the reference into a 24-channel deviation tensor
and injects it with a zero-initialised FiLM layer, so a network that contains
it is an exact function copy of its host network until training moves the FiLM
weights. Grids follow the CT-normalised input: one intensity unit is one plan
foreground standard deviation, so ``sigma0`` is given in those units.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

import torch
from torch import nn
from torch.nn import functional as F

REFERENCE_MODES = (
    "robust",
    "masked_mean",
    "gland_only",
    "local_only",
    "unmasked_lcn",
    "features_only",
    "hu_only",
    "none",
)
OUTPUT_MODES = ("softmax", "regions")
ROBUST_LOSSES = ("huber", "tukey")
INTENSITY_CHANNELS = 8
# z_loc, |z_loc|, smoothed z_loc, |smoothed z_loc|, z_gl, |z_gl|, support, log variance.
_GLAND_CHANNELS = (4, 5)
_Z_LIMIT = 20.0


def _kernel(kernel: Sequence[int]) -> tuple[int, int, int]:
    if (
        not isinstance(kernel, (tuple, list))
        or len(kernel) != 3
        or any(type(size) is not int or size < 1 or size % 2 == 0 for size in kernel)
    ):
        raise ValueError("Box kernels must contain three positive odd integers")
    return int(kernel[0]), int(kernel[1]), int(kernel[2])


def box_sum3d(values: torch.Tensor, kernel: Sequence[int]) -> torch.Tensor:
    """Sum over a centred odd box, clipped to the volume, computed separably in fp32.

    Voxels outside the volume contribute zero, so dividing by
    ``box_sum3d(ones)`` gives the mean over the valid part of every box.
    """
    if values.ndim != 5:
        raise ValueError("box_sum3d expects N,C,D,H,W")
    sizes = _kernel(kernel)
    result = values.float()
    for axis, size in enumerate(sizes):
        if size == 1:
            continue
        shape = [1, 1, 1]
        shape[axis] = size
        # F.pad orders padding from the last axis backwards: (W, W, H, H, D, D).
        padding = [0] * 6
        padding[2 * (2 - axis)] = padding[2 * (2 - axis) + 1] = size // 2
        # Explicit zero padding also supports grids smaller than the box.
        result = F.avg_pool3d(F.pad(result, padding), kernel_size=tuple(shape), stride=1) * size
    return result


def box_mean3d(values: torch.Tensor, kernel: Sequence[int]) -> torch.Tensor:
    """Mean over the valid voxels of each box (count-normalised at volume edges)."""
    ones = values.new_ones((1, 1, *values.shape[2:]), dtype=torch.float32)
    return box_sum3d(values, kernel) / box_sum3d(ones, kernel)


def robust_weights(residual: torch.Tensor, loss: str, k: float) -> torch.Tensor:
    """IRLS weights psi(r)/r for a standardised residual."""
    magnitude = residual.abs()
    if loss == "huber":
        return torch.clamp(k / magnitude.clamp_min(1e-12), max=1.0)
    if loss == "tukey":
        return torch.where(
            magnitude < k, (1 - (residual / k) ** 2) ** 2, torch.zeros_like(residual)
        )
    raise ValueError(f"robust loss must be one of {ROBUST_LOSSES}")


def _weighted_moments(
    values: torch.Tensor,
    weights: torch.Tensor,
    prior_mean: torch.Tensor | float,
    prior_var: torch.Tensor | float,
    prior_cells: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    dims = (2, 3, 4)
    total = weights.sum(dims, keepdim=True) + prior_cells
    total = total.clamp_min(1e-6)
    mean = ((weights * values).sum(dims, keepdim=True) + prior_cells * prior_mean) / total
    scatter = (weights * (values - mean) ** 2).sum(dims, keepdim=True)
    variance = (scatter + prior_cells * prior_var) / total
    return mean, variance.clamp_min(0)


def robust_gland_stats(
    values: torch.Tensor,
    weights: torch.Tensor,
    *,
    sigma0: float,
    loss: str = "huber",
    k: float = 1.5,
    iterations: int = 3,
    prior_mean: float = 0.0,
    prior_var: float = 1.0,
    prior_cells: float = 0.0,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Per-sample weighted location and variance with IRLS robust reweighting.

    Starts from the weighted mean and variance, then performs ``iterations``
    reweightings with residuals ``(x - mu) / sqrt(var + sigma0**2)``. The
    variance is the robust-weighted second moment; it is not rescaled to a
    Gaussian-consistent scale. ``prior_cells`` pseudo-cells at ``prior_mean``
    and ``prior_var`` keep the estimate defined when a patch has no host
    weight. Returns tensors of shape ``N, C, 1, 1, 1`` in fp32.
    """
    if values.ndim != 5 or weights.ndim != 5 or weights.shape[1] != 1:
        raise ValueError("Expected N,C,D,H,W values and N,1,D,H,W weights")
    if type(iterations) is not int or iterations < 0:
        raise ValueError("iterations must be a non-negative integer")
    values, weights = values.float(), weights.float()
    mean, variance = _weighted_moments(values, weights, prior_mean, prior_var, prior_cells)
    for _ in range(iterations):
        residual = (values - mean) / torch.sqrt(variance + sigma0**2)
        reweighted = weights * robust_weights(residual, loss, k)
        mean, variance = _weighted_moments(values, reweighted, prior_mean, prior_var, prior_cells)
    return mean, variance


def annulus_stats(
    values: torch.Tensor,
    weights: torch.Tensor,
    *,
    outer: Sequence[int],
    inner: Sequence[int],
    prior_mean: torch.Tensor,
    prior_var: torch.Tensor,
    shrinkage: float,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Weighted annular mean and variance, shrunk toward a per-sample prior.

    The annulus is the outer box minus the inner box. With annulus weight
    ``S``, ``mean = (S * mean_annulus + n0 * prior_mean) / (S + n0)`` and the
    variance is shrunk the same way. Returns ``(mean, variance, S)``.
    """
    outer, inner = _kernel(outer), _kernel(inner)
    if any(i > o for i, o in zip(inner, outer, strict=True)):
        raise ValueError("The inner box must fit inside the outer box")
    if shrinkage < 0:
        raise ValueError("shrinkage must be non-negative")
    values, weights = values.float(), weights.float()

    def ring(tensor: torch.Tensor) -> torch.Tensor:
        return box_sum3d(tensor, outer) - box_sum3d(tensor, inner)

    support = ring(weights).clamp_min(0)
    first = ring(weights * values)
    second = ring(weights * values * values)
    total = (support + shrinkage).clamp_min(1e-6)
    mean = (first + shrinkage * prior_mean) / total
    annulus_mean = first / support.clamp_min(1e-6)
    scatter = (second - first * annulus_mean).clamp_min(0)
    variance = (scatter + shrinkage * prior_var) / total
    return mean, variance, support


@dataclass(frozen=True)
class HostReference:
    """Host statistics on the statistics grid G (all fp32, detached inputs).

    ``weights`` are the robust annulus weights w', ``host_weights`` the raw
    ``p_host**2 * (1 - p_lesion)`` and ``lesion_weights`` ``p_lesion``.
    """

    weights: torch.Tensor
    host_weights: torch.Tensor
    lesion_weights: torch.Tensor
    gland_mean: torch.Tensor
    gland_var: torch.Tensor
    local_mean: torch.Tensor
    local_var: torch.Tensor
    support: torch.Tensor
    annulus_weight: torch.Tensor

    def detached(self) -> HostReference:
        return HostReference(**{name: value.detach() for name, value in vars(self).items()})


def host_lesion_probabilities(
    logits: torch.Tensor,
    *,
    output_mode: str,
    host_channels: Sequence[int],
    lesion_channels: Sequence[int],
) -> tuple[torch.Tensor, torch.Tensor]:
    """Return detached fp32 ``(p_host, p_lesion)``, each N,1,D,H,W.

    Softmax mode sums the softmax over the given channels. Region mode uses
    sigmoids: the host channel is the region that contains the lesion, so
    ``p_host = sigmoid(R) * (1 - sigmoid(M))``.
    """
    logits = logits.detach().float()
    if output_mode == "softmax":
        probabilities = torch.softmax(logits, 1)
        host = probabilities[:, list(host_channels)].sum(1, keepdim=True)
        lesion = probabilities[:, list(lesion_channels)].sum(1, keepdim=True)
        return host, lesion
    if output_mode == "regions":
        if len(host_channels) != 1 or len(lesion_channels) != 1:
            raise ValueError("Region mode needs exactly one host and one lesion channel")
        region = torch.sigmoid(logits[:, host_channels[0] : host_channels[0] + 1])
        lesion = torch.sigmoid(logits[:, lesion_channels[0] : lesion_channels[0] + 1])
        return region * (1 - lesion), lesion
    raise ValueError(f"output_mode must be one of {OUTPUT_MODES}")


def compute_host_reference(
    image: torch.Tensor,
    host: torch.Tensor,
    lesion: torch.Tensor,
    *,
    mode: str,
    sigma0: float,
    outer: Sequence[int],
    inner: Sequence[int],
    shrinkage: float,
    gland_prior_cells: float,
    gland_prior_var: float,
    robust_loss: str,
    robust_k: float,
    iterations: int,
) -> HostReference:
    """Gland and annular references for a CT-normalised image on grid G.

    ``gland_prior_cells`` pseudo-cells at the dataset foreground mean (0 after
    CT normalisation) with variance ``gland_prior_var`` keep the gland
    statistics defined in patches without host weight. The prior variance is
    parenchymal-scale (about 15 HU), not the dataset foreground variance, so it
    does not inflate ``sigma_g`` when a patch holds only part of the gland.
    """
    if mode not in REFERENCE_MODES:
        raise ValueError(f"reference mode must be one of {REFERENCE_MODES}")
    device_type = image.device.type
    with torch.autocast(device_type=device_type, enabled=False):
        image, host, lesion = image.float(), host.detach().float(), lesion.detach().float()
        host_weights = host * host * (1 - lesion)
        robust = mode not in {"masked_mean", "unmasked_lcn"}
        weights = torch.ones_like(host_weights) if mode == "unmasked_lcn" else host_weights
        # The dataset foreground maps to mean 0 under CT normalisation.
        gland_mean, gland_var = robust_gland_stats(
            image,
            weights,
            sigma0=sigma0,
            loss=robust_loss,
            k=robust_k,
            iterations=iterations if robust else 0,
            prior_mean=0.0,
            prior_var=gland_prior_var,
            prior_cells=gland_prior_cells,
        )
        if robust:
            residual = (image - gland_mean) / torch.sqrt(gland_var + sigma0**2)
            annulus_weights = weights * robust_weights(residual, robust_loss, robust_k)
        else:
            annulus_weights = weights
        if mode == "gland_only":
            local_mean = gland_mean.expand_as(image)
            local_var = gland_var.expand_as(image)
            ring = torch.zeros_like(image)
        else:
            local_mean, local_var, ring = annulus_stats(
                image,
                annulus_weights,
                outer=outer,
                inner=inner,
                prior_mean=gland_mean,
                prior_var=gland_var,
                shrinkage=shrinkage,
            )
        support = box_sum3d(weights, outer) / box_sum3d(torch.ones_like(weights[:1]), outer)
    return HostReference(
        weights=annulus_weights,
        host_weights=host_weights,
        lesion_weights=lesion,
        gland_mean=gland_mean,
        gland_var=gland_var,
        local_mean=local_mean,
        local_var=local_var,
        support=support,
        annulus_weight=ring,
    )


def _resize(field: torch.Tensor, shape: Sequence[int]) -> torch.Tensor:
    if tuple(field.shape[2:]) == tuple(shape):
        return field
    if all(size == 1 for size in field.shape[2:]):
        return field.expand(*field.shape[:2], *shape)
    return F.interpolate(field, size=tuple(shape), mode="trilinear", align_corners=False)


class HostReferenceBlock(nn.Module):
    """Deviation tensor from a shared host reference plus zero-initialised FiLM.

    ``X`` has 8 intensity channels (local and gland z-scores, their smoothed
    and unsigned forms, support and log local variance) and
    ``feature_channels`` channels of feature deviation ``D_P`` from a learned
    1x1 projection of the decoder features. ``F' = F * (1 + gamma) + beta``,
    where ``gamma`` and ``beta`` come from a zero-initialised 1x1 convolution,
    so the block is an identity map until that layer is trained.
    """

    channel_mask: torch.Tensor

    def __init__(
        self,
        channels: int,
        *,
        reference_mode: str = "robust",
        feature_channels: int = 16,
        hidden_channels: int = 32,
        sigma0: float,
        smoothing_box: Sequence[int] = (1, 5, 5),
        outer_box: Sequence[int] = (9, 17, 17),
        inner_box: Sequence[int] = (3, 7, 7),
        shrinkage: float = 50.0,
        feature_prior_cells: float = 10.0,
    ) -> None:
        super().__init__()
        if reference_mode not in REFERENCE_MODES:
            raise ValueError(f"reference_mode must be one of {REFERENCE_MODES}")
        for name, value in (
            ("channels", channels),
            ("feature_channels", feature_channels),
            ("hidden_channels", hidden_channels),
        ):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if isinstance(sigma0, bool) or not isinstance(sigma0, (int, float)) or not sigma0 > 0:
            raise ValueError("sigma0 must be a positive number in normalised intensity units")
        self.reference_mode = reference_mode
        self.feature_channels = feature_channels
        self.sigma0 = float(sigma0)
        self.smoothing_box = _kernel(smoothing_box)
        self.outer_box = _kernel(outer_box)
        self.inner_box = _kernel(inner_box)
        self.shrinkage = float(shrinkage)
        self.feature_prior_cells = float(feature_prior_cells)
        self.deviation_channels = INTENSITY_CHANNELS + feature_channels
        self.project = nn.Conv3d(channels, feature_channels, 1, bias=True)
        self.hidden = nn.Sequential(
            nn.Conv3d(self.deviation_channels, hidden_channels, 3, padding=1, bias=True),
            nn.InstanceNorm3d(hidden_channels, eps=1e-5, affine=True),
            nn.LeakyReLU(negative_slope=0.01, inplace=True),
        )
        self.film = nn.Conv3d(hidden_channels, 2 * channels, 1, bias=True)
        mask = torch.ones(self.deviation_channels)
        if reference_mode in {"features_only", "none"}:
            mask[:INTENSITY_CHANNELS] = 0
        if reference_mode in {"hu_only", "none"}:
            mask[INTENSITY_CHANNELS:] = 0
        if reference_mode == "local_only":
            mask[list(_GLAND_CHANNELS)] = 0
        self.register_buffer("channel_mask", mask.view(1, -1, 1, 1, 1), persistent=False)
        self.masks_channels = bool((mask == 0).any())
        self.reset_film()

    def reset_film(self) -> None:
        nn.init.zeros_(self.film.weight)
        if self.film.bias is not None:
            nn.init.zeros_(self.film.bias)

    def deviation(
        self,
        features: torch.Tensor,
        image: torch.Tensor,
        reference: HostReference,
        stats_stride: Sequence[int],
    ) -> torch.Tensor:
        """The 24-channel deviation tensor ``X`` on this block's grid (fp32)."""
        if self.reference_mode == "none":
            return features.new_zeros(
                (features.shape[0], self.deviation_channels, *features.shape[2:]),
                dtype=torch.float32,
            )
        shape = tuple(features.shape[2:])
        stride = tuple(int(value) for value in stats_stride)
        projected = self.project(features)
        with torch.autocast(device_type=features.device.type, enabled=False):
            image = image.float()
            sigma2 = self.sigma0**2
            local_mean = _resize(reference.local_mean, shape)
            local_var = _resize(reference.local_var, shape) + sigma2
            z_local = ((image - local_mean) / torch.sqrt(local_var)).clamp(-_Z_LIMIT, _Z_LIMIT)
            smoothed = box_mean3d(z_local, self.smoothing_box)
            z_gland = (
                (image - reference.gland_mean) / torch.sqrt(reference.gland_var + sigma2)
            ).clamp(-_Z_LIMIT, _Z_LIMIT)
            intensity = torch.cat(
                [
                    z_local,
                    z_local.abs(),
                    smoothed,
                    smoothed.abs(),
                    z_gland,
                    z_gland.abs(),
                    _resize(reference.support, shape),
                    torch.log(local_var),
                ],
                1,
            )
            projected = projected.float()
            coarse = (
                F.avg_pool3d(projected, kernel_size=stride, stride=stride)
                if any(value > 1 for value in stride)
                else projected
            )
            weights = reference.weights
            prior_mean = coarse.mean((2, 3, 4), keepdim=True)
            prior_var = coarse.var((2, 3, 4), keepdim=True, unbiased=False)
            gland_mean, gland_var = _weighted_moments(
                coarse, weights, prior_mean, prior_var, self.feature_prior_cells
            )
            if self.reference_mode == "gland_only":
                feature_local = gland_mean
            else:
                feature_local, _, _ = annulus_stats(
                    coarse,
                    weights,
                    outer=self.outer_box,
                    inner=self.inner_box,
                    prior_mean=gland_mean,
                    prior_var=gland_var,
                    shrinkage=self.shrinkage,
                )
            feature_deviation = (projected - _resize(feature_local, shape)) / torch.sqrt(
                gland_var + 1e-3
            )
            deviation = torch.cat([intensity, feature_deviation], 1)
        # Skip the copy when every channel is kept (the default robust mode).
        return deviation * self.channel_mask if self.masks_channels else deviation

    def forward(
        self,
        features: torch.Tensor,
        image: torch.Tensor,
        reference: HostReference,
        stats_stride: Sequence[int],
    ) -> torch.Tensor:
        deviation = self.deviation(features, image, reference, stats_stride)
        gamma, beta = self.film(self.hidden(deviation)).chunk(2, 1)
        return features * (1 + gamma) + beta


def override_reference(reference: HostReference, **fields: torch.Tensor) -> HostReference:
    """Replace named reference fields, for inference-time swap and zero tests."""
    return replace(reference, **fields)
