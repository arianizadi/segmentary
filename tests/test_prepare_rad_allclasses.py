"""A real tiny image/mask corpus exercises transactional all-class materialization."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from PIL import Image
from scripts import prepare_rad_allclasses as build


def fixture(tmp_path):
    source = tmp_path / "source"
    delivery = tmp_path / "delivery"
    (delivery / "jsons").mkdir(parents=True)
    samples = []
    names = [f"class-{i}" for i in range(21)]
    for i in range(6):
        key = f"group-{i}/{i:04}"
        root = source / "images/train"
        image = root / (key + ".png")
        image.parent.mkdir(parents=True)
        Image.fromarray(np.full((1, 21, 3), i, np.uint8)).save(image)
        mask = source / "masks/train" / (key + ".png")
        mask.parent.mkdir(parents=True)
        label = np.arange(21, dtype=np.uint8).reshape(1, 21)
        Image.fromarray(label).save(mask)
        annotation = delivery / "jsons" / f"{i:04}.json"
        annotation.write_text(json.dumps({"objects": [{"classTitle": "class-0"}]}))
        samples.append(
            {
                "key": key,
                "stem": f"{i:04}",
                "split": "train",
                "group": f"group-{i}",
                "image_extension": ".png",
                "width": 21,
                "height": 1,
                "image_sha256": build.digest(image),
                "mask_sha256": hashlib.sha256(label.tobytes()).hexdigest(),
                "mask_file_sha256": build.digest(mask),
                "annotation_sha256": build.digest(annotation),
                "class_pixels": {str(c): 1 for c in range(21)},
            }
        )
    build.write(source / "audit/samples.json", samples)
    build.write(source / "audit/validation.json", {"passed": True, "source": str(delivery)})
    build.write(
        source / "splits.json",
        {
            "train": [s["key"] for s in samples],
            "val": [],
            "test": [],
            "groups": {s["key"]: s["group"] for s in samples},
        },
    )
    build.write(
        source / "classes.json", {"classes": [{"id": i, "name": n} for i, n in enumerate(names)]}
    )
    groups = {
        "paired": {
            "original_groups": ["group-0", "group-1"],
            "images": 2,
            "keys": [samples[0]["key"], samples[1]["key"]],
        }
    }
    groups.update(
        {
            s["group"]: {"original_groups": [s["group"]], "images": 1, "keys": [s["key"]]}
            for s in samples[2:]
        }
    )
    assignment = {
        "paired": "train",
        "group-2": "val",
        "group-3": "val",
        "group-4": "test",
        "group-5": "test",
    }
    prop = {
        "schema_version": 1,
        "source_samples_sha256": build.digest(source / "audit/samples.json"),
        "images": 6,
        "class_names": names,
        "samples": samples,
        "groups": groups,
        "constraints": {"must_link_groups": [["group-0", "group-1"]]},
        "alternatives": [
            {
                "solver_status": 0,
                "hard_minimum_positive_images_per_class_per_split": 1,
                "group_assignment": assignment,
                "counts": {"train": 2, "val": 2, "test": 2},
                "positive_images": {split: dict.fromkeys(names, 2) for split in build.SPLITS},
            }
        ],
    }
    path = tmp_path / "proposal.json"
    build.write(path, prop)
    return source, path, prop, samples


def test_materialization_preserves_bytes_and_enforces_merged_blocks(tmp_path):
    source, proposal, _, samples = fixture(tmp_path)
    before = build.digest(source / "audit/samples.json")
    target = tmp_path / "new-version"
    result = build.prepare(source, proposal, target, 0, 1)
    assert result["passed"] and result["sizes"] == {"train": 2, "val": 2, "test": 2}
    assert build.digest(source / "audit/samples.json") == before
    splits = build.read(target / "splits.json")
    assert splits["groups"][samples[0]["key"]] == splits["groups"][samples[1]["key"]] == "paired"
    for row in build.read(target / "audit/samples.json"):
        assert (
            build.digest(target / "images" / row["split"] / (row["key"] + ".png"))
            == row["image_sha256"]
        )
        assert (target / row["annotation_path"]).is_file()
    assert not target.with_name(target.name + ".preparing").exists()


def test_mask_corruption_leaves_source_and_target_untouched(tmp_path):
    source, proposal, _, samples = fixture(tmp_path)
    target = tmp_path / "new-version"
    mask = source / "masks/train" / (samples[1]["key"] + ".png")
    mask.write_bytes(b"broken")
    with pytest.raises(ValueError, match="Encoded mask content changed"):
        build.prepare(source, proposal, target, 0, 1)
    assert not target.exists() and not target.with_name(target.name + ".preparing").exists()
    assert mask.read_bytes() == b"broken"


def test_weak_candidate_cannot_be_selected_for_minimum_five(tmp_path):
    source, proposal, _, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="below the required minimum"):
        build.prepare(source, proposal, tmp_path / "new-version", 0, 5)


def test_existing_target_is_not_overwritten(tmp_path):
    source, proposal, _, _ = fixture(tmp_path)
    target = tmp_path / "new-version"
    target.mkdir()
    (target / "keep").write_text("unchanged")
    with pytest.raises(FileExistsError):
        build.prepare(source, proposal, target, 0, 1)
    assert (target / "keep").read_text() == "unchanged"


def test_candidate_must_cover_each_original_group_exactly(tmp_path):
    _, _, prop, samples = fixture(tmp_path)
    prop["groups"]["group-2"]["keys"].append(samples[0]["key"])
    prop["groups"]["group-2"]["images"] += 1
    with pytest.raises(ValueError, match="multiple conservative blocks"):
        build.assignment(samples, prop, 0, 1)


def test_source_hash_change_fails_before_materialization(tmp_path):
    source, proposal, _, _ = fixture(tmp_path)
    (source / "audit/samples.json").write_text("[]")
    with pytest.raises(ValueError, match="Source sample audit hash"):
        build.prepare(source, proposal, tmp_path / "new-version", 0, 1)
    assert not (tmp_path / "new-version.preparing").exists()


def test_annotation_change_rolls_back_without_modifying_source(tmp_path):
    source, proposal, _, _ = fixture(tmp_path)
    ann = tmp_path / "delivery/jsons/0002.json"
    ann.write_text("changed")
    with pytest.raises(ValueError, match="Native annotation content changed"):
        build.prepare(source, proposal, tmp_path / "new-version", 0, 1)
    assert not (tmp_path / "new-version.preparing").exists()
    assert ann.read_text() == "changed"


def test_taxonomy_mismatch_cannot_be_silently_remapped(tmp_path):
    source, proposal, _, _ = fixture(tmp_path)
    schema = build.read(source / "classes.json")
    schema["classes"][0]["name"] = "wrong"
    build.write(source / "classes.json", schema)
    with pytest.raises(ValueError, match="Source taxonomy"):
        build.prepare(source, proposal, tmp_path / "new-version", 0, 1)


def test_candidate_support_claim_is_checked_against_actual_masks(tmp_path):
    source, proposal, prop, _ = fixture(tmp_path)
    prop["alternatives"][0]["positive_images"]["test"]["class-0"] = 1
    build.write(proposal, prop)
    with pytest.raises(ValueError, match="Mask-derived support"):
        build.prepare(source, proposal, tmp_path / "new-version", 0, 1)
    assert not (tmp_path / "new-version").exists()


def test_must_link_members_cannot_cross_splits(tmp_path):
    _, _, prop, samples = fixture(tmp_path)
    prop["constraints"]["must_link_groups"] = [["group-0", "group-2"]]
    with pytest.raises(ValueError, match="Must-link scene groups cross"):
        build.assignment(samples, prop, 0, 1)


@pytest.mark.parametrize(
    "constraint,value",
    [
        ("train_only_blocks", ["group-2"]),
        ("minimum_conservative_blocks_per_evaluation_split", 3),
        ("maximum_dominant_block_fraction_per_evaluation_split", 0.4),
    ],
)
def test_declared_pinned_groups_and_evaluation_diversity_are_enforced(tmp_path, constraint, value):
    _, _, prop, samples = fixture(tmp_path)
    prop["constraints"][constraint] = value
    with pytest.raises(ValueError):
        build.assignment(samples, prop, 0, 1)
