"""prepare_rad on a synthetic delivery: layout contract, label audit, parity, configs."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import yaml
from albumentations import Compose
from PIL import Image
from scripts import prepare_rad
from scripts.prepare_rtis import render

ROOT = Path(__file__).resolve().parents[1]
W, H = 16, 12


def poly(points):
    return {"exterior": points, "interior": []}


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def obj(title, points, holes=()):
    return {
        "classTitle": title,
        "geometryType": "polygon",
        "points": {"exterior": points, "interior": list(holes)},
    }


OBJECTS = {
    # terrain over the top 6 rows, sky over the bottom 6 rows, nothing uncovered
    "0000": [obj("terrain", rect(0, 0, W - 1, 5)), obj("sky", rect(0, 6, W - 1, H - 1))],
    # pole with a 2x2 hole over sky; columns 12..15 uncovered (4 x 12 = 48 px)
    "0001": [
        obj("sky", rect(0, 0, 11, H - 1)),
        obj("pole", rect(2, 2, 7, 7), holes=[rect(4, 4, 5, 5)]),
    ],
    # person plus a void polygon; one JPG image
    "0002": [obj("person", rect(0, 0, W - 1, H - 1)), obj("void", rect(0, 0, 3, 3))],
    "0003": [obj("mud-pumping", rect(0, 0, W - 1, H - 1))],
}


def labels():
    schema = yaml.safe_load((ROOT / "taxonomy/paul-test-rtis/canonical.yaml").read_text())
    return {c["name"]: c["id"] for c in schema["classes"]} | {"void": 255}


def paul_mask(objects):
    """Paul's defects reproduced exactly: uncovered -> 0, holes ignored, same raster."""
    flat = [o | {"points": {"exterior": o["points"]["exterior"], "interior": []}} for o in objects]
    mask, _ = render(flat, (H, W), labels(), "supervisely")
    covered, _ = render(objects, (H, W), dict.fromkeys(labels(), 0), "supervisely")
    mask[covered == 255] = 0
    return mask


def write_delivery(root):
    for folder in ("img", "jsons", "masks_machine"):
        (root / folder).mkdir(parents=True)
    for i, (stem, objects) in enumerate(OBJECTS.items()):
        ext = ".jpg" if stem == "0002" else ".png"
        Image.new("RGB", (W, H), (i * 40, 20, 200)).save(root / "img" / f"{stem}{ext}")
        (root / "jsons" / f"{stem}.json").write_text(
            json.dumps({"size": {"width": W, "height": H}, "objects": objects})
        )
        Image.fromarray(paul_mask(objects)).save(root / "masks_machine" / f"{stem}.png")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_spec(path, delivery, groups_enforced):
    rows = {
        "0000": ("train", "a"),
        "0001": ("train", "a"),
        "0002": ("val", "b"),
        "0003": ("test", "c"),
    }
    spec = {
        "dataset": "rad",
        "method": (
            {"name": "grouped", "reference": "ref", "new_images_file": "new.yaml", "seed": None}
            if groups_enforced
            else {
                "name": "stratified",
                "seed": 0,
                "anomaly_classes": ["mud-pumping"],
                "rare_threshold": 50,
                "rare_classes": ["person"],
            }
        ),
        "_grouping_status": "provisional" if groups_enforced else "none_stratified",
        "groups_enforced": groups_enforced,
        "assignments": {
            stem: {
                "split": split,
                "group": group,
                "image_sha256": sha(next((delivery / "img").glob(stem + ".*"))),
            }
            for stem, (split, group) in rows.items()
        },
        "report": {},
    }
    path.write_text(json.dumps(spec))
    return spec


@pytest.fixture
def delivery(tmp_path):
    root = tmp_path / "rad"
    write_delivery(root)
    return root


