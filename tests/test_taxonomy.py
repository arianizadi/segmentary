"""Taxonomy layer tests.

These run before anything touches a GPU. A taxonomy bug is invisible in the loss
curve, so it has to be caught here or it is not caught at all.
"""

from __future__ import annotations

import glob
import random

import numpy as np
import pytest

from segmentary.taxonomy import LUT_SIZE, TaxonomyError, colorize, load_mapping, load_space

SPACES = ["rail_union", "cityscapes19"]
SHIPPED = [
    ("rail_union", "cityscapes", None),
    ("rail_union", "cityscapes", "railbridge"),
    ("rail_union", "railsem19", None),
    ("rail_union", "custom", None),
    ("cityscapes19", "cityscapes", None),
    ("cityscapes19", "railsem19", None),
]


# --------------------------------------------------------------------------
# label space structure
# --------------------------------------------------------------------------


@pytest.mark.parametrize("space_name", SPACES)
def test_space_ids_are_contiguous_and_named_uniquely(taxonomy_root, space_name):
    space = load_space(taxonomy_root, space_name)
    assert [c.id for c in space.classes] == list(range(space.num_classes))
    assert len(set(space.names)) == space.num_classes
    assert space.ignore_index == 255
    assert space.num_classes < space.ignore_index


@pytest.mark.parametrize("space_name", SPACES)
def test_palette_covers_every_class_and_leaves_ignore_black(taxonomy_root, space_name):
    space = load_space(taxonomy_root, space_name)
    palette = space.palette
    assert palette.shape == (LUT_SIZE, 3) and palette.dtype == np.uint8
    for c in space.classes:
        assert tuple(palette[c.id]) == c.color
    assert tuple(palette[space.ignore_index]) == (0, 0, 0)


def test_colorize_round_trips_class_ids(taxonomy_root):
    space = load_space(taxonomy_root, "rail_union")
    ids = np.arange(space.num_classes, dtype=np.uint8).reshape(3, 7)
    rgb = colorize(ids, space)
    assert rgb.shape == (3, 7, 3)
    for cid in range(space.num_classes):
        assert tuple(rgb.reshape(-1, 3)[cid]) == space.classes[cid].color


# --------------------------------------------------------------------------
# SPEC: every native id maps to a valid canonical id or to ignore_index
# --------------------------------------------------------------------------


@pytest.mark.parametrize("space_name,dataset,variant", SHIPPED)
def test_lut_is_total_and_in_range(taxonomy_root, space_name, dataset, variant):
    space = load_space(taxonomy_root, space_name)
    mapping = load_mapping(taxonomy_root, space, dataset, variant)

    assert mapping.lut.shape == (LUT_SIZE,)
    assert mapping.lut.dtype == np.uint8

    valid = set(range(space.num_classes)) | {space.ignore_index}
    produced = set(mapping.lut.tolist())
    assert produced <= valid, f"LUT emits ids outside the space: {sorted(produced - valid)}"

    # Totality: applying the LUT to every possible uint8 input is well defined
    # and never yields an id the loss could not index.
    every_native = np.arange(LUT_SIZE, dtype=np.uint8)
    out = mapping.apply(every_native)
    assert out.shape == (LUT_SIZE,)
    assert set(out.tolist()) <= valid


@pytest.mark.parametrize("space_name,dataset,variant", SHIPPED)
def test_undeclared_native_ids_fall_through_to_ignore(taxonomy_root, space_name, dataset, variant):
    space = load_space(taxonomy_root, space_name)
    mapping = load_mapping(taxonomy_root, space, dataset, variant)
    undeclared = [i for i in range(LUT_SIZE) if i not in mapping._declared]
    if undeclared:
        assert set(mapping.lut[undeclared].tolist()) == {space.ignore_index}


@pytest.mark.parametrize("space_name,dataset,variant", SHIPPED)
def test_active_set_is_exactly_what_the_lut_can_emit(taxonomy_root, space_name, dataset, variant):
    space = load_space(taxonomy_root, space_name)
    mapping = load_mapping(taxonomy_root, space, dataset, variant)

    emitted = set(mapping.lut.tolist()) - {space.ignore_index}
    assert emitted == set(mapping.active_ids)
    assert set(mapping.active_ids).isdisjoint(mapping.inactive_ids)
    assert set(mapping.active_ids) | set(mapping.inactive_ids) == set(range(space.num_classes))

    mask = mapping.active_mask()
    assert mask.dtype == bool and mask.shape == (space.num_classes,)
    assert mask.sum() == len(mapping.active_ids)


