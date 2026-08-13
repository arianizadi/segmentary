"""Build datasets and dataloaders for one curriculum stage.

Kept separate from the curriculum chain logic so that "what data does this stage
see" is one readable function with no training concerns mixed in.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from torch.utils.data import DataLoader

from ..config import AugConfigSpec, DataConfig, StageConfig, TrainConfig
from ..taxonomy import LabelSpace, load_mapping
from ..utils.seed import seed_transforms, worker_init_fn
from .base import SegDataset
from .cityscapes import CityscapesDataset
from .custom import CustomRailDataset
from .folder import FolderSegmentationDataset
from .mixed import MixedDataset, collate
from .railsem19 import RailSem19Dataset
from .transforms import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    AugConfig,
    build_eval_transform,
    build_train_transform,
)

_BUILTIN_LOADERS: dict[str, type[SegDataset]] = {
    "cityscapes": CityscapesDataset,
    "railsem19": RailSem19Dataset,
    "custom": CustomRailDataset,
    "folder": FolderSegmentationDataset,
}


def resolve_dataset_loader(data: DataConfig) -> tuple[str, type[SegDataset]]:
    """Resolve a built-in loader id or an explicit ``module:class`` extension."""
    loader_name = data.loader or data.name
    if loader_name in _BUILTIN_LOADERS:
        return loader_name, _BUILTIN_LOADERS[loader_name]
    if ":" not in loader_name:
        raise ValueError(
            f"unknown dataset loader {loader_name!r} for dataset {data.name!r}. Built-ins are "
            f"{sorted(_BUILTIN_LOADERS)}. For an arbitrary paired dataset set loader: folder; "
            f"for a Python extension use loader: package.module:DatasetClass."
        )
    module_name, class_name = loader_name.split(":", 1)
    if not module_name or not class_name:
        raise ValueError(
            f"dataset loader {loader_name!r} must use the form package.module:DatasetClass"
        )
    try:
        module = importlib.import_module(module_name)
        cls: Any = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        raise ValueError(f"could not import dataset loader {loader_name!r}: {exc}") from exc
    if not isinstance(cls, type) or not issubclass(cls, SegDataset):
        raise ValueError(
            f"dataset loader {loader_name!r} resolved to {cls!r}, expected a SegDataset subclass"
        )
    return loader_name, cls


def load_data_mapping(data: DataConfig, space: LabelSpace, taxonomy_root: Path | str):
    """Load a mapping independently of the dataset's logical name or loader."""
    mapping = load_mapping(taxonomy_root, space, data.mapping or data.name, data.variant)
    if mapping.dataset != data.name:
        # ``data.name`` is the stable experiment identity used by mixed sampling,
        # active masks, logs, and result rows. The optional mapping filename is
        # merely a reusable source of native-id semantics.
        mapping = replace(mapping, dataset=data.name)
    return mapping


def input_normalization(model: object | None = None) -> dict[str, Any]:
    """Return the effective, recordable pixel preprocessing for a model."""
    mean = getattr(model, "input_mean", None) or IMAGENET_MEAN
    std = getattr(model, "input_std", None) or IMAGENET_STD
    channel_order = getattr(model, "input_channel_order", "rgb")
    return {
        "mean": [float(value) for value in mean],
        "std": [float(value) for value in std],
        "channel_order": channel_order,
        "source": getattr(model, "input_normalization_source", None)
        or ("hf_image_processor" if hasattr(model, "input_mean") else "imagenet"),
    }


def aug_from_spec(spec: AugConfigSpec, model: object | None = None) -> AugConfig:
    normalization = input_normalization(model)
    return AugConfig(
        crop=tuple(spec.crop),
        scale_min=spec.scale_min,
        scale_max=spec.scale_max,
        hflip_p=spec.hflip_p,
        color_jitter_p=spec.color_jitter_p,
        brightness=spec.brightness,
        contrast=spec.contrast,
        saturation=spec.saturation,
        hue=spec.hue,
        mean=tuple(normalization["mean"]),
        std=tuple(normalization["std"]),
        channel_order=normalization["channel_order"],
    )


