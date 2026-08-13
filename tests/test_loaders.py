"""Dataset-loader tests for the cross-dataset curriculum contract.

The fixtures use the real on-disk layouts and shipped taxonomy mappings.  They
are deliberately different sizes so a sampler that weights individual examples
instead of whole datasets gives a measurably wrong answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from segmentary.config import AugConfigSpec, DataConfig, StageConfig, TrainConfig
from segmentary.data.cityscapes import CityscapesDataset
from segmentary.data.custom import CustomRailDataset
from segmentary.data.folder import FolderSegmentationDataset
from segmentary.data.loaders import (
    build_dataset,
    build_train_loader,
    build_val_loader,
    stage_active_mask,
    validation_active_mask,
)
from segmentary.data.railsem19 import RailSem19Dataset
from segmentary.data.transforms import AugConfig, build_eval_transform
from segmentary.taxonomy import load_mapping, load_space


def _save_pair(image: Path, label: Path, shape: tuple[int, int], native_id: int) -> None:
    image.parent.mkdir(parents=True, exist_ok=True)
    label.parent.mkdir(parents=True, exist_ok=True)
    h, w = shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[..., 0] = native_id
    Image.fromarray(rgb, mode="RGB").save(image)
    Image.fromarray(np.full((h, w), native_id, dtype=np.uint8), mode="L").save(label)


def _make_cityscapes(root: Path, split: str, count: int, shape: tuple[int, int] = (12, 18)) -> None:
    for i in range(count):
        stem = f"toy_000000_{i:06d}"
        _save_pair(
            root / "leftImg8bit" / split / "toy" / f"{stem}_leftImg8bit.png",
            root / "gtFine" / split / "toy" / f"{stem}_gtFine_labelIds.png",
            shape,
            native_id=7,  # Cityscapes road
        )


def _make_railsem19(
    root: Path,
    split_file: Path,
    splits: dict[str, list[str]],
    shape: tuple[int, int] = (12, 18),
) -> None:
    keys = sorted({key for values in splits.values() for key in values})
    for key in keys:
        _save_pair(
            root / "jpgs" / "rs19_val" / f"{key}.jpg",
            root / "uint8" / "rs19_val" / f"{key}.png",
            shape,
            native_id=0,
        )
    split_file.write_text(json.dumps(splits))


def _make_custom(root: Path, split: str = "train") -> None:
    key = "run01_frame0001"
    _save_pair(
        root / "images" / split / f"{key}.png",
        root / "masks" / split / f"{key}.png",
        (12, 18),
        native_id=0,
    )
    (root / "splits.json").write_text(json.dumps({split: [key], "groups": {key: "run01"}}))


@pytest.fixture
def tiny_data(tmp_path: Path) -> dict[str, Path]:
    city = tmp_path / "cityscapes"
    rail = tmp_path / "railsem19"
    custom = tmp_path / "custom"
    split_file = tmp_path / "rail_splits.json"

    # Unequal sizes are intentional: natural sampling is 20/80, while the
    # weighted test below asks for 80/20.
    _make_cityscapes(city, "train", 2)
    _make_cityscapes(city, "val", 1, shape=(37, 53))
    _make_railsem19(
        rail,
        split_file,
        {
            "train": [f"rs{i:05d}" for i in range(8)],
            "val": ["rs99999"],
        },
    )
    _make_custom(custom)
    return {"city": city, "rail": rail, "custom": custom, "split": split_file}


def _eval_transform():
    return build_eval_transform(AugConfig())


def test_build_dataset_dispatches_all_supported_names(
    taxonomy_root: Path, tiny_data: dict[str, Path]
) -> None:
    space = load_space(taxonomy_root, "rail_union")
    cases = [
        (
            DataConfig(name="cityscapes", root=str(tiny_data["city"])),
            CityscapesDataset,
        ),
        (
            DataConfig(
                name="railsem19",
                root=str(tiny_data["rail"]),
                split_file=str(tiny_data["split"]),
            ),
            RailSem19Dataset,
        ),
        (
            DataConfig(name="custom", root=str(tiny_data["custom"])),
            CustomRailDataset,
        ),
    ]

    for data, expected_type in cases:
        dataset = build_dataset(data, space, taxonomy_root, "train", _eval_transform())
        assert type(dataset) is expected_type
        assert len(dataset) > 0
        assert dataset.name == data.name


def test_build_dataset_rejects_unknown_name_before_touching_the_root(
    taxonomy_root: Path,
) -> None:
    space = load_space(taxonomy_root, "rail_union")
    data = DataConfig(name="imaginary", root="/definitely/not/a/dataset")
    with pytest.raises(ValueError, match=r"unknown dataset loader 'imaginary'.*loader: folder"):
        build_dataset(data, space, taxonomy_root, "train", _eval_transform())


def test_loader_options_cannot_duplicate_split_file(taxonomy_root: Path) -> None:
    space = load_space(taxonomy_root, "rail_union")
    data = DataConfig(
        name="railsem19",
        root="/unused",
        split_file="manifest.json",
        loader_options={"split_file": "other.json"},
    )
    with pytest.raises(ValueError, match=r"cannot override core arguments.*split_file"):
        build_dataset(data, space, taxonomy_root, "train", _eval_transform())


def test_generic_folder_loader_decouples_logical_name_mapping_and_layout(
    tmp_path: Path, tmp_space
) -> None:
    taxonomy = tmp_space(
        mapping={
            "map": {0: 0, 1: 1},
            "source": "synthetic indexed masks",
        }
    )
    space = load_space(taxonomy, "toy")
    root = tmp_path / "photos"
    _save_pair(
        root / "rgb" / "train" / "nested" / "sample.jpg",
        root / "labels" / "train" / "nested" / "sample.png",
        (9, 13),
        native_id=1,
    )
    data = DataConfig(
        name="warehouse_photos",
        root=str(root),
        loader="folder",
        mapping="toy_ds",
        loader_options={
            "image_dir": "rgb/{split}",
            "mask_dir": "labels/{split}",
            "recursive": True,
        },
    )

    dataset = build_dataset(data, space, taxonomy, "train", _eval_transform())

    assert type(dataset) is FolderSegmentationDataset
    assert dataset.name == "warehouse_photos"
    assert dataset.samples[0].key == "nested/sample"
    sample = dataset[0]
    assert sample["dataset"] == "warehouse_photos"
    assert tuple(sample["mask"].shape) == (9, 13)
    assert set(sample["mask"].unique().tolist()) == {1}


def test_generic_loader_accepts_an_import_path(tmp_path: Path, tmp_space) -> None:
    taxonomy = tmp_space(mapping={"map": {0: 0}})
    space = load_space(taxonomy, "toy")
    root = tmp_path / "imported"
    _save_pair(
        root / "images" / "train" / "sample.png",
        root / "masks" / "train" / "sample.png",
        (7, 11),
        native_id=0,
    )
    dataset = build_dataset(
        DataConfig(
            name="imported_dataset",
            root=str(root),
            loader="segmentary.data.folder:FolderSegmentationDataset",
            mapping="toy_ds",
        ),
        space,
        taxonomy,
        "train",
        _eval_transform(),
    )
    assert type(dataset) is FolderSegmentationDataset
    assert dataset.name == "imported_dataset"


def test_folder_manifest_rejects_a_group_crossing_splits(tmp_path: Path, tmp_space) -> None:
    taxonomy = tmp_space(mapping={"map": {0: 0}})
    space = load_space(taxonomy, "toy")
    root = tmp_path / "leaky"
    _save_pair(
        root / "images" / "train" / "run1_frame1.png",
        root / "masks" / "train" / "run1_frame1.png",
        (7, 11),
        native_id=0,
    )
    (root / "splits.json").write_text(
        json.dumps(
            {
                "train": ["run1_frame1"],
                "val": ["run1_frame2"],
                "groups": {"run1_frame1": "run1", "run1_frame2": "run1"},
            }
        ),
        encoding="utf-8",
    )
    data = DataConfig(
        name="video_frames",
        root=str(root),
        loader="folder",
        mapping="toy_ds",
        loader_options={"require_groups": True},
    )
    with pytest.raises(ValueError, match=r"share groups.*leaks related samples"):
        build_dataset(data, space, taxonomy, "train", _eval_transform())


def test_folder_manifest_requires_the_requested_split(tmp_path: Path, tmp_space) -> None:
    taxonomy = tmp_space(mapping={"map": {0: 0}})
    space = load_space(taxonomy, "toy")
    root = tmp_path / "missing-split"
    _save_pair(
        root / "images" / "train" / "frame.png",
        root / "masks" / "train" / "frame.png",
        (7, 11),
        native_id=0,
    )
    (root / "splits.json").write_text(json.dumps({"val": [], "groups": {}}), encoding="utf-8")
    data = DataConfig(name="frames", root=str(root), loader="folder", mapping="toy_ds")
    with pytest.raises(ValueError, match="requested split 'train' is absent"):
        build_dataset(data, space, taxonomy, "train", _eval_transform())


def test_folder_manifest_requires_groups_for_every_split(tmp_path: Path, tmp_space) -> None:
    taxonomy = tmp_space(mapping={"map": {0: 0}})
    space = load_space(taxonomy, "toy")
    root = tmp_path / "partly-grouped"
    _save_pair(
        root / "images" / "train" / "train_frame.png",
        root / "masks" / "train" / "train_frame.png",
        (7, 11),
        native_id=0,
    )
    (root / "splits.json").write_text(
        json.dumps(
            {
                "train": ["train_frame"],
                "val": ["val_frame"],
                "groups": {"train_frame": "run_train"},
            }
        ),
        encoding="utf-8",
    )
    data = DataConfig(
        name="video_frames",
        root=str(root),
        loader="folder",
        mapping="toy_ds",
        loader_options={"require_groups": True},
    )

    with pytest.raises(ValueError, match=r"1 manifest keys have no group.*val_frame"):
        build_dataset(data, space, taxonomy, "train", _eval_transform())


def test_folder_loader_rejects_duplicate_relative_stems(tmp_path: Path, tmp_space) -> None:
    taxonomy = tmp_space(mapping={"map": {0: 0}})
    space = load_space(taxonomy, "toy")
    root = tmp_path / "duplicates"
    _save_pair(
        root / "images" / "train" / "frame.jpg",
        root / "masks" / "train" / "frame.png",
        (7, 11),
        native_id=0,
    )
    image = np.zeros((7, 11, 3), dtype=np.uint8)
    Image.fromarray(image, mode="RGB").save(root / "images" / "train" / "frame.png")
    data = DataConfig(name="frames", root=str(root), loader="folder", mapping="toy_ds")
    with pytest.raises(ValueError, match="multiple images resolve to key 'frame'"):
        build_dataset(data, space, taxonomy, "train", _eval_transform())


@pytest.mark.parametrize("orphan_kind", ["image", "mask"])
def test_folder_loader_requires_pairs_in_both_directions(
    tmp_path: Path, tmp_space, orphan_kind: str
) -> None:
    taxonomy = tmp_space(mapping={"map": {0: 0}})
    space = load_space(taxonomy, "toy")
    root = tmp_path / orphan_kind
    _save_pair(
        root / "images" / "train" / "paired.png",
        root / "masks" / "train" / "paired.png",
        (7, 11),
        native_id=0,
    )
    if orphan_kind == "image":
        Image.fromarray(np.zeros((7, 11, 3), dtype=np.uint8), mode="RGB").save(
            root / "images" / "train" / "orphan.png"
        )
    else:
        Image.fromarray(np.zeros((7, 11), dtype=np.uint8), mode="L").save(
            root / "masks" / "train" / "orphan.png"
        )
    data = DataConfig(name="frames", root=str(root), loader="folder", mapping="toy_ds")

    with pytest.raises(FileNotFoundError, match=r"not one-to-one.*orphan"):
        build_dataset(data, space, taxonomy, "train", _eval_transform())


def test_folder_loader_rejects_unapproved_format_placeholders(tmp_path: Path, tmp_space) -> None:
    taxonomy = tmp_space(mapping={"map": {0: 0}})
    space = load_space(taxonomy, "toy")
    root = tmp_path / "bad-template"
    root.mkdir()
    data = DataConfig(
        name="frames",
        root=str(root),
        loader="folder",
        mapping="toy_ds",
        loader_options={"image_dir": "images/{split.__class__}"},
    )
    with pytest.raises(ValueError, match=r"only the \{split\} placeholder"):
        build_dataset(data, space, taxonomy, "train", _eval_transform())


def test_railsem19_requires_an_explicit_split_file(taxonomy_root: Path, tmp_path: Path) -> None:
    space = load_space(taxonomy_root, "rail_union")
    data = DataConfig(name="railsem19", root=str(tmp_path))
    with pytest.raises(ValueError, match=r"explicit split_file.*reproducible"):
        build_dataset(data, space, taxonomy_root, "train", _eval_transform())


def _joint_stage(tiny_data: dict[str, Path], city_weight: float) -> StageConfig:
    return StageConfig(
        name="joint",
        data=[
            DataConfig(name="cityscapes", root=str(tiny_data["city"])),
            DataConfig(
                name="railsem19",
                root=str(tiny_data["rail"]),
                split_file=str(tiny_data["split"]),
            ),
        ],
        sample_weights={"cityscapes": city_weight, "railsem19": 1.0 - city_weight},
    )


def _no_random_aug() -> AugConfigSpec:
    return AugConfigSpec(
        crop=(12, 18),
        scale_min=1.0,
        scale_max=1.0,
        hflip_p=0.0,
        color_jitter_p=0.0,
    )


def test_mixed_batch_keeps_a_different_active_mask_per_sample(
    taxonomy_root: Path, tiny_data: dict[str, Path]
) -> None:
    space = load_space(taxonomy_root, "rail_union")
    loader = build_train_loader(
        _joint_stage(tiny_data, city_weight=0.5),
        space,
        taxonomy_root,
        _no_random_aug(),
        TrainConfig(batch_size=16, num_workers=0, val_every=2, seed=0),
    )

    batch = next(iter(loader))
    assert batch["active"].shape == (16, space.num_classes)
    assert batch["active"].dtype == torch.bool
    assert set(batch["dataset"]) == {"cityscapes", "railsem19"}

    expected = {
        name: torch.from_numpy(load_mapping(taxonomy_root, space, name).active_mask())
        for name in ("cityscapes", "railsem19")
    }
    for row, dataset_name in zip(batch["active"], batch["dataset"], strict=True):
        assert torch.equal(row, expected[dataset_name])
    assert not torch.equal(expected["cityscapes"], expected["railsem19"])


def test_sample_weights_control_dataset_ratio_not_individual_example_weight(
    taxonomy_root: Path, tiny_data: dict[str, Path]
) -> None:
    space = load_space(taxonomy_root, "rail_union")
    loader = build_train_loader(
        _joint_stage(tiny_data, city_weight=0.8),
        space,
        taxonomy_root,
        _no_random_aug(),
        TrainConfig(batch_size=20, num_workers=0, val_every=100, seed=11),
    )

    drawn = [name for batch in loader for name in batch["dataset"]]
    city_fraction = drawn.count("cityscapes") / len(drawn)
    assert len(drawn) == 2000
    assert city_fraction == pytest.approx(0.8, abs=0.04)
    # With plain concatenation the deliberately unequal fixture is 2/(2+8)=20%.
    assert city_fraction > 0.7


def test_validation_loader_uses_native_resolution_not_training_crop(
    taxonomy_root: Path, tiny_data: dict[str, Path]
) -> None:
    space = load_space(taxonomy_root, "rail_union")
    stage = StageConfig(
        name="city",
        data=[DataConfig(name="cityscapes", root=str(tiny_data["city"]))],
    )
    loader, dataset = build_val_loader(
        stage,
        space,
        taxonomy_root,
        AugConfigSpec(crop=(8, 8)),
        TrainConfig(num_workers=0),
    )

    batch = next(iter(loader))
    assert dataset.split == "val"
    assert batch["image"].shape == (1, 3, 37, 53)
    assert batch["mask"].shape == (1, 37, 53)


def test_mixed_stage_validation_scores_only_the_first_dataset_active_classes(
    taxonomy_root: Path, tiny_data: dict[str, Path]
) -> None:
    space = load_space(taxonomy_root, "rail_union")
    stage = _joint_stage(tiny_data, city_weight=0.5)

    actual = validation_active_mask(stage, space, taxonomy_root)
    city = torch.from_numpy(load_mapping(taxonomy_root, space, "cityscapes").active_mask())
    rail = torch.from_numpy(load_mapping(taxonomy_root, space, "railsem19").active_mask())

    assert torch.equal(actual, city)
    assert not torch.equal(actual, city | rail)
    assert actual[space.names.index("rail-raised")].item() is False
    assert torch.equal(stage_active_mask(stage, space, taxonomy_root), city | rail)