@pytest.mark.parametrize("label_source", ["paul", "rendered"])
def test_prepare_writes_the_campaign_layout(delivery, tmp_path, label_source):
    spec_path = tmp_path / "spec.json"
    write_spec(spec_path, delivery, groups_enforced=True)
    target = tmp_path / "out"
    validation = prepare_rad.prepare(delivery, spec_path, label_source, "name", target)
    assert validation["passed"] and validation["sizes"] == {"train": 2, "val": 1, "test": 1}
    assert not target.with_name("out.preparing").exists()
    files = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
    assert [f for f in files if f.startswith(("images/", "masks/"))] == [
        "images/test/c/0003.png",
        "images/train/a/0000.png",
        "images/train/a/0001.png",
        "images/val/b/0002.jpg",
        "masks/test/c/0003.png",
        "masks/train/a/0000.png",
        "masks/train/a/0001.png",
        "masks/val/b/0002.png",
    ]
    for name in (
        "README.md",
        "classes.json",
        "splits.json",
        "audit/samples.json",
        "audit/split-spec.json",
        "audit/validation.json",
        "audit/label-audit.json",
        "audit/label-audit.csv",
    ):
        assert name in files
    splits = json.loads((target / "splits.json").read_text())
    assert splits["train"] == ["a/0000", "a/0001"] and splits["val"] == ["b/0002"]
    assert splits["groups"]["b/0002"] == "b" and splits["_grouping_status"] == "provisional"
    assert all(k in ("train", "val", "test", "groups") or k.startswith("_") for k in splits)
    samples = json.loads((target / "audit/samples.json").read_text())
    assert [s["key"] for s in samples] == ["a/0000", "a/0001", "b/0002", "c/0003"]
    for s in samples:
        image = target / "images" / s["split"] / (s["key"] + s["image_extension"])
        mask = target / "masks" / s["split"] / (s["key"] + ".png")
        assert sha(image) == s["image_sha256"] and sha(mask) == s["mask_file_sha256"]
        with Image.open(mask) as decoded:
            assert decoded.mode == "L" and decoded.size == (s["width"], s["height"]) == (W, H)
            assert hashlib.sha256(decoded.tobytes()).hexdigest() == s["mask_sha256"]
        assert s["label_source"] == label_source and s["stem"] == s["key"].split("/")[1]
        assert s["annotation_sha256"] == sha(delivery / "jsons" / (s["stem"] + ".json"))
        assert sum(s["class_pixels"].values()) == W * H
    classes = json.loads((target / "classes.json").read_text())
    assert [c["name"] for c in classes["classes"]][13] == "mud-pumping" and classes[
        "ignore_index"
    ] == 255
    mask = np.asarray(Image.open(target / "masks/train/a/0001.png"))
    if label_source == "paul":
        assert sha(target / "masks/train/a/0001.png") == sha(delivery / "masks_machine/0001.png")
        assert mask[4, 4] == labels()["pole"] and mask[0, 13] == 0
    else:
        assert mask[4, 4] == labels()["sky"] and mask[0, 13] == 255
        assert np.asarray(Image.open(target / "masks/val/b/0002.png"))[0, 0] == 255


def test_label_audit_records_the_delivered_defects(delivery, tmp_path):
    spec_path = tmp_path / "spec.json"
    write_spec(spec_path, delivery, groups_enforced=False)
    target = tmp_path / "out"
    prepare_rad.prepare(delivery, spec_path, "paul", "name", target)
    audit = json.loads((target / "audit/label-audit.json").read_text())
    by_stem = {a["stem"]: a for a in audit["per_image"]}
    assert by_stem["0000"]["disagreement_px"] == 0
    assert by_stem["0001"]["uncovered_px"] == 48 == by_stem["0001"]["paul_zero_uncovered_px"]
    assert by_stem["0001"]["hole_px_changed"] == 4
    assert by_stem["0001"]["disagreement_px"] == 52
    assert by_stem["0002"]["person_px_rendered"] == W * H - 16
    assert by_stem["0002"]["person_px_paul"] == W * H - 16
    assert by_stem["0002"]["uncovered_px"] == 0
    assert audit["totals"]["disagreement_px"] == 52 and audit["totals"]["hole_px_changed"] == 4
    assert audit["per_class_totals"][str(labels()["pole"])]["paul_px_differing"] == 4
    assert audit["per_class_totals"]["255"]["rendered_px_differing"] == 48
    rows = (target / "audit/label-audit.csv").read_text().splitlines()
    assert rows[0].startswith("stem,key,split,uncovered_px") and rows[-1].startswith(
        "total,,,48,48,4,52"
    )
    splits = json.loads((target / "splits.json").read_text())
    assert "groups" not in splits and splits["_grouping_status"] == "none_stratified"