def test_known_active_sets(taxonomy_root):
    """Pin the cross-dataset structure used by every transfer experiment."""
    space = load_space(taxonomy_root, "rail_union")
    rail = {"rail-track", "rail-raised", "rail-embedded", "tram-track", "trackbed"}

    cs = load_mapping(taxonomy_root, space, "cityscapes")
    assert {space.classes[i].name for i in cs.inactive_ids} == rail, (
        "plain Cityscapes must supply no rail supervision"
    )

    rs = load_mapping(taxonomy_root, space, "railsem19")
    assert {space.classes[i].name for i in rs.inactive_ids} == {"motorcycle", "bicycle"}

    bridge = load_mapping(taxonomy_root, space, "cityscapes", "railbridge")
    assert {space.classes[i].name for i in bridge.active_ids} > {
        space.classes[i].name for i in cs.active_ids
    }
    assert {space.classes[i].name for i in bridge.inactive_ids} == {
        "rail-embedded",
        "tram-track",
        "trackbed",
    }


# --------------------------------------------------------------------------
# SPEC: no canonical id is silently produced by two different native classes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("space_name,dataset,variant", SHIPPED)
def test_every_merge_is_declared_with_a_reason(taxonomy_root, space_name, dataset, variant):
    space = load_space(taxonomy_root, space_name)
    mapping = load_mapping(taxonomy_root, space, dataset, variant)

    sources: dict[int, list[int]] = {}
    for native in sorted(mapping._declared):
        canonical = int(mapping.lut[native])
        if canonical != space.ignore_index:
            sources.setdefault(canonical, []).append(native)

    collisions = {c for c, n in sources.items() if len(n) > 1}
    assert collisions == set(mapping.merges), (
        f"declared merges {sorted(mapping.merges)} != actual collisions {sorted(collisions)}"
    )
    for reason in mapping.merges.values():
        assert reason.strip(), "a declared merge must carry a written justification"


def test_undeclared_merge_is_rejected(tmp_space):
    root = tmp_space(mapping={"map": {10: 0, 11: 0}})  # two natives -> class 0
    with pytest.raises(TaxonomyError, match="undeclared many-to-one merges"):
        load_mapping(root, "toy", "toy_ds")


def test_declared_merge_is_accepted(tmp_space):
    root = tmp_space(mapping={"map": {10: 0, 11: 0}, "allow_merge": {0: "intended"}})
    mapping = load_mapping(root, "toy", "toy_ds")
    assert mapping.active_ids == (0,)
    assert mapping.merges == {0: "intended"}


def test_stale_allow_merge_is_rejected(tmp_space):
    root = tmp_space(mapping={"map": {10: 0}, "allow_merge": {0: "nothing merges here"}})
    with pytest.raises(TaxonomyError, match=r"declares .* but nothing merges"):
        load_mapping(root, "toy", "toy_ds")


def test_merge_without_reason_is_rejected(tmp_space):
    root = tmp_space(mapping={"map": {10: 0, 11: 0}, "allow_merge": {0: "  "}})
    with pytest.raises(TaxonomyError, match="written reason"):
        load_mapping(root, "toy", "toy_ds")


# --------------------------------------------------------------------------
# validator rejects the rest of the footguns
# --------------------------------------------------------------------------


def test_default_other_than_ignore_is_rejected(tmp_space):
    root = tmp_space(mapping={"map": {10: 0}, "default": 0})
    with pytest.raises(TaxonomyError, match="must be ignore_index"):
        load_mapping(root, "toy", "toy_ds")


def test_out_of_space_canonical_id_is_rejected(tmp_space):
    root = tmp_space(mapping={"map": {10: 7}})  # space only has 0..2
    with pytest.raises(TaxonomyError, match="neither a class"):
        load_mapping(root, "toy", "toy_ds")


