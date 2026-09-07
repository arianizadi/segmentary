"""Compare exported predictions against official COCO reference evaluators."""

from __future__ import annotations

import contextlib
import io
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from .data import ObjectDataset, _categories, _safe_file, decode_instance_mask
from .metrics import InstanceMetrics, PanopticMetrics


def compare_reference(data: ObjectDataset, predictions: Path, tolerance: float = 1e-8) -> dict:
    """Same native pixels/categories/predictions on both sides; no model inference."""
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Reference tolerance must be finite and nonnegative")
    document = json.loads((predictions / "predictions.json").read_text())
    if document.get("task", data.task) != data.task:
        raise ValueError("Prediction task differs from reference dataset")
    if _categories(document.get("categories"), data.task) != data.categories:
        raise ValueError("Prediction categories differ from reference dataset")
    prediction_images = document["images"]
    if len({row["id"] for row in prediction_images}) != len(prediction_images) or len(
        {row["file_name"] for row in prediction_images}
    ) != len(prediction_images):
        raise ValueError("Duplicate prediction image ID or filename")
    categories = {c["id"]: i for i, c in enumerate(data.categories)}
    # Prediction exports enumerate files independently: join by relative image name.
    image_ids = {row["file_name"]: row["id"] for row in data.images}
    remap = {row["id"]: image_ids[row["file_name"]] for row in document["images"]}
    if set(remap.values()) != set(image_ids.values()) or len(remap) != len(image_ids):
        raise ValueError("Reference validation requires exactly the evaluation image set")
    annotations = [{**row, "image_id": remap[row["image_id"]]} for row in document["annotations"]]
    metric = (
        InstanceMetrics(data.num_classes, data.thing_ids)
        if data.task == "instance"
        else PanopticMetrics(data.num_classes, data.thing_ids)
    )
    grouped: dict[int, list] = {}
    for row in annotations:
        grouped.setdefault(row["image_id"], []).append(row)
    for index in range(len(data)):
        target = data[index]["target"]
        rows = grouped.get(target.image_id, [])
        if data.task == "instance":
            masks = [
                torch.from_numpy(decode_instance_mask(row["segmentation"], *target.original_size))
                for row in rows
            ]
            pred: dict[str, Any] = {
                "masks": torch.stack(masks)
                if masks
                else torch.zeros((0, *target.original_size), dtype=torch.bool),
                "class_ids": torch.tensor(
                    [categories[row["category_id"]] for row in rows], dtype=torch.long
                ),
                "scores": torch.tensor([row["score"] for row in rows], dtype=torch.float64),
            }
        else:
            if len(rows) != 1:
                raise ValueError("Expected one panoptic annotation per image")
            with Image.open(_safe_file(predictions, rows[0]["file_name"])) as handle:
                rgb = np.asarray(handle.convert("RGB")).astype(np.int64)
            pred = {
                "segmentation": torch.from_numpy(
                    rgb[..., 0] + 256 * rgb[..., 1] + 65536 * rgb[..., 2]
                ),
                "segments_info": [
                    {
                        **s,
                        "category_id": categories[s["category_id"]],
                        "isthing": categories[s["category_id"]] in data.thing_ids,
                    }
                    for s in rows[0]["segments_info"]
                ],
            }
        metric.update(pred, target)
    actual = metric.compute()
    if data.task == "instance":
        from pycocotools.coco import COCO
        from pycocotools.cocoeval import COCOeval

        with contextlib.redirect_stdout(io.StringIO()):
            truth = COCO(str(data.annotation_path))
            if annotations:
                result = truth.loadRes(annotations)
            else:
                result = COCO()
                result.dataset = {
                    "images": truth.dataset["images"],
                    "categories": truth.dataset["categories"],
                    "annotations": [],
                }
                result.createIndex()
            evaluator = COCOeval(truth, result, "segm")
            evaluator.params.imgIds = sorted(image_ids.values())
            evaluator.evaluate()
            evaluator.accumulate()
        precision = evaluator.eval["precision"][:, :, :, 0, 2]

        def average(values):
            supported = values[values > -1]
            return float(supported.mean()) if supported.size else None

        expected = {
            "map": average(precision),
            "map_50": average(precision[0]),
            "map_75": average(precision[5]),
            "mar_100": average(evaluator.eval["recall"][:, :, 0, 2]),
        }
        per_class = {
            str(i): {
                "map": average(precision[:, :, j]),
                "map_50": average(precision[0, :, j]),
                "map_75": average(precision[5, :, j]),
                "mar_100": average(evaluator.eval["recall"][:, j, 0, 2]),
            }
            for j, cat in enumerate(evaluator.params.catIds)
            if (i := categories.get(cat)) is not None
        }
        implementation = "pycocotools.cocoeval.COCOeval (segm, area=all, maxDets=100)"
    else:
        from panopticapi.evaluation import pq_compute_single_core

        gt = json.loads(data.annotation_path.read_text())
        pred_by_id = {row["image_id"]: row for row in annotations}
        pairs = [(row, pred_by_id[row["image_id"]]) for row in gt["annotations"]]
        with contextlib.redirect_stdout(io.StringIO()):
            stats = pq_compute_single_core(
                0,
                pairs,
                str(data.panoptic_root),
                str(predictions),
                {c["id"]: c for c in data.categories},
            )
            if any(
                stats[c["id"]].tp + stats[c["id"]].fp + stats[c["id"]].fn for c in data.categories
            ):
                aggregate, official_class = stats.pq_average(
                    {c["id"]: c for c in data.categories}, isthing=None
                )
            else:
                # Official pq_average divides by zero with no supported classes.
                # Its verified zero counts represent an undefined aggregate, not 0% PQ.
                aggregate = {key: None for key in ("pq", "sq", "rq")}
                official_class = {
                    c["id"]: {key: 0.0 for key in ("pq", "sq", "rq")} for c in data.categories
                }
        expected = {key: aggregate[key] for key in ("pq", "sq", "rq")}
        per_class = {str(categories[cat]): values for cat, values in official_class.items()}
        implementation = "cocodataset/panopticapi pq_compute_single_core + PQStat.pq_average"
    differences = {}
    for key, value in expected.items():
        differences[key] = (
            abs(actual[key] - value)
            if value is not None and actual[key] is not None
            else (0.0 if value is actual[key] else None)
        )
    for category, values in per_class.items():
        for key in expected:
            if key not in values:
                continue
            a, b = actual["per_class"][category].get(key), values[key]
            # Official PQ uses zero for unsupported classes; local reports use null.
            if a is not None:
                differences[f"class/{category}/{key}"] = abs(a - b)
    return {
        "implementation": implementation,
        "tolerance": tolerance,
        "passed": all(v is not None and v <= tolerance for v in differences.values()),
        "expected": expected,
        "actual": {key: actual[key] for key in expected},
        "absolute_differences": differences,
    }