def test_render_parity_against_reference(delivery, tmp_path, monkeypatch):
    spec_path = tmp_path / "spec.json"
    write_spec(spec_path, delivery, groups_enforced=True)
    reference = []
    for stem in ("0000", "0001", "0002"):
        image = next((delivery / "img").glob(stem + ".*"))
        mask, _ = render(OBJECTS[stem], (H, W), labels(), "supervisely")
        reference.append(
            {
                "key": f"old/{stem}",
                "image_sha256": sha(image),
                "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest(),
            }
        )
    reference[1]["mask_sha256"] = "0" * 64
    ref_path = tmp_path / "reference.json"
    ref_path.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match="differ from the reference audit"):
        prepare_rad.prepare(delivery, spec_path, "rendered", "name", tmp_path / "bad", ref_path)
    assert not (tmp_path / "bad").exists()
    monkeypatch.setattr(prepare_rad, "KNOWN_EDITED", {reference[1]["image_sha256"]: "0001"})
    validation = prepare_rad.prepare(
        delivery, spec_path, "rendered", "name", tmp_path / "ok", ref_path
    )
    parity = validation["render_parity"]
    assert (parity["matches"], parity["known_edited_mismatches"], parity["new_images"]) == (2, 1, 1)
    assert parity["known_edited_stems"] == ["0001"] and parity["new_image_stems"] == ["0003"]
    with pytest.raises(ValueError, match="Destination exists"):
        prepare_rad.prepare(delivery, spec_path, "rendered", "name", tmp_path / "ok")


def test_prepare_rejects_unknown_class_and_spec_mismatch(delivery, tmp_path):
    spec_path = tmp_path / "spec.json"
    spec = write_spec(spec_path, delivery, groups_enforced=True)
    spec["assignments"]["0003"]["image_sha256"] = "1" * 64
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="sha256 differs"):
        prepare_rad.prepare(delivery, spec_path, "rendered", "name", tmp_path / "a")
    write_spec(spec_path, delivery, groups_enforced=True)
    data = json.loads((delivery / "jsons/0003.json").read_text())
    data["objects"][0]["classTitle"] = "flood"
    (delivery / "jsons/0003.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="unknown class"):
        prepare_rad.prepare(delivery, spec_path, "rendered", "name", tmp_path / "b")


def test_prepare_rejects_duplicate_image_stems(delivery, tmp_path):
    """0002.jpg and 0002.png must not be silently collapsed into one image."""
    spec_path = tmp_path / "spec.json"
    write_spec(spec_path, delivery, groups_enforced=True)
    Image.new("RGB", (W, H)).save(delivery / "img/0002.png")
    with pytest.raises(ValueError, match="Duplicate image stem"):
        prepare_rad.prepare(delivery, spec_path, "paul", "name", tmp_path / "dup")
    assert not (tmp_path / "dup").exists() and not (tmp_path / "dup.preparing").exists()


@pytest.mark.parametrize(
    ("arm", "require_groups"),
    [("paul", False), ("fixed-stratified", False), ("fixed-grouped", True)],
)
def test_dataset_configs_load_and_drive_the_folder_loader(delivery, tmp_path, arm, require_groups):
    from segmentary.config import load_experiment
    from segmentary.curriculum import validate_training_contract
    from segmentary.data.loaders import build_dataset
    from segmentary.taxonomy import load_space

    name = f"rad_9_24_2026-{arm}"
    cfg = load_experiment(
        [
            ROOT / "configs/base.yaml",
            ROOT / "configs/models/segformer_b2.yaml",
            ROOT / f"configs/datasets/{name}.yaml",
        ]
    )
    validate_training_contract(cfg)
    data = cfg.stages[0].data[0]
    assert cfg.name == data.name == name and cfg.space == "paul-test-rtis"
    assert (
        cfg.stages[0].name == "rtis"
        and data.loader == "folder"
        and data.mapping == "paul-test-rtis"
    )
    assert data.loader_options == {"require_groups": require_groups}
    assert str(data.root) == f"data/{name}" and cfg.output_root == f"runs/{name}"
    spec_path = tmp_path / "spec.json"
    write_spec(spec_path, delivery, groups_enforced=require_groups)
    target = tmp_path / name
    prepare_rad.prepare(delivery, spec_path, "paul" if arm == "paul" else "rendered", name, target)
    data = replace(data, root=str(target))
    space = load_space(ROOT / cfg.taxonomy_root, cfg.space)
    for split, expected in (("train", ["a/0000", "a/0001"]), ("val", ["b/0002"])):
        dataset = build_dataset(data, space, ROOT / cfg.taxonomy_root, split, Compose([]))
        assert [s.key for s in dataset.samples] == expected
        groups = [s.group for s in dataset.samples]
        # Without a groups map the loader falls back to the key, so stratified arms
        # expose no recording identity to leak checks; grouped arms do.
        assert groups == ([k.split("/")[0] for k in expected] if require_groups else expected)
