"""Adversarial dataset-contract tests for manifests, pairs, and mixed sampling."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
from albumentations import Compose

from segmentary.data.base import Sample, SegDataset
from segmentary.data.cityscapes import CityscapesDataset, cityscapes_root
from segmentary.data.custom import CustomRailDataset
from segmentary.data.folder import FolderSegmentationDataset
from segmentary.data.mixed import MixedDataset
from segmentary.data.railsem19 import RailSem19Dataset
from segmentary.taxonomy import CanonicalClass, DatasetMapping, LabelSpace


def _space(name: str = "toy", class_names: tuple[str, ...] = ("ground", "rail")) -> LabelSpace:
    return LabelSpace(
        name=name,
        description="test label space",
        ignore_index=255,
        classes=tuple(
            CanonicalClass(id=index, name=class_name, color=(index, index, index))
            for index, class_name in enumerate(class_names)
        ),
        thin_classes=(),
    )


def _mapping(dataset: str = "toy", space: LabelSpace | None = None) -> DatasetMapping:
    resolved = space or _space()
    lut = np.full(256, resolved.ignore_index, dtype=np.uint8)
    lut[: resolved.num_classes] = np.arange(resolved.num_classes, dtype=np.uint8)
    return DatasetMapping(
        space=resolved,
        dataset=dataset,
        source="test mapping",
        variant=None,
        lut=lut,
        active_ids=tuple(range(resolved.num_classes)),
        merges={},
    )


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixture")


def _folder_pair(root: Path, key: str, split: str = "train") -> None:
    _touch(root / "images" / split / f"{key}.jpg")
    _touch(root / "masks" / split / f"{key}.png")


def _folder_dataset(root: Path, **kwargs) -> FolderSegmentationDataset:
    return FolderSegmentationDataset(root, "train", _mapping(), Compose([]), **kwargs)


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{", "cannot read valid JSON"),
        ("[]", "must contain a JSON object"),
        (json.dumps({"train": "frame", "groups": {}}), "split 'train' must be a list"),
        (
            json.dumps({"train": ["frame"], "groups": {"frame": " "}}),
            "groups must map string keys to group names",
        ),
    ],
    ids=["invalid-json", "non-object", "non-list-split", "blank-group"],
)
def test_folder_manifest_rejects_malformed_contracts(
    tmp_path: Path, contents: str, message: str
) -> None:
    _folder_pair(tmp_path, "frame")
    (tmp_path / "splits.json").write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _folder_dataset(tmp_path)


@pytest.mark.parametrize(
    "manifest",
    [
        {"train": ["frame", "frame"], "groups": {"frame": "run"}},
        {
            "train": ["frame"],
            "val": ["frame"],
            "groups": {"frame": "run"},
        },
    ],
    ids=["within-split", "across-splits"],
)
def test_folder_manifest_rejects_duplicate_frame_membership(tmp_path: Path, manifest: dict) -> None:
    _folder_pair(tmp_path, "frame")
    (tmp_path / "splits.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=r"duplicate keys|share groups"):
        _folder_dataset(tmp_path)


def test_folder_manifest_normalizes_groups_before_leakage_check(tmp_path: Path) -> None:
    _folder_pair(tmp_path, "train_frame")
    manifest = {
        "train": ["train_frame"],
        "val": ["val_frame"],
        "groups": {"train_frame": "run-7", "val_frame": " run-7 "},
    }
    (tmp_path / "splits.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=r"share groups.*run-7"):
        _folder_dataset(tmp_path, require_groups=True)


@pytest.mark.parametrize(
    ("manifest_keys", "message"),
    [(["declared", "missing"], r"missing=\['missing'\]"), ([], r"extra=\['declared'\]")],
    ids=["manifest-only", "disk-only"],
)
def test_folder_manifest_and_selected_split_disk_must_match_exactly(
    tmp_path: Path, manifest_keys: list[str], message: str
) -> None:
    _folder_pair(tmp_path, "declared")
    (tmp_path / "splits.json").write_text(
        json.dumps({"train": manifest_keys, "groups": {key: "run" for key in manifest_keys}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        _folder_dataset(tmp_path)


def test_folder_require_groups_refuses_unmanifested_video_frames(tmp_path: Path) -> None:
    _folder_pair(tmp_path, "run7/frame001")

    with pytest.raises(FileNotFoundError, match=r"require_groups=true needs split_file"):
        _folder_dataset(tmp_path, require_groups=True)


def test_folder_group_counts_use_manifest_groups_not_frame_keys(tmp_path: Path) -> None:
    for key in ("run7/frame001", "run7/frame002", "run8/frame001"):
        _folder_pair(tmp_path, key)
    manifest = {
        "train": ["run7/frame001", "run7/frame002", "run8/frame001"],
        "groups": {
            "run7/frame001": "run7",
            "run7/frame002": "run7",
            "run8/frame001": "run8",
        },
    }
    (tmp_path / "splits.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert _folder_dataset(tmp_path, require_groups=True).group_counts() == {
        "run7": 2,
        "run8": 1,
    }


class _MemberDataset(SegDataset):
    def __init__(self, root: Path, mapping: DatasetMapping, length: int) -> None:
        self._length = length
        super().__init__(root, "train", mapping, Compose([]))

    def index(self) -> list[Sample]:
        return [
            Sample(
                image=self.root / f"{index}.jpg",
                label=self.root / f"{index}.png",
                key=f"{self.name}-{index}",
                group=f"{self.name}-{index}",
            )
            for index in range(self._length)
        ]


def _member(tmp_path: Path, name: str, *, space: LabelSpace, length: int = 2) -> _MemberDataset:
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    return _MemberDataset(root, _mapping(name, space), length)


def test_mixed_dataset_rejects_same_named_but_semantically_different_spaces(
    tmp_path: Path,
) -> None:
    first = _member(tmp_path, "first", space=_space("shared", ("ground", "rail")))
    second = _member(tmp_path, "second", space=_space("shared", ("rail", "ground")))

    with pytest.raises(ValueError, match=r"share one label space|different things"):
        MixedDataset([first, second])


def test_mixed_dataset_rejects_duplicate_member_names(tmp_path: Path) -> None:
    space = _space()
    first = _member(tmp_path, "first", space=space)
    second_root = tmp_path / "second-copy"
    second_root.mkdir()
    second = _MemberDataset(second_root, _mapping("first", space), 1)

    with pytest.raises(ValueError, match="duplicate dataset names"):
        MixedDataset([first, second])


def test_mixed_dataset_requires_at_least_one_member() -> None:
    with pytest.raises(ValueError, match="at least one dataset"):
        MixedDataset([])


@pytest.mark.parametrize(
    ("weights", "message"),
    [
        ({"a": 1.0, "b": 1.0, "ghost": 1.0}, "unknown datasets.*ghost"),
        ({"a": 1.0}, "weights omit.*b"),
    ],
    ids=["unknown", "missing"],
)
def test_mixed_sampler_weight_names_must_match_members_exactly(
    tmp_path: Path, weights: dict[str, float], message: str
) -> None:
    space = _space()
    mixed = MixedDataset([_member(tmp_path, "a", space=space), _member(tmp_path, "b", space=space)])

    with pytest.raises(ValueError, match=message):
        mixed.sampler(weights, num_samples=10)


@pytest.mark.parametrize(
    "invalid_weight",
    [True, "1", 0.0, -1.0, float("nan"), float("inf")],
    ids=["bool", "string", "zero", "negative", "nan", "infinite"],
)
def test_mixed_sampler_rejects_nonfinite_or_nonpositive_numeric_contract(
    tmp_path: Path, invalid_weight: object
) -> None:
    space = _space()
    mixed = MixedDataset(
        [_member(tmp_path, "short", space=space, length=1), _member(tmp_path, "long", space=space)]
    )

    with pytest.raises(ValueError, match="sampler weights must be finite positive numbers"):
        mixed.sampler({"short": 1.0, "long": invalid_weight}, num_samples=10)


@pytest.mark.parametrize("num_samples", [0, -1, True, 1.5])
def test_mixed_sampler_requires_a_positive_integer_draw_count(
    tmp_path: Path, num_samples: object
) -> None:
    space = _space()
    mixed = MixedDataset([_member(tmp_path, "a", space=space), _member(tmp_path, "b", space=space)])

    with pytest.raises(ValueError, match="num_samples must be a positive integer"):
        mixed.sampler({"a": 1.0, "b": 1.0}, num_samples=num_samples)


def test_mixed_sampler_assigns_dataset_share_independent_of_member_size(tmp_path: Path) -> None:
    space = _space()
    mixed = MixedDataset(
        [
            _member(tmp_path, "short", space=space, length=1),
            _member(tmp_path, "long", space=space, length=9),
        ]
    )

    sampler = mixed.sampler({"short": 4.0, "long": 1.0}, num_samples=200, seed=19)
    assert sampler is not None
    assert sampler.weights[:1].sum().item() == pytest.approx(0.8)
    assert sampler.weights[1:].sum().item() == pytest.approx(0.2)
    assert list(sampler) == list(
        mixed.sampler({"short": 4.0, "long": 1.0}, num_samples=200, seed=19)
    )


def _city_pair(root: Path, stem: str, *, split: str = "train", city: str = "toy") -> None:
    _touch(root / "leftImg8bit" / split / city / f"{stem}_leftImg8bit.png")
    _touch(root / "gtFine" / split / city / f"{stem}_gtFine_labelIds.png")


@pytest.mark.parametrize("orphan", ["image", "label"])
def test_cityscapes_requires_image_label_pairs_in_both_directions(
    tmp_path: Path, orphan: str
) -> None:
    _city_pair(tmp_path, "toy_000000_000001")
    stem = "toy_000000_000002"
    if orphan == "image":
        _touch(tmp_path / "leftImg8bit" / "train" / "toy" / f"{stem}_leftImg8bit.png")
    else:
        _touch(tmp_path / "gtFine" / "train" / "toy" / f"{stem}_gtFine_labelIds.png")

    with pytest.raises(FileNotFoundError, match=rf"{orphan}.*no matching|no matching.*{orphan}"):
        CityscapesDataset(tmp_path, "train", _mapping(), Compose([]))


def test_cityscapes_rejects_server_only_test_split_before_indexing(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match=r"test.*blank labels.*meaningless"):
        CityscapesDataset(tmp_path, "test", _mapping(), Compose([]))


def test_cityscapes_root_requires_both_halves_of_nested_layout(tmp_path: Path) -> None:
    (tmp_path / "cityscapes" / "leftImg8bit").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match=r"leftImg8bit/ and gtFine/"):
        cityscapes_root(tmp_path)


@pytest.mark.parametrize("missing", ["leftImg8bit", "gtFine"])
def test_cityscapes_dataset_reports_missing_split_directory(tmp_path: Path, missing: str) -> None:
    present = "gtFine" if missing == "leftImg8bit" else "leftImg8bit"
    (tmp_path / present / "train").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match=rf"expected directory .*{missing}/train"):
        CityscapesDataset(tmp_path, "train", _mapping(), Compose([]))


def _rail_dirs(root: Path) -> tuple[Path, Path]:
    images = root / "jpgs" / "rs19_val"
    labels = root / "uint8" / "rs19_val"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    return images, labels


def _rail_dataset(root: Path, split_file: Path) -> RailSem19Dataset:
    return RailSem19Dataset(
        root,
        "train",
        _mapping("railsem19"),
        Compose([]),
        split_file=split_file,
    )


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{", "cannot read valid JSON"),
        ("[]", "must contain a JSON object"),
        (json.dumps({"train": "rs00001"}), "split 'train' must be a list"),
        (json.dumps({"train": [7]}), "split 'train' must be a list"),
    ],
    ids=["invalid-json", "non-object", "non-list", "non-string-key"],
)
def test_railsem19_rejects_malformed_split_manifests(
    tmp_path: Path, contents: str, message: str
) -> None:
    root = tmp_path / "rail"
    root.mkdir()
    split_file = tmp_path / "splits.json"
    split_file.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _rail_dataset(root, split_file)


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ({"train": ["rs00001", "rs00001"]}, "contains duplicate frame ids"),
        ({"train": ["rs00001"], "val": ["rs00001"]}, "share frame ids"),
    ],
    ids=["within-split", "across-splits"],
)
def test_railsem19_rejects_duplicate_or_cross_split_frames(
    tmp_path: Path, manifest: dict, message: str
) -> None:
    root = tmp_path / "rail"
    root.mkdir()
    split_file = tmp_path / "splits.json"
    split_file.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _rail_dataset(root, split_file)


@pytest.mark.parametrize("missing", ["image", "label"])
def test_railsem19_manifest_entries_require_both_files(tmp_path: Path, missing: str) -> None:
    root = tmp_path / "rail"
    images, labels = _rail_dirs(root)
    if missing != "image":
        _touch(images / "rs00001.jpg")
    if missing != "label":
        _touch(labels / "rs00001.png")
    split_file = tmp_path / "splits.json"
    split_file.write_text(json.dumps({"train": ["rs00001"]}), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match=r"1 frames.*first is rs00001"):
        _rail_dataset(root, split_file)


def test_railsem19_reports_missing_manifest_and_requested_split(tmp_path: Path) -> None:
    root = tmp_path / "rail"
    root.mkdir()
    split_file = tmp_path / "splits.json"

    with pytest.raises(FileNotFoundError, match="split file not found"):
        _rail_dataset(root, split_file)

    split_file.write_text(json.dumps({"val": []}), encoding="utf-8")
    with pytest.raises(KeyError, match=r"defines splits \['val'\].*not 'train'"):
        _rail_dataset(root, split_file)


@pytest.mark.parametrize("missing", ["jpgs", "uint8"])
def test_railsem19_reports_missing_dataset_half(tmp_path: Path, missing: str) -> None:
    root = tmp_path / "rail"
    images, labels = _rail_dirs(root)
    if missing == "jpgs":
        images.rmdir()
        images.parent.rmdir()
    else:
        labels.rmdir()
        labels.parent.rmdir()
    split_file = tmp_path / "splits.json"
    split_file.write_text(json.dumps({"train": ["rs00001"]}), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match=rf"expected directory .*{missing}"):
        _rail_dataset(root, split_file)


def _custom_dirs(root: Path, split: str = "train") -> tuple[Path, Path]:
    images = root / "images" / split
    masks = root / "masks" / split
    images.mkdir(parents=True)
    masks.mkdir(parents=True)
    return images, masks


def _custom_dataset(root: Path) -> CustomRailDataset:
    return CustomRailDataset(root, "train", _mapping("custom"), Compose([]))


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{", "cannot read valid JSON"),
        ("[]", "must contain a JSON object"),
        (json.dumps({"train": "frame", "groups": {}}), "split 'train' must be a list"),
        (json.dumps({"train": ["frame"], "groups": []}), "groups must map"),
    ],
    ids=["invalid-json", "non-object", "non-list-split", "non-object-groups"],
)
def test_custom_manifest_rejects_malformed_contracts(
    tmp_path: Path, contents: str, message: str
) -> None:
    _custom_dirs(tmp_path)
    (tmp_path / "splits.json").write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _custom_dataset(tmp_path)


def test_custom_manifest_requires_an_exact_group_for_every_split_key(tmp_path: Path) -> None:
    _custom_dirs(tmp_path)
    (tmp_path / "splits.json").write_text(
        json.dumps(
            {
                "train": ["train_frame"],
                "val": ["val_frame"],
                "groups": {"train_frame": "run-train", "stale": "run-stale"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match=r"groups do not exactly match.*missing=.*val_frame.*extra=.*stale"
    ):
        _custom_dataset(tmp_path)


def test_custom_manifest_normalizes_groups_before_leakage_check(tmp_path: Path) -> None:
    _custom_dirs(tmp_path)
    (tmp_path / "splits.json").write_text(
        json.dumps(
            {
                "train": ["train_frame"],
                "val": ["val_frame"],
                "groups": {"train_frame": "run-7", "val_frame": " run-7 "},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"share 1 group.*run-7"):
        _custom_dataset(tmp_path)


def test_custom_manifest_rejects_duplicate_keys_within_a_split(tmp_path: Path) -> None:
    _custom_dirs(tmp_path)
    (tmp_path / "splits.json").write_text(
        json.dumps({"train": ["frame", "frame"], "groups": {"frame": "run"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="split 'train' contains duplicate keys"):
        _custom_dataset(tmp_path)


def test_custom_manifest_requires_requested_split(tmp_path: Path) -> None:
    _custom_dirs(tmp_path)
    (tmp_path / "splits.json").write_text(
        json.dumps({"val": ["frame"], "groups": {"frame": "run"}}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="requested split 'train' is absent"):
        _custom_dataset(tmp_path)


def test_custom_selected_split_must_match_manifest_and_disk_exactly(tmp_path: Path) -> None:
    images, masks = _custom_dirs(tmp_path)
    _touch(images / "on_disk.jpg")
    _touch(masks / "on_disk.png")
    (tmp_path / "splits.json").write_text(
        json.dumps({"train": ["declared"], "groups": {"declared": "run"}}),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match=r"does not match disk.*missing=.*declared.*extra=.*on_disk"
    ):
        _custom_dataset(tmp_path)


@pytest.mark.parametrize("orphan", ["image", "mask"])
def test_custom_requires_image_mask_pairs_in_both_directions(tmp_path: Path, orphan: str) -> None:
    images, masks = _custom_dirs(tmp_path)
    _touch(images / "paired.jpg")
    _touch(masks / "paired.png")
    if orphan == "image":
        _touch(images / "orphan.jpg")
    else:
        _touch(masks / "orphan.png")
    keys = ["paired", "orphan"]
    (tmp_path / "splits.json").write_text(
        json.dumps({"train": keys, "groups": {key: f"run-{key}" for key in keys}}),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match=r"not one-to-one.*orphan"):
        _custom_dataset(tmp_path)


def test_custom_rejects_multiple_image_extensions_for_one_key(tmp_path: Path) -> None:
    images, masks = _custom_dirs(tmp_path)
    _touch(images / "frame.jpg")
    _touch(images / "frame.png")
    _touch(masks / "frame.png")
    (tmp_path / "splits.json").write_text(
        json.dumps({"train": ["frame"], "groups": {"frame": "run"}}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="multiple images resolve to key 'frame'"):
        _custom_dataset(tmp_path)


def test_custom_valid_manifest_preserves_group_audit_counts(tmp_path: Path) -> None:
    images, masks = _custom_dirs(tmp_path)
    for key in ("run1_a", "run1_b", "run2_a"):
        _touch(images / f"{key}.jpg")
        _touch(masks / f"{key}.png")
    manifest = {
        "train": ["run1_a", "run1_b", "run2_a"],
        "groups": {"run1_a": "run1", "run1_b": "run1", "run2_a": "run2"},
    }
    (tmp_path / "splits.json").write_text(json.dumps(manifest), encoding="utf-8")

    dataset = _custom_dataset(tmp_path)

    assert [sample.key for sample in dataset.samples] == ["run1_a", "run1_b", "run2_a"]
    assert dataset.group_counts() == {"run1": 2, "run2": 1}
    assert torch.equal(dataset.active, torch.tensor([True, True]))


@pytest.mark.parametrize("missing", ["images", "masks"])
def test_custom_reports_missing_split_directory(tmp_path: Path, missing: str) -> None:
    present = "masks" if missing == "images" else "images"
    (tmp_path / present / "train").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match=rf"expected .*{missing}/train"):
        _custom_dataset(tmp_path)
