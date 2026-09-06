"""Audit native RTIS exports into unsplit image/index-mask pairs; never edit sources.

Rasterization follows Supervisely's OpenCV fillPoly/bitmap-alpha implementation.
CVAT RLE uses alternating background/foreground runs in row-major order.
Later Supervisely objects / higher CVAT z_order paint over earlier objects, as
in the source renderers. Cross-class overwritten pixels are counted for review.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
from contextlib import suppress
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

ALIASES = {f"{name}_1": name for name in ("road", "standing-water", "terrain", "pole")}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def polygon(shape: tuple[int, int], exterior: list, interior: list) -> np.ndarray:
    mask = np.zeros(shape, np.uint8)
    contours = []
    for points in [exterior, *interior]:
        arr = np.asarray(points, dtype=float)
        if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) < 3 or not np.isfinite(arr).all():
            raise ValueError("Invalid polygon contour")
        contours.append(np.rint(arr).astype(np.int32))
    cv2.fillPoly(mask, contours[:1], 1)
    for contour in contours[1:]:
        cv2.fillPoly(mask, [contour], 0)
    return mask.astype(bool)


def place(shape: tuple[int, int], crop: np.ndarray, left: int, top: int) -> np.ndarray:
    height, width = crop.shape
    if left < 0 or top < 0 or left + width > shape[1] or top + height > shape[0]:
        raise ValueError("Bitmap extends outside image")
    mask = np.zeros(shape, bool)
    mask[top : top + height, left : left + width] = crop
    return mask


def sly_bitmap(obj: dict, shape: tuple[int, int]) -> np.ndarray:
    raw = base64.b64decode(obj["bitmap"]["data"], validate=True)
    with suppress(zlib.error):
        raw = zlib.decompress(raw)
    with Image.open(io.BytesIO(raw)) as im:
        if im.mode == "P":
            im = im.convert("RGBA")
        arr = np.asarray(im)
    if arr.ndim == 3 and arr.shape[2] == 4:
        crop = arr[:, :, 3] > 0
    elif arr.ndim == 2:
        crop = arr > 0
    else:
        raise ValueError("Unsupported Supervisely bitmap encoding")
    return place(shape, crop, *obj["bitmap"]["origin"])


def cvat_bitmap(obj: ET.Element, shape: tuple[int, int]) -> np.ndarray:
    width, height = int(obj.attrib["width"]), int(obj.attrib["height"])
    runs = [int(x.strip()) for x in obj.attrib["rle"].split(",")]
    if min(runs) < 0 or sum(runs) != width * height:
        raise ValueError("Invalid CVAT RLE lengths")
    crop = np.repeat(np.arange(len(runs)) % 2, runs).reshape(height, width).astype(bool)
    return place(shape, crop, int(obj.attrib["left"]), int(obj.attrib["top"]))


def render(objects: list, shape: tuple[int, int], labels: dict, source: str) -> tuple:
    result = np.full(shape, 255, np.uint8)
    painted = np.zeros(shape, bool)
    conflicts = np.zeros(shape, bool)
    geometries = Counter()
    empty_shapes = 0
    for obj in objects:
        title = obj["classTitle"] if source == "supervisely" else obj.attrib["label"]
        label = labels[ALIASES.get(title, title)]
        kind = obj["geometryType"] if source == "supervisely" else obj.tag
        geometries[kind] += 1
        if kind == "polygon":
            if source == "supervisely":
                points = obj["points"]
            else:
                points = {
                    "exterior": [
                        [float(v) for v in p.split(",")] for p in obj.attrib["points"].split(";")
                    ],
                    "interior": [],
                }
            region = polygon(shape, points["exterior"], points["interior"])
        elif kind == "bitmap" and source == "supervisely":
            region = sly_bitmap(obj, shape)
        elif kind == "mask" and source == "cvat":
            region = cvat_bitmap(obj, shape)
        else:
            raise ValueError(f"Unsupported geometry: {kind}")
        empty_shapes += int(not region.any())
        conflicts |= region & painted & (result != label)
        result[region] = label
        painted |= region
    return result, {
        "geometry_counts": dict(geometries),
        "empty_shapes": empty_shapes,
        "overlap_pixels": int(conflicts.sum()),
        "uncovered_pixels": int((~painted).sum()),
        "ignore_pixels": int((result == 255).sum()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    for name in ("images", "masks", "audit", "overlays"):
        (args.out / name).mkdir()
    meta = json.loads((args.source / "supervisely/meta.json").read_text())
    classes = [c for c in meta["classes"] if c["title"] not in ALIASES and c["title"] != "void"]
    labels = {c["title"]: i for i, c in enumerate(classes)} | {"void": 255}
    palette = np.zeros((256, 3), np.uint8)
    for c in classes:
        palette[labels[c["title"]]] = tuple(bytes.fromhex(c["color"].lstrip("#")))
    schema = {
        "name": "paul-test-rtis",
        "description": "RTIS native rail and anomaly labels",
        "ignore_index": 255,
        "classes": [
            {
                "id": labels[c["title"]],
                "name": c["title"],
                "color": palette[labels[c["title"]]].tolist(),
            }
            for c in classes
        ],
        "thin_classes": [
            labels[n]
            for n in ("rail-raised", "rail-embedded", "pole", "traffic-light", "traffic-sign")
        ],
    }
    (args.out / "canonical.yaml").write_text(yaml.safe_dump(schema, sort_keys=False))
    (args.out / "audit/source-meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    candidates = []
    for image in sorted((args.source / "supervisely").glob("*/img/*")):
        if not image.is_file():
            continue
        annotation = image.parent.parent / "ann" / (image.name + ".json")
        data = json.loads(annotation.read_text()) if annotation.exists() else None
        candidates.append(("supervisely", image, annotation, data))
    xml = args.source / "cvat/annotations.xml"
    cvat_images = {i.attrib["name"]: i for i in ET.parse(xml).getroot().findall("image")}
    for image in sorted((args.source / "cvat/images").rglob("*")):
        if image.is_file():
            name = image.relative_to(args.source / "cvat/images").as_posix()
            node = cvat_images.get(name)
            if node is None:
                node = cvat_images.get(image.name)
            candidates.append(("cvat", image, xml, node))
    rows, exclusions, seen = [], [], {}
    for index, (source, image, annotation, data) in enumerate(candidates):
        objects = (
            [] if data is None else (data["objects"] if source == "supervisely" else list(data))
        )
        row = {
            "source": source,
            "source_image": str(image),
            "source_annotation": str(annotation),
            "filename": image.name,
            "source_dataset": image.parent.parent.name if source == "supervisely" else "task-61",
            "annotation_count": len(objects),
            "image_sha256": digest(image),
        }
        if not objects:
            row["reason"] = "missing_annotation" if data is None else "empty_annotation"
            exclusions.append(row)
            continue
        with Image.open(image) as im:
            rgb = np.asarray(im.convert("RGB"))
        shape = rgb.shape[:2]
        expected = (
            (data["size"]["height"], data["size"]["width"])
            if source == "supervisely"
            else (int(data.attrib["height"]), int(data.attrib["width"]))
        )
        if shape != expected:
            raise ValueError(f"Image/annotation dimensions differ: {image}")
        if source == "cvat":
            objects = sorted(objects, key=lambda o: int(o.attrib.get("z_order", 0)))
        mask, stats = render(objects, shape, labels, source)
        row.update(stats)
        row["width"], row["height"] = shape[1], shape[0]
        row["pixel_sha256"] = hashlib.sha256(str(shape).encode() + rgb.tobytes()).hexdigest()
        row["mask_sha256"] = hashlib.sha256(mask.tobytes()).hexdigest()
        row["class_pixels"] = {
            str(i): int(n) for i, n in enumerate(np.bincount(mask.ravel(), minlength=256)) if n
        }
        if np.all(mask == 255):
            row["reason"] = "no_trainable_pixels"
            exclusions.append(row)
            continue
        # Exact decoded image matches are one sample. Supervisely is the primary
        # reviewed project; retain its annotation and explicitly audit differences.
        previous = seen.get(row["pixel_sha256"])
        if previous is not None:
            prior = np.asarray(Image.open(args.out / "masks" / (previous["key"] + ".png")))
            row.update(
                reason="duplicate_image",
                retained_key=previous["key"],
                differing_mask_pixels=int((prior != mask).sum()),
                duplicate_policy="first Supervisely annotation retained; CVAT is secondary",
            )
            exclusions.append(row)
            if row["differing_mask_pixels"]:
                Image.fromarray(mask).save(args.out / "audit" / f"duplicate-{index}.png")
            continue
        safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", image.stem)
        key = safe_stem + "-" + row["pixel_sha256"][:12]
        row["key"] = key
        row["image_extension"] = image.suffix.lower()
        row["annotation_sha256"] = digest(annotation)
        seen[row["pixel_sha256"]] = row
        shutil.copyfile(image, args.out / "images" / (key + image.suffix.lower()))
        Image.fromarray(mask).save(args.out / "masks" / (key + ".png"))
        overlay = (0.55 * rgb + 0.45 * palette[mask]).astype(np.uint8)
        preview = Image.fromarray(np.concatenate((rgb, overlay), axis=1))
        preview.thumbnail((1280, 400))
        preview.save(args.out / "overlays" / (key + ".jpg"), quality=85)
        rows.append(row)
        if len(rows) % 25 == 0:
            print(f"Prepared {len(rows)} annotated images", flush=True)
    summary = {
        "dataset": "paul-test-rtis",
        "input_images": len(candidates),
        "retained": len(rows),
        "excluded": dict(Counter(r["reason"] for r in exclusions)),
        "class_aliases": ALIASES,
        "overlap_policy": "source rendering order; Supervisely list order, CVAT ascending z_order",
        "uncovered_and_void": 255,
        "split_status": "not yet split",
        "source_image_counts": dict(Counter(r[0] for r in candidates)),
        "duplicate_mask_conflicts": sum(r.get("differing_mask_pixels", 0) > 0 for r in exclusions),
    }
    for name, value in (("samples", rows), ("exclusions", exclusions), ("summary", summary)):
        (args.out / "audit" / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
