"""Independent pixel fixtures for annotation auditing and immutable corrections."""

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scripts.audit_annotations import audit, inspect_layers, layers_for, safe_path, version_dataset
from scripts.prepare_rtis import digest


def fixture_dataset(tmp_path):
    source = tmp_path / "source/supervisely/scene"
    (source / "ann").mkdir(parents=True)
    (source / "img").mkdir()
    image = source / "img/frame.png"
    Image.fromarray(np.full((4, 4, 3), 100, np.uint8)).save(image)
    annotation = source / "ann/frame.png.json"
    annotation.write_text(
        json.dumps(
            {
                "size": {"height": 4, "width": 4},
                "objects": [
                    {
                        "id": "sky",
                        "classTitle": "sky",
                        "geometryType": "polygon",
                        "points": {"exterior": [[0, 0], [3, 0], [3, 3], [0, 3]], "interior": []},
                    },
                    {
                        "id": "terrain",
                        "classTitle": "terrain",
                        "geometryType": "polygon",
                        "points": {"exterior": [[0, 2], [3, 2], [3, 3], [0, 3]], "interior": []},
                    },
                ],
            }
        )
    )
    dataset = tmp_path / "v1"
    (dataset / "audit").mkdir(parents=True)
    (dataset / "masks/val/scene").mkdir(parents=True)
    (dataset / "images/val/scene").mkdir(parents=True)
    (dataset / "images/val/scene/frame.png").write_bytes(image.read_bytes())
    mask = np.zeros((4, 4), np.uint8)
    mask[2:] = 1
    Image.fromarray(mask).save(dataset / "masks/val/scene/frame.png")
    (dataset / "classes.json").write_text(
        json.dumps(
            {
                "ignore_index": 255,
                "classes": [
                    {"id": 0, "name": "sky", "color": [0, 100, 255]},
                    {"id": 1, "name": "terrain", "color": [100, 50, 0]},
                ],
            }
        )
    )
    row = {
        "split": "val",
        "key": "scene/frame",
        "height": 4,
        "width": 4,
        "source": "supervisely",
        "source_image": str(image),
        "source_annotation": str(annotation),
        "filename": "frame.png",
        "annotation_sha256": digest(annotation),
    }
    (dataset / "audit/samples.json").write_text(json.dumps([row]))
    (dataset / "splits.json").write_text('{"val":["scene/frame"]}')
    (dataset / "audit/summary.json").write_text("{}")
    return dataset, row


def test_layer_order_overlap_void_and_final_mismatch():
    whole = np.ones((2, 3), bool)
    bottom = np.zeros_like(whole)
    bottom[1] = True
    point = np.zeros_like(whole)
    point[1, 1] = True
    final = np.array([[0, 0, 1], [1, 255, 1]])
    stats, maps = inspect_layers(
        [("a", 0, whole), ("b", 1, bottom), ("c", 255, point)], final, 255, 0.85, 0.5
    )
    assert stats["overlap_pixels"] == stats["cross_class_overlap_pixels"] == 3
    assert stats["mismatch_pixels"] == 1
    assert stats["objects"][0]["cross_class_lost_pixels"] == 3
    assert stats["objects"][1]["cross_class_lost_pixels"] == 1
    assert stats["objects"][2]["remaining_class_pixels"] == 1
    assert sum(e["pixels"] for e in stats["overwrite_events"]) == 4
    assert maps["native"][1, 1] == 255


def test_same_class_overlap_is_not_class_loss():
    region = np.ones((2, 2), bool)
    stats, _ = inspect_layers(
        [("a", 0, region), ("b", 0, region)], np.zeros((2, 2), int), 255, 1, 0.5
    )
    assert stats["objects"][0]["overwritten_pixels"] == 4
    assert stats["objects"][0]["cross_class_lost_pixels"] == 0
    assert stats["cross_class_overlap_pixels"] == 0


def test_end_to_end_native_review_and_changed_source(tmp_path):
    dataset, row = fixture_dataset(tmp_path)
    report = audit(dataset, tmp_path / "review")
    result = report["samples"][0]
    assert report["errors"] == 0
    assert result["mismatch_pixels"] == 0
    assert result["cross_class_overlap_pixels"] == 8
    assert result["objects"][0]["lost_fraction"] == 0.5
    assert (tmp_path / "review" / result["preview"]).is_file()
    assert "object_class_coverage_lost:sky" in (tmp_path / "review/review.csv").read_text()
    annotation = Path(row["source_annotation"])
    annotation.write_text(annotation.read_text() + "\n")
    report = audit(dataset, tmp_path / "review2")
    assert "source_annotation_changed_since_packaging" in report["samples"][0]["flags"]


