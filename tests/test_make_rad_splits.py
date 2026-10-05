"""Split specification tool on a synthetic flat delivery; no real data required."""

import hashlib
import json
import random

import pytest
import yaml
from PIL import Image
from scripts import make_rad_splits as mrs

NAMES = [
    "person",
    "truck",
    "rail-track",
    "vegetation-overgrowth",
    "car",
    "on-rails",
    "traffic-sign",
    "road",
    "sidewalk",
    "construction",
    "tram-track",
    "pole",
    "traffic-light",
    "mud-pumping",
    "fence",
    "terrain",
    "sky",
    "rail-embedded",
    "rail-raised",
    "trackbed",
    "standing-water",
]


def square(width, height, x0=0, y0=0):
    return {
        "exterior": [
            [x0, y0],
            [x0 + width - 1, y0],
            [x0 + width - 1, y0 + height - 1],
            [x0, y0 + height - 1],
        ],
        "interior": [],
    }


def write_delivery(root, titles_by_stem, size=(12, 10), small=()):
    """Write img/, jsons/ and masks_machine/ with distinct image bytes per stem."""
    for folder in ("img", "jsons", "masks_machine"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    rng = random.Random(1)
    for stem, titles in titles_by_stem.items():
        w, h = (6, 6) if stem in small else size
        image = Image.new("RGB", (w, h), tuple(rng.randrange(256) for _ in range(3)))
        image.save(root / "img" / f"{stem}.png")
        objects = [
            {
                "classTitle": t,
                "geometryType": "polygon",
                "points": square(w, h // 2, 0, i % 2 * (h // 2)),
            }
            for i, t in enumerate(titles)
        ]
        (root / "jsons" / f"{stem}.json").write_text(
            json.dumps({"size": {"width": w, "height": h}, "objects": objects})
        )
        Image.new("L", (w, h), 0).save(root / "masks_machine" / f"{stem}.png")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_reference(root, delivery, rows, extra_train=()):
    """A prepared reference: audit/samples.json + splits.json in paul-test-rtis format."""
    samples, splits = [], {"train": [], "val": [], "test": [], "groups": {}}
    for stem, split, group in rows:
        key = f"{group}/old_{stem}"
        samples.append(
            {
                "key": key,
                "split": split,
                "group": group,
                "image_sha256": sha(delivery / "img" / f"{stem}.png"),
            }
        )
        splits[split].append(key)
        splits["groups"][key] = group
    for i, group in enumerate(extra_train):
        key = f"{group}/absent_{i}"
        samples.append({"key": key, "split": "train", "group": group, "image_sha256": f"{i:064x}"})
        splits["train"].append(key)
        splits["groups"][key] = group
    splits["_grouping_status"] = "provisional"
    (root / "audit").mkdir(parents=True)
    (root / "audit/samples.json").write_text(json.dumps(samples))
    (root / "splits.json").write_text(json.dumps(splits))


def write_new_images(
    path, delivery, entries, status="provisional_until_recording_provenance_confirmed"
):
    images = {
        sha(delivery / "img" / f"{stem}.png"): {"stem": stem, "group": group, "split": split}
        for stem, group, split in entries
    }
    path.write_text(yaml.safe_dump({"status": status, "images": images}))


@pytest.fixture
def delivery(tmp_path):
    root = tmp_path / "rad"
    titles = {
        "0000": ["terrain", "mud-pumping"],
        "0001": ["terrain", "sky"],
        "0002": ["terrain", "person"],
        "0003": ["sky", "void"],
        "0004": ["terrain", "mud-pumping"],
        "0005": ["sky", "person"],
        "0006": ["terrain", "truck"],
        "0007": ["sky", "mud-pumping"],
        "0008": ["terrain"],
        "0009": ["sky", "truck"],
        "0010": ["terrain", "person"],
        "0011": ["sky", "mud-pumping"],
    }
    write_delivery(root, titles, small=("0008",))
    return root


def test_grouped_carries_reference_and_lists_new_images(delivery, tmp_path):
    rows = [
        ("0000", "train", "a"),
        ("0001", "train", "a"),
        ("0002", "val", "b"),
        ("0003", "test", "c"),
        ("0004", "train", "d"),
        ("0005", "val", "b"),
        ("0006", "test", "c"),
        ("0007", "train", "d"),
        ("0008", "train", "a"),
        ("0009", "val", "b"),
    ]
    v1, v2 = tmp_path / "v1", tmp_path / "v2"
    write_reference(v1, delivery, rows, extra_train=("a", "e"))
    write_reference(v2, delivery, rows)
    listing = tmp_path / "new.yaml"
    write_new_images(listing, delivery, [("0010", "c", "test"), ("0011", "f", "train")])
    first = mrs.grouped(delivery, v1, listing)
    second = mrs.grouped(delivery, v2, listing)
    assert first["assignments"] == second["assignments"]
    assert first["groups_enforced"] and first["_grouping_status"].startswith("provisional")
    assert first["report"]["sizes"] == {"train": 6, "val": 3, "test": 3}
    assert first["assignments"]["0010"] == {
        "split": "test",
        "group": "c",
        "image_sha256": sha(delivery / "img/0010.png"),
        "reference_key": None,
        "listed_in": "new.yaml",
    }
    assert first["assignments"]["0002"]["reference_key"] == "b/old_0002"
    assert first["report"]["reference_train_images_absent_from_delivery"] == [
        "a/absent_0",
        "e/absent_1",
    ]
    assert first["report"]["class_image_counts"]["mud-pumping"] == {"train": 4, "val": 0, "test": 0}
    assert "void" not in first["report"]["class_image_counts"]
    assert json.dumps(first, sort_keys=True) == json.dumps(
        mrs.grouped(delivery, v1, listing), sort_keys=True
    )


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([("0010", "c", "test")], "neither in the reference nor listed"),
        (
            [("0010", "c", "test"), ("0011", "f", "train"), ("0003", "c", "test")],
            "absent from the delivery",
        ),
        ([("0010", "c", "test"), ("0011", "b", "train")], "more than one split"),
    ],
    ids=["unlisted", "listed-but-absent", "group-crosses-splits"],
)
def test_grouped_rejects_inconsistent_listings(delivery, tmp_path, entries, message):
    rows = [("0000", "train", "a"), ("0002", "val", "b"), ("0003", "test", "c")] + [
        (f"{i:04d}", "train", "a") for i in (1, 4, 5, 6, 7, 8, 9)
    ]
    write_reference(tmp_path / "ref", delivery, rows)
    listing = tmp_path / "new.yaml"
    write_new_images(listing, delivery, entries)
    if message == "absent from the delivery":
        data = yaml.safe_load(listing.read_text())
        data["images"]["f" * 64] = {"stem": "9999", "group": "z", "split": "train"}
        listing.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match=message):
        mrs.grouped(delivery, tmp_path / "ref", listing)


