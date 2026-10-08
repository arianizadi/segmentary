#!/usr/bin/env python3
"""RAD 9/24 comparison report: subset metrics of every completed run, validation split only.

    PYTHONPATH=.:src python scripts/rad_report.py --out <dir> \\
        [--campaign <root> ...] [--fork-runs <dir>] [--datasets-root <dir>] \\
        [--viewpoints configs/datasets/rad_9_24_2026-viewpoints.yaml] [--path-map OLD=NEW ...]

Scans the Segmentary campaign roots of the two arms, ``paul`` and ``fixed-grouped`` (defaults:
the HDRFS ``*-seed0-20261005-r2`` campaigns) and the Paul-fork run directory, computes ``scripts/rad_subset_metrics.py``
subsets for every completed job and writes ``<out>/rad-comparison.csv`` and
``<out>/README.md``. Read-only on every input; ``--out`` must lie outside the campaign and
fork roots.

The README's headline metrics count each class only on the images that contain it (mud IoU =
mean per-image mud IoU over the images with mud ground truth; mud precision/recall over those
images; mIoU over each class's images, then over the classes present; see
``segmentary.engine.present_image``). The CSV carries those plus the pixel-pooled metrics of
the summed confusion, in columns named ``*_pixel_pooled``, and per class the present-image IoU
and image count (``iou_present_images:<class>``, ``images_present:<class>``).

- Segmentary job: completed when ``state/<job>.json`` has ``status: completed`` and the
  diagnostics of the campaign's primary checkpoint with its auto raw/EMA weights on the
  validation split (``collection.diagnostics.results[...]``). That is ``best-auto-val`` (the
  checkpoint selected on validation) unless the campaign records ``primary_checkpoint: final``
  (``campaign.json``; ``plan.json`` must agree), whose result is ``final-auto-val``: the final
  checkpoint, accepted only when the job trained the whole ``target_steps`` budget (final
  checkpoint at that step, stopping reason ``budget_complete``, the result scored on the
  recorded final checkpoint), so nothing was selected on the validation images, as in
  ``scripts/cv_report.py``. The ``per-image-confusion.json.gz`` must match the SHA-256 the
  collector recorded and sum to the run's reported total (``evaluation.metrics.confusion`` for
  best, which must equal the diagnostics confusion; the ``final-auto-val`` confusion for final).
  The CSV's ``checkpoint`` column says which (``best`` / ``final``; fork runs ``best``, their
  ``best_mud_epoch``), the README's headline says it per arm.
- Fork run: completed when ``<run>/results-val.json`` (``score_predictions.py``, split val,
  whole-image single-scale) and its ``results-val-per-image-confusion.json.gz`` exist; runs
  with a probe, dry-run or pins override are excluded. Test results are never read.
- Each arm's ``audit/samples.json`` must be the one the campaign (``dataset_audit_sha256``) or
  the fork result (``arm_root.samples_sha256``) recorded.

``--path-map OLD=NEW`` rewrites absolute artifact paths recorded in the state files, so a
local copy of the needed files can be scanned. Output is deterministic apart from the single
``Generated`` line of the README.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import rad_subset_metrics as subsets

ARMS = ("paul", "fixed-grouped")
SHORT = {"paul": "P", "fixed-grouped": "FG"}
# Why the study has no arm with our labels on the stratified split (shown in the report).
LABEL_ARM_STOPPED = (
    "A third arm with our re-rendered masks on the stratified split was stopped on 2026-10-05 "
    "at 8 of 40 jobs: over 8 matched eomt runs the label fix changed cab-view mud IoU on "
    "stratified val by -3.3 to +4.7 points, -0.1 on average."
)
# The same, naming the metric it was measured with now that the headline metrics count only
# images with mud (LABEL_ARM_STOPPED stays as it was for scripts/make_rad_mud_case.py).
LABEL_ARM_STOPPED_POOLED = LABEL_ARM_STOPPED.replace(
    "cab-view mud IoU", "cab-view mud IoU (pixels pooled)"
)
DATASET = "rad_9_24_2026-{arm}"
# A campaign's primary checkpoint (``primary_checkpoint``, default best) -> the diagnostics
# result scored on it (auto raw/EMA weights, validation split).
BEST, FINAL = subsets.BEST, subsets.FINAL
VARIANT = subsets.VARIANTS
SELECTED = BEST  # the primary result of campaigns that record no primary_checkpoint
SPLIT = "val"
RUNS = Path("/data/izadia1/projects/segmentary-runs")
DEFAULT_CAMPAIGNS = tuple(RUNS / "rad_9_24_2026" / f"{arm}-seed0-20261005-r2" for arm in ARMS)
DEFAULT_FORK_RUNS = RUNS / "paul-fork-rad-9-24" / "runs"
DEFAULT_DATASETS = Path("/data/izadia1/datasets")
DEFAULT_VIEWPOINTS = (
    Path(__file__).resolve().parents[1] / "configs/datasets/rad_9_24_2026-viewpoints.yaml"
)
CAB = "cab-view"
EXCL = f"excl-{subsets.EXCLUDED_GROUP}"
# CSV column -> subset metric. Headline: present-image metrics (each class only on the images
# that contain it); the pixel-pooled columns (one summed confusion per subset) stay for
# traceability under names that say so.
CSV_METRICS = {
    "images": "images",
    "images_with_mud_gt": "images_with_mud_gt",
    "mud_iou_present_images": "mud_present_iou",
    "mud_precision_present_images": "mud_present_precision",
    "mud_recall_present_images": "mud_present_recall",
    "miou_present_images": "present_miou",
    "miou_present_images_classes": "present_miou_classes",
    "mud_gt_pixels": "mud_gt_pixels",
    "mud_iou_pixel_pooled": "mud_iou",
    "mud_precision_pixel_pooled": "mud_precision",
    "mud_recall_pixel_pooled": "mud_recall",
    "gt_class_miou_pixel_pooled": "gt_class_miou",
    "miou_pixel_pooled": "miou",
    "top5_mud_share": "top5_mud_share",
}
# Per class (every class of the arm): present-image IoU and the number of images with it.
CLASS_COLUMNS = (
    ("iou_present_images:{name}", "present_class_iou"),
    ("images_present:{name}", "present_class_images"),
)
CSV_FIELDS = (
    "source",
    "arm",
    "model",
    "protocol",
    "label",
    "checkpoint_owners",
    "job",
    "checkpoint",
    "subset",
    *CSV_METRICS,
)
FORK_SKIP_FLAGS = ("dry_run", "probe_epochs", "pins_override")
NO_DIAGNOSTICS = "completed, no {variant} diagnostics"
# Visual remarks on scene groups that decide a subset, shown when that group does.
GROUP_NOTES = {
    "rural-overcast-cab-view": (
        "a forward view centred on the track from a moving vehicle, but from a camera visibly "
        "lower than a locomotive cab (the ballast fills the lower frame; more like a "
        "front-bumper or draisine mount)"
    ),
}


class ReportError(ValueError):
    pass


@dataclass
class Result:
    source: str  # "segmentary" or "fork"
    arm: str
    job: str
    model: str = ""
    protocol: str = ""
    label: str = ""
    owners: str = ""
    selection: str = ""
    seed: str = ""
    checkpoint: str = "best"  # "best" (selected on validation) or "final" (full budget)
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class Coverage:
    source: str
    arm: str
    job: str
    status: str


@dataclass
class Report:
    results: list[Result]
    coverage: list[Coverage]
    composition: dict[str, dict[str, Any]]
    inputs: dict[str, str]
    missing_arms: list[str] = field(default_factory=list)
    # The primary checkpoint ("best" / "final") of each scanned campaign, by arm.
    checkpoints: dict[str, str] = field(default_factory=dict)


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
        raise ReportError(f"{path} does not exist") from error


def why(error: Exception) -> str:
    """A failure message; unexpected errors keep their type (e.g. a missing record key)."""
    if isinstance(error, (ReportError, subsets.SubsetError)):
        return str(error)
    return f"{type(error).__name__}: {error}"


def remap(path: str | Path, maps: list[tuple[str, str]]) -> Path:
    text = str(path)
    for old, new in maps:
        if text == old or text.startswith(old.rstrip("/") + "/"):
            return Path(new.rstrip("/") + text[len(old.rstrip("/")) :])
    return Path(text)


class Arms:
    """Each arm's audit samples and class names, loaded once and pinned by SHA-256."""

    def __init__(self, root: Path):
        self.root = root
        self.cache: dict[str, tuple[list[dict], list[str], str]] = {}

    def get(self, arm: str) -> tuple[list[dict], list[str], str]:
        if arm not in self.cache:
            base = self.root / DATASET.format(arm=arm)
            samples_path = base / "audit/samples.json"
            classes = base / "classes.json"
            names = subsets.class_names(classes if classes.is_file() else None)
            self.cache[arm] = (read(samples_path), names, sha256_file(samples_path))
        return self.cache[arm]


