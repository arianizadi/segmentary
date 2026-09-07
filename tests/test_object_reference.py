"""Independent official-evaluator parity on imperfect instance/panoptic predictions."""

import json

import numpy as np
import pytest
from PIL import Image
from pycocotools import mask as mask_utils

from segmentary.objects.benchmark_data import prepare_cityscapes
from segmentary.objects.data import ObjectDataset
from segmentary.objects.reference import compare_reference


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def encode(mask):
    region = mask_utils.encode(np.asfortranarray(mask.astype(np.uint8)))
    region["counts"] = region["counts"].decode("ascii")
    return region


def test_cityscapes_conversion_preserves_instances_crowd_void_and_provenance(tmp_path):
    for split in ("train", "val"):
        root = tmp_path / "city"
        image_dir = root / "leftImg8bit" / split / "city"
        gt = root / "gtFine" / split / "city"
        image_dir.mkdir(parents=True)
        gt.mkdir(parents=True)
        Image.new("RGB", (16, 16)).save(image_dir / "city_000_leftImg8bit.png")
        ids = np.zeros((16, 16), dtype=np.uint16)
        ids[0:4] = 7
        ids[4:8] = 24001
        ids[8:12] = 24002
        ids[12:14] = 24
        Image.fromarray(ids).save(gt / "city_000_gtFine_instanceIds.png")
    out = tmp_path / "converted"
    manifest = prepare_cityscapes(root, out, 1)
    assert len(manifest["splits"]["val"]["files"][0]["source_mask_sha256"]) == 64
    instance = ObjectDataset(
        images=root / "leftImg8bit/val", annotations=out / "val/instance.json", task="instance"
    )
    target = instance[0]["target"]
    assert target.iscrowd.sum() == 1 and len(target.masks) == 3
    panoptic = ObjectDataset(
        images=root / "leftImg8bit/val",
        annotations=out / "val/panoptic.json",
        panoptic_masks=out / "val/panoptic",
        task="panoptic",
    )
    assert len(panoptic[0]["target"].masks) == 4
    with pytest.raises(FileExistsError):
        prepare_cityscapes(root, out, 1)


@pytest.mark.parametrize("task", ["instance", "panoptic"])
def test_reference_parity_with_missing_extra_and_imperfect_objects(tmp_path, task):
    if task == "panoptic":
        pytest.importorskip("panopticapi")
    images = tmp_path / "images"
    images.mkdir()
    masks_dir = tmp_path / "gt"
    masks_dir.mkdir()
    pred_dir = tmp_path / "pred"
    pred_dir.mkdir()
    cats = [{"id": 7, "name": "object", "isthing": 1}, {"id": 23, "name": "other", "isthing": 1}]
    image_rows, gt_rows, pred_rows = [], [], []
    for i in range(1, 4):
        Image.new("RGB", (32, 32)).save(images / f"{i}.png")
        image_rows.append({"id": i, "file_name": f"{i}.png", "width": 32, "height": 32})
        gt_ids = np.zeros((32, 32), dtype=np.uint8)
        gt_ids[2:12, 2:12] = 1
        gt_ids[18:28, 18:28] = 2
        pred_ids = gt_ids.copy()
        pred_ids[2:4, 2:12] = 0
        if i == 2:
            pred_ids[pred_ids == 2] = 0
        if i == 3:
            pred_ids[18:28, 2:12] = 3
        if task == "instance":
            for region_id in [1, 2]:
                mask = gt_ids == region_id
                gt_rows.append(
                    {
                        "id": len(gt_rows) + 1,
                        "image_id": i,
                        "category_id": 7 if region_id == 1 else 23,
                        "segmentation": encode(mask),
                        "area": int(mask.sum()),
                        "iscrowd": int(i == 3 and region_id == 2),
                    }
                )
            for region_id in np.unique(pred_ids)[1:]:
                pred_rows.append(
                    {
                        "image_id": i,
                        "category_id": 7 if region_id in [1, 3] else 23,
                        "segmentation": encode(pred_ids == region_id),
                        "score": float(0.9 - region_id * 0.05),
                    }
                )
        else:
            Image.fromarray(
                np.stack([gt_ids, np.zeros_like(gt_ids), np.zeros_like(gt_ids)], -1)
            ).save(masks_dir / f"{i}.png")
            Image.fromarray(
                np.stack([pred_ids, np.zeros_like(pred_ids), np.zeros_like(pred_ids)], -1)
            ).save(pred_dir / f"{i}.png")
            gt_rows.append(
                {
                    "image_id": i,
                    "file_name": f"{i}.png",
                    "segments_info": [
                        {
                            "id": r,
                            "category_id": 7 if r == 1 else 23,
                            "area": int((gt_ids == r).sum()),
                            "iscrowd": int(i == 3 and r == 2),
                        }
                        for r in [1, 2]
                    ],
                }
            )
            pred_rows.append(
                {
                    "image_id": i,
                    "file_name": f"{i}.png",
                    "segments_info": [
                        {
                            "id": int(r),
                            "category_id": 7 if r in [1, 3] else 23,
                            "area": int((pred_ids == r).sum()),
                        }
                        for r in np.unique(pred_ids)[1:]
                    ],
                }
            )
    annotation = tmp_path / "truth.json"
    write_json(annotation, {"images": image_rows, "categories": cats, "annotations": gt_rows})
    write_json(
        pred_dir / "predictions.json",
        {"images": image_rows, "categories": cats, "annotations": pred_rows},
    )
    data = ObjectDataset(
        images=images,
        annotations=annotation,
        task=task,
        panoptic_masks=masks_dir if task == "panoptic" else None,
    )
    result = compare_reference(data, pred_dir)
    assert result["passed"], result
    assert max(result["absolute_differences"].values()) < 1e-8


def test_reference_all_void_panoptic_is_undefined_not_zero(tmp_path):
    pytest.importorskip("panopticapi")
    images, masks, predictions = (tmp_path / name for name in ("images", "masks", "predictions"))
    for directory in (images, masks, predictions):
        directory.mkdir()
        Image.new("RGB", (8, 8)).save(directory / "one.png")
    cats = [{"id": 7, "name": "road", "isthing": 0}]
    image_rows = [{"id": 1, "file_name": "one.png", "width": 8, "height": 8}]
    rows = [{"image_id": 1, "file_name": "one.png", "segments_info": []}]
    document = {"images": image_rows, "categories": cats, "annotations": rows}
    truth = tmp_path / "truth.json"
    write_json(truth, document)
    write_json(predictions / "predictions.json", document)
    data = ObjectDataset(images, truth, "panoptic", masks)
    result = compare_reference(data, predictions)
    assert result["passed"] and result["expected"]["pq"] is None
    json.dumps(result, allow_nan=False)
    document["images"] = image_rows * 2
    write_json(predictions / "predictions.json", document)
    with pytest.raises(ValueError, match="Duplicate"):
        compare_reference(data, predictions)