def build_dataset(
    data: DataConfig,
    space: LabelSpace,
    taxonomy_root: Path | str,
    split: str,
    transform,
) -> SegDataset:
    """Instantiate one dataset with its validated taxonomy mapping."""
    loader_name, cls = resolve_dataset_loader(data)
    mapping = load_data_mapping(data, space, taxonomy_root)
    options = dict(data.loader_options)
    reserved = {"root", "split", "mapping", "transform", "limit", "split_file"} & set(options)
    if reserved:
        raise ValueError(
            f"dataset {data.name!r} loader_options cannot override core arguments "
            f"{sorted(reserved)}"
        )

    if loader_name == "railsem19":
        if not data.split_file:
            raise ValueError(
                "railsem19 needs an explicit split_file: the dataset ships no official "
                "split, so leaving it implicit makes the run irreproducible"
            )
        options["split_file"] = data.split_file
    elif data.split_file is not None:
        options["split_file"] = data.split_file
    try:
        return cls(data.root, split, mapping, transform, limit=data.limit, **options)
    except TypeError as exc:
        raise ValueError(
            f"dataset {data.name!r} loader {loader_name!r} rejected loader_options "
            f"{sorted(options)}: {exc}"
        ) from exc


def build_train_loader(
    stage: StageConfig,
    space: LabelSpace,
    taxonomy_root: Path | str,
    aug: AugConfigSpec,
    train: TrainConfig,
    model: object | None = None,
) -> DataLoader:
    """Training loader for a stage, mixing datasets when the stage lists several."""
    transform = build_train_transform(aug_from_spec(aug, model))
    datasets = [
        build_dataset(d, space, taxonomy_root, d.train_split, transform) for d in stage.data
    ]

    common = dict(
        batch_size=train.batch_size,
        num_workers=train.num_workers,
        collate_fn=collate,
        pin_memory=True,
        drop_last=True,
        persistent_workers=train.num_workers > 0,
        worker_init_fn=worker_init_fn,
        prefetch_factor=4 if train.num_workers > 0 else None,
    )

    if len(datasets) == 1:
        loader = DataLoader(datasets[0], shuffle=True, **common)
    else:
        mixed = MixedDataset(datasets)
        # Iteration-based training means "epoch length" only needs to exceed the
        # gap between validations; the sampler draws with replacement anyway.
        num_samples = max(len(mixed), train.val_every * train.batch_size)
        sampler = mixed.sampler(stage.sample_weights, num_samples=num_samples, seed=train.seed)
        if sampler is None:
            loader = DataLoader(mixed, shuffle=True, **common)
        else:
            loader = DataLoader(mixed, sampler=sampler, **common)

    if train.num_workers == 0:
        # worker_init_fn only runs inside a worker process, so with in-process
        # loading albumentations keeps the OS-entropy seed it drew when the
        # Compose was built and the augmentation stream does not follow
        # train.seed -- silently, while the run still looks healthy.
        seed_transforms(loader.dataset, train.seed)
    return loader


def build_val_loader(
    stage: StageConfig,
    space: LabelSpace,
    taxonomy_root: Path | str,
    aug: AugConfigSpec,
    train: TrainConfig,
    batch_size: int = 1,
    model: object | None = None,
) -> tuple[DataLoader, SegDataset]:
    """Validation loader at NATIVE resolution.

    Validation never crops: native images may be larger than training crops, and
    crop-only scoring would measure a different task. Sliding-window inference
    handles the size.

    A stage with several datasets validates on the FIRST one, so a curriculum's
    stages remain individually interpretable; cross-dataset evaluation is the job
    of eval.py, not of the training loop.
    """
    transform = build_eval_transform(aug_from_spec(aug, model))
    data = stage.data[0]
    dataset = build_dataset(data, space, taxonomy_root, data.val_split, transform)
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=min(train.num_workers, 4),
        collate_fn=collate,
        pin_memory=True,
        drop_last=False,
        worker_init_fn=worker_init_fn,
    )
    return loader, dataset


def validation_active_mask(stage: StageConfig, space: LabelSpace, taxonomy_root: Path | str):
    """Active classes for the dataset used by this stage's validation loader.

    A mixed stage trains on the union of its datasets but, by contract,
    :func:`build_val_loader` evaluates only the first dataset. Using the training
    union here would score classes that the validation dataset cannot label as
    false-positive zeros and silently depress its native mIoU.
    """
    import torch

    mapping = load_data_mapping(stage.data[0], space, taxonomy_root)
    return torch.from_numpy(mapping.active_mask())


def stage_active_mask(stage: StageConfig, space: LabelSpace, taxonomy_root: Path | str):
    """Union of training-active classes across a stage's datasets.

    Kept for callers that need the historical stage-wide training mask. In-training
    validation must use :func:`validation_active_mask`, because it evaluates only
    the first dataset.
    """
    import torch

    out = torch.zeros(space.num_classes, dtype=torch.bool)
    for data in stage.data:
        mapping = load_data_mapping(data, space, taxonomy_root)
        out |= torch.from_numpy(mapping.active_mask())
    return out