def composition(arms: Arms, viewpoints: dict) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Label-only facts about each arm's validation split, independent of any model; and the
    arms whose prepared dataset is missing (reported, never silently dropped)."""
    out, missing = {}, []
    for arm in ARMS:
        try:
            samples, names, _ = arms.get(arm)
        except ReportError:
            missing.append(arm)
            continue
        mud = str(names.index(subsets.MUD))
        rows = [s for s in samples if s["split"] == SPLIT]
        train = [s for s in samples if s["split"] == "train"]
        train_groups = {s["group"] for s in train}
        total = sum(int(s["class_pixels"].get(mud, 0)) for s in rows)
        per: dict[str, dict[str, int]] = {
            v: {"images": 0, "with_mud": 0, "mud_pixels": 0} for v in subsets.VIEWPOINTS
        }
        group_pixels, group_with_mud = 0, 0
        cab_groups: dict[str, int] = {}
        for s in rows:
            entry = viewpoints.get(s["image_sha256"])
            if entry is None:
                raise ReportError(f"{arm} {s['key']}: image sha256 has no viewpoint")
            pixels = int(s["class_pixels"].get(mud, 0))
            per[entry["viewpoint"]]["images"] += 1
            per[entry["viewpoint"]]["with_mud"] += bool(pixels)
            per[entry["viewpoint"]]["mud_pixels"] += pixels
            if s["group"] == subsets.EXCLUDED_GROUP:
                group_pixels += pixels
                group_with_mud += bool(pixels)
            if pixels and entry["viewpoint"] == CAB:
                cab_groups[s["group"]] = cab_groups.get(s["group"], 0) + 1
        top = sorted(rows, key=lambda s: (-int(s["class_pixels"].get(mud, 0)), s["key"]))
        top = top[: subsets.TOP_K]
        out[arm] = {
            "images": len(rows),
            "mud_pixels": total,
            "viewpoints": per,
            "group_mud_share": group_pixels / total if total else None,
            "group_images_with_mud": group_with_mud,
            "cab_mud_groups": dict(sorted(cab_groups.items(), key=lambda kv: (-kv[1], kv[0]))),
            "val_groups": len({s["group"] for s in rows}),
            "val_groups_in_train": len({s["group"] for s in rows} & train_groups),
            "val_images": frozenset((s["key"], s["image_sha256"]) for s in rows),
            "train_images": frozenset((s["key"], s["image_sha256"]) for s in train),
            "top5": [
                {
                    "key": s["key"],
                    "viewpoint": viewpoints[s["image_sha256"]]["viewpoint"],
                    "mud_pixels": int(s["class_pixels"].get(mud, 0)),
                }
                for s in top
            ],
        }
    return out, missing


def primary_checkpoint(campaign: dict, plan: dict, root: Path) -> str:
    """``best`` or ``final``: the campaign's ``primary_checkpoint`` (default best, as for the
    campaigns planned before the key existed); a plan that records one must agree."""
    primary = campaign.get("primary_checkpoint", plan.get("primary_checkpoint", "best"))
    if plan.get("primary_checkpoint", primary) != primary:
        raise ReportError(f"{root}: campaign.json and plan.json disagree on primary_checkpoint")
    if primary not in VARIANT:
        raise ReportError(f"{root}: primary_checkpoint {primary!r} is not one of {list(VARIANT)}")
    return str(primary)


def campaign_checkpoint(root: Path) -> str:
    """The primary checkpoint of the campaign at ``root`` (``best`` / ``final``)."""
    return primary_checkpoint(read(root / "campaign.json"), read(root / "plan.json"), root)


def scan_campaign(
    root: Path, arms: Arms, viewpoints: dict, maps: list[tuple[str, str]]
) -> tuple[str, list[Result], list[Coverage]]:
    campaign = read(root / "campaign.json")
    arm = str(campaign.get("dataset", "")).removeprefix("rad_9_24_2026-")
    if arm not in ARMS:
        raise ReportError(f"{root}: dataset {campaign.get('dataset')!r} is not a RAD 9/24 arm")
    samples, names, samples_sha = arms.get(arm)
    if samples_sha != campaign.get("dataset_audit_sha256"):
        raise ReportError(f"{root}: {arm} audit/samples.json differs from the campaign's")
    plan = read(root / "plan.json")
    primary = primary_checkpoint(campaign, plan, root)
    variant = VARIANT[primary]
    results, coverage = [], []
    for job in sorted(plan["jobs"], key=lambda j: j["name"]):
        state_path = root / "state" / f"{job['name']}.json"
        state = read(state_path) if state_path.is_file() else {}
        status = str(state.get("status", "no state"))
        diagnostics = ((state.get("collection") or {}).get("diagnostics") or {}).get("results")
        selected = (diagnostics or {}).get(variant)
        if status == "completed" and not selected:
            status = NO_DIAGNOSTICS.format(variant=variant)
        if status != "completed":
            coverage.append(Coverage("segmentary", arm, job["name"], status))
            continue
        try:
            results.append(
                campaign_result(
                    state, selected, arm, job, samples, names, viewpoints, maps, campaign, primary
                )
            )
        except (
            ReportError,
            subsets.SubsetError,
            KeyError,
            TypeError,
            ValueError,
            OSError,
        ) as error:
            raise ReportError(f"{state_path}: {why(error)}") from error
        coverage.append(Coverage("segmentary", arm, job["name"], "completed"))
    return arm, results, coverage


def campaign_result(
    state: dict,
    selected: dict,
    arm: str,
    job: dict,
    samples: list[dict],
    names: list[str],
    viewpoints: dict,
    maps: list[tuple[str, str]],
    campaign: dict | None = None,
    primary: str = "best",
) -> Result:
    variant = VARIANT[primary]
    if selected.get("split") != SPLIT:
        raise ReportError(f"{variant} is not the {SPLIT} split")
    if primary == "final":
        # As scripts/cv_report.py: the final checkpoint at the full step budget, with no early
        # stop, so nothing was chosen on the validation images it is scored on.
        final = state["checkpoints"]["final"]
        if int(final["global_step"]) != int((campaign or {})["target_steps"]):
            raise ReportError(f"final checkpoint at step {final['global_step']}, not the budget")
        if (state.get("stopping") or {}).get("reason") != "budget_complete":
            raise ReportError("training did not run the full budget (selection on validation)")
        if selected.get("checkpoint_sha256") != final["sha256"]:
            raise ReportError(f"{variant} was not scored on the final checkpoint")
    artifact = state["collection"]["artifacts"][variant]["per-image-confusion.json.gz"]
    path = remap(artifact["path"], maps)
    if sha256_file(path) != artifact["sha256"]:
        raise ReportError(f"{path} differs from the SHA-256 recorded for it")
    total = subsets.reported_total(state, variant)
    if not np.array_equal(total, np.asarray(selected["metrics"]["confusion"])):
        raise ReportError(f"{variant} confusion differs from the evaluation")
    train = ((state.get("training") or {}).get("config") or {}).get("train") or {}
    monitor = train.get("selection_metric") or (state.get("stopping") or {}).get("monitor")
    seed = (state.get("training") or {}).get("seed", train.get("seed"))
    return Result(
        "segmentary",
        arm,
        job["name"],
        model=job["model"],
        protocol=job["protocol"],
        selection=str(monitor or "unrecorded"),
        seed="" if seed is None else str(seed),
        checkpoint=primary,
        metrics=subsets.run_subsets(path, total, samples, viewpoints, SPLIT, names),
    )


def owners_text(owners: dict[str, str]) -> str:
    return " -> ".join(f"{stage}:{owner}" for stage, owner in owners.items())


def scan_forks(
    runs: Path, arms: Arms, viewpoints: dict, maps: list[tuple[str, str]]
) -> tuple[list[Result], list[Coverage]]:
    from scripts.paul_forks.score_predictions import ScoreError, parse_label

    results, coverage = [], []
    if not runs.is_dir():
        return results, coverage
    for run in sorted(p for p in runs.iterdir() if (p / "provenance.json").is_file()):
        provenance = read(run / "provenance.json")
        label = str(provenance.get("label", ""))
        try:
            _, arm, _ = parse_label(label)
        except ScoreError:
            coverage.append(Coverage("fork", "?", run.name, f"not a RAD-stage label {label!r}"))
            continue
        flags = [flag for flag in FORK_SKIP_FLAGS if provenance.get(flag)]
        if flags:
            coverage.append(Coverage("fork", arm, run.name, f"excluded ({', '.join(flags)})"))
            continue
        result_path = run / "results-val.json"
        if not result_path.is_file():
            launcher = run / "gpu-assignment.json"
            record = read(launcher) if launcher.is_file() else {}
            status = str(record.get("status", "no launcher record"))
            if record.get("status") == "exited":
                status = f"exited {record.get('exit_code')}, val not scored"
            coverage.append(Coverage("fork", arm, run.name, status))
            continue
        scored = read(result_path)
        if not scored.get("per_image_confusion"):
            coverage.append(
                Coverage("fork", arm, run.name, "scored without per-image confusion; rescore")
            )
            continue
        try:
            results.append(fork_result(scored, provenance, arm, run, arms, viewpoints, maps))
        except (ReportError, subsets.SubsetError, KeyError, TypeError, OSError) as error:
            raise ReportError(f"{result_path}: {why(error)}") from error
        coverage.append(Coverage("fork", arm, run.name, "completed"))
    return results, coverage


def fork_result(
    scored: dict,
    provenance: dict,
    arm: str,
    run: Path,
    arms: Arms,
    viewpoints: dict,
    maps: list[tuple[str, str]],
) -> Result:
    label = str(provenance["label"])
    if scored.get("split") != SPLIT or scored.get("label") != label:
        raise ReportError(f"not the {SPLIT} result of {label}")
    if scored.get("inference") != "whole-image single-scale":
        raise ReportError("not a whole-image single-scale result")
    record = scored["per_image_confusion"]
    samples, names, samples_sha = arms.get(arm)
    if (scored.get("arm_root") or {}).get("samples_sha256") != samples_sha:
        raise ReportError(f"{arm} audit/samples.json changed since scoring")
    path = remap(record["path"], maps)
    if sha256_file(path) != record["sha256"]:
        raise ReportError(f"{path} differs from the SHA-256 recorded for it")
    return Result(
        "fork",
        arm,
        run.name,
        label=label,
        owners=owners_text(provenance["owner_of_each_checkpoint_in_chain"]),
        selection="best_mud_epoch (val mud IoU, Paul's protocol)",
        metrics=subsets.run_subsets(
            path, subsets.reported_total(scored), samples, viewpoints, SPLIT, names
        ),
    )


def build(
    campaigns: list[Path],
    fork_runs: Path | None,
    datasets: Path,
    viewpoints_path: Path,
    maps: list[tuple[str, str]],
) -> Report:
    viewpoints = subsets.load_viewpoints(viewpoints_path)
    arms = Arms(datasets)
    results, coverage = [], []
    seen: dict[str, Path] = {}
    checkpoints: dict[str, str] = {}
    for root in campaigns:
        arm, found, covered = scan_campaign(root, arms, viewpoints, maps)
        if arm in seen:
            raise ReportError(f"{root} and {seen[arm]} are both the {arm} arm")
        seen[arm] = root
        checkpoints[arm] = campaign_checkpoint(root)
        results += found
        coverage += covered
    if fork_runs is not None:
        found, covered = scan_forks(fork_runs, arms, viewpoints, maps)
        results += found
        coverage += covered
    inputs = {
        "viewpoints": f"{viewpoints_path.name} (sha256 {sha256_file(viewpoints_path)[:12]})",
        **{f"campaign {arm}": str(root) for arm, root in sorted(seen.items())},
        "fork runs": str(fork_runs) if fork_runs is not None else "not scanned",
        **{
            f"samples {arm}": f"sha256 {arms.cache[arm][2][:12]}"
            for arm in ARMS
            if arm in arms.cache
        },
    }
    composed, missing = composition(arms, viewpoints)
    for arm in missing:
        inputs[f"samples {arm}"] = f"not found under {datasets}"
    return Report(results, coverage, composed, inputs, missing, checkpoints)


# ----------------------------------------------------------------------------- rendering


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def class_names_of(report: Report) -> list[str]:
    """The classes of the scored runs, in class-id order (the same 21 for every arm)."""
    names: list[str] = []
    for r in report.results:
        for name in r.metrics["all"]["present_class_iou"]:
            if name not in names:
                names.append(name)
    return names


def csv_fields(names: list[str]) -> list[str]:
    return [*CSV_FIELDS, *(c.format(name=n) for n in names for c, _ in CLASS_COLUMNS)]


def csv_text(report: Report) -> str:
    buffer = io.StringIO()
    names = class_names_of(report)
    writer = csv.DictWriter(buffer, fieldnames=csv_fields(names), lineterminator="\n")
    writer.writeheader()
    for r in sorted(report.results, key=lambda r: (r.source, r.arm, r.model, r.protocol, r.job)):
        for subset in subsets.SUBSETS:
            m = r.metrics[subset]
            writer.writerow(
                {
                    "source": r.source,
                    "arm": r.arm,
                    "model": r.model,
                    "protocol": r.protocol,
                    "label": r.label,
                    "checkpoint_owners": r.owners,
                    "job": r.job,
                    "checkpoint": r.checkpoint,
                    "subset": subset,
                    **{column: fmt(m[key]) for column, key in CSV_METRICS.items()},
                    **{
                        column.format(name=n): fmt(m[key].get(n))
                        for n in names
                        for column, key in CLASS_COLUMNS
                    },
                }
            )
    return buffer.getvalue()


def pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}"


def delta(a: float | None, b: float | None) -> str:
    return "—" if a is None or b is None else f"{100 * (b - a):+.1f}"


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" if i < 2 else "---:" for i in range(len(headers))) + "|",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


# (title, subset, metric): present-image metrics, see How to read this.
HEADLINE = (
    ("mIoU", "all", "present_miou"),
    ("mud IoU", "all", "mud_present_iou"),
    ("mud IoU cab", CAB, "mud_present_iou"),
    ("mud precision cab", CAB, "mud_present_precision"),
    ("mud recall cab", CAB, "mud_present_recall"),
)


def keyed(results: list[Result], source: str, key) -> dict[tuple, dict[str, Result]]:
    out: dict[tuple, dict[str, Result]] = {}
    for r in results:
        if r.source == source:
            out.setdefault(key(r), {})[r.arm] = r
    return out


def metric(result: Result | None, subset: str, name: str) -> float | None:
    return None if result is None else result.metrics[subset][name]


def share(part: int, whole: int) -> str:
    return pct(part / whole) if whole else "—"


CHECKPOINT_TEXT = {
    "best": "selected on validation",
    "final": "final checkpoint after the full step budget",
}


def arm_names(arms: list[str]) -> str:
    return " and ".join(f"`{arm}` ({SHORT[arm]})" for arm in arms)


def finals_of(report: Report) -> list[str]:
    """The arms whose campaign reports the final checkpoint."""
    return [arm for arm in ARMS if report.checkpoints.get(arm) == "final"]


def checkpoint_sentence(report: Report) -> str:
    """Which checkpoint the headline reports, per arm."""
    if not finals_of(report):
        return f"Selected checkpoint `{SELECTED}`."
    return (
        "Checkpoint: "
        + ", ".join(
            f"{SHORT[arm]} `{VARIANT[report.checkpoints[arm]]}` "
            f"({CHECKPOINT_TEXT[report.checkpoints[arm]]})"
            for arm in ARMS
            if arm in report.checkpoints
        )
        + "."
    )


def optimism_caveat(report: Report, selections: list[str]) -> str:
    """The caveat on checkpoints chosen on the reported val split. A final-checkpoint campaign
    selects nothing on it, so the caveat names only the arms (and fork runs) that do."""
    selection = (
        f" (campaign selection and early stopping on `{'`, `'.join(selections)}`, "
        "with pixels pooled over the whole split)"
        if selections
        else ""
    )
    forks = "fork runs report their `best_mud_epoch` checkpoint, also chosen on this val split. "
    finals = finals_of(report)
    if not finals:
        return (
            "- **These val numbers are optimistic.** The reported checkpoint is the one selected "
            f"on this same val split{selection}; {forks}"
            "They are not held-out estimates, mud IoU least of all."
        )
    best = [arm for arm in ARMS if report.checkpoints.get(arm, "best") == "best"]
    final = (
        f"{arm_names(finals)} {'reports' if len(finals) == 1 else 'report'} the final checkpoint "
        f"(`{FINAL}`) after the full step budget, with no early stopping, so nothing is selected "
        "on its val images; it is still one val split, not a cross-validated estimate."
    )
    if best:
        return (
            "- **Best-checkpoint val numbers are optimistic.** For "
            f"{arm_names(best)} the reported checkpoint is the one selected on this same val "
            f"split{selection}; {forks}They are not held-out estimates, mud IoU least of all. "
            + final
        )
    return (
        "- **Fork numbers are optimistic.** Fork runs report their `best_mud_epoch` checkpoint, "
        "chosen on this val split, so they are not held-out estimates. " + final
    )


def how_to_read(report: Report) -> list[str]:
    comp = report.composition
    stratified, grouped = (comp.get(a) for a in ARMS)
    # Only best-checkpoint campaigns select on validation; a final checkpoint selects nothing.
    selections = sorted(
        {r.selection for r in report.results if r.source == "segmentary" and r.checkpoint == "best"}
    )
    seeds = sorted({r.seed for r in report.results if r.source == "segmentary"})
    lines = [
        "## How to read this",
        "",
        "All numbers are on the validation split"
        + (
            " (" + ", ".join(f"{a} {c['images']}" for a, c in comp.items()) + " images)"
            if comp
            else ""
        )
        + "; the test split is never read. Every metric counts a class only on the images "
        "that contain it. Mud IoU is the mean of per-image mud IoU over the images with mud "
        "ground truth: images without mud are not counted, so mud predicted on clean track does "
        "not lower it, and a mud image with no mud predicted scores 0. Mud precision and recall "
        "sum mud pixels over those same images only. mIoU averages each class's IoU over the "
        "images that contain it, then over the classes present in the subset. `n=` in a column "
        "header is the number of val images with mud GT behind that arm's mud metrics. The "
        "pixel-pooled numbers (confusions summed over the subset first, as used for checkpoint "
        "selection) stay in `rad-comparison.csv` as the `*_pixel_pooled` columns.",
        "",
        "**Arms.** All campaign models are trained by us. `paul` = Paul's delivered masks "
        "(the `masks_machine` copies) with the stratified split; `fixed-grouped` = our "
        "re-rendered masks with the scene-grouped split. P / FG below name these label/split "
        "arms, not who trained the model. " + LABEL_ARM_STOPPED_POOLED,
        "",
        "**Caveats.**",
        "",
        optimism_caveat(report, selections),
        "- **Single seed, no uncertainty.** "
        + (f"Every campaign result is seed {', '.join(seeds)}; " if seeds else "One seed per run; ")
        + "there are no repeats or confidence intervals, and the subsets are small (see `n=`), "
        "so differences of a few IoU points between models or arms are not established.",
    ]
    if stratified and stratified["mud_pixels"]:
        track = stratified["viewpoints"]["track-level"]
        cab = stratified["viewpoints"][CAB]
        top = stratified["top5"]
        total = stratified["mud_pixels"]
        top_share = sum(t["mud_pixels"] for t in top) / total
        with_mud = sum(v["with_mud"] for v in stratified["viewpoints"].values())
        in_group = stratified["group_images_with_mud"]
        group = f"`{subsets.EXCLUDED_GROUP}`"
        if in_group > with_mud / 2:
            lead = (
                "- **The stratified split's all-image mud IoU is dominated by "
                f"{in_group} track-level close-ups from the {group} scene group.** "
            )
        elif track["with_mud"] > with_mud / 2:
            lead = "- **The stratified split's all-image mud IoU is dominated by track-level images.** "
        else:
            lead = "- "
        lines += [
            lead + f"On the stratified val split (`paul` masks) {track['with_mud']} of the "
            f"{with_mud} images with mud GT are track-level and {cab['with_mud']} cab-view; "
            f"{in_group} come from the {group} scene group. By pixels that group holds "
            f"{pct(stratified['group_mud_share'])}% of all mud GT and the five largest images "
            f"({', '.join('`' + t['key'] + '`' for t in top)}) {pct(top_share)}%, which "
            "decides only the pixel-pooled CSV columns. Scene groups are directory layout names "
            "assigned from visual evidence, not confirmed recording provenance.",
        ]
    if grouped and grouped["mud_pixels"]:
        cab = grouped["viewpoints"][CAB]
        with_mud = sum(v["with_mud"] for v in grouped["viewpoints"].values())
        line = (
            f"- On the grouped val split {cab['with_mud']} of the {with_mud} images with mud GT "
            "are cab-view"
            + (
                ", so its `all` and `cab-view` mud IoU nearly coincide."
                if cab["with_mud"] >= 0.8 * with_mud
                else "."
            )
        )
        if grouped["cab_mud_groups"]:
            name, count = next(iter(grouped["cab_mud_groups"].items()))
            share_text = "All" if count == cab["with_mud"] else f"{count} of"
            line += f" {share_text} {count if count == cab['with_mud'] else cab['with_mud']}"
            line += f" cab-view ones come from the `{name}` scene group"
            note = GROUP_NOTES.get(name)
            line += f"; judged visually, {note}." if note else "."
            if count > cab["with_mud"] / 2:
                line += (
                    " The grouped arm's cab-view mud numbers therefore mostly measure that one "
                    "camera setup."
                )
        lines += [line]
    lines += [
        "- **`cab-view` is the deployment-relevant subset** (a camera on a moving train). Compare "
        "arms and models on cab-view mud IoU; read `all` with the composition above in mind.",
        "- Viewpoints come from `configs/datasets/rad_9_24_2026-viewpoints.yaml`, joined by image "
        "SHA-256: visual judgement only, from two labelling passes by AI model subagents with "
        "adjudication of disagreements. Both passes are the same model, so their agreement is "
        "not evidence from independent annotators.",
    ]
    split = (
        "- `paul` vs `fixed-grouped` changes **both** the labels and the split policy. The "
        "stopped label-fix arm (above) found the label part small on average but -3.3 to +4.7 "
        "points per run, measured on eomt models and stratified val only, so a model's FG - P "
        "difference within that range cannot be attributed to the split. "
    )
    if stratified and grouped:
        common_train = len(stratified["train_images"] & grouped["train_images"])
        split += (
            "The val sets are different images and the train sets differ too "
            f"({len(stratified['train_images'])} vs {len(grouped['train_images'])} train "
            f"images, {common_train} in common), so the difference mixes the training data, "
            "model generalisation and val composition. On the stratified split "
            f"{stratified['val_groups_in_train']} of its {stratified['val_groups']} val scene "
            f"groups also have train images; on the grouped split {grouped['val_groups_in_train']} "
            f"of {grouped['val_groups']} do (scene groups are visually assigned, not confirmed "
            "recordings)."
        )
    else:
        split += "One of the two arms is missing."
    lines += [split]
    if report.missing_arms:
        lines += [
            "- Prepared dataset not found for "
            + ", ".join(f"`{a}`" for a in report.missing_arms)
            + "; its composition is not shown and none of its jobs could be scored."
        ]
    lines += [
        "- Fork labels: in `paper-hrnet__rs19-paul__arm-paul`, `rs19-paul` means the RS19 stage "
        "uses Paul's checkpoint and `arm-paul` means the RAD stage trains on the `paul` arm "
        "(Paul's masks); the checkpoint owners column spells out who trained each stage.",
        "",
    ]
    return lines


def mud_n(report: Report, arm: str, subset: str, name: str) -> str:
    """`` (n=7)``: val images with mud GT behind an arm's mud metric (label-only fact)."""
    c = report.composition.get(arm)
    if c is None or not name.startswith("mud"):
        return ""
    views = subsets.VIEWPOINTS if subset == "all" else [subset]
    return f" (n={sum(c['viewpoints'][v]['with_mud'] for v in views)})"


