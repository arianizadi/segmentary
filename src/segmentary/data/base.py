"""SegDataset ABC: the one contract every dataset in this project satisfies.

Every subclass indexes (image, label) pairs, applies the taxonomy LUT, then the
albumentations pipeline. Doing the LUT here rather than in a preprocessing script
means there is no derived copy of the labels that can drift from the YAML.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from albumentations import Compose
from PIL import Image
from torch.utils.data import Dataset

from ..taxonomy import DatasetMapping


@dataclass(frozen=True)
class Sample:
    """One indexed example. ``group`` is the leakage-safe splitting unit."""

    image: Path
    label: Path
    key: str
    group: str


class SegDataset(Dataset, ABC):
    """Base class for semantic segmentation datasets in a canonical label space.

    Args:
        root: dataset root directory.
        split: "train", "val" or "test".
        mapping: validated native -> canonical LUT for this dataset.
        transform: albumentations pipeline ending in ToTensorV2.
        limit: keep only the first N samples (used by overfit_check).
    """

    def __init__(
        self,
        root: Path | str,
        split: str,
        mapping: DatasetMapping,
        transform: Compose,
        limit: int | None = None,
    ) -> None:
        self.root = Path(root)
        self.split = split
        self.mapping = mapping
        self.transform = transform

        if not self.root.is_dir():
            raise FileNotFoundError(f"{type(self).__name__}: dataset root not found: {self.root}")

        samples = self.index()
        if not samples:
            raise FileNotFoundError(
                f"{type(self).__name__}: no samples found for split {split!r} under {self.root}. "
                f"Check the directory layout rather than training on an empty loader."
            )
        self.samples = samples[:limit] if limit else samples

        # Cached so every batch carries it without recomputation.
        self._active = torch.from_numpy(mapping.active_mask())

    @abstractmethod
    def index(self) -> list[Sample]:
        """Enumerate samples for ``self.split``, sorted for reproducibility."""

    @property
    def name(self) -> str:
        return self.mapping.dataset

    @property
    def active(self) -> torch.Tensor:
        """(C,) bool mask of canonical classes this dataset supervises."""
        return self._active

    def __len__(self) -> int:
        return len(self.samples)

    def load_image(self, path: Path) -> np.ndarray:
        with Image.open(path) as im:
            return np.asarray(im.convert("RGB"))

    def load_label(self, path: Path) -> np.ndarray:
        """Read a single-channel index label. Palette PNGs are read as indices."""
        with Image.open(path) as im:
            if im.mode not in ("L", "P", "I;16", "I"):
                raise ValueError(
                    f"{path}: label image has mode {im.mode!r}. Expected a single-channel "
                    f"index image; an RGB label means you pointed at a *_color.png."
                )
            # mode "P" keeps the palette index, which is what we want -- convert("L")
            # would map through the palette and destroy the ids.
            return np.asarray(im)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        sample = self.samples[idx]
        image = self.load_image(sample.image)
        native = self.load_label(sample.label)

        if image.shape[:2] != native.shape[:2]:
            raise ValueError(
                f"{sample.key}: image {image.shape[:2]} and label {native.shape[:2]} differ in size"
            )

        canonical = self.mapping.apply(native)
        out = self.transform(image=image, mask=canonical)

        mask = out["mask"]
        if mask.dtype.is_floating_point:
            raise TypeError(f"{sample.key}: transform returned a float mask ({mask.dtype})")

        return {
            "image": out["image"],
            "mask": mask.long(),
            "active": self._active,
            "dataset": self.name,
            "key": sample.key,
        }

    def describe(self) -> str:
        return (
            f"{type(self).__name__}(name={self.name!r}, split={self.split!r}, "
            f"n={len(self)}, classes={len(self.mapping.active_ids)}/"
            f"{self.mapping.space.num_classes})"
        )
