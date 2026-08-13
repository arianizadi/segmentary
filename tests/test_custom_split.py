"""The custom dataset must be split by capture run, never by video frame."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from segmentary import make_split as make_custom_split


def _keys(num_groups: int = 6, frames_per_group: int = 3) -> tuple[list[str], dict[str, str]]:
    keys = [
        f"run{group:02d}_frame{frame:04d}"
        for group in range(num_groups)
        for frame in range(frames_per_group)
    ]
    groups = {key: key.split("_", 1)[0] for key in keys}
    return keys, groups


def _source_tree(tmp_path: Path, keys: list[str]) -> tuple[Path, Path]:
    images = tmp_path / "source" / "images"
    masks = tmp_path / "source" / "masks"
    images.mkdir(parents=True)
    masks.mkdir(parents=True)
    for key in keys:
        (images / f"{key}.jpg").write_bytes(b"jpeg-placeholder")
        (masks / f"{key}.png").write_bytes(b"png-placeholder")
    return images, masks


def _split_group_sets(splits: dict[str, list[str]], groups: dict[str, str]) -> dict[str, set[str]]:
    return {name: {groups[key] for key in splits[name]} for name in make_custom_split.SPLIT_NAMES}


def test_frame_split_leaks_but_group_split_does_not() -> None:
    keys, groups = _keys()

    # A plausible frame-random split: shuffle individual frames and hold out a
    # third.  Every run now appears in both train and validation -- exactly the
    # inflated evaluation protocol the utility exists to prevent.
    shuffled = list(keys)
    random.Random(0).shuffle(shuffled)
    n_val = len(shuffled) // 3
    naive = {"train": shuffled[n_val:], "val": shuffled[:n_val]}
    assert {groups[k] for k in naive["train"]} & {groups[k] for k in naive["val"]}

    safe = make_custom_split.split_by_group(keys, groups, seed=17, val_frac=0.20, test_frac=0.20)
    group_sets = _split_group_sets(safe, groups)
    assert not (group_sets["train"] & group_sets["val"])
    assert not (group_sets["train"] & group_sets["test"])
    assert not (group_sets["val"] & group_sets["test"])
    assert set().union(*map(set, safe.values())) == set(keys)


def test_split_is_stable_for_a_seed_and_changes_with_seed() -> None:
    keys, groups = _keys(num_groups=10, frames_per_group=2)
    kwargs = {"val_frac": 0.20, "test_frac": 0.20}
    first = make_custom_split.split_by_group(keys, groups, seed=123, **kwargs)
    repeated = make_custom_split.split_by_group(reversed(keys), groups, seed=123, **kwargs)
    different = make_custom_split.split_by_group(keys, groups, seed=124, **kwargs)
    assert first == repeated
    assert first != different


def test_fractions_count_groups_not_frames() -> None:
    keys = ["long_0", "long_1", "long_2", "short_a", "short_b", "short_c"]
    groups = {
        "long_0": "long",
        "long_1": "long",
        "long_2": "long",
        "short_a": "a",
        "short_b": "b",
        "short_c": "c",
    }
    splits = make_custom_split.split_by_group(keys, groups, seed=0, val_frac=0.25, test_frac=0.25)
    counts = {name: len({groups[key] for key in split}) for name, split in splits.items()}
    assert counts == {"train": 2, "val": 1, "test": 1}


def test_manifest_must_cover_every_frame_exactly(tmp_path: Path) -> None:
    path = tmp_path / "groups.json"
    path.write_text(json.dumps({"a": "run1", "extra": "run2"}))
    with pytest.raises(make_custom_split.SplitError, match=r"missing 1 frame.*unknown frame"):
        make_custom_split.load_group_manifest(path, ["a", "b"])


def test_regex_requires_an_explicit_capture_and_every_key_to_match() -> None:
    with pytest.raises(make_custom_split.SplitError, match="must contain"):
        make_custom_split.groups_from_regex(r"^run[0-9]+", ["run01_frame0001"])
    with pytest.raises(make_custom_split.SplitError, match="did not match"):
        make_custom_split.groups_from_regex(
            r"^(?P<group>run[0-9]+)_", ["run01_frame0001", "bad-frame"]
        )


def test_discovery_rejects_unpaired_files_and_duplicate_stems(tmp_path: Path) -> None:
    images, masks = _source_tree(tmp_path, ["frame1"])
    (images / "orphan.jpg").write_bytes(b"x")
    with pytest.raises(make_custom_split.SplitError, match="lack a PNG mask"):
        make_custom_split.discover_pairs(images, masks)

    (images / "orphan.jpg").unlink()
    (images / "frame1.png").write_bytes(b"x")
    with pytest.raises(make_custom_split.SplitError, match="duplicate image key"):
        make_custom_split.discover_pairs(images, masks)


def test_discovery_rejects_orphan_masks_and_duplicate_mask_stems(tmp_path: Path) -> None:
    images, masks = _source_tree(tmp_path, ["frame1"])
    (masks / "orphan.png").write_bytes(b"x")
    with pytest.raises(make_custom_split.SplitError, match=r"mask\(s\) lack an image"):
        make_custom_split.discover_pairs(images, masks)

    (masks / "orphan.png").unlink()
    nested = masks / "nested"
    nested.mkdir()
    (nested / "frame1.png").write_bytes(b"x")
    with pytest.raises(make_custom_split.SplitError, match="duplicate mask key"):
        make_custom_split.discover_pairs(images, masks)


def test_validate_split_rejects_duplicate_frame_within_one_split() -> None:
    groups = {"a": "run-a", "b": "run-b"}
    splits = {"train": ["a", "a"], "val": ["b"], "test": []}

    with pytest.raises(make_custom_split.SplitError, match=r"frame 'a'.*more than once"):
        make_custom_split.validate_split(splits, groups)


@pytest.mark.parametrize(
    ("splits", "message"),
    [
        ({"train": ["a"], "val": ["a", "b"], "test": []}, "more than one split"),
        ({"train": ["a"], "val": ["b"], "test": []}, "group 'run'.*leaks"),
        ({"train": ["a"], "val": [], "test": []}, "does not cover every frame"),
    ],
    ids=["frame-crossing", "group-crossing", "missing-frame"],
)
def test_validate_split_rejects_frame_and_group_leakage(
    splits: dict[str, list[str]], message: str
) -> None:
    groups = {"a": "run", "b": "run"}

    with pytest.raises(make_custom_split.SplitError, match=message):
        make_custom_split.validate_split(splits, groups)


def test_rounding_held_out_fractions_preserves_train_and_group_disjointness() -> None:
    keys, groups = _keys(num_groups=4, frames_per_group=2)

    # Rounding 4 * .49 twice independently asks for 2 val + 2 test groups.
    # The splitter must give one back to train without splitting any run.
    splits = make_custom_split.split_by_group(keys, groups, seed=3, val_frac=0.49, test_frac=0.49)
    group_sets = _split_group_sets(splits, groups)

    assert {name: len(values) for name, values in group_sets.items()} == {
        "train": 1,
        "val": 2,
        "test": 1,
    }
    assert set().union(*group_sets.values()) == set(groups.values())
    assert sum(len(values) for values in group_sets.values()) == len(set(groups.values()))


def test_rounding_returns_the_more_overrepresented_validation_group_to_train() -> None:
    keys, groups = _keys(num_groups=4, frames_per_group=1)

    splits = make_custom_split.split_by_group(keys, groups, seed=3, val_frac=0.40, test_frac=0.49)

    assert {name: len({groups[key] for key in frames}) for name, frames in splits.items()} == {
        "train": 1,
        "val": 1,
        "test": 2,
    }


def test_nonempty_held_out_splits_need_enough_indivisible_groups() -> None:
    keys, groups = _keys(num_groups=2, frames_per_group=3)

    with pytest.raises(make_custom_split.SplitError, match="need at least 3 groups"):
        make_custom_split.split_by_group(keys, groups, seed=0, val_frac=0.1, test_frac=0.1)


def test_cli_writes_loader_layout_and_provenance_without_copying(tmp_path: Path) -> None:
    keys, groups = _keys(num_groups=5, frames_per_group=2)
    images, masks = _source_tree(tmp_path, keys)
    group_file = tmp_path / "groups.json"
    group_file.write_text(json.dumps({"groups": groups}))
    out = tmp_path / "custom_rail"

    assert (
        make_custom_split.main(
            [
                "--images",
                str(images),
                "--masks",
                str(masks),
                "--groups",
                str(group_file),
                "--out-root",
                str(out),
                "--seed",
                "7",
                "--val-frac",
                "0.2",
                "--test-frac",
                "0.2",
            ]
        )
        == 0
    )

    manifest = json.loads((out / "splits.json").read_text())
    assert manifest["groups"] == groups
    assert manifest["_total_frames"] == len(keys)
    assert manifest["_total_groups"] == 5
    make_custom_split.validate_split(
        {name: manifest[name] for name in make_custom_split.SPLIT_NAMES}, manifest["groups"]
    )

    destinations: list[Path] = []
    for split_name in make_custom_split.SPLIT_NAMES:
        for key in manifest[split_name]:
            destinations.extend(
                [
                    out / "images" / split_name / f"{key}.jpg",
                    out / "masks" / split_name / f"{key}.png",
                ]
            )
    assert len(destinations) == 2 * len(keys)
    assert all(path.is_symlink() and path.exists() for path in destinations)

    with pytest.raises(SystemExit) as exc:
        make_custom_split.main(
            [
                "--images",
                str(images),
                "--masks",
                str(masks),
                "--groups",
                str(group_file),
                "--out-root",
                str(out),
            ]
        )
    assert exc.value.code == 2


@pytest.mark.parametrize(
    ("val_frac", "test_frac", "message"),
    [
        (-0.1, 0.1, r"must each be in \[0, 1\)"),
        (0.6, 0.4, "must be less than 1"),
    ],
)
def test_invalid_fractions_are_rejected(val_frac: float, test_frac: float, message: str) -> None:
    keys, groups = _keys()
    with pytest.raises(make_custom_split.SplitError, match=message):
        make_custom_split.split_by_group(
            keys, groups, seed=0, val_frac=val_frac, test_frac=test_frac
        )