def render(report: Report, generated_at: str) -> str:
    lines = ["# RAD 9/24 comparison (validation split)", "", f"Generated: {generated_at}", ""]
    lines += how_to_read(report)

    by_job = keyed(report.results, "segmentary", lambda r: (r.model, r.protocol))
    lines += [
        "## Headline: Segmentary campaign models",
        "",
        "Percent; columns per arm: P = `paul`, FG = `fixed-grouped`. "
        f"{checkpoint_sentence(report)} Empty = job not completed.",
        "",
    ]
    headers = ["model", "protocol"] + [
        f"{title} {SHORT[arm]}{mud_n(report, arm, subset, name)}"
        for title, subset, name in HEADLINE
        for arm in ARMS
    ]
    rows = [
        [model, protocol]
        + [
            pct(metric(arms.get(arm), subset, name)) if arm in arms else ""
            for _, subset, name in HEADLINE
            for arm in ARMS
        ]
        for (model, protocol), arms in sorted(by_job.items())
    ]
    lines += (table(headers, rows) if rows else ["No completed campaign job yet."]) + [""]

    lines += [
        "## Arm effects",
        "",
        "Differences in IoU points for model x protocol pairs completed in both arms, single "
        "seed, no uncertainty. Split = FG - P: different labels, val images and train images "
        "(the label part is small on average but up to about 5 points per run; see How to read "
        "this)."
        + (
            " The arms also report different checkpoints ("
            + ", ".join(f"{SHORT[a]} {report.checkpoints[a]}" for a in ARMS)
            + "), which the difference mixes in too."
            if all(a in report.checkpoints for a in ARMS)
            and len({report.checkpoints[a] for a in ARMS}) > 1
            else ""
        ),
        "",
    ]
    effect_rows = []
    for (model, protocol), arms in sorted(by_job.items()):
        for name, a, b in (("split", "paul", "fixed-grouped"),):
            if a in arms and b in arms:
                effect_rows.append(
                    [model, protocol, name]
                    + [
                        delta(metric(arms[a], subset, key), metric(arms[b], subset, key))
                        for _, subset, key in HEADLINE
                    ]
                )
    effect_headers = ["model", "protocol", "effect"] + [title for title, _, _ in HEADLINE]
    lines += (table(effect_headers, effect_rows) if effect_rows else ["No pair completed yet."]) + [
        ""
    ]

    lines += composition_section(report)
    lines += fork_section(report)
    lines += coverage_section(report)
    lines += [
        "## Inputs",
        "",
        *(f"- {name}: `{value}`" for name, value in report.inputs.items()),
        "",
        "Every subset metric of every completed job is in `rad-comparison.csv` (subsets "
        + ", ".join(f"`{s}`" for s in subsets.SUBSETS)
        + ").",
        "",
    ]
    return "\n".join(lines)


