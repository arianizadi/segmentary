"""Strict, immutable recipe for scratch CT architecture comparisons."""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TorchConfig:
    workspace: str
    model: str = "unet_3d"
    backend: str = "torch"
    backend_python: str = sys.executable
    initialization: str = "scratch"
    mode: str = "3d"
    context_slices: int = 1
    patch_size: tuple[int, ...] = (64, 128, 128)
    spacing_mm: tuple[float, float, float] = (1.5, 1.5, 2.5)
    hu_window: tuple[float, float] = (-100.0, 240.0)
    model_options: dict[str, Any] = field(default_factory=dict)
    gpu: str = "0"
    seed: int = 0
    workers: int = 2
    batch_size: int = 2
    epochs: int = 100
    steps_per_epoch: int = 100
    validation_interval: int = 1
    progress_interval: int = 10
    inference_batch_size: int = 1
    cache_root: str | None = None
    prefetch_batches: bool = False
    learning_rate: float = 0.0003
    weight_decay: float = 0.00001
    foreground_probability: float | None = 0.5
    # Explicit center modes replace (never supplement) the legacy foreground coin.
    # The first mode starts with uniform-volume probability, not background-only.
    center_probabilities: tuple[float, float, float] | None = None
    class_center_weights: tuple[float, float, float] | None = None
    overlap: float = 0.5
    precision: str = "fp32"
    deterministic: bool = False
    augment: bool = True
    rotation_probability: float = 0.0
    rotation_degrees: tuple[float, float] = (-15.0, 15.0)
    rotation_padding_value: float = 0.0
    intensity_scale_probability: float = 0.0
    intensity_scale_range: tuple[float, float] = (0.9, 1.1)
    gradient_clip: float = 12.0
    purpose: str = "baseline"

    def __post_init__(self) -> None:
        for name in (
            "seed",
            "workers",
            "batch_size",
            "epochs",
            "steps_per_epoch",
            "validation_interval",
            "progress_interval",
            "inference_batch_size",
            "context_slices",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "seed" else 1):
                raise ValueError(f"{name} must be an integer in range")
        if self.seed >= 2**32:
            raise ValueError("seed must be a uint32")
        for name in ("deterministic", "augment", "prefetch_batches"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        if self.backend != "torch" or self.initialization != "scratch":
            raise ValueError("Torch medical experiments require initialization: scratch")
        if self.mode not in {"2d", "2.5d", "3d"}:
            raise ValueError("mode must be 2d, 2.5d, or 3d")
        if self.context_slices % 2 != 1 or (self.mode != "2.5d" and self.context_slices != 1):
            raise ValueError("Only 2.5d accepts an odd context_slices greater than one")
        if self.mode == "2.5d" and self.context_slices < 3:
            raise ValueError("2.5d needs at least three adjacent slices")
        for name, length in (
            ("patch_size", 3 if self.mode == "3d" else 2),
            ("spacing_mm", 3),
            ("hu_window", 2),
        ):
            value = tuple(getattr(self, name))
            if len(value) != length or any(
                isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
                for x in value
            ):
                raise ValueError(f"Invalid {name}")
            if name == "patch_size" and any(type(x) is not int or x < 1 for x in value):
                raise ValueError("patch_size must contain positive integers")
            if name == "spacing_mm" and any(x <= 0 for x in value):
                raise ValueError("spacing_mm must be positive, in RAS x/y/z order")
            object.__setattr__(self, name, value)
        if self.hu_window[0] >= self.hu_window[1]:
            raise ValueError("hu_window must be increasing")
        explicit_centers = sum(
            value is not None for value in (self.center_probabilities, self.class_center_weights)
        )
        if explicit_centers > 1 or (explicit_centers and self.foreground_probability is not None):
            raise ValueError(
                "Use one center mode; explicit centers require foreground_probability: null"
            )
        if not explicit_centers and self.foreground_probability is None:
            raise ValueError("foreground_probability is required for legacy center sampling")
        for name, length in (
            ("center_probabilities", 3),
            ("class_center_weights", 3),
            ("rotation_degrees", 2),
            ("intensity_scale_range", 2),
        ):
            value = getattr(self, name)
            if value is None and name in {"center_probabilities", "class_center_weights"}:
                continue
            if (
                not isinstance(value, (list, tuple))
                or len(value) != length
                or any(
                    isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
                    for x in value
                )
            ):
                raise ValueError(f"Invalid {name}")
            value = tuple(value)
            if name in {"center_probabilities", "class_center_weights"}:
                if any(x < 0 for x in value) or not math.isfinite(sum(value)) or sum(value) <= 0:
                    raise ValueError(f"{name} must contain nonnegative weights with positive sum")
                if name == "center_probabilities" and not math.isclose(
                    sum(value), 1.0, rel_tol=0, abs_tol=1e-9
                ):
                    raise ValueError("center_probabilities must sum to one")
            elif name == "rotation_degrees":
                if not -180 <= value[0] <= value[1] <= 180:
                    raise ValueError("rotation_degrees must be ordered and within [-180,180]")
            elif not 0 < value[0] <= value[1]:
                raise ValueError("intensity_scale_range must be positive and ordered")
            object.__setattr__(self, name, value)
        for name in (
            "learning_rate",
            "weight_decay",
            "overlap",
            "gradient_clip",
            "rotation_probability",
            "rotation_padding_value",
            "intensity_scale_probability",
            *(("foreground_probability",) if self.foreground_probability is not None else ()),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
            ):
                raise ValueError(f"Invalid {name}")
        if self.learning_rate <= 0 or self.weight_decay < 0 or self.gradient_clip <= 0:
            raise ValueError(
                "Use positive learning rate/gradient clip and nonnegative weight decay"
            )
        if (
            self.foreground_probability is not None and not 0 <= self.foreground_probability <= 1
        ) or not 0 <= self.overlap < 1:
            raise ValueError("foreground_probability must be [0,1], overlap [0,1)")
        if any(
            not 0 <= value <= 1
            for value in (self.rotation_probability, self.intensity_scale_probability)
        ):
            raise ValueError("Augmentation probabilities must be [0,1]")
        if not 0 <= self.rotation_padding_value <= 1:
            raise ValueError("rotation_padding_value must use normalized CT intensities in [0,1]")
        if self.rotation_probability and not math.isclose(
            self.spacing_mm[0], self.spacing_mm[1], rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError("Axial rotation requires equal in-plane x/y spacing_mm")
        if not self.augment and (self.rotation_probability or self.intensity_scale_probability):
            raise ValueError("Optional augmentations require augment: true")
        if self.precision not in {"fp32", "bf16", "fp16"} or self.purpose not in {
            "baseline",
            "smoke",
            "overfit",
        }:
            raise ValueError("Unsupported precision or purpose")
        if not isinstance(self.model_options, dict) or not isinstance(self.model, str):
            raise ValueError("model must be a name and model_options a mapping")
        if not isinstance(self.gpu, str) or (
            self.gpu != "cpu" and not re.fullmatch(r"[0-9]+", self.gpu)
        ):
            raise ValueError("gpu must be one numeric device string or cpu")
        if self.gpu == "cpu" and self.precision != "fp32":
            raise ValueError("CPU verification uses fp32")
        if self.gpu != "cpu":
            object.__setattr__(self, "gpu", str(int(self.gpu)))
        if not isinstance(self.workspace, (str, Path)) or not isinstance(self.backend_python, str):
            raise ValueError("workspace and backend_python must be paths")
        object.__setattr__(self, "workspace", str(Path(self.workspace).expanduser().resolve()))
        if self.cache_root is not None:
            if not isinstance(self.cache_root, (str, Path)):
                raise ValueError("cache_root must be a path or null")
            object.__setattr__(
                self, "cache_root", str(Path(self.cache_root).expanduser().resolve())
            )
        object.__setattr__(
            self, "backend_python", str(Path(self.backend_python).expanduser().absolute())
        )

    @property
    def root(self) -> Path:
        return Path(self.workspace)