def test_grouped_rejects_stem_mismatch_and_missing_eval_images(delivery, tmp_path):
    rows = [("0000", "train", "a"), ("0002", "val", "b"), ("0003", "test", "c")] + [
        (f"{i:04d}", "train", "a") for i in (1, 4, 5, 6, 7, 8, 9)
    ]
    write_reference(tmp_path / "ref", delivery, rows)
    listing = tmp_path / "new.yaml"
    write_new_images(listing, delivery, [("0010", "c", "test"), ("0011", "f", "train")])
    data = yaml.safe_load(listing.read_text())
    next(iter(data["images"].values()))["stem"] = "0099"
    listing.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="lists stem"):
        mrs.grouped(delivery, tmp_path / "ref", listing)
    write_new_images(listing, delivery, [("0010", "c", "test"), ("0011", "f", "train")])
    (delivery / "img/0003.png").unlink()
    (delivery / "jsons/0003.json").unlink()
    with pytest.raises(ValueError, match="Reference test images absent"):
        mrs.grouped(delivery, tmp_path / "ref", listing)


def group_spec(delivery):
    return {
        "assignments": {
            p.stem: {"group": "g" + p.stem[-1], "split": "train"}
            for p in (delivery / "img").iterdir()
        }
    }


def test_stratified_is_deterministic_and_covers_every_label(delivery, tmp_path, monkeypatch):
    monkeypatch.setattr(mrs, "PIN_MIN_SIDE", 8)
    spec_path = tmp_path / "grouped.json"
    spec_path.write_text(json.dumps(group_spec(delivery)))
    sizes = {"train": 6, "val": 3, "test": 3}
    kwargs = dict(seed=0, sizes=sizes, rare_threshold=4, anomaly_classes=["mud-pumping"])
    spec = mrs.stratified(delivery, spec_path, **kwargs)
    again = mrs.stratified(delivery, spec_path, **kwargs)
    assert json.dumps(spec, sort_keys=True) == json.dumps(again, sort_keys=True)
    assert spec["groups_enforced"] is False
    assert spec["_grouping_status"] == mrs.STRATIFIED_STATUS
    assert spec["method"]["rare_classes"] == ["person", "truck"]
    assert spec["method"]["stratification_labels"] == ["mud-pumping", "person", "truck"]
    assert spec["report"]["sizes"] == sizes
    assert spec["report"]["pinned_small_images"] == ["0008"]
    assert spec["assignments"]["0008"]["split"] == "train"
    assert spec["assignments"]["0008"]["pinned_small_image"] is True
    assert spec["assignments"]["0000"]["stratification_labels"] == ["mud-pumping"]
    counts = spec["report"]["stratification_label_image_counts"]
    assert counts["mud-pumping"]["total"] == 4
    assert all(
        counts[label][split] >= 1
        for label in counts
        if counts[label]["total"] >= 3
        for split in ("train", "val", "test")
    )
    assert set(counts["truck"][s] for s in ("train", "val", "test")) == {0, 1}
    assert all(counts["mud-pumping"][s] in (1, 2) for s in ("train", "val", "test"))
    # Group names come from the grouped spec and are only reported, never enforced.
    assert spec["assignments"]["0003"]["group"] == "g3"
    assert (
        spec["report"]["class_image_counts"]["sky"]["train"]
        + spec["report"]["class_image_counts"]["sky"]["val"]
        + spec["report"]["class_image_counts"]["sky"]["test"]
        == 6
    )
    other = mrs.stratified(delivery, spec_path, **(kwargs | {"seed": 1}))
    assert {s: r["split"] for s, r in other["assignments"].items()} != {
        s: r["split"] for s, r in spec["assignments"].items()
    }