def composition_section(report: Report) -> list[str]:
    lines = [
        "## Validation composition (labels only)",
        "",
        "Images / images with mud GT / share of the split's mud GT pixels, by viewpoint.",
        "",
    ]
    rows = []
    for arm, c in report.composition.items():
        cells = []
        for view in subsets.VIEWPOINTS:
            v = c["viewpoints"][view]
            share = pct(v["mud_pixels"] / c["mud_pixels"]) if c["mud_pixels"] else "—"
            cells.append(f"{v['images']} / {v['with_mud']} / {share}%")
        rows.append(
            [arm, str(c["images"]), *cells, f"{c['mud_pixels']:,}", pct(c["group_mud_share"])]
        )
    rows += [
        [arm, "dataset not found", *([""] * (len(subsets.VIEWPOINTS) + 2))]
        for arm in report.missing_arms
    ]
    headers = [
        "arm",
        "images",
        *subsets.VIEWPOINTS,
        "mud GT px",
        f"{subsets.EXCLUDED_GROUP} mud share %",
    ]
    return [*lines, *table(headers, rows), ""]


def fork_section(report: Report) -> list[str]:
    lines = [
        "## Paul-fork runs",
        "",
        "Labelled exactly by run label; checkpoint owners per init-chain stage (`paul` = Paul's "
        "checkpoint, `ours` = trained by us, `nvidia` / `public-sfnet-authors` = public). The "
        "`arm-<arm>` part of a label is the RAD dataset arm, not an owner. "
        "Scored by `score_predictions.py` (whole-image single-scale) with the campaign's metric "
        "code. Percent.",
        "",
    ]
    forks = sorted(
        (r for r in report.results if r.source == "fork"), key=lambda r: (r.label, r.job)
    )
    headers = [
        "label",
        "run directory",
        "checkpoint owners",
        *(title for title, _, _ in HEADLINE),
        f"mud IoU {EXCL}",
    ]
    rows = [
        [f"`{r.label}`", f"`{r.job}`", r.owners]
        + [pct(metric(r, s, k)) for _, s, k in HEADLINE]
        + [pct(metric(r, EXCL, "mud_present_iou"))]
        for r in forks
    ]
    return (
        lines + (table(headers, rows) if rows else ["No fork run has a scored val result."]) + [""]
    )


