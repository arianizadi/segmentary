"""Mixed-dataset loader for joint-training curricula.

Two things make mixed training different from simply concatenating datasets:

1. Datasets often differ greatly in size. Plain concatenation lets the larger
   one dominate, which confounds "joint training" with "more of the largest
   dataset". `weights` makes the sampling ratio an explicit experimental knob.

2. A single batch holds samples from both datasets, and they disagree about which
   canonical classes are supervised. Each sample therefore carries its own active
   mask, and the loss masks per-sample -- see losses.mask_inactive.
"""

from __future__ import annotations

import math
from numbers import Real

import numpy as np
import torch
from torch.utils.data import ConcatDataset, Dataset, WeightedRandomSampler

from .base import SegDataset


class MixedDataset(ConcatDataset):
    """Concatenation of several SegDatasets sharing one canonical label space."""

    def __init__(self, datasets: list[SegDataset]) -> None:
        if not datasets:
            raise ValueError("MixedDataset needs at least one dataset")

        reference_space = datasets[0].mapping.space
        if any(dataset.mapping.space != reference_space for dataset in datasets[1:]):
            spaces = [f"{dataset.name}:{dataset.mapping.space.name}" for dataset in datasets]
            raise ValueError(
                f"all datasets in a mixed loader must share one label space, got {spaces}. "
                f"Mixing spaces would make the head's class ids mean different things per batch."
            )
        names = [d.name for d in datasets]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate dataset names in mixed loader: {names}")

        super().__init__(datasets)
        self.datasets: list[SegDataset]
        self.space = datasets[0].mapping.space

    @property
    def name(self) -> str:
        return "+".join(d.name for d in self.datasets)

    @property
    def active(self) -> torch.Tensor:
        """Union of the members' active classes -- what the head must cover."""
        out = torch.zeros(self.space.num_classes, dtype=torch.bool)
        for d in self.datasets:
            out |= d.active
        return out

    def sampler(self, weights: dict[str, float] | None, num_samples: int, seed: int = 0):
        """Build a WeightedRandomSampler that hits the requested dataset ratio.

        Args:
            weights: dataset name -> relative share of each batch. ``None`` keeps
                natural proportions (i.e. plain concatenation).
            num_samples: samples drawn per epoch; with iteration-based training
                this just needs to exceed the steps between validations.
        """
        if weights is None:
            return None
        if isinstance(num_samples, bool) or not isinstance(num_samples, int) or num_samples <= 0:
            raise ValueError(f"sampler num_samples must be a positive integer, got {num_samples!r}")

        unknown = sorted(set(weights) - {d.name for d in self.datasets})
        if unknown:
            raise ValueError(f"sampler weights name unknown datasets {unknown}")
        missing = sorted({d.name for d in self.datasets} - set(weights))
        if missing:
            raise ValueError(f"sampler weights omit {missing}; list every dataset explicitly")
        if any(
            isinstance(weight, bool)
            or not isinstance(weight, Real)
            or not math.isfinite(float(weight))
            or weight <= 0
            for weight in weights.values()
        ):
            raise ValueError(f"sampler weights must be finite positive numbers, got {weights}")

        total = math.fsum(float(weight) for weight in weights.values())
        per_sample = np.empty(len(self), dtype=np.float64)
        start = 0
        for d in self.datasets:
            n = len(d)
            # Each dataset's share is spread evenly across its own samples, so the
            # ratio holds regardless of how differently sized the datasets are.
            per_sample[start : start + n] = (weights[d.name] / total) / n
            start += n

        g = torch.Generator().manual_seed(seed)
        return WeightedRandomSampler(
            weights=torch.from_numpy(per_sample),
            num_samples=num_samples,
            replacement=True,
            generator=g,
        )

    def describe(self) -> str:
        parts = ", ".join(f"{d.name}={len(d)}" for d in self.datasets)
        return f"MixedDataset({parts}, total={len(self)})"


def collate(batch: list[dict]) -> dict:
    """Stack a batch, keeping per-sample active masks and string metadata."""
    return {
        "image": torch.stack([b["image"] for b in batch]),
        "mask": torch.stack([b["mask"] for b in batch]),
        "active": torch.stack([b["active"] for b in batch]),  # (N, C)
        "dataset": [b["dataset"] for b in batch],
        "key": [b["key"] for b in batch],
    }


def as_dataset(d: Dataset) -> SegDataset | MixedDataset:
    """Narrow a loader's dataset back to something with .active/.name."""
    if isinstance(d, (SegDataset, MixedDataset)):
        return d
    raise TypeError(f"expected SegDataset or MixedDataset, got {type(d).__name__}")