def test_cvat_z_order_and_mask(tmp_path):
    annotation = tmp_path / "annotations.xml"
    annotation.write_text(
        '<annotations><image name="nested/a.png" width="3" height="2"><mask label="water" z_order="3" width="1" height="1" left="1" top="1" rle="0,1"/><polygon label="sky" z_order="0" points="0,0;2,0;2,1;0,1"/></image></annotations>'
    )
    row = {
        "source": "cvat",
        "source_annotation": str(annotation),
        "source_image": "/old/cvat/images/nested/a.png",
        "filename": "a.png",
        "key": "a",
        "height": 2,
        "width": 3,
    }
    layers, _ = layers_for(row, {"sky": 0, "water": 1}, None)
    final = np.zeros((2, 3), int)
    final[1, 1] = 1
    stats, _ = inspect_layers(layers, final, 255, 0.85, 0.5)
    assert stats["mismatch_pixels"] == 0
    assert stats["cross_class_overlap_pixels"] == 1


def correction_plan(tmp_path, dataset, value=1):
    replacement = tmp_path / "replacement.png"
    Image.fromarray(np.full((4, 4), value, np.uint8)).save(replacement)
    plan = tmp_path / "corrections.json"
    plan.write_text(
        json.dumps(
            {
                "version": "v2",
                "reviewer": "human",
                "corrections": [
                    {
                        "split": "val",
                        "key": "scene/frame",
                        "expected_mask_sha256": digest(dataset / "masks/val/scene/frame.png"),
                        "replacement_mask": "replacement.png",
                        "reason": "Reviewed source correction",
                    }
                ],
            }
        )
    )
    return plan


def test_version_preserves_parent_and_splits_archives_stale_outputs(tmp_path):
    dataset, _ = fixture_dataset(tmp_path)
    before = {str(p.relative_to(dataset)): digest(p) for p in dataset.rglob("*") if p.is_file()}
    plan = correction_plan(tmp_path, dataset)
    result = version_dataset(dataset, plan, tmp_path / "v2")
    assert before == {
        str(p.relative_to(dataset)): digest(p) for p in dataset.rglob("*") if p.is_file()
    }
    assert result["parent_files_sha256"] == before
    assert (tmp_path / "v2/splits.json").read_bytes() == (dataset / "splits.json").read_bytes()
    assert not (tmp_path / "v2/audit/summary.json").exists()
    assert (tmp_path / "v2/audit/parent-version-artifacts/audit-summary.json").exists()
    assert json.loads((tmp_path / "v2/audit/samples.json").read_text())[0]["class_pixels"] == {
        "1": 16
    }
    with pytest.raises(ValueError, match="new separate"):
        version_dataset(dataset, plan, tmp_path / "v2")


@pytest.mark.parametrize("failure", ["hash", "class", "duplicate", "symlink"])
def test_invalid_corrections_never_create_version(tmp_path, failure):
    dataset, _ = fixture_dataset(tmp_path)
    plan = correction_plan(tmp_path, dataset, 23 if failure == "class" else 1)
    content = json.loads(plan.read_text())
    if failure == "hash":
        content["corrections"][0]["expected_mask_sha256"] = "bad"
    if failure == "duplicate":
        content["corrections"] *= 2
    if failure == "symlink":
        (dataset / "link").symlink_to(dataset / "classes.json")
    plan.write_text(json.dumps(content))
    with pytest.raises(ValueError):
        version_dataset(dataset, plan, tmp_path / "v2")
    assert not (tmp_path / "v2").exists()


def test_audit_error_is_explicit_and_paths_cannot_escape(tmp_path):
    dataset, row = fixture_dataset(tmp_path)
    Path(row["source_annotation"]).unlink()
    report = audit(dataset, tmp_path / "review")
    assert report["errors"] == 1
    assert report["samples"][0]["flags"] == ["audit_error"]
    with pytest.raises(ValueError, match="escapes"):
        safe_path(dataset, "../../escape")
    with pytest.raises(ValueError, match="outside"):
        audit(dataset, dataset / "review")


def test_relative_cli_paths_write_valid_preview_links(tmp_path, monkeypatch):
    dataset, _ = fixture_dataset(tmp_path)
    monkeypatch.chdir(tmp_path)
    report = audit(Path(dataset.name), Path("review"))
    assert report["errors"] == 0
    assert report["samples"][0]["preview"] == "previews/val/scene/frame.jpg"


def test_changed_source_image_and_missing_legacy_hash_are_explicit(tmp_path):
    dataset, row = fixture_dataset(tmp_path)
    row.pop("annotation_sha256")
    row["image_sha256"] = digest(Path(row["source_image"]))
    (dataset / "audit/samples.json").write_text(json.dumps([row]))
    Image.new("RGB", (4, 4), (255, 0, 0)).save(row["source_image"])
    report = audit(dataset, tmp_path / "review")
    record = report["samples"][0]
    assert record["source_annotation_packaging_hash_status"] == "unavailable"
    assert {
        "source_annotation_packaging_hash_unavailable",
        "source_image_changed_since_packaging",
        "packaged_image_differs_from_native_source",
    } <= set(record["flags"])
    assert report["errors"] == 0
