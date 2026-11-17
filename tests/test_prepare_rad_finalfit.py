"""The optional final-fit copy keeps the parent holdout and group identities exact."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest
from PIL import Image
from scripts import prepare_rad_finalfit as build


@pytest.fixture
def parent(tmp_path):
    source = tmp_path / "parent"
    splits = {"train": [], "val": [], "test": [], "groups": {}}
    samples = []
    for index in range(314):
        split = "train" if index < 187 else "val" if index < 255 else "test"
        key = f"{split}-scene/{index:04}"
        image = source / "images" / split / (key + ".png")
        mask = source / "masks" / split / (key + ".png")
        annotation = source / "source-annotations" / (key + ".json")
        for path in (image, mask, annotation):
            path.parent.mkdir(parents=True, exist_ok=True)
        rgb = np.zeros((1, 21, 3), dtype=np.uint8)
        rgb[:, :, 0] = index % 256
        rgb[:, :, 1] = index // 256
        Image.fromarray(rgb).save(image)
        label = np.arange(21, dtype=np.uint8).reshape(1, 21)
        Image.fromarray(label).save(mask)
        annotation.write_text(str(index))
        splits[split].append(key)
        splits["groups"][key] = split + "-scene"
        samples.append(
            {
                "key": key,
                "split": split,
                "group": split + "-scene",
                "original_group": "native-" + split,
                "image_extension": ".png",
                "width": 21,
                "height": 1,
                "image_sha256": build.digest(image),
                "mask_file_sha256": build.digest(mask),
                "mask_sha256": hashlib.sha256(label.tobytes()).hexdigest(),
                "annotation_path": str(annotation.relative_to(source)),
                "annotation_sha256": build.digest(annotation),
                "class_pixels": {str(c): 1 for c in range(21)},
            }
        )
    build.write(source / "splits.json", splits)
    build.write(source / "audit/samples.json", samples)
    build.write(
        source / "classes.json", {"classes": [{"id": c, "name": f"class-{c}"} for c in range(21)]}
    )
    build.write(
        source / "audit/validation.json",
        {
            "passed": True,
            "split_sha256": build.digest(source / "splits.json"),
            "samples_sha256": build.digest(source / "audit/samples.json"),
        },
    )
    return source, tmp_path / "final-fit", splits, samples


def test_exact_union_empty_validation_and_byte_identical_test(parent):
    source, target, old, samples = parent
    parent_files = {path: build.digest(path) for path in source.rglob("*") if path.is_file()}
    result = build.prepare(source, target, build.digest(source / "splits.json"))
    splits = build.read(target / "splits.json")
    assert result["sizes"] == {"train": 255, "val": 0, "test": 59}
    assert splits["train"] == sorted(set(old["train"]) | set(old["val"]))
    assert splits["val"] == [] and splits["test"] == old["test"]
    assert splits["groups"] == old["groups"]
    assert splits["_final_fit"] == result["final_fit"]
    assert result["final_fit"]["parent_split_sha256"] == build.digest(source / "splits.json")
    assert (target / "audit/parent-splits.json").read_bytes() == (
        source / "splits.json"
    ).read_bytes()
    assert result["final_fit"]["test_bytes_identical"]
    assert result["image_mask_annotation_copies_verified"] == 314 * 3
    assert build.digest(target / "classes.json") == build.digest(source / "classes.json")
    rendered = build.read(target / "audit/samples.json")
    assert {row["key"] for row in rendered} == {row["key"] for row in samples}
    assert {row["original_group"] for row in rendered} == {row["original_group"] for row in samples}
    for sample in samples:
        split = "test" if sample["split"] == "test" else "train"
        key = sample["key"]
        assert build.digest(target / "images" / split / (key + ".png")) == sample["image_sha256"]
        assert build.digest(target / "masks" / split / (key + ".png")) == sample["mask_file_sha256"]
    assert all(build.digest(path) == checksum for path, checksum in parent_files.items())
    assert not target.with_name(target.name + ".preparing").exists()


@pytest.mark.parametrize(
    "mutation", ["test-mask", "duplicate-image", "extra-native-record", "lost-group"]
)
def test_corrupt_parent_rolls_back_without_materializing(parent, mutation):
    source, target, splits, samples = parent
    if mutation == "test-mask":
        path = source / "masks/test" / (splits["test"][0] + ".png")
        path.write_bytes(b"changed")
    elif mutation == "duplicate-image":
        first, second = samples[0], samples[-1]
        original = source / "images" / first["split"] / (first["key"] + ".png")
        duplicate = source / "images" / second["split"] / (second["key"] + ".png")
        duplicate.write_bytes(original.read_bytes())
        second["image_sha256"] = build.digest(duplicate)
    elif mutation == "extra-native-record":
        samples.append({**samples[0], "key": "external-cvat/extra"})
    else:
        splits["groups"].pop(samples[0]["key"])
        build.write(source / "splits.json", splits)
    build.write(source / "audit/samples.json", samples)
    build.write(
        source / "audit/validation.json",
        {
            "passed": True,
            "split_sha256": build.digest(source / "splits.json"),
            "samples_sha256": build.digest(source / "audit/samples.json"),
        },
    )
    with pytest.raises(ValueError):
        build.prepare(source, target, build.digest(source / "splits.json"))
    assert not target.exists() and not target.with_name(target.name + ".preparing").exists()


def test_parent_hash_required_and_existing_target_preserved(parent):
    source, target, _, _ = parent
    with pytest.raises(ValueError, match="Parent split SHA-256"):
        build.prepare(source, target, "0" * 64)
    target.mkdir()
    (target / "keep").write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        build.prepare(source, target, build.digest(source / "splits.json"))
    assert (target / "keep").read_bytes() == b"preserve"