def coverage_section(report: Report) -> list[str]:
    lines = ["## Coverage", ""]
    rows = []
    extra = sorted({c.arm for c in report.coverage} - set(ARMS))
    for source in ("segmentary", "fork"):
        for arm in (*ARMS, *extra):
            entries = [c for c in report.coverage if c.source == source and c.arm == arm]
            if not entries:
                continue
            done = [c for c in entries if c.status == "completed"]
            pending: dict[str, int] = {}
            for c in entries:
                if c.status != "completed":
                    pending[c.status] = pending.get(c.status, 0) + 1
            rows.append(
                [
                    source,
                    arm,
                    f"{len(done)}/{len(entries)}",
                    ", ".join(f"{k} {v}" for k, v in sorted(pending.items())) or "—",
                ]
            )
    lines += [*table(["source", "arm", "completed", "not completed (status count)"], rows), ""]
    pending_jobs = sorted(
        (
            c
            for c in report.coverage
            if c.status != "completed" and (c.source == "fork" or c.status != "queued")
        ),
        key=lambda c: (c.source, c.arm, c.job),
    )
    if pending_jobs:
        lines += ["Not completed (queued campaign jobs are only counted above):", ""]
        lines += [f"- {c.source} `{c.arm}` `{c.job}`: {c.status}" for c in pending_jobs]
        lines += [""]
    return lines


