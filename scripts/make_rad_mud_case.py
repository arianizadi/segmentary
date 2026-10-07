#!/usr/bin/env python3
"""Regenerate the RAD 9/24 mud-pumping IoU case document and every figure in it.

    CUDA_VISIBLE_DEVICES="" PYTHONPATH=.:src python scripts/make_rad_mud_case.py \\
        [--datasets-root /data/izadia1/datasets] \\
        [--campaign-root /data/izadia1/projects/segmentary-runs/rad_9_24_2026] \\
        [--viewpoints configs/datasets/rad_9_24_2026-viewpoints.yaml] \\
        [--doc docs/guides/rad-9-24-2026-mud-iou-case.md] \\
        [--assets docs/guides/assets/rad-9-24-2026-mud-iou]

Reads, never writes, the prepared arms (``audit/samples.json``, images and masks of the
``paul`` arm) and the two ``*-seed0-20261005-r2`` campaigns (``paul``, ``fixed-grouped``). Run metrics come from
``scripts/rad_report.scan_campaign`` (which re-validates every per-image confusion file
against its recorded SHA-256 and the run's reported total), so the numbers here are the
numbers of ``rad_report.py``. A ``--campaign-root`` other than the HDRFS default is treated as a
copy of it: absolute artifact paths recorded in the state files are rewritten to it.

Figures use the ``paul`` arm's own ground truth (the masks the runs were scored against) and
the saved ``best-auto-val`` prediction PNGs; the script checks that the mud TP/FP/FN it
recounts from those PNGs equals the per-image confusion of the run. Validation split only;
the test split is never read. Output is deterministic for fixed inputs.

The cross-validation section reads the ``cv-seed0-20261006`` campaign (under
``--campaign-root``) through ``scripts/cv_report.build`` (fold-dataset, spec and confusion
hashes, per-fold val coverage) and the fold datasets ``rad_9_24_2026-cv/fold-<k>`` (under
``--datasets-root``). It shows one run (``CV_RUN``) at its final checkpoint
(``final-auto-val``), each image scored by the fold model that held its scene out; every
CV-scored image of ``configs/datasets/rad_9_24_2026-cv-spec.json`` must be scored exactly once,
and the mud TP/FP/FN recounted from every prediction PNG must equal the run's per-image
confusion.
"""

from __future__ import annotations

import argparse
import html
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts import cv_report as cvr
from scripts import rad_report as report
from scripts import rad_subset_metrics as subsets
from scripts.collect_rtis_statistics import mud_counts

from segmentary.data.group_cv import CvError, fold_splits

DEFAULT_CAMPAIGN_ROOT = report.RUNS / "rad_9_24_2026"
CAMPAIGN_DIR = "{arm}-seed0-20261005-r2"
DOC = ROOT / "docs/guides/rad-9-24-2026-mud-iou-case.md"
ASSETS = ROOT / "docs/guides/assets/rad-9-24-2026-mud-iou"
REFERENCE_JOB = "eomt_large--railsem19_to_rtis--seed-0"
ARM = "paul"  # the stratified-split arm (Paul's masks)
MUD = 13
IGNORE = 255
CAB = "cab-view"
CLOSEUP_GROUP = subsets.EXCLUDED_GROUP
EXCL = f"excl-{CLOSEUP_GROUP}"
NEIGHBOUR_QUERIES = 3  # track-level frames shown in figure 3
NEIGHBOURS = 3  # train frames per val frame
# Cosine at or above which a train frame is called a near-copy. 0.90 does not separate: cab-view
# frames reach 0.90 against train frames of *other* scene groups.
DUPLICATE = 0.93
REDUCE = 4  # integer downscale (PIL ``Image.reduce``) applied before the standard transform
FONT = 24  # figure text; figures are ~1600 px wide and GitHub shows them at ~880 px
# Cross-validation section: scene-grouped 5-fold CV on the re-rendered (fixed-grouped) labels.
CV_CAMPAIGN = "cv-seed0-20261006"
CV_DATASET = "rad_9_24_2026-cv"
CV_SPEC = ROOT / "configs/datasets/rad_9_24_2026-cv-spec.json"
CV_RUN = ("eomt_dinov3_large", "rtis_only", 0)  # model, protocol, seed
CV_START = "recipe pretrained weights"  # plain name of the rtis_only starting point
CV_SHOWN = 8  # train-camera images with the most false-positive mud in figure 5
MUD_NAME = "mud-pumping"

# Categorical slots 1-3 of the dataviz reference palette (validated all-pairs, light mode).
BLUE, ORANGE, GREEN = (42, 120, 214), (235, 104, 52), (27, 175, 122)
INK, MUTED, SURFACE = (11, 11, 11), (82, 81, 78), (252, 252, 251)


class CaseError(ValueError):
    pass


@dataclass
class Run:
    job: str
    model: str
    protocol: str
    metrics: dict[str, dict[str, Any]]
    diagnostics: Path

    @property
    def name(self) -> str:
        return f"{self.model} {self.protocol}"


# ----------------------------------------------------------------------------- data


def sha256_file(path: Path) -> str:
    return report.sha256_file(path)


def load_campaigns(
    campaign_root: Path, arms: report.Arms, viewpoints: dict
) -> tuple[dict[str, list[Run]], list[report.Coverage]]:
    maps = []
    if campaign_root.resolve() != DEFAULT_CAMPAIGN_ROOT:
        maps = [(str(DEFAULT_CAMPAIGN_ROOT), str(campaign_root))]
    runs: dict[str, list[Run]] = {}
    coverage: list[report.Coverage] = []
    for arm in report.ARMS:
        root = campaign_root / CAMPAIGN_DIR.format(arm=arm)
        found_arm, results, covered = report.scan_campaign(root, arms, viewpoints, maps)
        if found_arm != arm:
            raise CaseError(f"{root} is the {found_arm} arm, expected {arm}")
        coverage += covered
        runs[arm] = []
        for r in results:
            state = report.read(root / "state" / f"{r.job}.json")
            artifact = state["collection"]["artifacts"][report.SELECTED]
            path = report.remap(artifact["per-image-confusion.json.gz"]["path"], maps)
            runs[arm].append(Run(r.job, r.model, r.protocol, r.metrics, path.parent))
    return runs, coverage


def per_image(run: Run) -> dict[str, dict[str, Any]]:
    matrices = subsets.load_confusion(run.diagnostics / "per-image-confusion.json.gz")
    return {key: mud_counts(m, MUD) for key, m in matrices.items()}


