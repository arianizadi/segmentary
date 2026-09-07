"""Object viewer exports preserve masks and join by filename, never incidental IDs."""

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from segmentary.objects.viewer_bundle import export_bundle, foreground_runs


def fixture(tmp_path: Path, task: str = "instance"):
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (4, 4)).save(images / "frame.png")
    categories = [{"id": 3, "name": "object", "isthing": 1}]
    gt = {
        "images": [{"id": 99, "file_name": "frame.png", "width": 4, "height": 4}],
        "categories": categories,
        "annotations": [],
    }
    pred_dir = tmp_path / "prediction"
    pred_dir.mkdir()
    pred = {
        "task": task,
        "images": [{"id": 1, "file_name": "frame.png", "width": 4, "height": 4}],
        "categories": categories,
        "annotations": [],
        "checkpoint_sha256": "abc",
    }
    masks = tmp_path / "masks"
    masks.mkdir()
    if task == "instance":
        # Two independently stored, overlapping foreground masks.
        for i in range(2):
            record = {
                "id": i + 5,
                "category_id": 3,
                "segmentation": {"size": [4, 4], "counts": [i, 8, 8 - i]},
                "area": 8,
                "bbox": [0, 0, 4, 4],
                "iscrowd": 0,
            }
            gt["annotations"].append({**record, "image_id": 99})
            pred["annotations"].append({**record, "image_id": 1, "score": 0.9})
    else:
        pixels = np.zeros((4, 4, 3), dtype=np.uint8)
        pixels[:2, :, 0] = 1
        pixels[2:, :, 0] = 2
        for root in (masks, pred_dir):
            Image.fromarray(pixels).save(root / "segments.png")
        segments = [{"id": i, "category_id": 3, "area": 8, "iscrowd": 0} for i in (1, 2)]
        gt["annotations"] = [
            {"image_id": 99, "file_name": "segments.png", "segments_info": segments}
        ]
        pred["annotations"] = [
            {"image_id": 1, "file_name": "segments.png", "segments_info": segments}
        ]
    annotation = tmp_path / "gt.json"
    prediction = pred_dir / "predictions.json"
    annotation.write_text(json.dumps(gt))
    prediction.write_text(json.dumps(pred))
    return images, annotation, prediction, masks


@pytest.mark.parametrize("task", ["instance", "panoptic"])
def test_export_independent_ids_and_filename_join(tmp_path, task):
    images, gt, predictions, masks = fixture(tmp_path, task)
    output = tmp_path / "bundle"
    assert export_bundle(
        images, gt, [predictions], output, masks if task == "panoptic" else None
    ) == {"scenes": 1, "models": 1}
    scene = json.loads((output / "scene-99" / "objects.json").read_text())
    assert scene["task"] == task
    assert len(scene["layers"][0]["objects"]) == 2
    assert scene["layers"][0]["objects"][0]["runs"] == scene["layers"][1]["objects"][0]["runs"]
    assert scene["layers"][1]["checkpoint"] == "abc"
    assert json.loads((output / "config.json").read_text())["task"] == task
    with pytest.raises(FileExistsError):
        export_bundle(images, gt, [predictions], output, masks if task == "panoptic" else None)


def test_runs_roundtrip_preserves_disconnected_regions():
    mask = np.array([[1, 1, 0], [0, 1, 0], [1, 0, 1]], dtype=bool)
    out = np.zeros(mask.size, dtype=bool)
    for start, length in foreground_runs(mask):
        out[start : start + length] = True
    np.testing.assert_array_equal(out.reshape(mask.shape), mask)


@pytest.mark.parametrize("change", ["filename", "category", "hash"])
def test_misaligned_predictions_rejected(tmp_path, change):
    images, gt, prediction, _ = fixture(tmp_path)
    document = json.loads(prediction.read_text())
    if change == "filename":
        document["images"][0]["file_name"] = "unrelated.png"
    elif change == "category":
        document["categories"][0]["name"] = "different"
    else:
        document["images"][0]["sha256"] = "wrong"
    prediction.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        export_bundle(images, gt, [prediction], tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".object-review-*"))


def test_panoptic_stuff_identity_is_preserved(tmp_path):
    images, gt, predictions, masks = fixture(tmp_path, "panoptic")
    for file in (gt, predictions):
        document = json.loads(file.read_text())
        document["categories"][0]["isthing"] = 0
        file.write_text(json.dumps(document))
    output = tmp_path / "bundle"
    export_bundle(images, gt, [predictions], output, masks)
    objects = json.loads((output / "scene-99" / "objects.json").read_text())["layers"][0]["objects"]
    assert [object["id"] for object in objects] == [1, 2]
    assert all(not object["isthing"] for object in objects)
