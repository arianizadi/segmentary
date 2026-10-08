#!/usr/bin/env python3
"""Mud-pumping and mIoU metrics of one RAD 9/24 run on named image subsets.

    PYTHONPATH=.:src python scripts/rad_subset_metrics.py \\
        --confusion <diagnostics>/best-auto-val/per-image-confusion.json.gz \\
        --total <state>.json --samples <arm>/audit/samples.json \\
        --viewpoints configs/datasets/rad_9_24_2026-viewpoints.yaml [--split val] \\
        [--checkpoint best|final] [--out x.json]

Inputs are a run's per-image confusion matrices (``{key: 21x21 rows=GT, cols=prediction}``,
gzip JSON as written by ``scripts/collect_rtis_statistics.py`` and by
``scripts/paul_forks/score_predictions.py``), the run's reported total confusion (a campaign
state JSON, whose ``evaluation.metrics.confusion`` is used after checking it equals the
``best-auto-val`` diagnostics confusion, or with ``--checkpoint final`` (campaigns with
``primary_checkpoint: final``, ``final-auto-val/per-image-confusion.json.gz``) its
``final-auto-val`` diagnostics confusion; a fork ``results-<split>.json`` or
a ``metrics.json``), the arm's ``audit/samples.json`` and the tracked viewpoint file.

Images are joined to viewpoints by ``image_sha256`` from the arm's samples, never by stem;
the viewpoint file's stem is only a checked annotation. Validation (fail closed):

- every image of the split is present and nothing else (keys from ``samples.json``);
- each per-image matrix's ground-truth row sums equal the image's audited ``class_pixels``;
- the per-image matrices sum exactly to the run's reported total confusion;
- every image has a viewpoint, and the viewpoint's stem equals the sample's stem.

Subsets: ``all``, ``cab-view``, ``not-cab-view`` (track-level + other) and
``excl-trackside-maintenance`` (every image whose scene group, the ``group`` of
``samples.json``, is not ``trackside-maintenance``; groups are layout names, not recording
provenance).

Headline metrics per subset count each class only on the images that contain it
(``segmentary.engine.present_image``): ``mud_present_iou`` is the mean per-image mud IoU over
the subset's images with mud ground truth (``images_with_mud_gt`` of them; images without mud
are left out, so their false-positive mud does not count, and a missed mud image scores 0),
``mud_present_precision`` / ``mud_present_recall`` sum mud TP/FP/FN over those images only,
and ``present_miou`` averages the present-image IoU over the ``present_miou_classes`` classes
that have at least one image in the subset. ``present_class_iou`` / ``present_class_images``
give every class's present-image IoU (``None`` when no image contains it) and image count.

Kept for traceability, from the subset's summed (pixel-pooled) matrix: images, mud GT pixels,
mud IoU/precision/recall (``collect_rtis_statistics.mud_counts``), the GT-class mIoU
(``publish_rtis_results.fixed_miou`` of ``collect_rtis_statistics.matrix_metrics``: mean IoU
over classes with ground truth in the subset), the campaign mIoU (``matrix_metrics``
``miou``: classes with non-zero union), ``mud_image_mean_iou`` (an independent computation of
``mud_present_iou``) and the share of the subset's mud GT pixels contributed by its five
images with the most mud GT. The test split is refused.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.collect_rtis_statistics import matrix_metrics, mud_counts
from scripts.publish_rtis_results import fixed_miou

from segmentary.engine.present_image import present_image_metrics

NUM_CLASSES = 21
MUD = "mud-pumping"
VIEWPOINTS = ("cab-view", "track-level", "other")
EXCLUDED_GROUP = "trackside-maintenance"
SUBSETS = ("all", "cab-view", "not-cab-view", f"excl-{EXCLUDED_GROUP}")
SPLITS = ("train", "val")
TOP_K = 5
# Campaign diagnostics results of the two primary checkpoints (auto raw/EMA weights, val).
BEST, FINAL = "best-auto-val", "final-auto-val"
VARIANTS = {"best": BEST, "final": FINAL}


class SubsetError(ValueError):
    """Inputs that do not describe exactly one run on exactly one split."""


@dataclass(frozen=True)
class Image:
    key: str
    stem: str
    group: str
    image_sha256: str
    viewpoint: str
    matrix: np.ndarray


def class_names(path: Path | None = None) -> list[str]:
    """The arm's class names in id order (``classes.json``); 21 classes, mud-pumping = 13."""
    schema = json.loads(Path(path).read_text()) if path else None
    names = [c["name"] for c in schema["classes"]] if schema else None
    if names is None:
        from segmentary.taxonomy import load_space

        root = Path(__file__).resolve().parents[1] / "taxonomy"
        names = list(load_space(root, "paul-test-rtis").names)
    if len(names) != NUM_CLASSES or names.index(MUD) != 13:
        raise SubsetError("expected the 21-class paul-test-rtis space with mud-pumping = 13")
    return names


