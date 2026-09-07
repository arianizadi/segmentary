"""Versioned Cityscapes instance/panoptic conversion for reproducible validation.

Consumes licensed local Cityscapes data; never downloads or republishes images.
Label IDs and crowd convention follow cityscapesScripts/helpers/labels.py and
preparation/createPanopticImgs.py. COCO mask AP is not Cityscapes instance AP.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .runner import file_digest, write_json

# Original IDs, not train IDs. The final eight labels are things.
CITY_LABELS = [
    (7, "road"),
    (8, "sidewalk"),
    (11, "building"),
    (12, "wall"),
    (13, "fence"),
    (17, "pole"),
    (19, "traffic light"),
    (20, "traffic sign"),
    (21, "vegetation"),
    (22, "terrain"),
    (23, "sky"),
    (24, "person"),
    (25, "rider"),
    (26, "car"),
    (27, "truck"),
    (28, "bus"),
    (31, "train"),
    (32, "motorcycle"),
    (33, "bicycle"),
]


def prepare_cityscapes(root: Path, output: Path, limit: int | None = None) -> dict:
    from pycocotools import mask as mask_utils

    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    root = root.resolve()
    if output.exists():
        raise FileExistsError(output)
    categories = [{"id": i, "name": name, "isthing": int(i >= 24)} for i, name in CITY_LABELS]
    allowed = {c["id"]: c for c in categories}
    inputs = {}
    for split in ("train", "val"):
        files = sorted((root / "gtFine" / split).glob("*/*_gtFine_instanceIds.png"))
        if not files:
            raise FileNotFoundError(f"No Cityscapes instanceIds in {root / 'gtFine' / split}")
        inputs[split] = files[:limit] if limit else files
    output.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "schema": "segmentary-cityscapes-objects-v1",
        "source": str(root),
        "selection": "sorted relative annotation filenames within official train and val splits",
        "limit_per_split": limit,
        "splits": {},
        "purpose": "subset integration validation"
        if limit
        else "full official train/val conversion",
    }
    for split, files in inputs.items():
        images: list[dict[str, Any]] = []
        instances: list[dict[str, Any]] = []
        panoptic: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        mask_dir = output / split / "panoptic"
        mask_dir.mkdir(parents=True)
        for image_id, path in enumerate(files, 1):
            stem = path.name.removesuffix("_gtFine_instanceIds.png")
            image_name = f"{path.parent.name}/{stem}_leftImg8bit.png"
            image_path = root / "leftImg8bit" / split / image_name
            with Image.open(path) as handle:
                original = np.asarray(handle).astype(np.int64)
            with Image.open(image_path) as handle:
                if handle.size != (original.shape[1], original.shape[0]):
                    raise ValueError(f"Image/mask dimensions differ: {path}")
            images.append(
                {
                    "id": image_id,
                    "file_name": image_name,
                    "height": original.shape[0],
                    "width": original.shape[1],
                }
            )
            ids = np.zeros_like(original, dtype=np.uint32)
            segments: list[dict[str, Any]] = []
            for value in np.unique(original):
                category = int(value // 1000 if value >= 1000 else value)
                if category not in allowed:
                    continue
                mask = original == value
                crowd = int(bool(allowed[category]["isthing"]) and value < 1000)
                region = mask_utils.encode(np.asfortranarray(mask.astype(np.uint8)))
                bbox = mask_utils.toBbox(region).tolist()
                region["counts"] = region["counts"].decode("ascii")
                segment_id = len(segments) + 1
                ids[mask] = segment_id
                segments.append(
                    {
                        "id": segment_id,
                        "category_id": category,
                        "area": int(mask.sum()),
                        "bbox": bbox,
                        "iscrowd": crowd,
                    }
                )
                if allowed[category]["isthing"]:
                    instances.append(
                        {
                            "id": len(instances) + 1,
                            "image_id": image_id,
                            "category_id": category,
                            "segmentation": region,
                            "area": int(mask.sum()),
                            "bbox": bbox,
                            "iscrowd": crowd,
                        }
                    )
            filename = f"{stem}.png"
            Image.fromarray(
                np.stack([ids % 256, ids // 256 % 256, ids // 65536 % 256], -1).astype(np.uint8)
            ).save(mask_dir / filename)
            panoptic.append(
                {"image_id": image_id, "file_name": filename, "segments_info": segments}
            )
            provenance.append(
                {
                    "image": image_name,
                    "image_sha256": file_digest(image_path),
                    "source_mask": str(path.relative_to(root)),
                    "source_mask_sha256": file_digest(path),
                }
            )
        for task, annotation_rows in (("instance", instances), ("panoptic", panoptic)):
            write_json(
                output / f"{split}/{task}.json",
                {
                    "images": images,
                    "annotations": annotation_rows,
                    "categories": categories
                    if task == "panoptic"
                    else [c for c in categories if c["isthing"]],
                },
            )
        manifest["splits"][split] = {
            "images": str(root / "leftImg8bit" / split),
            "count": len(images),
            "files": provenance,
        }
    write_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--limit", type=int, help="First N sorted images per official split; omit for full data"
    )
    args = parser.parse_args()
    result = prepare_cityscapes(args.root, args.out, args.limit)
    print(
        json.dumps(
            {
                "output": str(args.out),
                "images": {k: v["count"] for k, v in result["splits"].items()},
            }
        )
    )


if __name__ == "__main__":
    main()
