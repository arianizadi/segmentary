"""Strict, versionable configuration for object segmentation runs."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..config import ModelConfig, from_dict, load_yaml


@dataclass
class ObjectDataConfig:
    images: str
    annotations: str
    panoptic_masks: str | None = None


@dataclass
class ObjectConfig:
    task: Literal["instance", "panoptic"]
    model: ModelConfig
    train: ObjectDataConfig
    val: ObjectDataConfig
    output: str
    image_size: list[int] = field(default_factory=lambda: [640, 640])
    max_steps: int = 1000
    val_every: int = 100
    batch_size: int = 1
    lr: float = 0.0001
    weight_decay: float = 0.05
    allow_train_val_overlap: bool = False
    seed: int = 0
    device: str = "cpu"
    num_points: int = 1024
    score_threshold: float = 0.05
    mask_threshold: float = 0.5
    overlap_threshold: float = 0.8

    def __post_init__(self):
        if self.task not in ("instance", "panoptic"):
            raise ValueError("objects.task must be instance or panoptic")
        if len(self.image_size) != 2 or any(n < 1 for n in self.image_size):
            raise ValueError("image_size must contain positive height and width")
        for key in ("max_steps", "val_every", "batch_size", "num_points"):
            if getattr(self, key) < 1:
                raise ValueError(f"{key} must be positive")
        for key in ("score_threshold", "mask_threshold", "overlap_threshold"):
            if not 0 < getattr(self, key) <= 1:
                raise ValueError(f"{key} must be in (0,1]")
        if not math.isfinite(self.lr) or self.lr <= 0:
            raise ValueError("lr must be finite and positive")
        if not math.isfinite(self.weight_decay) or self.weight_decay < 0:
            raise ValueError("weight_decay must be finite and nonnegative")
        if not 0 <= self.seed < 2**32:
            raise ValueError("seed must be in [0,2**32)")
        if self.model.arch not in ("eomt_large", "eomt_dinov3_large"):
            raise ValueError("Object tasks currently require eomt_large or eomt_dinov3_large")
        if self.task == "panoptic" and any(
            d.panoptic_masks is None for d in (self.train, self.val)
        ):
            raise ValueError("panoptic train and val require panoptic_masks directories")


def load_config(path: str | Path) -> ObjectConfig:
    """Resolve data/output paths relative to the configuration file, never the cwd."""
    path = Path(path).resolve()
    config = from_dict(ObjectConfig, load_yaml(path))
    for data in (config.train, config.val):
        for name in ("images", "annotations", "panoptic_masks"):
            value = getattr(data, name)
            if value is not None:
                setattr(data, name, str((path.parent / value).resolve()))
    config.output = str((path.parent / config.output).resolve())
    if config.model.checkpoint:
        local = path.parent / config.model.checkpoint
        if local.exists() or config.model.checkpoint.startswith(("./", "../")):
            config.model.checkpoint = str(local.resolve())
    return config