def load_viewpoints(path: Path) -> dict[str, dict[str, str]]:
    data = yaml.safe_load(Path(path).read_text())
    images = data.get("images") if isinstance(data, dict) else None
    if not isinstance(images, dict) or not images:
        raise SubsetError(f"{path}: no images map")
    stems = set()
    for sha, entry in images.items():
        if not isinstance(sha, str) or len(sha) != 64:
            raise SubsetError(f"{path}: key {sha!r} is not an image sha256")
        if entry.get("viewpoint") not in VIEWPOINTS:
            raise SubsetError(f"{path}: {sha} has viewpoint {entry.get('viewpoint')!r}")
        if entry.get("stem") in stems:
            raise SubsetError(f"{path}: stem {entry.get('stem')!r} appears twice")
        stems.add(entry.get("stem"))
    return images


def load_confusion(path: Path) -> dict[str, np.ndarray]:
    raw = Path(path).read_bytes()
    data = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    matrices = {}
    for key, value in data.items():
        matrix = np.asarray(value, dtype=np.int64)
        if matrix.shape != (NUM_CLASSES, NUM_CLASSES) or (matrix < 0).any():
            raise SubsetError(f"{path}: {key} is not a non-negative 21x21 confusion matrix")
        matrices[key] = matrix
    return matrices


def reported_total(record: dict[str, Any], variant: str = BEST) -> np.ndarray:
    """The run's own total confusion: campaign state, fork results or a metrics.json.

    For a campaign state and ``variant`` ``best-auto-val`` (the checkpoint selected on
    validation) the total is ``evaluation.metrics.confusion`` and must equal the
    ``best-auto-val`` diagnostics confusion the per-image file belongs to, when recorded. For
    ``final-auto-val`` (campaigns with ``primary_checkpoint: final``) the standalone evaluation
    scored the best checkpoint, so the total is the ``final-auto-val`` diagnostics confusion."""
    if variant not in VARIANTS.values():
        raise SubsetError(f"checkpoint result {variant!r} is not one of {list(VARIANTS.values())}")
    diagnostics = ((record.get("collection") or {}).get("diagnostics") or {}).get("results")
    if variant == FINAL:
        final = ((diagnostics or {}).get(FINAL) or {}).get("metrics") or {}
        if "confusion" not in final:
            raise SubsetError(f"record carries no {FINAL} confusion")
        total = np.asarray(final["confusion"], dtype=np.int64)
        if total.shape != (NUM_CLASSES, NUM_CLASSES):
            raise SubsetError("reported total confusion is not 21x21")
        return total
    selected = ((diagnostics or {}).get(BEST) or {}).get("metrics") or {}
    if "confusion" in selected:
        evaluated = (record.get("evaluation") or {}).get("metrics") or {}
        if not np.array_equal(
            np.asarray(selected["confusion"]), np.asarray(evaluated.get("confusion"))
        ):
            raise SubsetError("best-auto-val diagnostics confusion differs from the evaluation")
    for candidate in (
        (record.get("evaluation") or {}).get("metrics"),
        record.get("metrics"),
        record,
    ):
        if isinstance(candidate, dict) and "confusion" in candidate:
            total = np.asarray(candidate["confusion"], dtype=np.int64)
            if total.shape != (NUM_CLASSES, NUM_CLASSES):
                raise SubsetError("reported total confusion is not 21x21")
            return total
    raise SubsetError("record carries no total confusion")


def join(
    matrices: dict[str, np.ndarray],
    samples: list[dict[str, Any]],
    viewpoints: dict[str, dict[str, str]],
    split: str,
    total: np.ndarray,
) -> list[Image]:
    """Validate and join per-image matrices to samples (by key) and viewpoints (by sha256)."""
    if split not in SPLITS:
        raise SubsetError(f"split {split!r} is refused; only {list(SPLITS)} (never test)")
    keys = [s["key"] for s in samples]
    if len(set(keys)) != len(keys):
        raise SubsetError("samples.json has duplicate keys")
    by_key = {s["key"]: s for s in samples if s["split"] == split}
    if not by_key:
        raise SubsetError(f"samples.json has no {split} images")
    missing, extra = sorted(set(by_key) - set(matrices)), sorted(set(matrices) - set(by_key))
    if missing or extra:
        raise SubsetError(
            f"per-image confusion does not cover the {split} split exactly: "
            f"missing {missing}, extra {extra}"
        )
    summed = sum(matrices.values(), np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64))
    if not np.array_equal(summed, np.asarray(total, dtype=np.int64)):
        raise SubsetError(
            f"per-image confusion matrices do not sum to the run's reported total "
            f"({int(np.abs(summed - total).sum())} pixels differ)"
        )
    images = []
    for key in sorted(by_key):
        sample, matrix = by_key[key], matrices[key]
        expected = np.zeros(NUM_CLASSES, np.int64)
        for value, count in sample["class_pixels"].items():
            if int(value) < NUM_CLASSES:
                expected[int(value)] = int(count)
        if not np.array_equal(matrix.sum(axis=1), expected):
            raise SubsetError(f"{key}: ground-truth rows differ from the audited class_pixels")
        entry = viewpoints.get(sample["image_sha256"])
        if entry is None:
            raise SubsetError(f"{key}: image sha256 {sample['image_sha256']} has no viewpoint")
        if str(entry.get("stem")) != str(sample["stem"]):
            raise SubsetError(
                f"{key}: viewpoint stem {entry.get('stem')!r} differs from sample stem "
                f"{sample['stem']!r} for the same image sha256"
            )
        images.append(
            Image(
                key=key,
                stem=str(sample["stem"]),
                group=sample["group"],
                image_sha256=sample["image_sha256"],
                viewpoint=entry["viewpoint"],
                matrix=matrix,
            )
        )
    return images