def write(report: Report, out: Path, generated_at: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "rad-comparison.csv").write_text(csv_text(report))
    (out / "README.md").write_text(render(report, generated_at))


def parse_map(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("--path-map needs OLD=NEW")
    old, new = text.split("=", 1)
    return old, new


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--campaign", type=Path, action="append", help="repeat; default: HDRFS r2")
    p.add_argument("--fork-runs", type=Path, default=DEFAULT_FORK_RUNS)
    p.add_argument("--no-forks", action="store_true")
    p.add_argument("--datasets-root", type=Path, default=DEFAULT_DATASETS)
    p.add_argument("--viewpoints", type=Path, default=DEFAULT_VIEWPOINTS)
    p.add_argument("--path-map", type=parse_map, action="append", default=[])
    args = p.parse_args(argv)
    campaigns = args.campaign or list(DEFAULT_CAMPAIGNS)
    forks = None if args.no_forks else args.fork_runs
    out = args.out.resolve()
    for root in [*campaigns, *([forks] if forks else []), args.datasets_root]:
        if out == root.resolve() or root.resolve() in out.parents:
            raise SystemExit(f"rad_report: --out {out} lies inside input root {root}")
    try:
        report = build(campaigns, forks, args.datasets_root, args.viewpoints, args.path_map)
    except (ReportError, subsets.SubsetError) as error:
        raise SystemExit(f"rad_report: {error}") from error
    generated = datetime.now(UTC).replace(microsecond=0).isoformat()
    write(report, out, generated)
    done = sum(c.status == "completed" for c in report.coverage)
    print(f"rad_report: {done}/{len(report.coverage)} jobs completed; wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
