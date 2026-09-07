"""Build a portable object-review bundle without flattening overlapping masks.

Run ``python -m segmentary.objects.viewer_bundle --help``. Predictions must be
Segmentary's predictions.json, whose image filenames are joined to COCO ground
truth filenames (prediction image IDs need not equal dataset image IDs).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .data import ObjectDataset, _safe_file, decode_instance_mask


def foreground_runs(mask: np.ndarray) -> list[list[int]]:
    """Return sorted [start, length] foreground intervals in row-major order."""
    padded = np.pad(mask.astype(np.int8).ravel(), (1, 1))
    changes = np.flatnonzero(np.diff(padded))
    return [[int(a), int(b - a)] for a, b in zip(changes[::2], changes[1::2], strict=True)]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _export_bundle(
    images: Path,
    annotations: Path,
    predictions: list[Path],
    output: Path,
    panoptic_masks: Path | None = None,
) -> dict[str, int]:
    documents = [json.loads(path.read_text()) for path in predictions]
    if not documents:
        raise ValueError("At least one predictions.json is required")
    task = documents[0].get("task")
    if task not in {"instance", "panoptic"}:
        raise ValueError("Predictions must declare instance or panoptic task")
    dataset = ObjectDataset(images, annotations, task, panoptic_masks=panoptic_masks)
    if len(dataset.categories) > 255:
        raise ValueError("Viewer currently supports at most 255 categories")
    categories = {c["id"]: c for c in dataset.categories}
    class_ids = dataset.category_id_to_class_id
    gt = json.loads(annotations.read_text())
    models = []
    gt_names = {image["file_name"] for image in dataset.images}
    if len(gt_names) != len(dataset.images):
        raise ValueError("Ground-truth filenames must be unique")
    gt_by_image: dict[int, list[dict[str, Any]]] = {}
    for annotation in gt["annotations"]:
        gt_by_image.setdefault(annotation["image_id"], []).append(annotation)
    for path, document in zip(predictions, documents, strict=True):
        if document.get("task") != task:
            raise ValueError("All prediction tasks must match")
        if {c["id"]: (c["name"], bool(c.get("isthing", 1))) for c in document["categories"]} != {
            c["id"]: (c["name"], bool(c["isthing"])) for c in dataset.categories
        }:
            raise ValueError("Prediction category IDs, names and thing/stuff labels must match GT")
        by_name = {record["file_name"]: record for record in document["images"]}
        if len(by_name) != len(document["images"]) or set(by_name) != gt_names:
            raise ValueError("Prediction filenames must match GT exactly, without duplicates")
        image_ids = [record["id"] for record in document["images"]]
        if len(set(image_ids)) != len(image_ids):
            raise ValueError("Duplicate prediction image IDs")
        grouped: dict[int, list[dict[str, Any]]] = {i: [] for i in image_ids}
        for record in document["annotations"]:
            if record["image_id"] not in grouped:
                raise ValueError("Prediction references unknown image")
            grouped[record["image_id"]].append(record)
        models.append((path, document, by_name, grouped))
    output = output.resolve()
    protected = [images.resolve(), annotations.resolve(), *(path.resolve() for path in predictions)]
    if panoptic_masks is not None:
        protected.append(panoptic_masks.resolve())
    if any(output == p or output in p.parents or p in output.parents for p in protected):
        raise ValueError("Output must be separate from inputs")
    output.mkdir(parents=True, exist_ok=False)
    labels = [
        {
            "name": f"category-{c['id']}",
            "readable": c["name"],
            "evaluate": True,
            "instances": bool(c["isthing"]),
            "color": c.get(
                "color",
                [
                    (c["id"] * 67 + 71) % 256,
                    (c["id"] * 131 + 93) % 256,
                    (c["id"] * 193 + 117) % 256,
                ],
            ),
        }
        for c in dataset.categories
    ]
    (output / "config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "task": task,
                "title": f"{task.title()} object review",
                "labels": labels,
                "ignoreIndex": 255,
            }
        )
        + "\n"
    )
    for image in dataset.images:
        width, height = image["width"], image["height"]
        source = _safe_file(images.resolve(), image["file_name"])
        with Image.open(source) as original:
            if original.size != (width, height):
                raise ValueError("Ground-truth image dimensions do not match pixels")
        scene = output / f"scene-{image['id']}"
        scene.mkdir()
        if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            shutil.copyfile(source, scene / ("input" + source.suffix.lower()))
        else:
            with Image.open(source) as original:
                original.convert("RGB").save(scene / "input.png")
        layers = []
        gt_records = gt_by_image.get(image["id"], [])
        sources = [("Ground truth", gt_records, panoptic_masks, None)]
        for index, (path, doc, by_name, grouped) in enumerate(models):
            record = by_name[image["file_name"]]
            if (record["width"], record["height"]) != (width, height):
                raise ValueError("Prediction dimensions differ from GT")
            if record.get("sha256") and record["sha256"] != _digest(source):
                raise ValueError("Prediction image hash differs from GT image")
            sources.append(
                (
                    f"Model {index + 1}: {path.parent.name}",
                    grouped[record["id"]],
                    path.parent,
                    doc.get("checkpoint_sha256"),
                )
            )
        for layer_index, (name, records, mask_root, checkpoint) in enumerate(sources):
            objects = []
            semantic = np.full((height, width), 255, dtype=np.uint8)
            segment_map = None
            if task == "panoptic":
                if len(records) != 1 or mask_root is None:
                    raise ValueError("Panoptic image needs exactly one segmentation record")
                with Image.open(_safe_file(mask_root.resolve(), records[0]["file_name"])) as png:
                    if png.mode != "RGB" or png.size != (width, height):
                        raise ValueError("Panoptic masks must be native-size RGB PNGs")
                    rgb = np.asarray(png, dtype=np.uint32)
                segment_map = rgb[..., 0] + 256 * rgb[..., 1] + 65536 * rgb[..., 2]
                records = records[0]["segments_info"]
                listed = [r["id"] for r in records]
                if len(set(listed)) != len(listed) or 0 in listed:
                    raise ValueError("Panoptic segment IDs must be unique and nonzero")
                if set(np.unique(segment_map)) - {0} != set(listed):
                    raise ValueError("Panoptic segment IDs disagree with segments_info")
            seen = set()
            for index, record in enumerate(records):
                category = record["category_id"]
                if category not in categories:
                    raise ValueError("Unknown object category")
                object_id = record.get("id", index + 1)
                if type(object_id) is not int or object_id < 0 or object_id in seen:
                    raise ValueError(
                        "Object IDs must be unique nonnegative integers within each image"
                    )
                seen.add(object_id)
                score = record.get("score")
                if score is not None and (
                    isinstance(score, bool)
                    or not isinstance(score, (int, float))
                    or not np.isfinite(score)
                    or not 0 <= score <= 1
                ):
                    raise ValueError("Confidence must be finite and between zero and one")
                mask = (
                    segment_map == object_id
                    if segment_map is not None
                    else decode_instance_mask(record["segmentation"], height, width)
                )
                if not mask.any():
                    raise ValueError("Empty object mask")
                semantic[mask] = class_ids[category]
                objects.append(
                    {
                        "id": object_id,
                        "classId": class_ids[category],
                        "categoryId": category,
                        "isthing": bool(categories[category]["isthing"]),
                        "crowd": bool(record.get("iscrowd", 0)),
                        "score": score,
                        "runs": foreground_runs(mask),
                    }
                )
            layers.append({"name": name, "checkpoint": checkpoint, "objects": objects})
            Image.fromarray(semantic).save(
                scene / ("gt.png" if layer_index == 0 else f"model-{layer_index}.png")
            )
        (scene / "scene.json").write_text(json.dumps({"title": image["file_name"]}) + "\n")
        (scene / "objects.json").write_text(
            json.dumps(
                {"version": 1, "task": task, "width": width, "height": height, "layers": layers},
                separators=(",", ":"),
            )
            + "\n"
        )
    return {"scenes": len(dataset), "models": len(models)}


def export_bundle(
    images: Path,
    annotations: Path,
    predictions: list[Path],
    output: Path,
    panoptic_masks: Path | None = None,
) -> dict[str, int]:
    """Publish only a complete bundle; leave all inputs and existing outputs untouched."""
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".object-review-", dir=output.parent) as temporary:
        staging = Path(temporary) / "bundle"
        result = _export_bundle(images, annotations, predictions, staging, panoptic_masks)
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"Output already exists: {output}")
        staging.rename(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, action="append", required=True)
    parser.add_argument("--panoptic-masks", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            export_bundle(
                args.images, args.annotations, args.predictions, args.out, args.panoptic_masks
            )
        )
    )


if __name__ == "__main__":
    main()