def members(images: list[Image], subset: str) -> list[Image]:
    if subset == "all":
        return list(images)
    if subset == "cab-view":
        return [i for i in images if i.viewpoint == "cab-view"]
    if subset == "not-cab-view":
        return [i for i in images if i.viewpoint != "cab-view"]
    if subset == f"excl-{EXCLUDED_GROUP}":
        return [i for i in images if i.group != EXCLUDED_GROUP]
    raise SubsetError(f"unknown subset {subset!r}")


def _finite(value: float | None) -> float | None:
    return None if value is None or math.isnan(value) else float(value)


def subset_metrics(images: list[Image], names: list[str]) -> dict[str, Any]:
    mud = names.index(MUD)
    supports = sorted((int(i.matrix[mud].sum()) for i in images), reverse=True)
    mud_pixels = sum(supports)
    with_mud = [i for i in images if i.matrix[mud].sum() > 0]
    present = present_image_metrics((i.matrix for i in images), NUM_CLASSES)
    result: dict[str, Any] = {
        "images": len(images),
        "images_with_mud_gt": len(with_mud),
        "mud_gt_pixels": mud_pixels,
        "mud_iou": None,
        "mud_precision": None,
        "mud_recall": None,
        "mud_image_mean_iou": None,
        "gt_class_miou": None,
        "miou": None,
        "mud_present_iou": None,
        "mud_present_precision": None,
        "mud_present_recall": None,
        "present_miou": None,
        "present_miou_classes": 0,
        # every class: present-image IoU (None without a present image) and its image count
        "present_class_iou": {n: s.iou for n, s in zip(names, present.classes, strict=True)},
        "present_class_images": {n: s.images for n, s in zip(names, present.classes, strict=True)},
        "top5_mud_share": sum(supports[:TOP_K]) / mud_pixels if mud_pixels else None,
        "keys": [i.key for i in images],
    }
    if not images:
        return result
    total = sum((i.matrix for i in images), np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64))
    counts = mud_counts(total, mud)
    metrics = matrix_metrics(total, names)
    per_image = [mud_counts(i.matrix, mud)["iou"] for i in with_mud]
    focus = present.classes[mud]
    result.update(
        mud_present_iou=focus.iou,
        mud_present_precision=focus.precision,
        mud_present_recall=focus.recall,
        present_miou=present.miou,
        present_miou_classes=present.miou_classes,
        mud_iou=counts["iou"],
        mud_precision=counts["precision"],
        mud_recall=counts["recall"],
        mud_image_mean_iou=sum(per_image) / len(per_image) if per_image else None,
        gt_class_miou=_finite(fixed_miou(metrics)),
        miou=_finite(metrics["miou"]),
    )
    return result


def compute(images: list[Image], names: list[str]) -> dict[str, dict[str, Any]]:
    return {subset: subset_metrics(members(images, subset), names) for subset in SUBSETS}


def run_subsets(
    confusion: Path,
    total: np.ndarray,
    samples: list[dict[str, Any]],
    viewpoints: dict[str, dict[str, str]],
    split: str = "val",
    names: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    images = join(load_confusion(confusion), samples, viewpoints, split, total)
    return compute(images, names or class_names())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--confusion", type=Path, required=True, help="per-image confusion (.json.gz)")
    p.add_argument(
        "--total",
        type=Path,
        required=True,
        help="campaign state JSON, fork results-<split>.json or metrics.json",
    )
    p.add_argument("--samples", type=Path, required=True, help="the arm's audit/samples.json")
    p.add_argument("--viewpoints", type=Path, required=True)
    p.add_argument("--classes", type=Path, help="the arm's classes.json (default: taxonomy)")
    p.add_argument("--split", choices=SPLITS, default="val")
    p.add_argument(
        "--checkpoint",
        choices=list(VARIANTS),
        default="best",
        help="campaign state: the checkpoint --confusion belongs to (final for campaigns with "
        "primary_checkpoint: final); default best",
    )
    p.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = p.parse_args(argv)
    try:
        result = run_subsets(
            args.confusion,
            reported_total(json.loads(args.total.read_text()), VARIANTS[args.checkpoint]),
            json.loads(args.samples.read_text()),
            load_viewpoints(args.viewpoints),
            args.split,
            class_names(args.classes),
        )
    except SubsetError as error:
        raise SystemExit(f"rad_subset_metrics: {error}") from error
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