def test_non_contiguous_class_ids_are_rejected(tmp_space):
    root = tmp_space(
        classes=[{"id": 0, "name": "a"}, {"id": 2, "name": "b"}],
        mapping={"map": {1: 0}},
    )
    with pytest.raises(TaxonomyError, match="contiguous"):
        load_space(root, "toy")


def test_duplicate_class_names_are_rejected(tmp_space):
    root = tmp_space(
        classes=[{"id": 0, "name": "a"}, {"id": 1, "name": "a"}], mapping={"map": {1: 0}}
    )
    with pytest.raises(TaxonomyError, match="duplicate class names"):
        load_space(root, "toy")


def test_space_mismatch_is_rejected(tmp_space):
    root = tmp_space(mapping={"map": {10: 0}, "space": "some_other_space"})
    with pytest.raises(TaxonomyError, match="declares space"):
        load_mapping(root, "toy", "toy_ds")


def test_missing_file_fails_loudly(taxonomy_root):
    with pytest.raises(TaxonomyError, match="not found"):
        load_mapping(taxonomy_root, "rail_union", "no_such_dataset")


def test_assert_covers_flags_undeclared_ids(taxonomy_root):
    mapping = load_mapping(taxonomy_root, "rail_union", "railsem19")
    mapping.assert_covers([0, 1, 18, 255])  # all declared -> silent
    with pytest.raises(TaxonomyError, match=r"native ids \[42\]"):
        mapping.assert_covers([0, 42])


def test_apply_rejects_ids_beyond_the_lut(taxonomy_root):
    mapping = load_mapping(taxonomy_root, "rail_union", "cityscapes")
    bad = np.array([[0, 300]], dtype=np.int32)
    with pytest.raises(TaxonomyError, match="uint8 LUT"):
        mapping.apply(bad)


def test_apply_preserves_shape_and_dtype(taxonomy_root):
    mapping = load_mapping(taxonomy_root, "rail_union", "cityscapes")
    native = np.random.default_rng(0).integers(0, 34, size=(13, 17), dtype=np.uint8)
    out = mapping.apply(native)
    assert out.shape == native.shape and out.dtype == np.uint8


# --------------------------------------------------------------------------
# real data: the LUT must actually cover what is on disk
# --------------------------------------------------------------------------


def _sample(pattern: str, n: int) -> list[str]:
    files = sorted(glob.glob(pattern))
    assert files, f"no files matched {pattern}"
    random.Random(0).shuffle(files)
    return files[:n]


def _observed_ids(files) -> set[int]:
    from PIL import Image

    ids: set[int] = set()
    for f in files:
        ids |= set(np.unique(np.array(Image.open(f))).tolist())
    return ids


@pytest.mark.slow
@pytest.mark.parametrize("variant", [None, "railbridge"])
def test_cityscapes_masks_are_fully_declared(taxonomy_root, cityscapes_root, variant):
    files = _sample(str(cityscapes_root / "gtFine" / "*" / "*" / "*_labelIds.png"), 40)
    mapping = load_mapping(taxonomy_root, "rail_union", "cityscapes", variant)
    mapping.assert_covers(_observed_ids(files))


@pytest.mark.slow
def test_railsem19_masks_are_fully_declared(taxonomy_root, railsem19_root):
    files = _sample(str(railsem19_root / "uint8" / "rs19_val" / "*.png"), 40)
    mapping = load_mapping(taxonomy_root, "rail_union", "railsem19")
    mapping.assert_covers(_observed_ids(files))


@pytest.mark.slow
def test_railsem19_config_matches_shipped_mapping(taxonomy_root, railsem19_root):
    """The mapping's native ids must match the dataset's own rs19-config.json."""
    import json

    cfg = json.loads((railsem19_root / "rs19-config.json").read_text())
    native_names = {i: lab["name"] for i, lab in enumerate(cfg["labels"])}
    mapping = load_mapping(taxonomy_root, "rail_union", "railsem19")

    declared = set(mapping._declared) - {255}
    assert declared == set(native_names), (
        f"mapping declares {sorted(declared)} but rs19-config.json defines {sorted(native_names)}"
    )