def test_stratified_fails_when_a_label_misses_a_split(delivery, tmp_path, monkeypatch):
    monkeypatch.setattr(mrs, "PIN_MIN_SIDE", 8)
    spec_path = tmp_path / "grouped.json"
    spec_path.write_text(json.dumps(group_spec(delivery)))
    # Three truck images cannot be spread over three splits when test takes none of them.
    monkeypatch.setattr(
        mrs,
        "iterative_stratification",
        lambda labels, cap, des, rng: (
            dict.fromkeys(labels, "train")
            | {
                "0001": "val",
                "0003": "val",
                "0005": "val",
                "0000": "test",
                "0004": "test",
                "0007": "test",
            }
        ),
    )
    with pytest.raises(ValueError, match="missing from a split"):
        mrs.stratified(
            delivery, spec_path, 0, {"train": 6, "val": 3, "test": 3}, 4, ["mud-pumping"]
        )
    with pytest.raises(ValueError, match="do not sum"):
        mrs.stratified(
            delivery, spec_path, 0, {"train": 6, "val": 3, "test": 4}, 4, ["mud-pumping"]
        )
    with pytest.raises(ValueError, match="Anomaly classes absent"):
        mrs.stratified(delivery, spec_path, 0, {"train": 6, "val": 3, "test": 3}, 4, ["flood"])


def test_iterative_stratification_honours_capacity_and_desired_counts():
    labels = {f"i{n}": frozenset({"a"} if n < 6 else {"b"} if n < 9 else set()) for n in range(12)}
    capacity = {"train": 6, "val": 3, "test": 3}
    desired = {s: {"a": 6 * capacity[s] / 12, "b": 3 * capacity[s] / 12} for s in capacity}
    placed = mrs.iterative_stratification(labels, capacity, desired, random.Random(0))
    assert sorted(placed) == sorted(labels)
    from collections import Counter

    assert Counter(placed.values()) == capacity
    for label in ("a", "b"):
        per_split = Counter(placed[i] for i in labels if label in labels[i])
        assert set(per_split) == set(capacity), label
