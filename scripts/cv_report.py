#!/usr/bin/env python3
"""Cross-validation report of one RTIS campaign: pooled out-of-fold and per-fold metrics.

    PYTHONPATH=.:src python scripts/cv_report.py --campaign <root> --out <dir> \\
        [--viewpoints configs/datasets/rad_9_24_2026-viewpoints.yaml] \\
        [--focus-class mud-pumping] [--path-map OLD=NEW ...]

The campaign must be planned with a ``cross_validation`` block (jobs
``<model>--<protocol>--fold-<k>--seed-<s>``). For every completed job the PRIMARY result is the
final checkpoint at the full step budget, scored on its fold's held-out val split with the
campaign's auto raw/EMA weights (``collection.diagnostics.results["final-auto-val"]`` and its
per-image confusions); with ``primary_checkpoint: final`` the job must have trained the whole
budget, so nothing is chosen on the held-out fold. The best-on-val checkpoint
(``best-auto-val``) is reported only as a labelled, optimistic secondary.

- Pooled out-of-fold: per model x protocol x seed the per-image confusions of all folds' val
  images are scored together, so each scored image counts once, scored by the model that never
  trained on its group. Complete when every planned fold is.
- Per fold: the same metrics per fold; mean and sample standard deviation over folds (focus
  class metrics only over folds whose subset has focus-class ground truth).
- Subsets: ``all`` plus one per viewpoint when ``--viewpoints`` (YAML ``images: {sha256:
  {viewpoint}}``) is given, joined by image SHA-256.
- Headline metrics count each class only on the images that contain it
  (``segmentary.engine.present_image``): for ``--focus-class`` (default: the spec's first
  required class) the mean per-image IoU over the images with its ground truth (images without
  it are left out, a missed image scores 0) and precision/recall summed over those images only;
  and mIoU = each class's present-image IoU averaged over the classes present in the subset.
- Kept in the CSV for traceability, from the summed (pixel-pooled) confusion: focus-class
  IoU/precision/recall, GT-class mIoU (``publish_rtis_results.fixed_miou``: classes with ground
  truth in the subset) and the campaign mIoU (classes with non-zero union), in columns named
  ``*_pixel_pooled``. Per class the CSV also has the present-image IoU and image count
  (``iou_present_images:<class>``, ``images_present:<class>``).
- Fail closed: fold datasets must match the hashes the campaign recorded, every confusion
  artifact its SHA-256, per-image matrices must cover the fold's val split exactly, sum to the
  recorded total and (when ``class_pixels`` is audited) match each image's ground truth.

Read-only on every input; ``--out`` must lie outside the campaign. Deterministic apart from
the README's ``Generated`` line.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.collect_rtis_statistics import matrix_metrics, mud_counts
from scripts.publish_rtis_results import fixed_miou

from segmentary.engine.present_image import present_image_metrics

PRIMARY = "final-auto-val"
SECONDARY = "best-auto-val"
ANCHOR = {PRIMARY: "final", SECONDARY: "best"}
METRICS = (
    "images",
    "images_with_focus_gt",
    "focus_present_iou",
    "focus_present_precision",
    "focus_present_recall",
    "present_miou",
    "present_miou_classes",
    "focus_gt_pixels",
    "focus_iou",
    "focus_precision",
    "focus_recall",
    "focus_image_mean_iou",
    "gt_class_miou",
    "miou",
)
# CSV column -> metric: present-image headline metrics, then the pixel-pooled ones (the summed
# confusion of the scope's images) under names that say so. ``focus_image_mean_iou`` is an
# independent computation of ``focus_present_iou`` and is not repeated in the CSV.
CSV_METRICS = {
    "images": "images",
    "images_with_focus_gt": "images_with_focus_gt",
    "focus_iou_present_images": "focus_present_iou",
    "focus_precision_present_images": "focus_present_precision",
    "focus_recall_present_images": "focus_present_recall",
    "miou_present_images": "present_miou",
    "miou_present_images_classes": "present_miou_classes",
    "focus_gt_pixels": "focus_gt_pixels",
    "focus_iou_pixel_pooled": "focus_iou",
    "focus_precision_pixel_pooled": "focus_precision",
    "focus_recall_pixel_pooled": "focus_recall",
    "gt_class_miou_pixel_pooled": "gt_class_miou",
    "miou_pixel_pooled": "miou",
}
# Per class: present-image IoU and the number of scored images with it.
CLASS_COLUMNS = (
    ("iou_present_images:{name}", "present_class_iou"),
    ("images_present:{name}", "present_class_images"),
)
CSV_FIELDS = (
    "model",
    "protocol",
    "seed",
    "checkpoint",
    "scope",
    "folds_done",
    "subset",
    *CSV_METRICS,
)
# (title, metric) of the focus class per subset in the summary tables (present-image rule).
FOCUS_HEADLINE = (("{focus} IoU", "focus_present_iou"),)


class CvReportError(ValueError):
    pass


@dataclass(frozen=True)
class Scored:
    key: str
    image_sha256: str
    subset: str | None
    matrix: np.ndarray
    group: str | None = None


@dataclass
class Run:
    model: str
    protocol: str
    seed: int
    fold: int
    job: str
    images: dict[str, list[Scored]]


@dataclass
class Report:
    campaign: dict
    folds: list[int]
    names: list[str]
    focus: str | None
    subsets: list[str]
    runs: list[Run]
    coverage: dict[int, dict[str, int]]
    spec: dict | None
    inputs: dict[str, str] = field(default_factory=dict)
    table_subsets: list[str] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError as error:
        raise CvReportError(f"{path} does not exist") from error


def remap(path: str | Path, maps: list[tuple[str, str]]) -> Path:
    text = str(path)
    for old, new in maps:
        if text == old or text.startswith(old.rstrip("/") + "/"):
            return Path(new.rstrip("/") + text[len(old.rstrip("/")) :])
    return Path(text)


def class_names(fold_root: Path, job_config: Path) -> list[str]:
    if (fold_root / "classes.json").is_file():
        classes = read(fold_root / "classes.json")["classes"]
        return [c["name"] for c in sorted(classes, key=lambda c: c["id"])]
    from segmentary.config import load_experiment
    from segmentary.taxonomy import load_space

    cfg = load_experiment([job_config])
    return list(load_space(cfg.taxonomy_root, cfg.space).names)


def load_confusion(path: Path, n: int) -> dict[str, np.ndarray]:
    raw = path.read_bytes()
    data = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    out = {}
    for key, value in data.items():
        matrix = np.asarray(value, dtype=np.int64)
        if matrix.shape != (n, n) or (matrix < 0).any():
            raise CvReportError(f"{path}: {key} is not a non-negative {n}x{n} confusion matrix")
        out[key] = matrix
    return out


def join(
    matrices: dict[str, np.ndarray],
    samples: list[dict],
    total: np.ndarray,
    viewpoints: dict[str, str] | None,
) -> list[Scored]:
    val = {s["key"]: s for s in samples if s["split"] == "val"}
    missing, extra = sorted(set(val) - set(matrices)), sorted(set(matrices) - set(val))
    if missing or extra:
        raise CvReportError(f"confusions do not cover the fold's val split: {missing} {extra}")
    n = total.shape[0]
    if not np.array_equal(sum(matrices.values(), np.zeros((n, n), np.int64)), total):
        raise CvReportError("per-image confusions do not sum to the recorded total")
    scored = []
    for key in sorted(val):
        sample, matrix = val[key], matrices[key]
        if "class_pixels" in sample:
            expected = np.zeros(n, np.int64)
            for value, count in sample["class_pixels"].items():
                if int(value) < n:
                    expected[int(value)] = int(count)
            if not np.array_equal(matrix.sum(axis=1), expected):
                raise CvReportError(f"{key}: ground-truth rows differ from audited class_pixels")
        subset = None
        if viewpoints is not None:
            subset = viewpoints.get(sample["image_sha256"])
            if subset is None:
                raise CvReportError(f"{key}: image sha256 has no viewpoint")
        scored.append(Scored(key, sample["image_sha256"], subset, matrix, sample.get("group")))
    return scored


def _finite(value: float | None) -> float | None:
    return None if value is None or math.isnan(value) else float(value)


def subset_metrics(images: list[Scored], names: list[str], focus: str | None) -> dict[str, Any]:
    n = len(names)
    out: dict[str, Any] = dict.fromkeys(METRICS)
    out["images"] = len(images)
    out["present_miou_classes"] = 0
    present = present_image_metrics((i.matrix for i in images), n)
    # every class: present-image IoU (None without a present image) and its image count
    out["present_class_iou"] = {c: s.iou for c, s in zip(names, present.classes, strict=True)}
    out["present_class_images"] = {c: s.images for c, s in zip(names, present.classes, strict=True)}
    if not images:
        return out
    total = sum((i.matrix for i in images), np.zeros((n, n), np.int64))
    metrics = matrix_metrics(total, names)
    out.update(
        gt_class_miou=_finite(fixed_miou(metrics)),
        miou=_finite(metrics["miou"]),
        present_miou=present.miou,
        present_miou_classes=present.miou_classes,
    )
    if focus is not None:
        index = names.index(focus)
        with_gt = [i for i in images if i.matrix[index].sum() > 0]
        counts = mud_counts(total, index)
        per_image = [mud_counts(i.matrix, index)["iou"] for i in with_gt]
        score = present.classes[index]
        out.update(
            focus_present_iou=score.iou,
            focus_present_precision=score.precision,
            focus_present_recall=score.recall,
            images_with_focus_gt=len(with_gt),
            focus_gt_pixels=counts["support"],
            focus_iou=counts["iou"],
            focus_precision=counts["precision"],
            focus_recall=counts["recall"],
            focus_image_mean_iou=sum(per_image) / len(per_image) if per_image else None,
        )
    return out


def compute(images: list[Scored], report: Report) -> dict[str, dict[str, Any]]:
    out = {"all": subset_metrics(images, report.names, report.focus)}
    for name in report.subsets:
        members = [i for i in images if i.subset == name]
        out[name] = subset_metrics(members, report.names, report.focus)
    return out


def build(
    root: Path,
    viewpoints_path: Path | None,
    focus: str | None,
    maps: list[tuple[str, str]],
    table_subsets: list[str] | None = None,
) -> Report:
    campaign = read(root / "campaign.json")
    cv = campaign.get("cross_validation")
    if not cv:
        raise CvReportError(f"{root} is not a cross-validation campaign")
    primary = campaign.get("primary_checkpoint", "best")
    spec = None
    spec_path = remap(cv["spec"], maps)
    if spec_path.is_file():
        if sha256_file(spec_path) != cv["spec_sha256"]:
            raise CvReportError(f"{spec_path} differs from the campaign's spec")
        spec = read(spec_path)
    if focus is None and spec is not None and spec["method"].get("require_classes"):
        focus = spec["method"]["require_classes"][0]
    viewpoints = None
    if viewpoints_path is not None:
        images = (yaml.safe_load(viewpoints_path.read_text()) or {}).get("images") or {}
        viewpoints = {str(k): str(v["viewpoint"]) for k, v in images.items()}
    plan = read(root / "plan.json")
    folds = [int(k) for k in cv["fold_datasets"]]
    datasets: dict[int, list[dict]] = {}
    names: list[str] = []
    for key, entry in cv["fold_datasets"].items():
        fold_root = remap(entry["root"], maps)
        if sha256_file(fold_root / "splits.json") != entry["split_sha256"]:
            raise CvReportError(f"{fold_root}/splits.json differs from the campaign's")
        if sha256_file(fold_root / "audit/samples.json") != entry["dataset_audit_sha256"]:
            raise CvReportError(f"{fold_root}/audit/samples.json differs from the campaign's")
        datasets[int(key)] = read(fold_root / "audit/samples.json")
        if not names:
            names = class_names(fold_root, remap(plan["jobs"][0]["config"], maps))
    if focus is not None and focus not in names:
        raise CvReportError(f"focus class {focus!r} is not a class of this campaign")
    subsets = (
        sorted(
            {
                viewpoints[s["image_sha256"]]
                for rows in datasets.values()
                for s in rows
                if s["split"] == "val" and s["image_sha256"] in viewpoints
            }
        )
        if viewpoints is not None
        else []
    )
    report = Report(
        campaign, sorted(folds), names, focus, subsets, [], {k: {} for k in folds}, spec
    )
    unknown = sorted(set(table_subsets or []) - set(subsets))
    if unknown:
        raise CvReportError(f"--subset {unknown} not among the viewpoint subsets {subsets}")
    report.table_subsets = list(table_subsets) if table_subsets else list(subsets)
    for job in sorted(plan["jobs"], key=lambda j: j["name"]):
        state_path = root / "state" / f"{job['name']}.json"
        state = read(state_path) if state_path.is_file() else {}
        status = str(state.get("status", "no state"))
        results = ((state.get("collection") or {}).get("diagnostics") or {}).get("results") or {}
        if status == "completed" and PRIMARY not in results:
            status = f"completed, no {PRIMARY} diagnostics"
        counts = report.coverage[int(job["fold"])]
        counts[status] = counts.get(status, 0) + 1
        if status != "completed":
            continue
        try:
            report.runs.append(
                run_of(
                    job,
                    state,
                    campaign,
                    primary,
                    datasets[int(job["fold"])],
                    viewpoints,
                    maps,
                    len(names),
                )
            )
        except (CvReportError, KeyError, TypeError, OSError) as error:
            raise CvReportError(f"{state_path}: {type(error).__name__}: {error}") from error
    report.inputs = {
        "campaign": str(root),
        "code": str(campaign.get("code_sha", "")),
        "spec": f"sha256 {cv['spec_sha256'][:12]}" + ("" if spec else " (file not found)"),
        "viewpoints": (
            f"{viewpoints_path.name} (sha256 {sha256_file(viewpoints_path)[:12]})"
            if viewpoints_path
            else "none"
        ),
        "primary checkpoint": primary,
    }
    return report


def run_of(
    job: dict,
    state: dict,
    campaign: dict,
    primary: str,
    samples: list[dict],
    viewpoints: dict[str, str] | None,
    maps: list[tuple[str, str]],
    n: int,
) -> Run:
    if primary == "final":
        final = state["checkpoints"]["final"]
        if int(final["global_step"]) != int(campaign["target_steps"]):
            raise CvReportError(f"final checkpoint at step {final['global_step']}, not the budget")
        if (state.get("stopping") or {}).get("reason") != "budget_complete":
            raise CvReportError("training did not run the full budget (selection on the fold)")
    results = state["collection"]["diagnostics"]["results"]
    images = {}
    for variant in (PRIMARY, SECONDARY):
        if variant not in results:
            continue
        result = results[variant]
        if result.get("split") != "val":
            raise CvReportError(f"{variant} is not the val split")
        if result.get("checkpoint_sha256") != state["checkpoints"][ANCHOR[variant]]["sha256"]:
            raise CvReportError(f"{variant} was not scored on the {ANCHOR[variant]} checkpoint")
        total = np.asarray(result["metrics"]["confusion"], dtype=np.int64)
        if variant == SECONDARY and "evaluation" in state:
            evaluated = np.asarray(state["evaluation"]["metrics"]["confusion"], dtype=np.int64)
            if not np.array_equal(evaluated, total):
                raise CvReportError(f"{variant} differs from the standalone evaluation")
        artifact = state["collection"]["artifacts"][variant]["per-image-confusion.json.gz"]
        path = remap(artifact["path"], maps)
        if sha256_file(path) != artifact["sha256"]:
            raise CvReportError(f"{path} differs from the SHA-256 recorded for it")
        images[variant] = join(load_confusion(path, n), samples, total, viewpoints)
    return Run(
        job["model"], job["protocol"], int(job["seed"]), int(job["fold"]), job["name"], images
    )


# ----------------------------------------------------------------------------- aggregation


def groups_of(report: Report) -> dict[tuple[str, str, int], dict[int, Run]]:
    out: dict[tuple[str, str, int], dict[int, Run]] = {}
    for run in report.runs:
        out.setdefault((run.model, run.protocol, run.seed), {})[run.fold] = run
    return out


def pooled(runs: dict[int, Run], variant: str, report: Report) -> dict | None:
    if not runs or any(variant not in r.images for r in runs.values()):
        return None
    images = [i for r in runs.values() for i in r.images[variant]]
    if len({i.key for i in images}) != len(images):
        raise CvReportError("an image is scored in more than one fold")
    return compute(images, report)


def per_fold(runs: dict[int, Run], variant: str, report: Report) -> dict[int, dict]:
    return {
        k: compute(r.images[variant], report)
        for k, r in sorted(runs.items())
        if variant in r.images
    }


def fold_values(folds: dict[int, dict], subset: str, metric: str) -> list[float]:
    values = []
    for m in folds.values():
        cell = m[subset]
        if metric.startswith("focus") and not cell["images_with_focus_gt"]:
            continue
        if cell[metric] is not None:
            values.append(cell[metric])
    return values


def pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}"


def mean_std(values: list[float]) -> str:
    if not values:
        return "—"
    if len(values) == 1:
        return f"{100 * values[0]:.1f} (n=1)"
    mean, sd = 100 * statistics.fmean(values), 100 * statistics.stdev(values)
    return f"{mean:.1f} (SD {sd:.1f}, n={len(values)})"


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" if i < 3 else "---:" for i in range(len(headers))) + "|",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def focus_images(report: Report, subset: str = "all") -> dict[int, list[Scored]]:
    """Per fold, the scored images of ``subset`` with focus-class ground truth: a label-only
    fact, the same for every model (taken from whichever completed runs scored the fold)."""
    if report.focus is None:
        return {}
    index = report.names.index(report.focus)
    found: dict[int, dict[str, Scored]] = {}
    for run in report.runs:
        for image in run.images.get(PRIMARY, []):
            if (subset == "all" or image.subset == subset) and image.matrix[index].sum() > 0:
                found.setdefault(run.fold, {})[image.key] = image
    return {fold: list(images.values()) for fold, images in sorted(found.items())}


def headline(report: Report) -> list[tuple[str, str, str]]:
    """(title, subset, metric) columns of the summary tables."""
    cols = [("mIoU", "all", "present_miou")]
    if report.focus is not None:
        for subset in ["all", *report.table_subsets]:
            for title, metric in FOCUS_HEADLINE:
                cols.append((f"{title.format(focus=report.focus)} {subset}", subset, metric))
    return cols


def summary(report: Report, variant: str) -> list[str]:
    cols = headline(report)

    def pooled_title(title: str, subset: str, metric: str) -> str:
        if not metric.startswith("focus"):
            return f"pooled {title}"
        n = sum(len(images) for images in focus_images(report, subset).values())
        return f"pooled {title} (n={n})"  # scored images with focus-class ground truth

    headers = ["model", "protocol", "seed", "folds"]
    headers += [pooled_title(*c) for c in cols] + [f"per-fold {t}" for t, _, _ in cols]
    rows = []
    for (model, protocol, seed), runs in sorted(groups_of(report).items()):
        pool = pooled(runs, variant, report)
        folds = per_fold(runs, variant, report)
        mark = "" if set(runs) == set(report.folds) else "*"
        rows.append(
            [model, protocol, str(seed), f"{len(runs)}/{len(report.folds)}"]
            + [(pct(pool[s][m]) + mark) if pool else "—" for _, s, m in cols]
            + [mean_std(fold_values(folds, s, m)) for _, s, m in cols]
        )
    return table(headers, rows) if rows else ["No completed job yet."]


def csv_cell(value: Any) -> Any:
    return "" if value is None else f"{value:.6f}" if isinstance(value, float) else value


def csv_fields(names: list[str]) -> list[str]:
    """The CSV header: CSV_FIELDS, then per class its present-image IoU and image count."""
    return [*CSV_FIELDS, *(c.format(name=n) for n in names for c, _ in CLASS_COLUMNS)]


def csv_text(report: Report) -> str:
    buffer = io.StringIO()
    fields = csv_fields(report.names)
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for (model, protocol, seed), runs in sorted(groups_of(report).items()):
        for variant in (PRIMARY, SECONDARY):
            scopes: list[tuple[str, dict | None]] = [("pooled", pooled(runs, variant, report))]
            scopes += [(f"fold-{k}", m) for k, m in per_fold(runs, variant, report).items()]
            for scope, metrics in scopes:
                for subset, values in (metrics or {}).items():
                    writer.writerow(
                        {
                            "model": model,
                            "protocol": protocol,
                            "seed": seed,
                            "checkpoint": ANCHOR[variant],
                            "scope": scope,
                            "folds_done": len(runs),
                            "subset": subset,
                            **{
                                column: csv_cell(values[key]) for column, key in CSV_METRICS.items()
                            },
                            **{
                                column.format(name=n): csv_cell(values[key][n])
                                for n in report.names
                                for column, key in CLASS_COLUMNS
                            },
                        }
                    )
    return buffer.getvalue()


def render(report: Report, generated_at: str) -> str:
    from segmentary.data.group_cv import fold_table

    k = len(report.campaign["cross_validation"]["fold_datasets"])
    lines = [
        f"# Cross-validation report: {report.campaign['dataset']}",
        "",
        f"Generated: {generated_at}",
        "",
        "## How to read this",
        "",
        f"- {k} folds of whole groups; each job trains on the other folds and scores its own "
        "val fold. The holdout (test) is never trained on or scored.",
        f"- **Primary = `{PRIMARY}`** (final checkpoint, full step budget, no early stopping): "
        "nothing is chosen on the held-out fold. The best-on-val checkpoint "
        f"(`{SECONDARY}`) is selected on the fold it is scored on and appears only in the "
        "secondary table.",
        "- **Pooled** scores every fold's val images together, so each scored image counts "
        "once; `*` marks a model whose folds are not all done (not comparable). "
        "**Per-fold** is the mean over folds with the sample SD and n folds; focus-class metrics only over folds "
        "whose subset has focus-class ground truth.",
        "- Every metric counts a class only on the images that contain it: the focus-class IoU "
        "is the mean of per-image IoU over the images with its ground truth (images without it "
        "are not counted, so false positives on them do not lower it; a missed image scores 0), "
        "and mIoU averages each class's IoU over the images that contain it, then over the "
        "classes present in the subset. The pixel-pooled metrics (confusions summed first, so "
        "images with large "
        "areas of a class dominate) are in the CSV as `*_pixel_pooled`.",
        "- One seed per job unless several seeds are listed: the per-fold spread mixes model "
        "variance with very different fold compositions (see below).",
        "",
        "## Primary: final checkpoint",
        "",
        "Percent.",
        "",
        *summary(report, PRIMARY),
        "",
        "## Secondary (optimistic): best-on-val checkpoint",
        "",
        "Selected on the same fold it is scored on; shown only to size that bias.",
        "",
        *summary(report, SECONDARY),
        "",
        "## Coverage",
        "",
        *table(
            ["fold", "completed", "not completed (status count)", "jobs"],
            [
                [
                    str(f),
                    str(c.get("completed", 0)),
                    ", ".join(f"{s} {n}" for s, n in sorted(c.items()) if s != "completed") or "—",
                    str(sum(c.values())),
                ]
                for f, c in sorted(report.coverage.items())
            ],
        ),
        "",
    ]
    if report.spec is not None:
        lines += ["## Fold composition (labels only)", "", fold_table(report.spec), ""]
    lines += ["## Inputs", "", *(f"- {k}: `{v}`" for k, v in report.inputs.items()), ""]
    lines += ["Every metric, subset, fold and checkpoint is in `cv-report.csv`.", ""]
    return "\n".join(lines)


def parse_map(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("--path-map needs OLD=NEW")
    old, new = text.split("=", 1)
    return old, new


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--campaign", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--viewpoints", type=Path)
    p.add_argument("--focus-class")
    p.add_argument(
        "--subset", action="append", help="viewpoint subset shown in the README (default: all)"
    )
    p.add_argument("--path-map", type=parse_map, action="append", default=[])
    args = p.parse_args(argv)
    out, root = args.out.resolve(), args.campaign.resolve()
    if out == root or root in out.parents:
        raise SystemExit(f"cv_report: --out {out} lies inside the campaign {root}")
    try:
        report = build(root, args.viewpoints, args.focus_class, args.path_map, args.subset)
        csv_body = csv_text(report)
        readme = render(report, datetime.now(UTC).replace(microsecond=0).isoformat())
    except CvReportError as error:
        raise SystemExit(f"cv_report: {error}") from error
    out.mkdir(parents=True, exist_ok=True)
    (out / "cv-report.csv").write_text(csv_body)
    (out / "README.md").write_text(readme)
    done = sum(c.get("completed", 0) for c in report.coverage.values())
    total = sum(sum(c.values()) for c in report.coverage.values())
    print(f"cv_report: {done}/{total} jobs completed; wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
