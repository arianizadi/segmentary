"""Read-only native-resolution Cityscapes/RailSem19 annotation baseline audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from PIL import __version__ as pillow_version

# Official cityscapesscripts/helpers/labels.py IDs, including evaluation ignore IDs.
CITY_NAMES = [
    "unlabeled",
    "ego vehicle",
    "rectification border",
    "out of roi",
    "static",
    "dynamic",
    "ground",
    "road",
    "sidewalk",
    "parking",
    "rail track",
    "building",
    "wall",
    "fence",
    "guard rail",
    "bridge",
    "tunnel",
    "pole",
    "polegroup",
    "traffic light",
    "traffic sign",
    "vegetation",
    "terrain",
    "sky",
    "person",
    "rider",
    "car",
    "truck",
    "bus",
    "caravan",
    "trailer",
    "train",
    "motorcycle",
    "bicycle",
]
CITY_EVAL = {7, 8, 11, 12, 13, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 31, 32, 33}
CITY_SOURCE = (
    "https://github.com/mcordts/cityscapesScripts/blob/master/cityscapesscripts/helpers/labels.py"
)
CITY_RENDER_SOURCE = "https://github.com/mcordts/cityscapesScripts/blob/master/cityscapesscripts/preparation/json2labelImg.py"


def mask_stats(
    mask: np.ndarray, valid: set[int], ignored: set[int], coverage: float = 0.85
) -> dict:
    """Fractions use all native image pixels, not only labeled pixels."""
    if mask.ndim != 2:
        raise ValueError("Expected a single-channel ID mask")
    ids, frequencies = np.unique(mask, return_counts=True)
    counts = {int(k): int(v) for k, v in zip(ids, frequencies, strict=True)}
    invalid = sorted(set(counts) - valid)
    ignore_pixels = sum(v for k, v in counts.items() if k in ignored)
    flags = []
    if invalid:
        flags.append("invalid_class_ids")
    if ignore_pixels == mask.size:
        flags.append("all_ignore")
    dominant = [
        k
        for k, v in counts.items()
        if k not in ignored and k in valid and v / mask.size >= coverage
    ]
    if dominant:
        flags.append("dominant_class")
    edges = int(
        np.count_nonzero(mask[1:] != mask[:-1]) + np.count_nonzero(mask[:, 1:] != mask[:, :-1])
    )
    h, w = mask.shape
    pairs = (h - 1) * w + h * (w - 1)
    return dict(
        pixels=int(mask.size),
        class_pixels=counts,
        ignore_pixels=ignore_pixels,
        invalid_ids=invalid,
        dominant_classes=dominant,
        boundary_pairs=edges,
        neighbor_pairs=pairs,
        boundary_fraction=edges / pairs if pairs else 0.0,
        flags=flags,
    )


def polygon_region(points: list, size: tuple[int, int]) -> tuple[tuple, np.ndarray]:
    """Rasterize in original coordinates, then crop without changing edge rounding."""
    w, h = size
    xy = np.asarray(points)
    x0, y0 = np.maximum(np.floor(xy.min(axis=0)).astype(int) - 1, 0)
    x1, y1 = np.minimum(np.ceil(xy.max(axis=0)).astype(int) + 2, [w, h])
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    if x1 <= x0 or y1 <= y0:
        return (slice(0, 0), slice(0, 0)), np.zeros((0, 0), bool)
    canvas = Image.new("1", size)
    ImageDraw.Draw(canvas).polygon([tuple(point) for point in points], fill=1)
    return (slice(y0, y1), slice(x0, x1)), np.asarray(canvas.crop((x0, y0, x1, y1)), dtype=bool)


def mismatch_distances(expected: np.ndarray, final: np.ndarray) -> dict:
    """Separate near-boundary rasterization disagreements from interior differences."""
    boundary = np.zeros(final.shape, bool)
    for mask in (expected, final):
        edge = mask[1:] != mask[:-1]
        boundary[1:] |= edge
        boundary[:-1] |= edge
        edge = mask[:, 1:] != mask[:, :-1]
        boundary[:, 1:] |= edge
        boundary[:, :-1] |= edge
    # Chebyshev distance <= 2 from either label map's 4-neighbor boundary.
    for _ in range(2):
        old = boundary.copy()
        boundary[1:] |= old[:-1]
        boundary[:-1] |= old[1:]
        old = boundary.copy()
        boundary[:, 1:] |= old[:, :-1]
        boundary[:, :-1] |= old[:, 1:]
    mismatch = expected != final
    return dict(
        mismatch_near_boundary_2px=int(np.count_nonzero(mismatch & boundary)),
        mismatch_interior_beyond_2px=int(np.count_nonzero(mismatch & ~boundary)),
    )


def city_geometry(data: dict, final: np.ndarray) -> dict:
    """Cityscapes official source-order rules; overlap is descriptive, not an error."""
    size = (data["imgWidth"], data["imgHeight"])
    if size != (final.shape[1], final.shape[0]):
        raise ValueError("Source/mask dimensions differ")
    names = {name: i for i, name in enumerate(CITY_NAMES)} | {"license plate": -1}
    expected = np.zeros(final.shape, np.uint8)
    seen = np.zeros(final.shape, bool)
    cross = np.zeros(final.shape, bool)
    overlap = np.zeros(final.shape, bool)
    objects = []
    for index, obj in enumerate(data["objects"]):
        if obj.get("deleted", False):
            continue
        label = obj["label"]
        if label not in names and label.endswith("group"):
            label = label[:-5]
        class_id = names[label]
        if class_id < 0:
            continue
        region_slice, region = polygon_region(obj["polygon"], size)
        overlap[region_slice] |= region & seen[region_slice]
        cross[region_slice] |= region & seen[region_slice] & (expected[region_slice] != class_id)
        expected[region_slice][region] = class_id
        seen[region_slice][region] = True
        objects.append((index, class_id, obj["polygon"]))
    loss, empty, max_loss = 0, 0, 0.0
    lost_objects = []
    for index, class_id, points in objects:
        region_slice, region = polygon_region(points, size)
        area = int(region.sum())
        lost = int(np.count_nonzero(region & (expected[region_slice] != class_id)))
        fraction = lost / area if area else 0.0
        max_loss = max(max_loss, fraction)
        empty += not area
        if area and fraction >= 0.5:
            loss += 1
            lost_objects.append(
                dict(
                    object_id=index,
                    class_id=class_id,
                    source_pixels=area,
                    cross_class_lost_pixels=lost,
                )
            )
    mismatch = int(np.count_nonzero(expected != final))
    return dict(
        source_objects=len(objects),
        empty_objects=empty,
        objects_lost_at_least_half=loss,
        max_object_cross_class_loss=max_loss,
        lost_objects=lost_objects,
        overlap_pixels=int(overlap.sum()),
        cross_class_overlap_pixels=int(cross.sum()),
        uncovered_source_pixels=int(np.count_nonzero(~seen)),
        mismatch_pixels=mismatch,
        **mismatch_distances(expected, final),
    )


def quantiles(values: list) -> dict:
    if not values:
        return {}
    return dict(
        zip(
            ["min", "p25", "median", "p75", "p95", "max"],
            map(float, np.quantile(values, [0, 0.25, 0.5, 0.75, 0.95, 1])),
            strict=True,
        )
    )


def audit(kind: str, root: Path, out: Path, limit: int | None = None) -> dict:
    root, out = root.resolve(), out.resolve()
    if out.is_relative_to(root):
        raise ValueError("Output must be outside immutable dataset")
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    if kind == "cityscapes":
        classes = {i: name for i, name in enumerate(CITY_NAMES)}
        ignored = set(classes) - CITY_EVAL
        files = sorted(
            p
            for split in ["train", "val"]
            for p in (root / "gtFine" / split).rglob("*_labelIds.png")
        )
        splits: dict[str, str] = {}
    else:
        config = json.loads((root / "rs19-config.json").read_text())
        classes = {i: item["name"] for i, item in enumerate(config["labels"])} | {255: "void"}
        ignored = {255}
        files = sorted((root / "uint8").rglob("*.png"))
        splits = {}
        for name in ["train", "val", "test"]:
            path = root / "splits" / f"{name}.txt"
            if path.exists():
                for line in path.read_text().splitlines():
                    key = Path(line.strip().split()[0]).stem if line.strip() else ""
                    if key in splits:
                        raise ValueError(f"Duplicate split membership {key}")
                    splits[key] = name
    if not files:
        raise ValueError("No native masks found; check dataset root")
    if limit:
        files = files[:limit]
    rows: list[dict[str, Any]] = []
    with (out / "images.jsonl").open("w") as stream:
        for index, path in enumerate(files):
            rel = path.relative_to(root)
            if kind == "cityscapes":
                split = rel.parts[1]
                image = (
                    root
                    / "leftImg8bit"
                    / split
                    / rel.parts[2]
                    / path.name.replace("_gtFine_labelIds.png", "_leftImg8bit.png")
                )
                source = path.with_name(path.name.replace("_labelIds.png", "_polygons.json"))
            else:
                split = splits.get(path.stem, "unassigned")
                image = root / "jpgs" / path.parent.name / (path.stem + ".jpg")
                source = root / "jsons" / path.parent.name / (path.stem + ".json")
            row: dict[str, Any] = dict(
                key=path.stem,
                split=split,
                mask=str(rel),
                image=str(image.relative_to(root)),
                source=str(source.relative_to(root)),
            )
            try:
                raw = path.read_bytes()
                row["mask_sha256"] = hashlib.sha256(raw).hexdigest()
                with Image.open(path) as im:
                    mask = np.asarray(im)
                row.update(mask_stats(mask, set(classes), ignored))
                with Image.open(image) as im:
                    if im.size != (mask.shape[1], mask.shape[0]):
                        row["flags"].append("image_mask_dimension_mismatch")
                if source.exists():
                    raw = source.read_bytes()
                    row["source_sha256"] = hashlib.sha256(raw).hexdigest()
                    data = json.loads(raw)
                    if (data.get("imgWidth"), data.get("imgHeight")) != (
                        mask.shape[1],
                        mask.shape[0],
                    ):
                        row["flags"].append("source_mask_dimension_mismatch")
                    elif kind == "cityscapes":
                        row["geometry"] = city_geometry(data, mask)
                        if row["geometry"]["mismatch_pixels"]:
                            row["flags"].append(
                                "native_render_interior_difference"
                                if row["geometry"]["mismatch_interior_beyond_2px"]
                                else "native_render_boundary_only_difference"
                            )
                        if row["geometry"]["empty_objects"]:
                            row["flags"].append("empty_source_object")
                        if row["geometry"]["objects_lost_at_least_half"]:
                            row["flags"].append("object_class_coverage_lost")
                    else:
                        row["source_geometry_types"] = dict(
                            Counter(key for obj in data["objects"] for key in obj if key != "label")
                        )
                else:
                    row["flags"].append("source_annotation_missing")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                row.setdefault("flags", []).append("read_or_schema_error")
                row["error"] = str(exc)
            rows.append(row)
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            if (index + 1) % 100 == 0:
                print(
                    f"{kind}: {index + 1}/{len(files)} ({time.time() - started:.0f}s)", flush=True
                )
    summary: dict[str, Any] = dict(
        dataset=kind,
        pillow_version=pillow_version,
        dataset_root=str(root),
        image_count=len(rows),
        limited=limit is not None,
        duration_seconds=time.time() - started,
        class_names=classes,
        mask_checks="Native source ID masks; all fractions use all image pixels; ignored IDs excluded only from dominant-class flags",
        thresholds=dict(dominant_class=0.85, object_cross_class_loss=0.5),
        geometry_comparison="exact Cityscapes PIL source-order reconstruction"
        if kind == "cityscapes"
        else "Unavailable: sparse geometry plus weakly supervised dense masks; full rerender would not be a valid equality test",
        sources=[CITY_SOURCE, CITY_RENDER_SOURCE]
        if kind == "cityscapes"
        else ["rs19-config.json", "readme.txt", "example-vis.py"],
        splits={},
        classes={},
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    for split in sorted({r["split"] for r in rows}):
        group = [r for r in rows if r["split"] == split]
        summary["splits"][split] = dict(
            images=len(group),
            readable_masks=sum("pixels" in r for r in group),
            flagged_images=sum(bool(r["flags"]) for r in group),
            flags=dict(Counter(flag for r in group for flag in r["flags"])),
            pixels=sum(r.get("pixels", 0) for r in group),
            ignore_pixels=sum(r.get("ignore_pixels", 0) for r in group),
            boundary_fraction=quantiles(
                [r["boundary_fraction"] for r in group if "boundary_fraction" in r]
            ),
            geometry_checked_images=sum("geometry" in r for r in group),
            geometry={
                key: (
                    sum(r["geometry"].get(key, 0) for r in group if "geometry" in r)
                    if any("geometry" in r for r in group)
                    else None
                )
                for key in [
                    "source_objects",
                    "empty_objects",
                    "objects_lost_at_least_half",
                    "overlap_pixels",
                    "cross_class_overlap_pixels",
                    "mismatch_pixels",
                    "mismatch_near_boundary_2px",
                    "mismatch_interior_beyond_2px",
                ]
            },
        )
    for class_id, name in classes.items():
        fractions = [
            r["class_pixels"].get(class_id, 0) / r["pixels"] for r in rows if "pixels" in r
        ]
        present = [x for x in fractions if x > 0]
        summary["classes"][str(class_id)] = dict(
            name=name,
            ignored=class_id in ignored,
            images_present=len(present),
            total_pixels=sum(r.get("class_pixels", {}).get(class_id, 0) for r in rows),
            coverage_all_images=quantiles(fractions),
            coverage_when_present=quantiles(present),
        )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "review.json").write_text(
        json.dumps(
            [dict(key=r["key"], split=r["split"], flags=r["flags"]) for r in rows if r["flags"]],
            indent=2,
        )
        + "\n"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=["cityscapes", "railsem19"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    summary = audit(args.dataset, args.root, args.out, args.limit)
    print(json.dumps(summary["splits"], indent=2))


if __name__ == "__main__":
    main()