def read_mask(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        if im.mode not in ("L", "P"):
            raise CaseError(f"{path}: mask mode {im.mode}")
        return np.asarray(im)


def read_image(path: Path, expected_sha: str) -> Image.Image:
    if sha256_file(path) != expected_sha:
        raise CaseError(f"{path}: image sha256 differs from audit/samples.json")
    with Image.open(path) as im:
        return im.convert("RGB")


class Arm:
    """The paul arm's samples, images and masks (sha-checked on read)."""

    def __init__(self, root: Path, viewpoints: dict):
        self.root = root
        self.samples = report.read(root / "audit/samples.json")
        self.by_key = {s["key"]: s for s in self.samples}
        self.viewpoints = viewpoints

    def viewpoint(self, key: str) -> str:
        return self.viewpoints[self.by_key[key]["image_sha256"]]["viewpoint"]

    def image(self, key: str) -> Image.Image:
        s = self.by_key[key]
        path = self.root / "images" / s["split"] / f"{s['key']}{s['image_extension']}"
        return read_image(path, s["image_sha256"])

    def mask(self, key: str) -> np.ndarray:
        s = self.by_key[key]
        mask = read_mask(self.root / "masks" / s["split"] / f"{s['key']}.png")
        if int((mask == MUD).sum()) != int(s["class_pixels"].get(str(MUD), 0)):
            raise CaseError(f"{key}: mud pixels of the mask differ from audit class_pixels")
        return mask


def checked_prediction(
    path: Path, label: str, gt: np.ndarray, counts: dict[str, Any]
) -> np.ndarray:
    """The prediction PNG, after checking its mud TP/FP/FN against the run's confusion."""
    pred = read_mask(path)
    if pred.shape != gt.shape:
        raise CaseError(f"{label}: prediction shape {pred.shape} != mask {gt.shape}")
    valid = gt != IGNORE
    tp = int(((gt == MUD) & (pred == MUD)).sum())
    fp = int(((gt != MUD) & valid & (pred == MUD)).sum())
    fn = int(((gt == MUD) & (pred != MUD)).sum())
    if (tp, fp, fn) != (counts["tp"], counts["fp"], counts["fn"]):
        raise CaseError(
            f"{label}: prediction PNG gives mud TP/FP/FN {(tp, fp, fn)}, the run's "
            f"per-image confusion {(counts['tp'], counts['fp'], counts['fn'])}"
        )
    return pred


def prediction(run: Run, key: str, gt: np.ndarray, counts: dict[str, Any]) -> np.ndarray:
    path = run.diagnostics / "predictions" / f"{key}.png"
    return checked_prediction(path, f"{run.job} {key}", gt, counts)


# ----------------------------------------------------------------------------- cross-validation


@dataclass
class CvFold:
    fold: int
    job: str
    arm: Arm  # the fold dataset (val = this fold's scored images)
    predictions: Path


@dataclass
class CvImage:
    key: str
    fold: int
    group: str
    viewpoint: str
    counts: dict[str, Any]  # mud_counts of the image's per-image confusion

    @property
    def fp(self) -> int:
        return int(self.counts["fp"])

    @property
    def gt(self) -> int:
        return int(self.counts["support"])


@dataclass
class CvCase:
    campaign: str
    folds: dict[int, CvFold]
    images: list[CvImage]
    pooled: dict[str, dict[str, Any]]  # cv_report.pooled of the run, by subset
    rank: int  # of the run among complete setups, by pooled cab-view mud IoU
    setups: int
    spec_sha256: str


def check_cv_coverage(spec: dict, scored: dict[int, list[tuple[str, str]]]) -> None:
    """Every CV-scored image of the spec is scored exactly once, by the fold that holds it out.

    ``scored`` maps fold -> [(key, image_sha256)] of the run's per-image confusions."""
    folds = int(spec["method"]["folds"])
    if sorted(scored) != list(range(folds)):
        raise CaseError(f"cross-validation folds {sorted(scored)}, the spec has {folds}")
    seen: dict[str, int] = {}
    for fold, rows in sorted(scored.items()):
        keys = [k for k, _ in rows]
        expected = fold_splits(spec, fold)[0]["val"]
        if sorted(keys) != sorted(expected) or len(set(keys)) != len(keys):
            missing = sorted(set(expected) - set(keys))
            extra = sorted(set(keys) - set(expected))
            raise CaseError(
                f"fold {fold}: scored images differ from the spec's val fold "
                f"(missing {missing}, extra {extra}, {len(keys) - len(set(keys))} duplicates)"
            )
        for key, sha in rows:
            if key in seen:
                raise CaseError(f"{key} is scored in folds {seen[key]} and {fold}")
            seen[key] = fold
            if sha != spec["assignments"][key]["image_sha256"]:
                raise CaseError(f"{key}: image sha256 differs from the cross-validation spec")
    wanted = {k for k, row in spec["assignments"].items() if row["scored"]}
    if set(seen) != wanted:
        raise CaseError(f"scored images differ from the spec: {sorted(wanted ^ set(seen))}")


def load_cv(
    cv_root: Path,
    viewpoints_path: Path,
    viewpoints: dict,
    maps: list[tuple[str, str]],
    spec_path: Path = CV_SPEC,
) -> CvCase:
    rep = cvr.build(cv_root, viewpoints_path, MUD_NAME, maps)
    if rep.names[MUD] != MUD_NAME:
        raise CaseError(f"class {MUD} of {cv_root.name} is {rep.names[MUD]!r}, not {MUD_NAME}")
    cv = rep.campaign["cross_validation"]
    if sha256_file(spec_path) != cv["spec_sha256"]:
        raise CaseError(f"{spec_path} is not the spec of {cv_root}")
    spec = report.read(spec_path)
    model, protocol, seed = CV_RUN
    setups = cvr.groups_of(rep)
    runs = setups.get(CV_RUN, {})
    if set(runs) != set(rep.folds):
        raise CaseError(f"{model} {protocol} seed {seed}: folds {sorted(runs)} of {rep.folds}")
    check_cv_coverage(
        spec,
        {k: [(i.key, i.image_sha256) for i in r.images[cvr.PRIMARY]] for k, r in runs.items()},
    )
    pooled = cvr.pooled(runs, cvr.PRIMARY, rep)
    if pooled is None or pooled[CAB]["focus_iou"] is None:
        raise CaseError(f"{model} {protocol}: no pooled {CAB} mud IoU")
    complete = {
        key: cvr.pooled(r, cvr.PRIMARY, rep)
        for key, r in setups.items()
        if set(r) == set(rep.folds)
    }

    def cab_iou(p: dict | None) -> float:
        value = (p or {}).get(CAB, {}).get("focus_iou")
        return -1.0 if value is None else float(value)

    scores = sorted((-cab_iou(p), key) for key, p in complete.items())
    folds, images = {}, []
    for k, run in sorted(runs.items()):
        state = report.read(cv_root / "state" / f"{run.job}.json")
        result = state["collection"]["diagnostics"]["results"][cvr.PRIMARY]
        root = report.remap(cv["fold_datasets"][str(k)]["root"], maps)
        folds[k] = CvFold(
            k, run.job, Arm(root, viewpoints), report.remap(result["prediction_directory"], maps)
        )
        for i in run.images[cvr.PRIMARY]:
            group = spec["assignments"][i.key]["group"]
            images.append(CvImage(i.key, k, group, str(i.subset), mud_counts(i.matrix, MUD)))
    case = CvCase(
        cv_root.name,
        folds,
        sorted(images, key=lambda i: i.key),
        pooled,
        [key for _, key in scores].index(CV_RUN) + 1,
        len(complete),
        cv["spec_sha256"],
    )
    for image in case.images:  # the recount check on every scored image, not only those shown
        cv_prediction(case, image)
    return case


def cv_prediction(case: CvCase, image: CvImage) -> tuple[np.ndarray, np.ndarray]:
    """(ground truth, checked prediction) of one cross-validation image."""
    fold = case.folds[image.fold]
    gt = fold.arm.mask(image.key)
    path = fold.predictions / f"{image.key}.png"
    return gt, checked_prediction(path, f"{fold.job} {image.key}", gt, image.counts)


def rank_false_positives(images: list[CvImage], n: int = CV_SHOWN) -> list[CvImage]:
    """The train-camera images with the most false-positive mud pixels (ties by key)."""
    cab = [i for i in images if i.viewpoint == CAB and i.fp > 0]
    return sorted(cab, key=lambda i: (-i.fp, i.key))[:n]


def fp_zoom_box(
    mask: np.ndarray,
    aspect: float = 16 / 9,
    min_w: int = 480,
    max_zoom_w: float = 0.5,
    step: int = 8,
) -> tuple[int, int, int, int]:
    """A zoom window on the false-positive pixels of ``mask``.

    Width as in ``zoom_box`` (1.6x the extent, 16:9) but over the central 90% of the pixels
    (5th-95th percentile on each axis) and at most ``max_zoom_w`` of the frame width (at least a
    2x zoom); placed, on a ``step``-pixel grid, where it holds the most pixels of ``mask`` (the
    first such position in raster order)."""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise CaseError("no false-positive pixel to zoom on")
    x0, x1 = np.percentile(xs, [5, 95])
    y0, y1 = np.percentile(ys, [5, 95])
    cw = max(min_w, int(1.6 * (x1 - x0 + 1)), int(1.6 * (y1 - y0 + 1) * aspect))
    cw = min(cw, int(w * max_zoom_w), int(h * aspect))
    ch = round(cw / aspect)
    table = np.zeros((h + 1, w + 1), np.int64)
    table[1:, 1:] = mask.astype(np.int64).cumsum(0).cumsum(1)
    tops = np.unique(np.r_[np.arange(0, h - ch + 1, step), h - ch])
    lefts = np.unique(np.r_[np.arange(0, w - cw + 1, step), w - cw])
    t, left = np.meshgrid(tops, lefts, indexing="ij")
    inside = table[t + ch, left + cw] - table[t, left + cw] - table[t + ch, left] + table[t, left]
    i, j = np.unravel_index(int(np.argmax(inside)), inside.shape)
    top, lft = int(tops[i]), int(lefts[j])
    return lft, top, lft + cw, top + ch


# ----------------------------------------------------------------------------- drawing


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def shrink(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Any-coverage downscale, so a patch of a few pixels still shows at display size."""
    im = Image.fromarray(mask.astype(np.uint8) * 255).resize(size, Image.Resampling.BOX)
    return np.asarray(im) > 0


def edge(mask: np.ndarray) -> np.ndarray:
    inner = mask.copy()
    inner[1:, :] &= mask[:-1, :]
    inner[:-1, :] &= mask[1:, :]
    inner[:, 1:] &= mask[:, :-1]
    inner[:, :-1] &= mask[:, 1:]
    out = mask & ~inner
    thick = out.copy()
    thick[1:, :] |= out[:-1, :]
    thick[:, 1:] |= out[:, :-1]
    return thick & mask


def paint(
    base: Image.Image, layers: list[tuple[np.ndarray, tuple[int, int, int]]], alpha: float = 0.5
) -> Image.Image:
    """Translucent fills with an opaque outline; layers are full-resolution boolean masks."""
    size = base.size
    out = np.asarray(base.resize(size), dtype=np.float32).copy()
    for mask, colour in layers:
        small = shrink(mask, size) if mask.shape[::-1] != size else mask
        colour_arr = np.array(colour, np.float32)
        out[small] = (1 - alpha) * out[small] + alpha * colour_arr
        out[edge(small)] = colour_arr
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


def gt_layers(gt: np.ndarray) -> list:
    return [(gt == MUD, BLUE)]


def pred_layers(gt: np.ndarray, pred: np.ndarray) -> list:
    valid = gt != IGNORE
    return [
        ((gt == MUD) & (pred != MUD), GREEN),
        ((gt != MUD) & valid & (pred == MUD), ORANGE),
        ((gt == MUD) & (pred == MUD), BLUE),
    ]


def panel(
    image: Image.Image, layers: list, size: tuple[int, int], alpha: float = 0.5
) -> Image.Image:
    return paint(image.resize(size, Image.Resampling.LANCZOS), layers, alpha)


LINE = FONT + 8


def legend_strip(
    width: int, items: list[tuple[tuple[int, int, int], str]], note: str = ""
) -> Image.Image:
    """Swatches on one line (wrapping when needed); the note on its own line(s) below."""
    f = font(FONT)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    places, x, line = [], 10, 0
    for colour, text in items:
        w = FONT + 8 + int(probe.textlength(text, font=f))
        if x > 10 and x + w > width - 10:
            x, line = 10, line + 1
        places.append((x, line, colour, text))
        x += w + 28
    notes = wrap(probe, note, width - 20, f) if note else []
    strip = Image.new("RGB", (width, LINE * (line + 1 + len(notes)) + 12), SURFACE)
    draw = ImageDraw.Draw(strip)
    for x, ln, colour, text in places:
        top = 8 + ln * LINE
        draw.rounded_rectangle((x, top + 2, x + FONT - 4, top + FONT - 2), radius=4, fill=colour)
        draw.text((x + FONT + 4, top), text, fill=INK, font=f)
    for i, text in enumerate(notes):
        draw.text((10, 8 + (line + 1 + i) * LINE), text, fill=MUTED, font=f)
    return strip


def wrap(draw: ImageDraw.ImageDraw, text: str, width: int, f) -> list[str]:
    """Greedy word wrap; a single word wider than the line is truncated with an ellipsis."""
    lines: list[str] = []
    for word in text.split(" "):
        trial = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textlength(trial, font=f) <= width:
            lines[-1] = trial
        else:
            lines.append(fit(draw, word, width, f))
    return lines


def header_row(widths: list[int], titles: list[str]) -> Image.Image:
    f = font(FONT)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    cells = [wrap(probe, t, w - 8, f) for w, t in zip(widths, titles, strict=True)]
    height = LINE * max(len(c) for c in cells) + 8
    row = Image.new("RGB", (sum(widths) + 4 * (len(widths) - 1), height), SURFACE)
    draw = ImageDraw.Draw(row)
    x = 0
    for w, lines in zip(widths, cells, strict=True):
        for i, t in enumerate(lines):
            draw.text((x + 4, 4 + i * LINE), t, fill=INK, font=f)
        x += w + 4
    return row


def fit(draw: ImageDraw.ImageDraw, text: str, width: int, f) -> str:
    while draw.textlength(text, font=f) > width and len(text) > 4:
        text = text.removesuffix("…")[:-1] + "…"
    return text


def caption_row(width: int, text: str) -> Image.Image:
    f = font(FONT)
    lines = wrap(ImageDraw.Draw(Image.new("RGB", (1, 1))), text, width - 8, f)
    row = Image.new("RGB", (width, LINE * len(lines) + 10), SURFACE)
    draw = ImageDraw.Draw(row)
    for i, t in enumerate(lines):
        draw.text((4, 6 + i * LINE), t, fill=MUTED, font=f)
    return row


def stack(parts: list[Image.Image], gap: int = 4, horizontal: bool = False) -> Image.Image:
    if horizontal:
        size = (sum(p.width for p in parts) + gap * (len(parts) - 1), max(p.height for p in parts))
    else:
        size = (max(p.width for p in parts), sum(p.height for p in parts) + gap * (len(parts) - 1))
    out = Image.new("RGB", size, SURFACE)
    pos = 0
    for p in parts:
        out.paste(p, (pos, 0) if horizontal else (0, pos))
        pos += (p.width if horizontal else p.height) + gap
    return out


def save_jpeg(image: Image.Image, path: Path) -> None:
    image.save(path, "JPEG", quality=80, optimize=True, progressive=True)


PRED_LEGEND = [
    (BLUE, "mud: ground truth / correctly predicted"),
    (ORANGE, "predicted mud, not in GT (FP)"),
    (GREEN, "GT mud missed (FN)"),
]


def figure_track_level(arm: Arm, keys: list[str], runs: list[Run], counts, path: Path) -> None:
    size = (400, 227)
    widths = [size[0]] * (2 + len(runs))
    titles = ["image", "ground truth (paul masks)"] + [f"prediction: {r.name}" for r in runs]
    rows = [
        legend_strip(sum(widths) + 4 * (len(widths) - 1), PRED_LEGEND),
        header_row(widths, titles),
    ]
    for key in keys:
        image, gt = arm.image(key), arm.mask(key)
        cells = [image.resize(size, Image.Resampling.LANCZOS), panel(image, gt_layers(gt), size)]
        ious = []
        for r in runs:
            pred = prediction(r, key, gt, counts[r.job][key])
            cells.append(panel(image, pred_layers(gt, pred), size))
            ious.append(f"{r.model} {pct(counts[r.job][key]['iou'])}")
        share = 100 * float(gt.__eq__(MUD).mean())
        text = (
            f"{arm.by_key[key]['stem']} · {arm.by_key[key]['group']} · mud covers {share:.0f}% of "
            "the frame · per-image mud IoU: " + ", ".join(ious)
        )
        rows += [
            caption_row(sum(widths) + 4 * (len(widths) - 1), text),
            stack(cells, horizontal=True),
        ]
    save_jpeg(stack(rows), path)


def zoom_box(
    mask: np.ndarray, aspect: float = 16 / 9, min_w: int = 320
) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    cw = max(min_w, int(1.6 * (x1 - x0)), int(1.6 * (y1 - y0) * aspect))
    cw = min(cw, w, int(h * aspect))
    ch = round(cw / aspect)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    left = int(np.clip(cx - cw // 2, 0, w - cw))
    top = int(np.clip(cy - ch // 2, 0, h - ch))
    return left, top, left + cw, top + ch


def figure_cab(arm: Arm, keys: list[str], runs: list[Run], counts, path: Path) -> list[dict]:
    size = (400, 225)
    widths = [size[0]] * (2 + len(runs))
    titles = ["full frame, GT (white box = zoom)", "zoom: ground truth"] + [
        f"zoom: {r.name}" for r in runs
    ]
    total_w = sum(widths) + 4 * (len(widths) - 1)
    rows = [legend_strip(total_w, PRED_LEGEND), header_row(widths, titles)]
    notes = []
    for key in keys:
        image, gt = arm.image(key), arm.mask(key)
        box = zoom_box(gt == MUD)
        full = panel(image, gt_layers(gt), size)
        sx, sy = size[0] / gt.shape[1], size[1] / gt.shape[0]
        ImageDraw.Draw(full).rectangle(
            (box[0] * sx, box[1] * sy, box[2] * sx - 1, box[3] * sy - 1),
            outline=(255, 255, 255),
            width=3,
        )
        crop = image.crop(box)
        sub = (slice(box[1], box[3]), slice(box[0], box[2]))
        cells = [full, panel(crop, gt_layers(gt[sub]), size)]
        bits = []
        for r in runs:
            pred = prediction(r, key, gt, counts[r.job][key])
            cells.append(panel(crop, pred_layers(gt[sub], pred[sub]), size))
            fp_all = counts[r.job][key]["fp"]
            fp_in = int(((gt[sub] != MUD) & (gt[sub] != IGNORE) & (pred[sub] == MUD)).sum())
            bits.append(
                f"{r.model} IoU {pct(counts[r.job][key]['iou'])}, FP outside zoom "
                f"{fp_all - fp_in:,} px"
            )
            notes.append({"key": key, "job": r.job, "fp_outside": fp_all - fp_in})
        s = arm.by_key[key]
        zoom = (box[2] - box[0]) / gt.shape[1]
        text = (
            f"{s['stem']} · {s['group']} · mud GT {int((gt == MUD).sum()):,} px · "
            f"zoom {1 / zoom:.1f}x · " + "; ".join(bits)
        )
        rows += [caption_row(total_w, text), stack(cells, horizontal=True)]
    save_jpeg(stack(rows), path)
    return notes


def cv_caption(image: CvImage, zoom: float, fp_outside: int) -> str:
    bits = [image.key.rsplit("/", 1)[-1], image.group, f"fold {image.fold}"]
    if image.gt:
        bits += [f"mud GT {image.gt:,} px", f"FP {image.fp:,} px"]
        bits.append(f"image mud IoU {pct(image.counts['iou'])}")
    else:
        bits += ["no mud in GT", f"FP {image.fp:,} px"]
    bits += [f"zoom {zoom:.1f}x", f"FP outside zoom {fp_outside:,} px"]
    return " · ".join(bits)


def figure_cv_fp(case: CvCase, shown: list[CvImage], path: Path) -> list[dict]:
    size = (432, 243)
    widths = [size[0]] * 3
    titles = ["full frame: prediction (white box = zoom)", "zoom: image", "zoom: prediction"]
    total_w = sum(widths) + 4 * (len(widths) - 1)
    rows = [legend_strip(total_w, PRED_LEGEND), header_row(widths, titles)]
    notes = []
    for image in shown:
        gt, pred = cv_prediction(case, image)
        rgb = case.folds[image.fold].arm.image(image.key)
        fp = (gt != MUD) & (gt != IGNORE) & (pred == MUD)
        box = fp_zoom_box(fp)
        full = panel(rgb, pred_layers(gt, pred), size)
        sx, sy = size[0] / gt.shape[1], size[1] / gt.shape[0]
        ImageDraw.Draw(full).rectangle(
            (box[0] * sx, box[1] * sy, box[2] * sx - 1, box[3] * sy - 1),
            outline=(255, 255, 255),
            width=3,
        )
        crop = rgb.crop(box)
        sub = (slice(box[1], box[3]), slice(box[0], box[2]))
        cells = [
            full,
            crop.resize(size, Image.Resampling.LANCZOS),
            panel(crop, pred_layers(gt[sub], pred[sub]), size),
        ]
        fp_outside = image.fp - int(fp[sub].sum())
        zoom = gt.shape[1] / (box[2] - box[0])
        rows += [
            caption_row(total_w, cv_caption(image, zoom, fp_outside)),
            stack(cells, horizontal=True),
        ]
        notes.append({"key": image.key, "box": box, "fp_outside": fp_outside})
    save_jpeg(stack(rows), path)
    return notes


class Embedder:
    """Global-average-pooled ImageNet ResNet-50 features (torchvision ``IMAGENET1K_V2``), CPU.

    A generic appearance embedding: cosine near 1 means near-duplicate content and framing.
    It is not trained on rail data and is not evidence of a shared recording on its own."""

    def __init__(self, reduce: int = REDUCE) -> None:
        import torch
        import torchvision

        self.torch = torch
        weights = torchvision.models.ResNet50_Weights.IMAGENET1K_V2
        torch.manual_seed(0)
        self.model = torchvision.models.resnet50(weights=weights).eval()
        self.model.fc = torch.nn.Identity()
        self.transform = weights.transforms()
        self.weights = weights.url.rsplit("/", 1)[-1]
        self.reduce = reduce

    def __call__(self, image: Image.Image) -> np.ndarray:
        with self.torch.no_grad():
            v = self.model(self.transform(image.reduce(self.reduce))[None])[0].double().numpy()
        return v / np.linalg.norm(v)


def neighbours(arm: Arm, keys: list[str], embed: Embedder) -> dict[str, list[tuple[float, str]]]:
    train = sorted(s["key"] for s in arm.samples if s["split"] == "train")
    bank = np.stack([embed(arm.image(k)) for k in train])
    out = {}
    for key in keys:
        scores = bank @ embed(arm.image(key))
        order = sorted(range(len(train)), key=lambda i: (-round(float(scores[i]), 6), train[i]))
        out[key] = [(float(scores[i]), train[i]) for i in order]
    return out


def adjacent(arm: Arm, key: str) -> str:
    """The frames on either side of an image in stem order within its scene group, with split."""
    group = arm.by_key[key]["group"]
    stems = sorted((s["stem"], s["split"]) for s in arm.samples if s["group"] == group)
    i = [st for st, _ in stems].index(arm.by_key[key]["stem"])
    side = [stems[j] for j in (i - 1, i + 1) if 0 <= j < len(stems)]
    return ", ".join(f"`{st}` {sp}" for st, sp in side)


def figure_neighbours(arm: Arm, keys: list[str], nn, path: Path) -> None:
    size = (400, 227)
    widths = [size[0]] * (1 + NEIGHBOURS)
    titles = ["val frame (GT mud)"] + [
        f"train neighbour {i + 1} (GT mud)" for i in range(NEIGHBOURS)
    ]
    total_w = sum(widths) + 4 * (len(widths) - 1)
    rows = [
        legend_strip(
            total_w,
            [(BLUE, "mud ground truth")],
            f"sim = cosine of ImageNet ResNet-50 features ({REDUCE}x downscale, then the standard "
            "torchvision transform), searched over all train frames",
        ),
        header_row(widths, titles),
    ]
    for key in keys:
        cells = [panel(arm.image(key), gt_layers(arm.mask(key)), size, 0.2)]
        bits = [f"val {arm.by_key[key]['stem']} ({arm.by_key[key]['group']})"]
        for score, k in nn[key][:NEIGHBOURS]:
            cells.append(panel(arm.image(k), gt_layers(arm.mask(k)), size, 0.2))
            s = arm.by_key[k]
            bits.append(f"{s['stem']} {s['group']} sim {score:.3f}")
        rows += [caption_row(total_w, " | ".join(bits)), stack(cells, horizontal=True)]
    save_jpeg(stack(rows), path)


def scatter_svg(runs: list[Run], marked: dict[str, str], path: Path) -> None:
    """All-image vs cab-view mud IoU, one dot per run, y = x reference, median guides."""
    W, H, L, R, T, B = 720, 520, 64, 24, 48, 56
    pw, ph = W - L - R, H - T - B

    def x(v: float) -> float:
        return L + pw * v

    def y(v: float) -> float:
        return T + ph * (1 - v)

    xs = [r.metrics["all"]["mud_iou"] for r in runs]
    ys = [r.metrics[CAB]["mud_iou"] for r in runs]
    mx, my = statistics.median(xs), statistics.median(ys)
    e = html.escape
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        'font-family="system-ui, -apple-system, Segoe UI, sans-serif" role="img" '
        'aria-labelledby="t d">',
        '<title id="t">Mud-pumping IoU per run: all val images vs cab-view val images</title>',
        f'<desc id="d">{len(runs)} runs of the paul arm. Median all-image {pct(mx)}, median cab-view {pct(my)}.</desc>',
        "<style>",
        ".bg{fill:#fcfcfb}.grid{stroke:#e4e3df;stroke-width:1}.axis{stroke:#c3c2b7;stroke-width:1}"
        ".ref{stroke:#8a8983;stroke-width:1.5}.med{stroke:#8a8983;stroke-width:1}"
        ".t1{fill:#0b0b0b}.t2{fill:#52514e}.dot{fill:#2a78d6;stroke:#fcfcfb;stroke-width:2}"
        ".hit{fill:transparent}",
        "@media (prefers-color-scheme: dark){.bg{fill:#1a1a19}.grid{stroke:#2e2e2b}.axis{stroke:#4a4a46}"
        ".ref,.med{stroke:#8f8e86}.t1{fill:#ffffff}.t2{fill:#c3c2b7}.dot{fill:#3987e5;stroke:#1a1a19}}",
        "</style>",
        f'<rect class="bg" width="{W}" height="{H}" rx="8"/>',
        f'<text class="t1" x="{L}" y="24" font-size="15" font-weight="600">Mud-pumping IoU, all val images vs cab-view val images ({len(runs)} runs, paul arm)</text>',
    ]
    for t in range(0, 101, 20):
        v = t / 100
        out += [
            f'<line class="grid" x1="{x(0)}" x2="{x(1)}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>',
            f'<line class="grid" y1="{y(0)}" y2="{y(1)}" x1="{x(v):.1f}" x2="{x(v):.1f}"/>',
            f'<text class="t2" x="{L - 8}" y="{y(v) + 4:.1f}" font-size="12" text-anchor="end">{t}</text>',
            f'<text class="t2" x="{x(v):.1f}" y="{T + ph + 18}" font-size="12" text-anchor="middle">{t}</text>',
        ]
    out += [
        f'<line class="axis" x1="{x(0)}" x2="{x(1)}" y1="{y(0)}" y2="{y(0)}"/>',
        f'<line class="ref" x1="{x(0)}" y1="{y(0)}" x2="{x(1)}" y2="{y(1)}"/>',
        f'<text class="t2" x="{x(0.70):.1f}" y="{y(0.74):.1f}" font-size="12" transform="rotate(-{np.degrees(np.arctan(ph / pw)):.1f} {x(0.70):.1f} {y(0.74):.1f})">y = x (cab-view as good as all images)</text>',
        f'<line class="med" x1="{x(mx):.1f}" x2="{x(mx):.1f}" y1="{y(0)}" y2="{y(1)}"/>',
        f'<line class="med" x1="{x(0)}" x2="{x(1)}" y1="{y(my):.1f}" y2="{y(my):.1f}"/>',
        f'<text class="t2" x="{x(mx) - 6:.1f}" y="{y(0.03):.1f}" font-size="12" text-anchor="end">median all {pct(mx)}</text>',
        f'<text class="t2" x="{x(0.01):.1f}" y="{y(my) - 6:.1f}" font-size="12">median cab-view {pct(my)}</text>',
        f'<text class="t1" x="{L + pw / 2}" y="{H - 16}" font-size="13" text-anchor="middle">mud IoU, all {runs[0].metrics["all"]["images"]} val images (%)</text>',
        f'<text class="t1" transform="translate(18 {T + ph / 2}) rotate(-90)" font-size="13" text-anchor="middle">mud IoU, cab-view val images (%)</text>',
    ]
    for r, vx, vy in sorted(zip(runs, xs, ys, strict=True), key=lambda t: t[0].job):
        tip = e(f"{r.name}: all {pct(vx)}, cab-view {pct(vy)}")
        out.append(
            f'<g><title>{tip}</title><circle class="hit" cx="{x(vx):.1f}" cy="{y(vy):.1f}" r="10"/>'
            f'<circle class="dot" cx="{x(vx):.1f}" cy="{y(vy):.1f}" r="5"/></g>'
        )
    # Direct labels sit left of the cluster, joined to their dot by a hairline leader.
    labelled = sorted(
        ((vy, vx, r) for r, vx, vy in zip(runs, xs, ys, strict=True) if r.job in marked),
        key=lambda t: -t[0],
    )
    last = None
    for vy, vx, r in labelled:
        ly = y(vy) + 4 if last is None else max(y(vy) + 4, last + 18)
        last = ly
        lx = x(min(xs)) - 24
        out += [
            f'<line class="med" x1="{lx + 4:.1f}" y1="{ly - 4:.1f}" x2="{x(vx) - 7:.1f}" y2="{y(vy):.1f}"/>',
            f'<text class="t1" x="{lx:.1f}" y="{ly:.1f}" font-size="12" '
            f'text-anchor="end">{e(marked[r.job])}: {pct(vy)}</text>',
        ]
    out.append("</svg>")
    path.write_text("\n".join(out) + "\n")


# ----------------------------------------------------------------------------- text


def pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}"


def table(headers: list[str], rows: list[list[str]], right: set[int]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---:" if i in right else "---" for i in range(len(headers))) + "|",
        *("| " + " | ".join(r) + " |" for r in rows),
        "",
    ]


CV_FIGURE = "fig5-cv-false-positives.jpg"
# What figure 5 visibly shows, written after looking at it. Printed only while the figure shows
# exactly these images, so a change of data cannot leave a stale description behind.
CV_OBSERVED_KEYS: tuple[str, ...] = (
    "miscellaneous-numbered-cab-views/0032",
    "sunny-mainline-cab-view/0146",
    "sunny-mountain-stations/0230",
    "sunny-mainline-cab-view/0154",
    "sunny-mainline-cab-view/0157",
    "sunny-mainline-cab-view/0143",
    "sunny-mainline-cab-view/0153",
    "sunny-mainline-cab-view/0151",
)
CV_OBSERVED = (
    "In the pictures the false positives sit on pale ground in the track area: the gravel and "
    "concrete around the rack track in `0032`, the paved crossing over the tracks in `0230`, "
    "and light ballast along and between the rails in the `sunny-mainline-cab-view` frames, "
    "often as a fringe around the true patches. In `0151` the predicted mud is a strip of "
    "ballast beside a rail, away from the true patches, which are mostly missed."
)


def cv_title(case: CvCase) -> str:
    who = "the best model" if case.rank == 1 else f"the {CV_RUN[0]} model"
    return f"Cross-validation: where {who} predicts mud that is not there"


def cv_section(case: CvCase, shown: list[CvImage], number: int, figure: int, rel: str) -> list[str]:
    model, protocol, _ = CV_RUN
    cab = [i for i in case.images if i.viewpoint == CAB]
    fp_total = sum(i.fp for i in cab)
    if not fp_total or not shown:
        raise CaseError(f"{model} {protocol}: no false-positive mud on {CAB} images")
    no_gt = [i for i in cab if i.fp and not i.gt]
    with_gt = [i for i in cab if i.fp and i.gt]
    fp_no_gt, fp_gt = sum(i.fp for i in no_gt), sum(i.fp for i in with_gt)
    precision = case.pooled[CAB]["focus_precision"]

    def share(value: int) -> str:
        return f"{100 * value / fp_total:.1f}%"

    def images(n: int) -> str:
        return f"{n} image{'s' if n != 1 else ''}"

    best = (
        f"the best of the {case.setups} complete setups"
        if case.rank == 1
        else f"rank {case.rank} of the {case.setups} complete setups"
    )
    L = [
        f"## {number}. {cv_title(case)}",
        "",
        f"Run: **{model}, `{protocol}`** ({CV_START}) of the `{case.campaign}` cross-validation "
        f"([guide](cross-validation.md#worked-example-rad_9_24_2026)), {best} by pooled "
        "train-camera mud IoU. Final checkpoint (`final-auto-val`). Each image is scored by the "
        "fold model that never saw its scene group. Ground truth is our re-rendered labels (the "
        f"`{CV_DATASET}` folds), not the `paul` masks used above. On the "
        f"{case.pooled[CAB]['images']} train-camera (cab-view) images the pooled mud precision is "
        f"{pct(precision)}%, so {pct(1 - precision)}% of the pixels predicted as mud are false "
        "positives.",
        "",
        f"- **{fp_total:,} false-positive mud pixels** on train-camera images, in "
        f"{len(no_gt) + len(with_gt)} of {len(cab)} images.",
        f"- {fp_no_gt:,} ({share(fp_no_gt)}) are on {images(len(no_gt))} with no mud in the "
        f"ground truth; {fp_gt:,} ({share(fp_gt)}) are on {images(len(with_gt))} that have mud, "
        "outside the true patch.",
        f"- The {len(shown)} images with the most (figure {figure}) hold "
        f"{share(sum(i.fp for i in shown))}.",
        "",
        f"**Figure {figure}.** The {len(shown)} train-camera images with the most false-positive "
        "mud pixels. The first column is the whole frame with the prediction and the zoom box; "
        "the other columns are the zoomed region without and with the prediction. The zoom box "
        "sits where it holds the most false-positive pixels; false positives outside it are "
        "counted in the caption.",
        "",
        f"![Train-camera false-positive mud in cross-validation]({rel}/{CV_FIGURE})",
        "",
    ]
    L += table(
        [
            "image",
            "scene group",
            "fold",
            "mud GT",
            "GT mud px",
            "FP px",
            "share of train-camera FP",
            "image mud IoU",
        ],
        [
            [
                f"`{i.key.rsplit('/', 1)[-1]}`",
                f"`{i.group}`",
                str(i.fold),
                "yes" if i.gt else "no",
                f"{i.gt:,}",
                f"{i.fp:,}",
                share(i.fp),
                pct(i.counts["iou"]) if i.gt else "—",
            ]
            for i in shown
        ],
        {2, 4, 5, 6, 7},
    )
    if CV_OBSERVED and tuple(i.key for i in shown) == CV_OBSERVED_KEYS:
        L += [CV_OBSERVED, ""]
    return L


def write_doc(ctx: dict[str, Any], path: Path) -> None:
    c = ctx
    arm, comp = c["arm"], c["comp"]
    strat, grouped = comp[ARM], comp["fixed-grouped"]
    total = strat["mud_pixels"]
    best, ref = c["best"], c["ref"]
    runs = c["runs"]
    med = c["medians"]
    close = c["closeup_keys"]
    cab = c["cab_keys"]
    close_px = sum(c["mud_px"][k] for k in close)
    cab_px = sum(c["mud_px"][k] for k in cab)
    rel = "assets/rad-9-24-2026-mud-iou"
    n_runs = len(runs)
    below = sum(r.metrics[CAB]["mud_iou"] < r.metrics["all"]["mud_iou"] for r in runs)
    fg_done, fg_total = c["done"]["fixed-grouped"]
    grouped_cab = grouped["viewpoints"][CAB]
    grouped_top_group, grouped_top_n = next(iter(grouped["cab_mud_groups"].items()))
    nn = c["nn"]
    close_same = sum(arm.by_key[nn[k][0][1]]["group"] == CLOSEUP_GROUP for k in close)
    dup = [k for k in close if nn[k][0][0] >= DUPLICATE]
    not_dup = [k for k in close if k not in dup]
    stems = lambda keys: ", ".join(arm.by_key[k]["stem"] for k in keys)  # noqa: E731
    dup_other = max(
        (next(sc for sc, kk in nn[k] if arm.by_key[kk]["group"] != CLOSEUP_GROUP) for k in dup),
        default=0.0,
    )
    close_share = f"{100 * close_px / total:.1f}%"
    best_cab = pct(best.metrics[CAB]["mud_iou"])
    pending = fg_done < fg_total
    cv_case: CvCase = c["cv"]
    cv_fp = 1 - cv_case.pooled[CAB]["focus_precision"]
    cv_bullet = [
        f"- **Cross-validation false positives.** For {CV_RUN[0]} `{CV_RUN[1]}`"
        + (", the best cross-validation run," if cv_case.rank == 1 else "")
        + f" {pct(cv_fp)}% of the mud it predicts on train-camera images is not mud in the "
        "ground truth; figure 5 shows the images with the most (section 8)."
    ]
    L: list[str] = []
    L += [
        "# Where the stratified-split mud-pumping IoU comes from (RAD 9/24/2026)",
        "",
        "A case file for the `rad_9_24_2026` comparison ([guide](rad-9-24-2026.md)). Every number, "
        "table and figure below is written by `scripts/make_rad_mud_case.py` from the prepared "
        "datasets and the campaign results; nothing is typed by hand. Validation split only.",
        "",
        "## 1. Summary",
        "",
        f"- **Where the score comes from.** On the stratified val split, {len(close)} track-level "
        f"frames from one scene group hold {close_share} of the val mud-pumping pixels. The high "
        "all-image mud IoU mostly reflects those frames.",
        f"- **Cab-view is much lower.** Over {n_runs} single-seed runs the median mud IoU is "
        f"{pct(med['all'])} on all val images and {pct(med['cab'])} on cab-view images; "
        f"{below} of {n_runs} runs score lower on cab-view. The models do segment cab-view mud "
        f"in part: the best run reaches {best_cab}.",
        f"- **Same-scene frames are in train.** All {strat['val_groups_in_train']} of "
        f"{strat['val_groups']} val scene groups also have train frames, including neighbouring "
        "frames of the same stretch of track.",
        "- **Optimistic and unreplicated.** One seed per run, and checkpoints are selected on this "
        "same val split.",
        "- **Scene-grouped results: "
        + (
            f"pending** ({fg_done} of {fg_total} jobs completed)."
            if pending
            else "see section 7.**"
        ),
        *cv_bullet,
        "",
        "In more detail: "
        f"{len(close)} track-level frames from the `{CLOSEUP_GROUP}` scene group hold "
        f"{close_share} of all mud-pumping ground-truth pixels on the stratified val split, and "
        f"the {len(cab)} cab-view images that contain mud hold {100 * cab_px / total:.1f}%. "
        "Because mud IoU is aggregated over pixels, the headline number mostly measures those "
        f"frames: across the {n_runs} `paul`-arm runs the median mud IoU is {pct(med['all'])} on "
        f"all val images but {pct(med['cab'])} on the cab-view images, and {below} of {n_runs} "
        f"runs score lower on cab-view. The best cab-view run ({best.name}) reaches {best_cab}. "
        + (
            f"For all {len(close)} track-level frames"
            if close_same == len(close)
            else f"For {close_same} of the {len(close)} track-level frames"
        )
        + " the most similar train frame is from the same scene group. "
        + (
            f"For {len(dup)} of them ({stems(dup)}) it scores at least {DUPLICATE:.2f}, against "
            f"at most {dup_other:.3f} for any train frame from another group; figure 3 shows "
            "them side by side with their nearest train frames. "
            if dup
            else ""
        )
        + (
            f"For {' and '.join(arm.by_key[k]['stem'] for k in not_dup)} the best score is only "
            f"{' and '.join(f'{nn[k][0][0]:.2f}' for k in not_dup)}, so these are neighbouring "
            "frames, not copies. "
            if not_dup
            else ""
        )
        + "The high all-image number therefore mostly measures segmentation of large, "
        "close-range mud on a stretch of track whose neighbouring frames are in training; it says "
        "little about spotting small mud patches from the cab. "
        + (
            f"The scene-grouped arm, the closest test we have of that, has {fg_done} of "
            f"{fg_total} jobs completed, so the comparison is still pending."
            if pending
            else f"All {fg_total} scene-grouped jobs are completed; see section 7."
        ),
        "",
        "The `paul` arm uses a stratified random split over frames (multi-label iterative "
        "stratification, see the guide), a standard choice that keeps rare classes in every "
        "split. The issue here is not the split rule: many frames in this dataset are neighbouring "
        "views of the same scene, so a random frame-level split puts such neighbours in both "
        "train and val.",
        "",
        "## 2. The metric",
        "",
        "Pixel-aggregated mud IoU sums true positives, false positives and false negatives over "
        "all images first and then computes TP / (TP + FP + FN), so each image counts in "
        "proportion to its number of mud pixels. An image whose frame is one-third mud carries "
        "as much weight as dozens of cab-view frames with a small patch each, and a model that "
        "segments a few large, easy frames can score high even if it does poorly on the rest "
        f"(here the {len(close)} track-level frames are {close_share} of the mud pixels).",
        "",
        "## 3. Evidence A: where the val mud pixels are",
        "",
        "Every val image with mud ground truth on the stratified split (`paul` arm masks). "
        f"Per-image mud IoU is shown for the best cab-view run, **{best.name}**, and for the "
        f"reference run **{ref.name}**. `share` is the image's share of all {total:,} val mud "
        "pixels; `frame` is the share of the image covered by mud.",
        "",
    ]
    rows = []
    for k in c["mud_keys"]:
        s = arm.by_key[k]
        rows.append(
            [
                f"`{s['stem']}`",
                arm.viewpoint(k),
                f"`{s['group']}`",
                f"{c['mud_px'][k]:,}",
                f"{100 * c['mud_px'][k] / total:.1f}%",
                f"{100 * c['mud_px'][k] / (s['width'] * s['height']):.1f}%",
                pct(c["counts"][best.job][k]["iou"]),
                pct(c["counts"][ref.job][k]["iou"]),
            ]
        )
    L += table(
        [
            "image",
            "viewpoint",
            "scene group",
            "mud px",
            "share",
            "frame",
            f"IoU {best.model}",
            f"IoU {ref.model}",
        ],
        rows,
        {3, 4, 5, 6, 7},
    )
    sub_rows = []
    for title, key in (
        ("all val images", "all"),
        ("cab-view", CAB),
        (f"excluding `{CLOSEUP_GROUP}`", EXCL),
    ):
        sub_rows.append(
            [
                title,
                f"{best.metrics[key]['images_with_mud_gt']}",
                pct(best.metrics[key]["mud_iou"]),
                pct(ref.metrics[key]["mud_iou"]),
            ]
        )
    L += [
        "Pixel-aggregated mud IoU of the same two runs on each subset:",
        "",
        *table(["subset", "images with mud", best.name, ref.name], sub_rows, {1, 2, 3}),
    ]
    fp_keys = sorted(
        (
            k
            for k in c["val_keys"]
            if not c["mud_px"][k] and any(c["counts"][r.job][k]["fp"] for r in (best, ref))
        ),
        key=lambda k: (-max(c["counts"][r.job][k]["fp"] for r in (best, ref)), k),
    )
    if fp_keys:
        L += [
            "False-positive mud on val images **without** mud ground truth (pixels). They count "
            "against every subset that contains them, including all val images, but matter most "
            f"relative to the small cab-view total ({cab_px:,} mud pixels).",
            "",
            *table(
                ["image", "viewpoint", "scene group", f"FP {best.model}", f"FP {ref.model}"],
                [
                    [
                        f"`{arm.by_key[k]['stem']}`",
                        arm.viewpoint(k),
                        f"`{arm.by_key[k]['group']}`",
                        f"{c['counts'][best.job][k]['fp']:,}",
                        f"{c['counts'][ref.job][k]['fp']:,}",
                    ]
                    for k in fp_keys
                ],
                {3, 4},
            ),
        ]
    L += [
        "## 4. Evidence B: what these images look like",
        "",
        "Colours are the same in every figure: blue = mud in the ground truth (in a prediction "
        "panel, mud predicted correctly), orange = mud predicted where the ground truth has none, "
        "green = ground-truth mud the model missed. Images are downscaled; small regions are "
        "drawn with any-coverage downscaling and an outline so they stay visible. Click a figure "
        "to see it at full size.",
        "",
        f"**Figure 1.** The {len(close)} `{CLOSEUP_GROUP}` track-level frames that hold "
        f"{close_share} of the val mud pixels. Two are close-ups of the track bed; the others "
        "look down the track from standing height.",
        "",
        f"![Trackside-maintenance track-level frames with ground truth and predictions]({rel}/fig1-track-level.jpg)",
        "",
        f"**Figure 2.** The {len(cab)} cab-view val images with mud ground truth "
        f"({100 * cab_px / total:.1f}% of the val mud pixels). The first column is the whole "
        "frame with the ground truth and the zoom box; the other columns are the zoomed region. "
        "Mud predicted outside the zoom box is counted in the caption.",
        "",
        f"![Cab-view val images, zoomed on the mud patches]({rel}/fig2-cab-view.jpg)",
        "",
        f"**Figure 3.** The {len(c['nn_queries'])} track-level frames whose nearest train frame "
        f"is most similar, with their {NEIGHBOURS} most similar frames among all "
        f"{c['n_train']} train images (searched over every scene group). Similarity is the "
        "cosine between global-average-pooled ImageNet ResNet-50 features (torchvision "
        f"`IMAGENET1K_V2`, CPU). Each image is first downscaled {REDUCE}x (PIL `Image.reduce"
        f"({REDUCE})`) and then passed through the weights' standard transform (resize to 232, "
        "centre crop 224, normalise). It is a generic appearance score in which near 1 means "
        "near-identical content and framing, not proof of a shared recording.",
        "",
        f"![Track-level frames and their nearest train frames]({rel}/fig3-train-neighbours.jpg)",
        "",
        "Nearest train frame of every val image with mud, by the same score. `best other group` is "
        "the highest score reached by any train frame from a different scene group; `without "
        "downscale` is the nearest train frame when the standard transform is applied to the "
        "full-resolution image instead (a sensitivity check); `stem neighbours` are the frames "
        "just before and after the image in stem (file-name) order within its scene group, with "
        "their split.",
        "",
    ]
    rows = []

    def where(key: str, group: str) -> str:
        g = arm.by_key[key]["group"]
        return f"`{arm.by_key[key]['stem']}` ({'same group' if g == group else f'`{g}`'})"

    changed = []
    for k in c["mud_keys"]:
        nn = c["nn"][k]
        top_score, top_key = nn[0]
        alt_score, alt_key = c["nn_full"][k][0]
        group = arm.by_key[k]["group"]
        other = next(sc for sc, kk in nn if arm.by_key[kk]["group"] != group)
        if alt_key != top_key:
            changed.append(k)
        rows.append(
            [
                f"`{arm.by_key[k]['stem']}`",
                f"`{group}`",
                where(top_key, group),
                f"{top_score:.3f}",
                f"{other:.3f}",
                "same" if alt_key == top_key else f"{where(alt_key, group)} {alt_score:.3f}",
                str(c["train_in_group"][group]),
                adjacent(arm, k),
            ]
        )
    L += table(
        [
            "val image",
            "scene group",
            "nearest train",
            "similarity",
            "best other group",
            "without downscale",
            "train frames in group",
            "stem neighbours",
        ],
        rows,
        {3, 4, 6},
    )
    changed_close = [k for k in changed if k in close]
    L += [
        "Cab-view frames look alike to an ImageNet embedding (the best score from another group is "
        "already high for them, up to "
        f"{max(next(sc for sc, kk in c['nn'][k] if arm.by_key[kk]['group'] != arm.by_key[k]['group']) for k in cab):.3f}), "
        "so the score separates near-identical frames mainly for the track-level frames. "
        + (
            f"Without the downscale the nearest train frame changes for {len(changed)} of "
            f"{len(c['mud_keys'])} images ({stems(changed)}), "
            + (
                "none of them track-level frames, so cab-view nearest-frame matches depend on "
                "preprocessing and should not be read individually. "
                if not changed_close
                else f"including track-level frames {stems(changed_close)}. "
            )
            if changed
            else "Without the downscale every nearest train frame stays the same. "
        )
        + "The stem order shows the track-level frames sit in a numbered sequence whose "
        "neighbouring frames went to train and test.",
        "",
    ]
    L += [
        f"## 5. Evidence C: all {n_runs} runs",
        "",
        f"Each dot is one `paul`-arm run (selected `best-auto-val` checkpoint). Dots below the "
        f"diagonal score lower on cab-view images than on all images; {below} of {n_runs} do. "
        "The labelled dots are the top 3 runs by cab-view mud IoU and the reference run "
        f"({ref.name}).",
        "",
        f"![All-image vs cab-view mud IoU for every run]({rel}/fig4-all-vs-cab.svg)",
        "",
        f"Medians over the {n_runs} runs (percent):",
        "",
    ]
    L += table(
        ["metric", "median"],
        [
            ["mud IoU, all val images", pct(med["all"])],
            ["mud IoU, cab-view", pct(med["cab"])],
            [f"mud IoU, excluding `{CLOSEUP_GROUP}`", pct(med["excl"])],
            ["image-mean mud IoU, cab-view", pct(med["cab_img"])],
            ["GT-class mIoU, all val images", pct(med["miou"])],
            ["GT-class mIoU, cab-view", pct(med["miou_cab"])],
        ],
        {1},
    )
    L += ["Top 10 runs by cab-view mud IoU (percent):", ""]
    ranked = sorted(runs, key=lambda r: (-r.metrics[CAB]["mud_iou"], r.job))[:10]
    L += table(
        [
            "rank",
            "model",
            "protocol",
            "mud IoU cab",
            "mud IoU all",
            "img-mean mud IoU cab",
            "GT-class mIoU all",
        ],
        [
            [
                str(i + 1),
                f"`{r.model}`",
                f"`{r.protocol}`",
                pct(r.metrics[CAB]["mud_iou"]),
                pct(r.metrics["all"]["mud_iou"]),
                pct(r.metrics[CAB]["mud_image_mean_iou"]),
                pct(r.metrics["all"]["gt_class_miou"]),
            ]
            for i, r in enumerate(ranked)
        ],
        {0, 3, 4, 5, 6},
    )
    L += [
        "## 6. Evidence D: split overlap",
        "",
        'Scene groups are the directory layout names of the prepared arms. A val group "in '
        'train" has at least one train image in the same group. The stratified column is the '
        "`paul` arm (Paul's masks), the scene-grouped column the `fixed-grouped` arm (re-rendered "
        "masks), so the mud pixel counts also differ by the label render.",
        "",
    ]
    splits = (strat, grouped)
    rows = [
        ["arm (masks)", "`paul` (masks_machine)", "`fixed-grouped` (re-rendered)"],
        ["val images", *(str(cc["images"]) for cc in splits)],
        ["train images", *(str(len(cc["train_images"])) for cc in splits)],
        [
            "val scene groups that also have train images",
            *(f"{cc['val_groups_in_train']} of {cc['val_groups']}" for cc in splits),
        ],
    ]
    for v in subsets.VIEWPOINTS:
        rows += [
            [
                f"{v} val images (with mud)",
                *(
                    f"{cc['viewpoints'][v]['images']} ({cc['viewpoints'][v]['with_mud']})"
                    for cc in splits
                ),
            ],
            [
                f"{v} share of val mud pixels",
                *(
                    f"{100 * cc['viewpoints'][v]['mud_pixels'] / cc['mud_pixels']:.1f}%"
                    for cc in splits
                ),
            ],
        ]
    rows.append(["val mud pixels", *(f"{cc['mud_pixels']:,}" for cc in splits)])
    L += table(["", "stratified", "scene-grouped"], rows, {1, 2})
    mud_groups = grouped["cab_mud_groups"]
    L += [
        f"On the grouped split the cab-view val mud sits in {len(mud_groups)} scene "
        f"group{'s' if len(mud_groups) != 1 else ''}: "
        + ", ".join(f"`{g}` ({n} image{'s' if n != 1 else ''})" for g, n in mud_groups.items())
        + ".",
        "",
        "## 7. What the scene-grouped arm will tell us",
        "",
        "The `fixed-grouped` arm keeps every val scene group out of train. If the stratified "
        "numbers are inflated by same-scene frames, its mud IoU should fall to (or below) the "
        "stratified cab-view numbers rather than near the stratified all-image numbers. Three "
        "things are not separated by this test: the grouped arm also uses the re-rendered labels "
        "(a small effect on average, see section 10), it changes the training set "
        f"({len(strat['train_images'])} vs {len(grouped['train_images'])} train images) and its "
        f"val mud is {grouped_top_n} of {grouped_cab['with_mud']} cab-view images from one camera "
        f"setup (`{grouped_top_group}`), so it is a different and narrower val set, not the same "
        "val set with same-group frames removed.",
        "",
    ]
    cov_rows = [
        [f"`{a}`", f"{d} / {t}", st]
        for a, (d, t, st) in ((a, (*c["done"][a], c["status"][a])) for a in report.ARMS)
    ]
    L += table(["arm", "completed jobs", "other statuses"], cov_rows, {1})
    fg_runs = c["all_runs"]["fixed-grouped"]
    if fg_runs:
        L += [f"Completed `fixed-grouped` jobs ({len(fg_runs)} of {fg_total}), percent:", ""]
        L += table(
            ["model", "protocol", "mud IoU all", "mud IoU cab", "stratified (`paul`) mud IoU cab"],
            [
                [
                    f"`{r.model}`",
                    f"`{r.protocol}`",
                    pct(r.metrics["all"]["mud_iou"]),
                    pct(r.metrics[CAB]["mud_iou"]),
                    pct(c["paul_by_job"][r.job].metrics[CAB]["mud_iou"])
                    if r.job in c["paul_by_job"]
                    else "—",
                ]
                for r in sorted(fg_runs, key=lambda r: r.job)
            ],
            {2, 3, 4},
        )
    if fg_done < fg_total:
        L += [
            f"Pending: {fg_total - fg_done} of {fg_total} `fixed-grouped` jobs are not completed. "
            "Regenerate this document with `scripts/make_rad_mud_case.py` when they are.",
            "",
        ]
    L += cv_section(c["cv"], c["cv_shown"], 8, 5, rel)
    L += [
        "## 9. Comparison with the published RAD results",
        "",
        "The paper this dataset comes from (Stanik et al., IEEE journal manuscript, "
        "Rail Anomalies Dataset) reports the same pattern. Quoted facts, from its "
        "Section IV-C and Table II:",
        "",
        "- **Split:** 152 annotated images, 106 train / 30 validation / 16 test. The paper "
        "gives only the sizes. `scripts/shuffle_files.py` in pauls3/rail_segmentation "
        "(commit 28191e5) shuffles the image list with `random.seed(17)` and cuts it at 70% "
        "and 90%, which gives 106/30/16 for 152 images: a frame-level random split with no "
        "scene or recording grouping.",
        "- **Mud-pumping dominates the pixels:** it covers 26.68% of all labelled pixels and "
        "appears in 74.34% of frames (Table II), far more than any other non-background class.",
        '- **One source video:** the paper states that "the majority of the frames containing '
        "mud-pumping were sourced from a single video from the point-of-view of a person "
        "repairing the rail track\", with only a few from the locomotive's point of view, and "
        "that the trained models produced many mud-pumping false positives on RailSem19.",
        "",
        "| Model (paper, RAD test set) | mud-pumping IoU | test mIoU |",
        "| --- | ---: | ---: |",
        "| FRRN-B (City → RS19) | 84.21 | 49.9 |",
        "| HRNet + OCR + MS attention (Map → City → RS19) | 87.49 | 67.1 |",
        "| SFNet-ResNet-18 (Map → City → RS19) | 88.78 | 61.0 |",
        "",
        "All three published models, including the older FRRN-B baseline, score 84-89 on "
        "mud-pumping, well above their own mIoU. That is consistent with this document's "
        "finding: on a frame-level split of a dataset whose mud-pumping comes mostly from one "
        "close-range video, pixel-aggregated mud IoU mostly measures those close-range frames. "
        "The published numbers are on a different (2022, 19-class) version of the data and a "
        "16-image test set, so they are not directly comparable with the values above; the "
        "point is the shared pattern, not the exact figures.",
        "",
        "## 10. Caveats",
        "",
        "- **Single seed.** Every run is seed 0; there are no repeats or intervals, so differences "
        "of a few points between runs are not established.",
        "- **Optimistic checkpoints.** Each run's checkpoint is selected (and early stopped) on "
        "val mud IoU of this same val split, so every number here is an optimistic val score, "
        "not a held-out estimate.",
        f"- **Small cab-view subset.** On the stratified split the cab-view mud numbers rest on "
        f"{len(cab)} images ({cab_px:,} mud pixels); one image can move them by many points.",
        "- **Viewpoints are AI-assisted visual judgements.** "
        "`configs/datasets/rad_9_24_2026-viewpoints.yaml` comes from two labelling passes by the "
        "same AI model with adjudication of disagreements; not independent human annotation.",
        "- **Scene groups are layout names,** assigned from visual evidence, not confirmed "
        "recording provenance. The similarity in figure 3 is a generic ImageNet appearance score.",
        "- **Mask-conversion differences in the delivered `masks_machine/` masks** (used by the "
        "`paul` arm). The conversion labels pixels covered by no polygon as `person` and ignores "
        "polygon holes (see the guide); this is mechanical, not an annotation judgement. The "
        "figures use those masks because the runs were scored against them. "
        + report.LABEL_ARM_STOPPED,
        "",
        "## 11. Reproduce",
        "",
        "On the GPU host, from a repository checkout, with a Python environment that has torch "
        "and torchvision (read-only on the data; writes only this document and its assets). The "
        "ResNet-50 ImageNet weights are fetched once into the torch hub cache. Runs on CPU.",
        "",
        "```bash",
        "cd segmentary",
        'CUDA_VISIBLE_DEVICES="" PYTHONPATH=.:src python scripts/make_rad_mud_case.py',
        "```",
        "",
        "From local copies of the prepared datasets and campaigns (state files keep their HDRFS "
        "paths; the script rewrites them to `--campaign-root`):",
        "",
        "```bash",
        'CUDA_VISIBLE_DEVICES="" PYTHONPATH=.:src .venv/bin/python scripts/make_rad_mud_case.py \\',
        "  --datasets-root <copy>/datasets --campaign-root <copy>/rad_9_24_2026",
        "```",
        "",
        "Inputs used for this version:",
        "",
        *(f"- {k}: {v}" for k, v in c["inputs"].items()),
        "",
    ]
    path.write_text("\n".join(L))


# ----------------------------------------------------------------------------- main


def build(
    datasets: Path, campaign_root: Path, viewpoints_path: Path, doc: Path, assets: Path
) -> dict:
    viewpoints = subsets.load_viewpoints(viewpoints_path)
    arms = report.Arms(datasets)
    all_runs, coverage = load_campaigns(campaign_root, arms, viewpoints)
    comp, missing = report.composition(arms, viewpoints)
    if missing:
        raise CaseError(f"prepared datasets missing: {missing}")
    runs = all_runs[ARM]
    if not runs:
        raise CaseError("the paul arm has no completed job")
    arm = Arm(datasets / report.DATASET.format(arm=ARM), viewpoints)
    by_job = {r.job: r for r in runs}
    best = max(runs, key=lambda r: (r.metrics[CAB]["mud_iou"], r.job))
    if REFERENCE_JOB not in by_job:
        raise CaseError(f"reference job {REFERENCE_JOB} is not completed in the paul arm")
    ref = by_job[REFERENCE_JOB]
    shown = [best, ref] if best.job != ref.job else [best]
    counts = {r.job: per_image(r) for r in shown}
    cv_maps = []
    if campaign_root.resolve() != DEFAULT_CAMPAIGN_ROOT:
        cv_maps.append((str(DEFAULT_CAMPAIGN_ROOT), str(campaign_root)))
    if datasets.resolve() != report.DEFAULT_DATASETS:
        cv_maps.append((str(report.DEFAULT_DATASETS), str(datasets)))
    cv_case = load_cv(campaign_root / CV_CAMPAIGN, viewpoints_path, viewpoints, cv_maps)
    cv_shown = rank_false_positives(cv_case.images)

    val = [s for s in arm.samples if s["split"] == "val"]
    mud_px = {s["key"]: int(s["class_pixels"].get(str(MUD), 0)) for s in val}
    mud_keys = sorted((k for k in mud_px if mud_px[k]), key=lambda k: (-mud_px[k], k))
    close = [k for k in mud_keys if arm.by_key[k]["group"] == CLOSEUP_GROUP]
    cab = [k for k in mud_keys if arm.viewpoint(k) == CAB]

    assets.mkdir(parents=True, exist_ok=True)
    for stale in ("fig1-closeups.jpg",):  # renamed outputs of earlier versions
        (assets / stale).unlink(missing_ok=True)
    figure_track_level(arm, close, shown, counts, assets / "fig1-track-level.jpg")
    figure_cab(arm, cab, shown, counts, assets / "fig2-cab-view.jpg")
    embed = Embedder()
    nn = neighbours(arm, mud_keys, embed)
    nn_full = neighbours(arm, mud_keys, Embedder(reduce=1))
    queries = sorted(close, key=lambda k: (-nn[k][0][0], k))[:NEIGHBOUR_QUERIES]
    figure_neighbours(arm, queries, nn, assets / "fig3-train-neighbours.jpg")
    top = sorted(runs, key=lambda r: (-r.metrics[CAB]["mud_iou"], r.job))[:3]
    labelled = {r.job: f"#{i + 1} cab-view: {r.name}" for i, r in enumerate(top)}
    labelled.setdefault(ref.job, f"reference: {ref.name}")
    scatter_svg(runs, labelled, assets / "fig4-all-vs-cab.svg")
    figure_cv_fp(cv_case, cv_shown, assets / CV_FIGURE)

    train = [s for s in arm.samples if s["split"] == "train"]
    done, status = {}, {}
    for a in report.ARMS:
        entries = [cv for cv in coverage if cv.arm == a]
        counter: dict[str, int] = {}
        for cv in entries:
            if cv.status != "completed":
                counter[cv.status] = counter.get(cv.status, 0) + 1
        done[a] = (len(entries) - sum(counter.values()), len(entries))
        status[a] = ", ".join(f"{k} {v}" for k, v in sorted(counter.items())) or "—"

    def median(subset: str, name: str) -> float:
        return statistics.median(r.metrics[subset][name] for r in runs)

    ctx = {
        "arm": arm,
        "comp": comp,
        "runs": runs,
        "all_runs": all_runs,
        "paul_by_job": by_job,
        "best": best,
        "ref": ref,
        "counts": counts,
        "cv": cv_case,
        "cv_shown": cv_shown,
        "mud_px": mud_px,
        "mud_keys": mud_keys,
        "val_keys": sorted(mud_px),
        "closeup_keys": close,
        "cab_keys": cab,
        "nn": nn,
        "nn_full": nn_full,
        "labelled": labelled,
        "nn_queries": queries,
        "n_train": len(train),
        "train_in_group": {
            g: sum(s["group"] == g for s in train) for g in {s["group"] for s in val}
        },
        "done": done,
        "status": status,
        "medians": {
            "all": median("all", "mud_iou"),
            "cab": median(CAB, "mud_iou"),
            "excl": median(EXCL, "mud_iou"),
            "cab_img": median(CAB, "mud_image_mean_iou"),
            "miou": median("all", "gt_class_miou"),
            "miou_cab": median(CAB, "gt_class_miou"),
        },
        "inputs": {
            "viewpoints": f"`{viewpoints_path.name}` (sha256 `{sha256_file(viewpoints_path)[:12]}`)",
            **{f"samples `{a}`": f"sha256 `{arms.cache[a][2][:12]}`" for a in report.ARMS},
            "similarity weights": f"torchvision `{embed.weights}`",
            "campaigns": ", ".join(f"`{CAMPAIGN_DIR.format(arm=a)}`" for a in report.ARMS),
            "cross-validation": f"`{CV_CAMPAIGN}` (`{CV_SPEC.name}` sha256 "
            f"`{cv_case.spec_sha256[:12]}`)",
        },
    }
    write_doc(ctx, doc)
    return ctx


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--datasets-root", type=Path, default=report.DEFAULT_DATASETS)
    p.add_argument("--campaign-root", type=Path, default=DEFAULT_CAMPAIGN_ROOT)
    p.add_argument("--viewpoints", type=Path, default=report.DEFAULT_VIEWPOINTS)
    p.add_argument("--doc", type=Path, default=DOC)
    p.add_argument("--assets", type=Path, default=ASSETS)
    args = p.parse_args(argv)
    try:
        build(args.datasets_root, args.campaign_root, args.viewpoints, args.doc, args.assets)
    except (
        CaseError,
        report.ReportError,
        subsets.SubsetError,
        cvr.CvReportError,
        CvError,
    ) as error:
        raise SystemExit(f"make_rad_mud_case: {error}") from error
    for f in sorted(args.assets.iterdir()):
        print(f"{f.stat().st_size:>10,}  {f}")
    print(f"wrote {args.doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
