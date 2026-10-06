"""Stratified group k-fold cross-validation folds for a prepared folder dataset.

Input is any folder dataset in the campaign layout::

    <root>/images/<split>/<key>.<ext>     <root>/masks/<split>/<key>.png
    <root>/splits.json                    {"train": [...], ..., "groups": {key: group}}

The images of the *pool* splits (default ``train`` and ``val``) are divided into K folds by
whole groups (scenes, recordings), so frames of one group are never on both sides of a fold.
The *holdout* splits (default ``test``) stay out of every fold: they are carried into each fold
view as ``test`` and are never trained on or scored.

Stratification labels are per-image class presence read from the masks (any non-ignore pixel
of the class): the requested ``anomaly_classes`` plus every class present in fewer than
``rare_threshold`` images of the whole dataset. Groups are indivisible, so the folds come from
a seeded search: per restart, iterative stratification over whole groups (Sechidis et al.
2011, rarest label first) followed by steepest descent over single-group moves and pairwise
swaps; the best restart under :data:`OBJECTIVE` is kept. The objective is computed exactly in
integers, so the result does not depend on floating point or platform.

Images with ``min(width, height) < val_min_side`` are never scored (they would take an untested
whole-image evaluation path). In the fold of their group they are left out of the fold view
entirely, so no frame of a scored group trains; in the other folds they train. Groups without
a scorable image train in every fold.

:func:`materialize` writes ``<out>/cv-spec.json`` and one standard dataset per fold,
``<out>/fold-<k>/`` (val = fold k, train = the other pool groups, test = holdout), whose image
and mask files are hardlinks to the source (copies across filesystems). Each fold view is an
ordinary prepared dataset, so the folder loader and every campaign validator read it unchanged.

Command line (also ``segmentary-make-split --scheme stratified-group-kfold``)::

    segmentary-make-split --scheme stratified-group-kfold --root data/my_dataset \\
        --folds 5 --seed 0 --anomaly-classes defect --rare-threshold 50 \\
        --spec-out folds.json                     # inspect, then:
    segmentary-make-split --scheme stratified-group-kfold --root data/my_dataset \\
        --spec folds.json --out-root data/my_dataset-cv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

SCHEME = "stratified-group-kfold"
SPEC_NAME = "cv-spec.json"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
IMAGES_COLUMN = "<images>"
ROLES = ("cv_fold", "train_all_folds", "holdout")
OBJECTIVE = (
    "sum over balance columns c (each stratification label with scored images, plus the "
    "scored image count) and folds k of (x[k][c] / x[c] - 1/K)^2, where x[k][c] is the number "
    "of fold k's scored images carrying label c (or all of them) and x[c] its pool total; lower "
    "is better, 0 is a perfect 1/K share of every column in every fold. Exact integer "
    "arithmetic; ties broken by the canonical fold assignment."
)


class CvError(ValueError):
    """The dataset cannot be folded as requested, or a spec does not match its dataset."""


@dataclass(frozen=True)
class Item:
    key: str
    group: str
    split: str
    image: Path
    mask: Path
    image_sha256: str
    size: tuple[int, int]
    class_pixels: dict[str, int]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def class_names(root: Path) -> dict[int, str]:
    """Class id -> name from ``<root>/classes.json`` when present (else ids are used)."""
    path = root / "classes.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    return {int(c["id"]): str(c["name"]) for c in data.get("classes", [])}


def _image_file(root: Path, split: str, key: str) -> Path:
    found = [
        root / "images" / split / f"{key}{ext}"
        for ext in IMAGE_EXTENSIONS
        if (root / "images" / split / f"{key}{ext}").is_file()
    ]
    if len(found) != 1:
        raise CvError(f"{root}: expected one image for {split}/{key}, found {len(found)}")
    return found[0]


def scan_dataset(root: Path, ignore_index: int = 255) -> list[Item]:
    """Every image of a grouped folder dataset with its class presence from the mask."""
    splits_path = root / "splits.json"
    if not splits_path.is_file():
        raise CvError(f"{root} has no splits.json")
    splits = json.loads(splits_path.read_text())
    groups = splits.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise CvError(f"{splits_path} has no groups map; folds need whole groups")
    names = class_names(root)
    items = []
    seen: set[str] = set()
    for split, keys in splits.items():
        if split == "groups" or split.startswith("_") or not isinstance(keys, list):
            continue
        for key in keys:
            if key in seen:
                raise CvError(f"{splits_path}: {key} is in more than one split")
            if key not in groups:
                raise CvError(f"{splits_path}: {key} has no group")
            seen.add(key)
            image = _image_file(root, split, key)
            mask = root / "masks" / split / f"{key}.png"
            with Image.open(image) as im:
                size = im.size
            with Image.open(mask) as m:
                values = np.asarray(m)
            if values.shape[:2] != (size[1], size[0]):
                raise CvError(f"{mask}: mask size differs from its image")
            counts = np.bincount(values.ravel().astype(np.int64), minlength=256)
            pixels = {
                names.get(i, str(i)): int(n)
                for i, n in enumerate(counts)
                if n and i != ignore_index
            }
            items.append(
                Item(key, str(groups[key]), split, image, mask, sha256_file(image), size, pixels)
            )
    by_group: dict[str, set[str]] = {}
    for item in items:
        by_group.setdefault(item.group, set()).add(item.split)
    crossing = sorted(g for g, s in by_group.items() if len(s) > 1)
    if crossing:
        raise CvError(f"{splits_path}: groups in more than one split: {crossing}")
    return sorted(items, key=lambda i: i.key)


def stratification_labels(
    items: Sequence[Item], anomaly_classes: Sequence[str], rare_threshold: int
) -> tuple[list[str], list[str]]:
    present = Counter(c for i in items for c in i.class_pixels)
    missing = sorted(set(anomaly_classes) - set(present))
    if missing:
        raise CvError(f"Anomaly classes absent from every mask: {missing}")
    rare = sorted(c for c, n in present.items() if n < rare_threshold)
    return sorted(set(anomaly_classes) | set(rare)), rare


# ----------------------------------------------------------------------------- search


def _cost(sums: list[int], totals: list[int], weights: list[int], folds: int) -> int:
    return sum(w * (folds * s - t) ** 2 for w, s, t in zip(weights, sums, totals, strict=True))


def _add(a: list[int], b: list[int], sign: int = 1) -> list[int]:
    return [x + sign * y for x, y in zip(a, b, strict=True)]


def _greedy(
    groups: list[str],
    counts: dict[str, list[int]],
    totals: list[int],
    folds: int,
    rng: random.Random,
) -> dict[str, int]:
    """Iterative stratification over whole groups, rarest balance column first."""
    image = len(totals) - 1
    sums = [[0] * len(totals) for _ in range(folds)]
    fold_of: dict[str, int] = {}
    remaining = set(groups)

    def need(k: int, column: int) -> int:
        return totals[column] - folds * sums[k][column]

    while remaining:
        live = {c: n for c in range(image) if (n := sum(counts[g][c] for g in remaining)) > 0}
        column = image
        if live:
            fewest = min(live.values())
            column = rng.choice(sorted(c for c, n in live.items() if n == fewest))
        members = sorted(g for g in remaining if column == image or counts[g][column])
        rng.shuffle(members)
        members.sort(key=lambda g: -counts[g][column])
        for group in members:
            k = max(range(folds), key=lambda f: (need(f, column), need(f, image), rng.random()))
            fold_of[group] = k
            sums[k] = _add(sums[k], counts[group])
            remaining.discard(group)
    return fold_of


def _descend(
    fold_of: dict[str, int],
    groups: list[str],
    counts: dict[str, list[int]],
    totals: list[int],
    weights: list[int],
    folds: int,
) -> dict[str, int]:
    """Steepest descent over moves and swaps; a fold never loses its last scored image."""
    fold_of = dict(fold_of)
    sums = [[0] * len(totals) for _ in range(folds)]
    for g in groups:
        sums[fold_of[g]] = _add(sums[fold_of[g]], counts[g])
    cost = [_cost(s, totals, weights, folds) for s in sums]
    while True:
        best: tuple[int, str, str | None, int, int, list[int], list[int]] | None = None
        for i, g in enumerate(groups):
            a = fold_of[g]
            candidates: list[tuple[str | None, int, list[int]]] = [
                (None, b, counts[g]) for b in range(folds) if b != a
            ]
            candidates += [
                (h, fold_of[h], _add(counts[g], counts[h], -1))
                for h in groups[i + 1 :]
                if fold_of[h] != a
            ]
            for h, b, moved in candidates:
                new_a, new_b = _add(sums[a], moved, -1), _add(sums[b], moved)
                if new_a[-1] == 0 or new_b[-1] == 0:
                    continue
                delta = (
                    _cost(new_a, totals, weights, folds)
                    + _cost(new_b, totals, weights, folds)
                    - cost[a]
                    - cost[b]
                )
                if delta < 0 and (best is None or delta < best[0]):
                    best = (delta, g, h, a, b, new_a, new_b)
        if best is None:
            return fold_of
        _, g, h, a, b, new_a, new_b = best
        fold_of[g] = b
        if h is not None:
            fold_of[h] = a
        sums[a], sums[b] = new_a, new_b
        cost[a], cost[b] = (_cost(s, totals, weights, folds) for s in (new_a, new_b))


def _canonical(fold_of: dict[str, int], groups: list[str]) -> tuple[int, ...]:
    """Folds renumbered in order of their alphabetically first group (folds are exchangeable)."""
    order: dict[int, int] = {}
    for g in groups:
        order.setdefault(fold_of[g], len(order))
    return tuple(order[fold_of[g]] for g in groups)


def assign_folds(
    counts: dict[str, list[int]], folds: int, seed: int, restarts: int
) -> tuple[dict[str, int], dict[str, Any]]:
    """Best of ``restarts`` seeded group stratifications under :data:`OBJECTIVE`.

    ``counts[group]`` holds the group's scored images per balance column, the last column
    being its scored image count. Every fold receives at least one scored image."""
    groups = sorted(counts)
    if folds < 2:
        raise CvError("folds must be at least 2")
    if len(groups) < folds:
        raise CvError(f"{len(groups)} scorable groups cannot fill {folds} folds")
    if restarts < 1:
        raise CvError("restarts must be positive")
    width = len(next(iter(counts.values())))
    totals = [sum(counts[g][c] for g in groups) for c in range(width)]
    if any(t == 0 for t in totals):
        raise CvError("every balance column needs at least one scored image")
    scale = math.lcm(*(t * t for t in totals))
    weights = [scale // (t * t) for t in totals]
    rng = random.Random(seed)
    found: Counter[tuple[int, ...]] = Counter()
    best: tuple[int, tuple[int, ...]] | None = None
    infeasible = 0
    for _ in range(restarts):
        fold_of = _greedy(groups, counts, totals, folds, rng)
        canon = _canonical(_descend(fold_of, groups, counts, totals, weights, folds), groups)
        sums = [[0] * width for _ in range(folds)]
        for g, k in zip(groups, canon, strict=True):
            sums[k] = _add(sums[k], counts[g])
        if len(set(canon)) < folds or any(s[-1] == 0 for s in sums):
            infeasible += 1
            continue
        score = sum(_cost(s, totals, weights, folds) for s in sums)
        found[canon] += 1
        if best is None or (score, canon) < best:
            best = (score, canon)
    if best is None:
        raise CvError("no restart produced K folds that each score an image")
    objective = Fraction(best[0], folds * folds * scale)
    return dict(zip(groups, best[1], strict=True)), {
        "restarts": restarts,
        "infeasible_restarts": infeasible,
        "distinct_local_optima": len(found),
        "restarts_reaching_best": found[best[1]],
        "objective": float(objective),
        "objective_exact": f"{objective.numerator}/{objective.denominator}",
    }


# ----------------------------------------------------------------------------- spec


def load_viewpoints(path: Path) -> dict[str, str]:
    """``{image_sha256: viewpoint}`` from a YAML ``images: {sha256: {viewpoint: ...}}``."""
    images = (yaml.safe_load(Path(path).read_text()) or {}).get("images")
    if not isinstance(images, dict) or not images:
        raise CvError(f"{path}: no images map")
    return {str(sha): str(entry["viewpoint"]) for sha, entry in images.items()}


def source_identity(root: Path) -> dict[str, Any]:
    splits = json.loads((root / "splits.json").read_text())
    samples = root / "audit/samples.json"
    return {
        "dataset": root.name,
        "splits_sha256": sha256_file(root / "splits.json"),
        "samples_sha256": sha256_file(samples) if samples.is_file() else None,
        "grouping_status": splits.get("_grouping_status"),
    }


def make_spec(
    root: Path,
    *,
    folds: int = 5,
    seed: int = 0,
    restarts: int = 2000,
    anomaly_classes: Sequence[str] = (),
    rare_threshold: int = 50,
    pool_splits: Sequence[str] = ("train", "val"),
    holdout_splits: Sequence[str] = ("test",),
    val_min_side: int = 0,
    require_classes: Sequence[str] = (),
    viewpoints: Path | None = None,
    ignore_index: int = 255,
) -> dict[str, Any]:
    """Fold assignment and per-fold composition report of a grouped folder dataset."""
    items = scan_dataset(root, ignore_index)
    unknown = sorted({i.split for i in items} - set(pool_splits) - set(holdout_splits))
    if unknown:
        raise CvError(f"splits {unknown} are neither pool nor holdout")
    strat, rare = stratification_labels(items, anomaly_classes, rare_threshold)
    pool = [i for i in items if i.split in pool_splits]
    if not pool:
        raise CvError(f"no images in the pool splits {list(pool_splits)}")
    scored = [i for i in pool if min(i.size) >= val_min_side]
    columns = [c for c in strat if any(c in i.class_pixels for i in scored)]
    cv_groups = sorted({i.group for i in scored})
    counts = {
        g: [sum(c in i.class_pixels for i in scored if i.group == g) for c in columns]
        + [sum(i.group == g for i in scored)]
        for g in cv_groups
    }
    fold_of, search = assign_folds(counts, folds, seed, restarts)
    view = load_viewpoints(viewpoints) if viewpoints is not None else None
    if view is not None:
        missing = [i.key for i in pool if i.image_sha256 not in view]
        if missing:
            raise CvError(f"{viewpoints}: no viewpoint for {missing[:5]}")

    assignments: dict[str, dict[str, Any]] = {}
    for item in items:
        if item.split not in pool_splits:
            role, fold, is_scored = "holdout", None, False
        elif item.group in fold_of:
            role, fold, is_scored = "cv_fold", fold_of[item.group], min(item.size) >= val_min_side
        else:
            role, fold, is_scored = "train_all_folds", None, False
        assignments[item.key] = {
            "group": item.group,
            "source_split": item.split,
            "image_sha256": item.image_sha256,
            "role": role,
            "fold": fold,
            "scored": is_scored,
            "labels": sorted(set(item.class_pixels) & set(strat)),
        }

    pixel_totals = {c: sum(i.class_pixels.get(c, 0) for i in scored) for c in strat}
    report_folds = []
    for k in range(folds):
        members = [i for i in pool if assignments[i.key]["fold"] == k]
        val = [i for i in members if assignments[i.key]["scored"]]
        entry: dict[str, Any] = {
            "fold": k,
            "groups": sorted({i.group for i in members}),
            "val_images": len(val),
            "train_images": len(pool) - len(members),
            "excluded_small_images": sorted(i.key for i in members if i not in val),
            "label_images": {c: sum(c in i.class_pixels for i in val) for c in strat},
            "label_pixel_share": {
                c: (sum(i.class_pixels.get(c, 0) for i in val) / pixel_totals[c])
                if pixel_totals[c]
                else None
                for c in strat
            },
        }
        if view is not None:
            entry["viewpoints"] = dict(sorted(Counter(view[i.image_sha256] for i in val).items()))
            entry["label_images_by_viewpoint"] = {
                v: {
                    c: sum(c in i.class_pixels for i in val if view[i.image_sha256] == v)
                    for c in strat
                }
                for v in sorted(set(view[i.image_sha256] for i in pool))
            }
            entry["label_pixel_share_by_viewpoint"] = {
                v: {
                    c: (
                        sum(i.class_pixels.get(c, 0) for i in val if view[i.image_sha256] == v)
                        / total
                    )
                    if (
                        total := sum(
                            i.class_pixels.get(c, 0) for i in scored if view[i.image_sha256] == v
                        )
                    )
                    else None
                    for c in require_classes
                }
                for v in sorted(set(view[i.image_sha256] for i in pool))
            }
        report_folds.append(entry)
    for name in require_classes:
        present = sum(f["label_images"].get(name, 0) > 0 for f in report_folds)
        if present < 2:
            raise CvError(f"required class {name!r} is scored in {present} fold(s); need >= 2")
    label_groups = {c: sorted({i.group for i in scored if c in i.class_pixels}) for c in strat}
    warnings = [
        {
            "label": c,
            "folds_without": [f["fold"] for f in report_folds if not f["label_images"][c]],
            "scored_images": sum(c in i.class_pixels for i in scored),
            "source_groups": len(label_groups[c]),
        }
        for c in strat
        if any(not f["label_images"][c] for f in report_folds)
    ]
    return {
        "scheme": SCHEME,
        "source": source_identity(root),
        "method": {
            "folds": folds,
            "seed": seed,
            "restarts": restarts,
            "pool_splits": list(pool_splits),
            "holdout_splits": list(holdout_splits),
            "anomaly_classes": sorted(anomaly_classes),
            "rare_threshold": rare_threshold,
            "rare_classes": rare,
            "stratification_labels": strat,
            "presence_rule": f"a class is present when its mask has any pixel of it ({ignore_index} ignored)",
            "balance_columns": [*columns, IMAGES_COLUMN],
            "objective": OBJECTIVE,
            "search": "per restart: iterative stratification over whole groups (rarest balance "
            "column first, each group to the fold that most lacks it, ties by image deficit "
            "then seeded RNG), then steepest descent over single-group moves and pairwise "
            "swaps; the best restart is kept",
            "val_min_side": val_min_side,
            "require_classes": list(require_classes),
            "viewpoints": None if viewpoints is None else Path(viewpoints).name,
            "viewpoints_sha256": None if viewpoints is None else sha256_file(Path(viewpoints)),
        },
        "assignments": assignments,
        "report": {
            "pool_images": len(pool),
            "scored_images": len(scored),
            "holdout_images": len(items) - len(pool),
            "pool_groups": len({i.group for i in pool}),
            "cv_groups": len(cv_groups),
            "train_all_folds_groups": sorted({i.group for i in pool} - set(cv_groups)),
            "holdout_groups": sorted({i.group for i in items if i.split not in pool_splits}),
            "small_images_never_scored": sorted(i.key for i in pool if i not in scored),
            "search": search,
            "label_scored_images": {c: sum(c in i.class_pixels for i in scored) for c in strat},
            "label_scored_groups": label_groups,
            "folds": report_folds,
            "label_coverage_warnings": warnings,
        },
    }


def fold_splits(spec: dict[str, Any], fold: int) -> tuple[dict[str, list[str]], list[str]]:
    """``({train, val, test: keys}, excluded keys)`` of one fold of a spec."""
    if spec.get("scheme") != SCHEME:
        raise CvError(f"not a {SCHEME} spec")
    if not 0 <= fold < spec["method"]["folds"]:
        raise CvError(f"fold {fold} outside 0..{spec['method']['folds'] - 1}")
    out: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    excluded: list[str] = []
    for key, row in sorted(spec["assignments"].items()):
        if row["role"] not in ROLES:
            raise CvError(f"{key}: unknown role {row['role']!r}")
        if row["role"] == "holdout":
            out["test"].append(key)
        elif row["role"] == "cv_fold" and row["fold"] == fold:
            (out["val"] if row["scored"] else excluded).append(key)
        else:
            out["train"].append(key)
    by_group: dict[str, set[str]] = {}
    for split, keys in out.items():
        for key in keys:
            by_group.setdefault(spec["assignments"][key]["group"], set()).add(split)
    crossing = sorted(g for g, s in by_group.items() if len(s) > 1)
    if crossing:
        raise CvError(f"fold {fold}: groups in more than one split: {crossing}")
    return out, excluded


def check_source(spec: dict[str, Any], root: Path) -> list[Item]:
    """The spec was made from exactly this dataset (splits, samples and every image hash)."""
    if source_identity(root) != spec["source"]:
        raise CvError(f"{root} is not the dataset this spec was made from")
    items = scan_dataset(root)
    if {i.key: i.image_sha256 for i in items} != {
        k: r["image_sha256"] for k, r in spec["assignments"].items()
    }:
        raise CvError(f"{root}: images differ from the spec")
    return items


def _place(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
        return "hardlinked"
    except OSError:
        shutil.copyfile(source, destination)
        return "copied"


def materialize(root: Path, spec: dict[str, Any], out_root: Path) -> dict[str, Any]:
    """Write ``<out_root>/cv-spec.json`` and one prepared dataset per fold, atomically."""
    if out_root.exists():
        raise CvError(f"output root already exists: {out_root}")
    items = {i.key: i for i in check_source(spec, root)}
    source_splits = json.loads((root / "splits.json").read_text())
    samples_path = root / "audit/samples.json"
    samples = json.loads(samples_path.read_text()) if samples_path.is_file() else None
    out_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out_root.name}.tmp-", dir=out_root.parent))
    placed: Counter[str] = Counter()
    try:
        spec_text = json.dumps(spec, indent=2, sort_keys=True) + "\n"
        (staging / SPEC_NAME).write_text(spec_text)
        spec_sha = hashlib.sha256(spec_text.encode()).hexdigest()
        summary = []
        for k in range(spec["method"]["folds"]):
            view = staging / f"fold-{k}"
            splits, excluded = fold_splits(spec, k)
            for split, keys in splits.items():
                for key in keys:
                    item = items[key]
                    ext = item.image.suffix.lower()
                    placed[_place(item.image, view / "images" / split / f"{key}{ext}")] += 1
                    placed[_place(item.mask, view / "masks" / split / f"{key}.png")] += 1
                    if sha256_file(view / "images" / split / f"{key}{ext}") != item.image_sha256:
                        raise CvError(f"fold {k}: written image differs: {key}")
            manifest: dict[str, Any] = dict(splits)
            manifest["groups"] = {
                key: spec["assignments"][key]["group"] for keys in splits.values() for key in keys
            }
            for name, value in source_splits.items():
                if name.startswith("_"):
                    manifest[f"_source{name}"] = value
            manifest["_grouping_status"] = source_splits.get("_grouping_status")
            manifest["_split_method"] = SCHEME
            manifest["_cv_fold"] = k
            manifest["_cv_folds"] = spec["method"]["folds"]
            manifest["_cv_spec_sha256"] = spec_sha
            manifest["_cv_excluded_small_images"] = excluded
            (view / "splits.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            if (root / "classes.json").is_file():
                shutil.copyfile(root / "classes.json", view / "classes.json")
            if samples is not None:
                split_of = {key: split for split, keys in splits.items() for key in keys}
                rows = [s | {"split": split_of[s["key"]]} for s in samples if s["key"] in split_of]
                (view / "audit").mkdir(exist_ok=True)
                (view / "audit/samples.json").write_text(
                    json.dumps(rows, indent=2, sort_keys=True) + "\n"
                )
            summary.append(
                {"fold": k, **{s: len(v) for s, v in splits.items()}, "excluded": len(excluded)}
            )
            (view / "README.md").write_text(
                f"# {out_root.name} fold {k}\n\nFold {k} of a {SCHEME} cross-validation of "
                f"`{root.name}` (`{SPEC_NAME}` sha256 `{spec_sha[:12]}`): val = this fold's "
                "groups, train = the other pool groups, test = the holdout (never scored). "
                f"Files are hardlinks to `{root}`. Left out of this fold: "
                f"{', '.join(excluded) or 'none'}.\n"
            )
        record = {
            "spec_sha256": spec_sha,
            "source": str(root),
            "files": dict(placed),
            "folds": summary,
        }
        (staging / "materialized.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
        staging.rename(out_root)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return record


def fold_table(spec: dict[str, Any]) -> str:
    """Markdown summary of a spec's folds."""
    report = spec["report"]
    method = spec["method"]
    labels = method["stratification_labels"]
    required = method.get("require_classes") or []
    head = ["fold", "groups", "val images", *labels]
    head += [f"{c} px share" for c in required]
    by_view = bool(report["folds"]) and "label_images_by_viewpoint" in report["folds"][0]
    views = sorted(report["folds"][0]["label_images_by_viewpoint"]) if by_view else []
    head += [f"{v} {c} images" for c in required for v in views]
    head += [f"{v} {c} px share" for c in required for v in views]
    head += ["excluded small"]
    lines = [
        "| " + " | ".join(head) + " |",
        "|---:|---|" + "---:|" * (len(head) - 3) + "---|",
    ]

    def pct(value: float | None) -> str:
        return "—" if value is None else f"{100 * value:.1f}%"

    for f in report["folds"]:
        cells = [str(f["fold"]), ", ".join(f["groups"]), str(f["val_images"])]
        cells += [str(f["label_images"][c]) for c in labels]
        cells += [pct(f["label_pixel_share"][c]) for c in required]
        cells += [str(f["label_images_by_viewpoint"][v][c]) for c in required for v in views]
        cells += [pct(f["label_pixel_share_by_viewpoint"][v][c]) for c in required for v in views]
        cells += [", ".join(f["excluded_small_images"]) or "—"]
        lines.append("| " + " | ".join(cells) + " |")
    warnings = report["label_coverage_warnings"]
    lines += [
        "",
        "Label coverage warnings: "
        + (
            "; ".join(
                f"{w['label']} absent from folds {w['folds_without']} ({w['scored_images']} "
                f"scored images in {w['source_groups']} groups)"
                for w in warnings
            )
            or "none"
        ),
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="segmentary-make-split --scheme stratified-group-kfold",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--scheme", choices=(SCHEME,), required=True)
    p.add_argument("--root", type=Path, required=True, help="prepared grouped folder dataset")
    p.add_argument("--spec", type=Path, help="materialize this existing spec instead of searching")
    p.add_argument("--spec-out", type=Path, help="write the spec here")
    p.add_argument("--out-root", type=Path, help="write cv-spec.json and fold-<k>/ views here")
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--restarts", type=int, default=2000)
    p.add_argument("--anomaly-classes", default="", help="comma-separated class names")
    p.add_argument("--rare-threshold", type=int, default=50)
    p.add_argument("--pool", default="train,val", help="splits divided into folds")
    p.add_argument("--holdout", default="test", help="splits kept out of every fold")
    p.add_argument("--val-min-side", type=int, default=0, help="never score smaller images")
    p.add_argument("--require-class", action="append", default=[], help="must be in >= 2 folds")
    p.add_argument("--viewpoints", type=Path, help="YAML images: {sha256: {viewpoint}} (report)")
    p.add_argument("--ignore-index", type=int, default=255)
    return p


def _split_list(text: str) -> list[str]:
    return [v for v in text.split(",") if v]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.spec_out is None and args.out_root is None:
        parser.error("give --spec-out, --out-root or both")
    try:
        if args.spec is not None:
            spec = json.loads(args.spec.read_text())
        else:
            spec = make_spec(
                args.root,
                folds=args.folds,
                seed=args.seed,
                restarts=args.restarts,
                anomaly_classes=_split_list(args.anomaly_classes),
                rare_threshold=args.rare_threshold,
                pool_splits=_split_list(args.pool),
                holdout_splits=_split_list(args.holdout),
                val_min_side=args.val_min_side,
                require_classes=args.require_class,
                viewpoints=args.viewpoints,
                ignore_index=args.ignore_index,
            )
        if args.spec_out is not None:
            args.spec_out.parent.mkdir(parents=True, exist_ok=True)
            args.spec_out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
        record = materialize(args.root, spec, args.out_root) if args.out_root else None
    except (OSError, CvError) as error:
        parser.error(str(error))
    print(fold_table(spec))
    print(json.dumps(spec["report"]["search"], sort_keys=True))
    if record is not None:
        print(f"wrote {args.out_root}: {json.dumps(record['files'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
