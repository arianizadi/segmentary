#!/usr/bin/env python3
"""Publish the whole RAD 9/24 study to docs/results/rad_9_24_2026 from a separate clone.

    PYTHONPATH=<code checkout>:<code checkout>/src python scripts/publish_rad_results.py \\
        --checkout <publisher clone> [--once] [--interval-seconds 1800] \\
        [--campaign <root> ...] [--fork-runs <dir>] [--datasets-root <dir>] \\
        [--cv-campaign <root>] [--viewpoints <yaml>] \\
        [--state-dir <dir>] [--max-tree-mb 200] [--max-file-mb 20] \\
        [--remote origin] [--branch main] [--dry-run-remote <git url>]

One cycle (every ``--interval-seconds``, default three hours to bound public history):

1. Check the publisher clone: a git top level, not this code checkout and not a campaign's
   frozen code checkout, on ``--branch``, whose ``--remote`` fetch and push URLs are the target
   (``https://github.com/arianizadi/segmentary.git``, or ``--dry-run-remote`` for tests).
   Local changes or unpushed commits touching anything outside ``docs/results/rad_9_24_2026``
   (and the ``docs/results/README.md`` index) are refused and stop the loop. Otherwise fetch
   and hard-reset to ``<remote>/<branch>``.
2. Render ``docs/results/rad_9_24_2026``: a short study page (``README.md``: what was tested,
   the key result, one compact table per split, caveats, links), ``details.md`` with the full
   record (label defects, the cab-view comparison of ``scripts/rad_report.py``, fork runs,
   provenance) and its ``rad-comparison.csv``, one directory per arm rendered by
   ``scripts/publish_rtis_results.py`` exactly as for RTIS v2, and with ``--cv-campaign`` the
   cross-validation report (``scripts/cv_report.py`` in-process, ``--viewpoints`` subsets)
   in ``cross-validation/`` (``README.md`` + ``cv-report.csv``). A partial CV campaign renders
   with its coverage (unfinished models marked ``*``).

   Each split is scored at its campaign's primary checkpoint (``rad_report``): the one selected
   on validation, or with ``primary_checkpoint: final`` the final checkpoint after the full step
   budget, for which the pages drop the "selected on validation" caveat. Several ``--campaign``
   roots may share a split (e.g. ``fixed-grouped-seed0-20261005-r2``, 10 models, best
   checkpoint, and ``fgall-seed0-20261007``, every catalog model, final checkpoint): the newest
   one (``created_at``) with a completed job is the split's pages and tables, so a new campaign
   takes over with its first finished run and the pages never go empty before that; a newer
   one without a finished run is shown only with its coverage ("N of M runs done"), and older
   ones are superseded: details.md summarises each (e.g. "First scene-grouped run (10 models,
   best-on-validation checkpoint)") with its CSV in ``earlier-runs/``. A partial split renders
   with its coverage (models with unfinished starting points marked ``*``); a model planned
   from one starting point only is labelled so. Smoke campaigns are refused.

   Headline metrics count each class only on the images that contain it
   (``segmentary.engine.present_image``): mud-pumping IoU is the mean per-image IoU over the
   images with mud-pumping ground truth (images without it are not counted, a missed one scores
   0), mud precision/recall sum pixels over those images, and mIoU averages each class over
   the images that contain it, then over the classes present. They head the study page, the
   per-split pages' Quality and Mud-pumping tables, a table on every model page and the CV
   page; "best starting point" is chosen by the train-camera mud-pumping IoU. The campaign's
   own pixel-pooled numbers (which selected the best checkpoints) stay in the CSVs as
   ``*_pixel_pooled`` and in the per-run tables of the arm and model pages, labelled so (for
   a final-checkpoint campaign they describe its best-on-validation checkpoint). The
   per-split, model and CV pages also carry a per-class IoU table (every class by the same
   present-image rule; ``—`` where no image contains it), and the study tables show speed,
   inference GPU memory and parameters from the performance records: memory is the
   whole-process ``process_total_bytes`` when recorded, else the allocator's
   ``peak_reserved_bytes`` marked as excluding the CUDA context.
3. Size guard (tree and per-file caps); prediction directories, test-split evidence and
   file types other than the evidence formats are never published. The repository's docs
   checks (legacy name, resolving links) run on the rendered tree before anything is staged.
   When the cab-view comparison fails after one was published, the cycle publishes nothing
   rather than removing it. When the CV report fails (or its campaign is missing), the
   published ``cross-validation/`` pages are kept unchanged, the study page says so, the error
   is recorded as ``cv_error`` in the status and the next cycle retries.
4. Stage only the tree (and the index line when missing), verify nothing else changed,
   commit "Update RAD 9/24 results" when anything changed and push; a non-fast-forward
   rejection is fetched and rebased, at most three times. Never forced.

Campaign, fork-run and dataset directories are only read. ``publisher-status.json``,
``publisher.lock`` (one instance) and ``STOP`` (ends the loop) live in ``--state-dir``.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import io
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from zoneinfo import ZoneInfo

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from scripts import cv_report, rad_report
from scripts import publish_rtis_results as reports

TREE = Path("docs/results/rad_9_24_2026")
INDEX = Path("docs/results/README.md")
INDEX_ROW = (
    "| [RAD 9/24 (rad_9_24_2026)](rad_9_24_2026/README.md) | 10 models x 4 initialization paths on "
    "two arms: Paul's masks with a stratified split, re-rendered masks with a scene-grouped "
    "split; plus Paul Stanik's "
    "paper recipes (HRNet-OCR, SFNet) retrained by us with his fork code | Validation only, "
    "seed 0; cab-view subset; test held out |"
)
GUIDE = Path("docs/guides/rad-9-24-2026.md")
TARGET_URL = "https://github.com/arianizadi/segmentary.git"
RUNS = rad_report.RUNS
DEFAULT_STATE = RUNS / "rad_9_24_2026" / "publisher"
COMMIT_MESSAGE = "Update RAD 9/24 results"
PUSH_ATTEMPTS = 3
# Directory names that hold dumped prediction masks; refused anywhere in the tree.
PREDICTION_PARTS = {"pred", "preds", "prediction", "predictions", "masks", "dumps"}
# The evidence formats the arm pages publish (as for RTIS v2); anything else is refused.
PUBLISHED_SUFFIXES = (".md", ".csv", ".json", ".json.gz", ".jpg")
# A directory naming the test split (``best-auto-test``, ``test``): never published.
TEST_PART = re.compile(r"(^|[-_.])test($|[-_.])", re.IGNORECASE)
LEGACY_ENV = "/data/izadia1/envs/" + "rail" + "yard" + "/"
FORK_SECTION = "## Paper-recipe fork runs"
FORK_ANCHOR = "#paper-recipe-fork-runs"
# rad_report sections the study page already covers from its own snapshot.
DROPPED_REPORT_SECTIONS = {"## Paul-fork runs", "## Coverage"}
ARM_TEXT = {
    "paul": ("Paul's delivered `masks_machine` copies", "stratified random (seed 0)"),
    "fixed-grouped": ("re-rendered from the polygon JSONs", "scene-grouped (from v1/v2)"),
}
# Plain names for the study page: splits (the campaign "arms") and starting points (protocols).
SPLIT_NAME = {"paul": "Paul's split", "fixed-grouped": "Scene-grouped split"}
SPLIT_PHRASE = {"paul": "Paul's split", "fixed-grouped": "the scene-grouped split"}
START = {
    "rtis_only": "recipe pretrained weights",
    "cityscapes_to_rtis": "Cityscapes",
    "railsem19_to_rtis": "RailSem19",
    "cityscapes_to_railsem19_to_rtis": "Cityscapes → RailSem19",
}
FORK_BASE = {
    "paper-hrnet__rs19-paul": "HRNet-OCR, Paul's RailSem19 checkpoint",
    "paper-hrnet__rs19-ours": "HRNet-OCR, our RailSem19 retraining",
    "paper-hrnet__mapcity-direct": "HRNet-OCR, public Mapillary/Cityscapes checkpoint",
    "paper-sfnet__rs19-paul": "SFNet-R18, Paul's RailSem19 checkpoint",
    "paper-sfnet__rs19-ours": "SFNet-R18, our RailSem19 retraining",
    "paper-sfnet__mapcity-direct": "SFNet-R18, public Mapillary/Cityscapes checkpoint",
}
DETAILS = "details.md"
CV_DIR = "cross-validation"
# The CV README's tables show these viewpoint subsets (cv_report --subset); the CSV has all.
CV_TABLE_SUBSETS = ("cab-view",)
# Column titles of the study tables (present-image metrics, see the module docstring).
MUD_CAB = "Mud-pumping IoU, train-camera images with mud"
MUD_ALL = "Mud-pumping IoU, all images with mud"
MIOU = "mIoU (each class over images that contain it)"
# The shared RTIS per-run table, relabelled on RAD pages: its numbers pool pixels.
POOLED_HEADERS = [
    "Model",
    "Initialization path",
    "Seed",
    "Status",
    "Steps",
    "Best step",
    "Mud IoU, pixels pooled (%)",
    "Mud precision, pixels pooled (%)",
    "Mud recall, pixels pooled (%)",
    "Final mud IoU (trainer val, pixels pooled, %)",
    "mIoU, pixels pooled (%)",
    "Fixed GT-class mIoU, pixels pooled (%)",
]
# The same for a final-checkpoint campaign, whose per-run evaluation is the best-on-validation
# checkpoint kept as secondary evidence.
POOLED_HEADERS_BEST_CHECKPOINT = [
    *POOLED_HEADERS[:6],
    "Best-checkpoint mud IoU, pixels pooled (%)",
    "Best-checkpoint mud precision, pixels pooled (%)",
    "Best-checkpoint mud recall, pixels pooled (%)",
    "Final mud IoU (trainer val, pixels pooled, %)",
    "Best-checkpoint mIoU, pixels pooled (%)",
    "Best-checkpoint fixed GT-class mIoU, pixels pooled (%)",
]
CASE_GUIDE = Path("docs/guides/rad-9-24-2026-mud-iou-case.md")
CV_GUIDE = Path("docs/guides/cross-validation.md")
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


class Refusal(RuntimeError):
    """The publisher clone needs a human; the loop stops."""


class GitError(RuntimeError):
    pass


class SizeError(RuntimeError):
    pass


class DocsError(RuntimeError):
    """The rendered tree would fail the repository's documentation checks."""


class ComparisonError(RuntimeError):
    """The comparison failed after one was published; keep the published one this cycle."""


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=GIT_ENV
    )
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise GitError(f"git {' '.join(args)}: {detail}")
    return proc.stdout


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text())


# ----------------------------------------------------------------------------- rendering


def arm_of(root: Path) -> str:
    arm = str(read_json(root / "campaign.json").get("dataset", "")).removeprefix("rad_9_24_2026-")
    if arm not in rad_report.ARMS:
        raise ValueError(f"{root}: not a RAD 9/24 arm")
    return arm


# What a campaign's primary checkpoint means, in the plain words of the study pages.
CHECKPOINT_PHRASE = {
    "best": "best-on-validation checkpoint",
    "final": "final checkpoint after the full training budget",
}


@dataclass
class Campaign:
    """One campaign root of a split (``arm``): its records and job statuses, only read."""

    root: Path
    arm: str
    record: dict[str, Any]
    plan: dict[str, Any]
    statuses: Counter[str]

    @property
    def done(self) -> int:
        return self.statuses.get("completed", 0)

    @property
    def total(self) -> int:
        return sum(self.statuses.values())

    @property
    def checkpoint(self) -> str:
        """``best`` or ``final``, as ``rad_report`` scores it."""
        return rad_report.primary_checkpoint(self.record, self.plan, self.root)

    @property
    def models(self) -> dict[str, list[str]]:
        """The planned starting points (protocols) of every model."""
        out: dict[str, list[str]] = {}
        for job in self.plan.get("jobs", []):
            protocols = out.setdefault(job["model"], [])
            if job["protocol"] not in protocols:
                protocols.append(job["protocol"])
        return out

    def describe(self) -> str:
        """``41 models, final checkpoint after the full training budget``."""
        count = len(self.models)
        return f"{count} model{'s' * (count != 1)}, {CHECKPOINT_PHRASE[self.checkpoint]}"


def campaign_of(root: Path) -> Campaign:
    record = read_json(root / "campaign.json")
    if record.get("smoke"):
        raise ValueError(f"{root}: a smoke campaign is never published")
    plan = read_json(root / "plan.json") if (root / "plan.json").is_file() else {"jobs": []}
    statuses: Counter[str] = Counter()
    for job in plan.get("jobs", []):
        path = root / "state" / f"{job['name']}.json"
        statuses[
            str(read_json(path).get("status", "no state")) if path.is_file() else "no state"
        ] += 1
    return Campaign(root, arm_of(root), record, plan, statuses)


@dataclass
class Split:
    """The campaigns of one split: ``current`` is published as the split; ``earlier`` ones are
    superseded (summarised in details.md), ``upcoming`` ones have no finished run yet."""

    current: Campaign
    earlier: list[Campaign] = field(default_factory=list)
    upcoming: list[Campaign] = field(default_factory=list)


def choose(campaigns: list[Campaign]) -> dict[str, Split]:
    """Per split, the newest campaign (``created_at``, then argument order) with a completed job
    is the current one, so a newly started campaign takes over the split's pages with its first
    finished run and the pages never go empty before that; when none has one, the newest."""
    seen: dict[Path, Path] = {}
    by_arm: dict[str, list[tuple[str, int, Campaign]]] = {}
    for index, campaign in enumerate(campaigns):
        key = campaign.root.resolve()
        if key in seen:
            raise ValueError(f"campaign root {campaign.root} given twice")
        seen[key] = campaign.root
        created = str(campaign.record.get("created_at", ""))
        by_arm.setdefault(campaign.arm, []).append((created, index, campaign))
    splits = {}
    for arm, entries in by_arm.items():
        order = [c for _, _, c in sorted(entries, key=lambda e: (e[0], e[1]))]
        finished = [i for i, c in enumerate(order) if c.done]
        at = finished[-1] if finished else len(order) - 1
        splits[arm] = Split(order[at], order[:at], order[at + 1 :])
    return {arm: splits[arm] for arm in rad_report.ARMS if arm in splits}


def anchor(heading: str) -> str:
    """GitHub's anchor of a Markdown heading."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return "#" + text.replace(" ", "-")


def earlier_heading(split: Split, campaign: Campaign) -> str:
    """``First scene-grouped run (10 models, best-on-validation checkpoint)``."""
    order = [*split.earlier, split.current, *split.upcoming]
    ordinal = "First" if order.index(campaign) == 0 else "Earlier"
    name = {"paul": "run on Paul's split", "fixed-grouped": "scene-grouped run"}[campaign.arm]
    return f"{ordinal} {name} ({campaign.describe()})"


PER_CLASS = "Per-class IoU"
PER_CLASS_ANCHOR = "#per-class-iou"
PER_CLASS_NOTE = (
    "IoU (%) of every class, each averaged only over the validation images that contain the "
    "class (n = those images); — = no image contains it. mIoU averages the classes with at least "
    "one such image."
)


def per_class_table(
    lead: list[str],
    entries: list[tuple[list[Any], dict[str, Any] | None]],
    pct=None,
    mark: str = "",
) -> list[str]:
    """One row per entry (lead cells + a subset's metrics, or None), columns mIoU and every
    class with its image count (label-only, taken from the first scored entry)."""
    pct = pct or reports.pct
    scored = next((m for _, m in entries if m is not None), None)
    if scored is None:
        return ["Not available this cycle."]
    names = list(scored["present_class_iou"])
    counts = scored["present_class_images"]
    headers = [*lead, MIOU, *(f"{c} (n={counts[c]})" for c in names)]
    rows = []
    for cells, m in entries:
        if m is None:
            rows.append([*cells, *(["—"] * (1 + len(names)))])
            continue
        values = [m["present_miou"], *(m["present_class_iou"][c] for c in names)]
        rows.append([*cells, *(pct(v) + (mark if v is not None else "") for v in values)])
    return reports.table(headers, rows).splitlines()


def replace_once(text: str, old: str, new: str, where: str) -> str:
    """Replace a known passage of the shared RTIS rendering; fail loudly if it moved."""
    if old not in text:
        raise ValueError(f"{where}: the shared RTIS page no longer contains {old[:60]!r}")
    return text.replace(old, new, 1)


def table_header(headers: list[str]) -> str:
    return reports.table(headers, []).splitlines()[0]


def csv_header(headers: list[str]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(headers)
    return buffer.getvalue()


def arm_files(
    data: dict, arm: str, report: rad_report.Report | None = None
) -> dict[str, str | bytes]:
    """The RTIS v2 rendering of one arm, with the page title and dataset facts of RAD, and the
    present-image metrics of ``report`` (``—`` without one) in place of the pooled tables."""
    files = reports.artifacts(data)
    jobs = data["jobs"]
    grouping = data["campaign"].get("grouping_status", "unrecorded")
    labels, split = ARM_TEXT[arm]
    starts = ", ".join(f"`{p}` = {START[p]}" for p in START)
    by_job = {(r.model, r.protocol): r for r in split_results(report, arm)}
    with_mud = ((report.composition if report else {}).get(arm) or {}).get("viewpoints") or {}
    n_all = sum(v["with_mud"] for v in with_mud.values()) if with_mud else None
    n_cab = with_mud[rad_report.CAB]["with_mud"] if with_mud else None

    def value(subset: str, name: str):
        return lambda row: rad_report.metric(
            by_job.get((row["model"], row["protocol"])), subset, name
        )

    def n(count: int | None) -> str:
        return "" if count is None else f" (n={count})"

    def metrics_of(row: dict) -> dict[str, Any] | None:
        result = by_job.get((row["model"], row["protocol"]))
        return None if result is None else result.metrics["all"]

    def percent(count: int | None) -> str:
        return "(%)" if count is None else f"(%, n={count})"

    final = data["campaign"].get("primary_checkpoint", "best") == "final"
    pooled_numbers = (
        "pixel-pooled numbers of the checkpoint that scored best on validation, kept as "
        "secondary evidence"
        if final
        else "pixel-pooled numbers, which selected the checkpoints"
    )
    intro = (
        f"# RAD 9/24: {SPLIT_NAME[arm]} (`{arm}`)\n\n"
        f"Every model and starting point trained on {SPLIT_PHRASE[arm]} (labels: {labels}; "
        f"split: {split}). Every model on this page was trained by us. The tables keep the "
        "shared RTIS report's names: an *initialization path* is the starting point "
        f"(pretraining before training on these images): {starts}. The Quality, Mud-pumping "
        f"and [{PER_CLASS}]({PER_CLASS_ANCHOR}) tables count each class only on the validation "
        "images that contain it"
        + (
            " and score the final checkpoint after the full training budget (no early "
            "stopping, so nothing is selected on the validation images)"
            if final
            else ""
        )
        + "; the per-run table, `results.csv` and the model pages also keep the campaign's own "
        f"{pooled_numbers}. The [study page](../README.md) compares the splits."
    )
    readme = files["README.md"]
    readme = replace_once(readme, "# RTIS model comparison", intro, "arm README")
    readme = replace_once(
        readme, "[Dataset and preparation](../README.md)", "[RAD 9/24 study](../README.md)", arm
    )
    readme = readme.replace(
        "Validation groups are provisional and lack person, truck and on-rails ground truth.",
        f"Split grouping status: `{grouping}`.",
        1,
    )
    readme = replace_once(
        readme,
        "Validation **mIoU (%)** across classes. Cells show the mean over completed seeds. "
        "Per-seed values are retained on model pages and in machine records. Partial groups "
        "are provisional; — means unavailable. These are the existing selected-checkpoint "
        "evaluations, not newly selected mIoU-best checkpoints. Raw/EMA settings are recorded "
        "on each model page.\n\n" + reports.seed_summary(jobs),
        "Validation **mIoU (%)**: each class's IoU averaged over the validation images that "
        "contain it, then over the classes present. Cells show the mean over completed seeds; "
        "— means unavailable. Raw/EMA settings are recorded on each model page.\n\n"
        + reports.comparison_table(jobs, value("all", "present_miou")),
        f"{arm} README quality",
    )
    readme = replace_once(
        readme,
        "Validation **mud-pumping IoU (%)** for the same checkpoints. Precision, recall, "
        "per-class scores and examples are on each model page and in the CSV.\n\n"
        + reports.comparison_table(
            jobs,
            lambda r: (
                r.get("evaluation", {}).get("metrics", {}).get("per_class_iou", {}).get(reports.MUD)
            ),
        ),
        "Validation **mud-pumping IoU (%)** for the same checkpoints, averaged over the "
        "validation images with mud-pumping (images without it are not counted). Precision, "
        "recall and examples are on each model page.\n\n"
        f"All images with mud{n(n_all)}:\n\n"
        + reports.comparison_table(jobs, value("all", "mud_present_iou"))
        + f"\n\nTrain-camera images with mud{n(n_cab)}:\n\n"
        + reports.comparison_table(jobs, value(rad_report.CAB, "mud_present_iou")),
        f"{arm} README mud-pumping",
    )
    if final:
        readme = replace_once(
            readme,
            "This campaign selects checkpoints and early-stops by **mud-pumping validation "
            "IoU**. Both overall mIoU and mud IoU above describe that same selected checkpoint. "
            "This report layout does not change the training objective or selection policy. "
            "mIoU averages classes with nonzero union;",
            "This campaign reports the **final checkpoint** after the full step budget, with no "
            "early stopping: the Quality, Mud-pumping and per-class tables above describe it, "
            "counting each class only on the images that contain it, so nothing is selected on "
            "the validation images. The checkpoint that scored best on the **mud-pumping "
            "validation IoU** (pixels pooled over all validation images) is kept as secondary "
            "evidence and is what the per-run table shows. Pooled mIoU there averages classes "
            "with nonzero union;",
            f"{arm} README selection",
        )
        readme = replace_once(
            readme,
            "Validation approximately every 250 optimizer steps; stop after five checks without "
            "a 0.1 percentage-point mud-IoU improvement. At most 4,000 steps.",
            "Validation approximately every 250 optimizer steps, only to keep the "
            "best-on-validation checkpoint as secondary evidence; no early stopping: every job "
            f"trains the full {int(data['campaign']['target_steps']):,} steps.",
            f"{arm} README stopping",
        )
    else:
        readme = readme.replace(
            "Both overall mIoU and mud IoU above describe that same selected checkpoint. This "
            "report layout does not change the training objective or selection policy. mIoU "
            "averages classes with nonzero union;",
            "The Quality and Mud-pumping tables above describe that same selected checkpoint, "
            "counting each class only on the images that contain it; the selection itself used "
            "the mud IoU with pixels pooled over all validation images, shown in the per-run "
            "table. Pooled mIoU there averages classes with nonzero union;",
            1,
        )
    order = {p: i for i, p in enumerate(START)}
    entries = [
        (
            [f"[{r['model']}](models/{r['model']}/README.md)", r["protocol"], r.get("seed", 0)],
            metrics_of(r),
        )
        for r in sorted(jobs, key=lambda r: (r["model"], order.get(r["protocol"], 99)))
    ]
    readme = replace_once(
        readme,
        "## Standardized model-only inference",
        f"## {PER_CLASS}\n\nValidation {PER_CLASS_NOTE}\n\n"
        + "\n".join(per_class_table(["Model", "Initialization path", "Seed"], entries))
        + "\n\n## Standardized model-only inference",
        f"{arm} README per-class",
    )
    headers = POOLED_HEADERS_BEST_CHECKPOINT if final else POOLED_HEADERS
    pooled = table_header(headers)
    readme = replace_once(readme, table_header(reports.HEADERS), pooled, f"{arm} README runs")
    files["README.md"] = readme
    files["results.csv"] = replace_once(
        str(files["results.csv"]),
        csv_header(reports.HEADERS),
        csv_header(headers),
        f"{arm} results.csv",
    )
    for name, content in files.items():
        match = re.fullmatch(r"models/([^/]+)/README\.md", name)
        if not match or not isinstance(content, str):
            continue
        content = replace_once(
            content,
            "[RTIS comparison](../../README.md)",
            f"[RAD 9/24: {SPLIT_NAME[arm]}](../../README.md)",
            name,
        )
        content = content.replace(
            "Primary selection and early stopping: **mud-pumping validation IoU**.",
            "Primary result: the **final checkpoint** after the full step budget (no early "
            "stopping). The checkpoint with the best **mud-pumping validation IoU, pixels pooled "
            "over all validation images**, is kept as secondary evidence."
            if final
            else "Primary selection and early stopping: **mud-pumping validation IoU, pixels "
            "pooled over all validation images**.",
            1,
        )
        rows = [r for r in jobs if r["model"] == match.group(1)]
        study = [
            [
                r["protocol"],
                r.get("seed", 0),
                *(
                    reports.pct(value(subset, key)(r))
                    for subset, key in (
                        (rad_report.CAB, "mud_present_iou"),
                        ("all", "mud_present_iou"),
                        ("all", "mud_present_precision"),
                        ("all", "mud_present_recall"),
                        ("all", "present_miou"),
                    )
                ),
            ]
            for r in rows
        ]
        headers = [
            "Initialization path",
            "Seed",
            f"{MUD_CAB} {percent(n_cab)}",
            f"{MUD_ALL} {percent(n_all)}",
            "Mud precision, all images with mud (%)",
            "Mud recall, all images with mud (%)",
            f"{MIOU} (%)",
        ]
        block = (
            "Study metrics"
            + (" of the final checkpoint" if final else "")
            + ", counting each class only on the validation images that contain "
            "it: mud-pumping IoU is the mean per-image IoU over the images with mud-pumping, "
            "precision and recall sum pixels over those images, and mIoU averages each class "
            "over the images that contain it, then over the classes present.\n\n"
            + reports.table(headers, study)
            + f"\n\n{PER_CLASS}: {PER_CLASS_NOTE}\n\n"
            + "\n".join(
                per_class_table(
                    ["Initialization path", "Seed"],
                    [([r["protocol"], r.get("seed", 0)], metrics_of(r)) for r in rows],
                )
            )
            + "\n\nEverything below is the campaign's own record, with pixels pooled over all "
            + (
                "validation images: its evaluation is the checkpoint that scored best on that "
                "pooled mud IoU (secondary evidence here); the diagnostics also cover the final "
                "checkpoint (`final-auto-val`).\n\n"
                if final
                else "validation images (the checkpoint was selected on that pooled mud IoU).\n\n"
            )
            + pooled
        )
        files[name] = replace_once(content, table_header(reports.HEADERS), block, name)
    return {f"{arm}/{name}": content for name, content in files.items()}


def comparison_markdown(report: rad_report.Report, arms: set[str]) -> str:
    """rad_report's page as a section: no timestamp, headings one level down, campaign
    roots linked to their published arm pages (the path stays as provenance text)."""
    out, dropping = [], False
    for line in rad_report.render(report, "").splitlines():
        if line.startswith("## "):
            dropping = line in DROPPED_REPORT_SECTIONS
        if dropping or line.startswith("Generated:"):
            continue
        if line.startswith("# "):
            line = "## Cab-view comparison (validation split)"
        elif line.startswith("#"):
            line = "#" + line
        match = re.fullmatch(r"- campaign ([a-z-]+): `(.+)`", line)
        if match and match.group(1) in arms:
            line = (
                f"- campaign {match.group(1)}: [published arm]({match.group(1)}/README.md); "
                f"source `{match.group(2)}`"
            )
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def tail(path: Path, size: int = 4 << 20) -> str:
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - size))
        return stream.read().decode("utf-8", "replace")


def max_epoch(provenance: dict) -> str:
    args = [str(a) for a in provenance.get("recipe_args") or []]
    for i, arg in enumerate(args):
        if arg == "--max_epoch" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--max_epoch="):
            return arg.split("=", 1)[1]
    return "?"


def fork_progress(run: Path, provenance: dict) -> dict[str, Any]:
    """In-training progress from the fork's own log and best-mud record (not comparable)."""
    out: dict[str, Any] = {"epoch": None, "max_epoch": max_epoch(provenance)}
    log = run / "console.log"
    if log.is_file():
        text = tail(log)
        # Training lines only: ``best : [epoch N]`` repeats an older epoch.
        epochs = re.findall(r"^\[epoch (\d+)\], \[iter", text, re.M)
        out["epoch"] = int(epochs[-1]) if epochs else None
        best = re.findall(r"^best\s*:\s*\[epoch (\d+)\].*?\[mean_iu ([0-9.]+)\]", text, re.M)
        if best:
            out["best_miou_epoch"], out["best_miou"] = int(best[-1][0]), float(best[-1][1])
    for path in sorted(run.glob("*/best_mud.json")):
        record = read_json(path)
        out["best_mud_epoch"] = record.get("epoch")
        out["best_mud_iou"] = record.get("mud_iou")
        break
    return out


def fork_rows(fork_runs: Path | None, report: rad_report.Report | None) -> list[dict]:
    from scripts.paul_forks.score_predictions import ScoreError, parse_label

    scored = {r.job: r for r in (report.results if report else []) if r.source == "fork"}
    rows, seen = [], set()
    runs = sorted(p for p in fork_runs.iterdir() if p.is_dir()) if fork_runs else []
    for run in runs:
        if not (run / "provenance.json").is_file():
            continue
        provenance = read_json(run / "provenance.json")
        label = str(provenance.get("label", run.name))
        seen.add(run.name)
        try:
            _, arm, _ = parse_label(label)
            rad_stage = True
        except ScoreError:
            # RS19-stage runs validate on RailSem19 test (HRNet) or inside trainVal (SFNet):
            # their printouts are not val numbers, so only the status is shown.
            arm, rad_stage = "— (RS19 stage)", False
        row = {
            "label": label,
            "run": run.name,
            "arm": arm,
            "owners": rad_report.owners_text(
                provenance.get("owner_of_each_checkpoint_in_chain") or {}
            ),
            "result": scored.get(run.name),
        }
        flags = [f for f in rad_report.FORK_SKIP_FLAGS if provenance.get(f)]
        launcher = run / "gpu-assignment.json"
        record = read_json(launcher) if launcher.is_file() else {}
        if flags:
            row["status"] = f"excluded ({', '.join(flags)})"
        elif row["result"] is not None:
            row["status"] = "scored (val)"
        elif record.get("status") == "running":
            p = fork_progress(run, provenance)
            row["status"] = f"training, epoch {p['epoch'] if p['epoch'] is not None else '?'}"
            row["status"] += f" (0-based, of {p['max_epoch']})"
            if rad_stage:
                row["progress"] = p
        elif record.get("status") == "exited":
            code = record.get("exit_code")
            row["status"] = "trained, val not yet scored" if code == 0 else f"exited {code}"
            if rad_stage:
                row["progress"] = fork_progress(run, provenance)
        else:
            row["status"] = str(record.get("status", "no launcher record"))
        rows.append(row)
    queue = fork_runs.parent / "queue-state.json" if fork_runs else None
    if queue is not None and queue.is_file():
        for job in read_json(queue).get("jobs", {}).values():
            name = Path(str(job.get("run_dir", ""))).name
            if not name or name in seen:
                continue
            label = str(job.get("label", name))
            try:
                _, arm, _ = parse_label(label)
            except ScoreError:
                arm = "— (RS19 stage)"
            rows.append(
                {
                    "label": label,
                    "run": name,
                    "arm": arm,
                    "owners": "",
                    "result": None,
                    "status": f"queue: {job.get('status', '?')}",
                }
            )
    return sorted(rows, key=lambda r: (r["result"] is None, "progress" not in r, r["label"]))


def fork_section(rows: list[dict]) -> list[str]:
    pct = rad_report.pct
    lines = [
        FORK_SECTION,
        "",
        "Paul Stanik's two paper recipes (HRNet-OCR-Mscale `pauls3/semantic-segmentation@5e619e6`, "
        "SFNet-R18 `pauls3/SFSegNets-2@0bb9e59`), retrained by us with his fork code on the same "
        "two arms: every RAD stage (`rad:ours`) is trained by us, and earlier stages may start "
        "from Paul's or public checkpoints. The run label states the init chain; checkpoint "
        "owners name who trained each stage (`paul` = Paul's checkpoint, `ours` = trained by us, "
        "`nvidia` / `public-sfnet-authors` = public). The `arm-<arm>` part of a label is the RAD "
        "dataset arm, not an owner.",
        "",
        "**Scored** runs use Segmentary's metric code on our val split "
        "(`score_predictions.py`, whole-image single-scale) and are comparable with the campaign "
        "tables above. **In-training** numbers are the fork's own validation printout "
        "(multi-scale fork evaluator, its own class handling, epoch picked on the same val "
        "split): progress only, **not comparable** with any scored number. Epoch numbers are the "
        "fork's own 0-based indices. RS19-stage runs (pretraining on RailSem19) show their status "
        "only: their printouts are not RAD validation numbers.",
        "",
    ]
    if not rows:
        return [*lines, "No fork run yet.", ""]
    table = []
    for r in rows:
        result, progress = r["result"], r.get("progress") or {}
        if result is not None:
            scored = " / ".join(
                pct(rad_report.metric(result, s, k)) for _, s, k in rad_report.HEADLINE
            )
        else:
            scored = "—"
        own = []
        if progress.get("best_mud_iou") is not None:
            own.append(
                f"mud IoU {100 * progress['best_mud_iou']:.1f} @ epoch {progress['best_mud_epoch']}"
            )
        if progress.get("best_miou") is not None:
            own.append(
                f"mIoU {100 * progress['best_miou']:.1f} @ epoch {progress['best_miou_epoch']}"
            )
        table.append(
            [
                f"`{r['label']}`" + (f" (run `{r['run']}`)" if r["run"] != r["label"] else ""),
                r["arm"],
                r["owners"] or "—",
                r["status"],
                scored,
                "; ".join(own) or "—",
            ]
        )
    headers = [
        "label",
        "arm",
        "checkpoint owners",
        "status",
        "scored: " + " / ".join(title for title, _, _ in rad_report.HEADLINE),
        "fork's own in-training best (not comparable)",
    ]
    lines += reports.table(headers, table).splitlines()
    lines += [
        "",
        "`paul-reference__rr22-0.8964` (Paul's finished RAD model) may have trained on our "
        "val/test images and is never scored on our splits. Deviations from Paul's protocol "
        "are recorded in each run's `provenance.json` on HDRFS.",
        "",
    ]
    return lines


def label_defects(datasets: Path) -> list[str]:
    lines = [
        "## Label defects in the delivered masks",
        "",
        "The annotator's `masks_machine` PNGs start from a black canvas and draw exterior "
        "polygon rings only, so pixels covered by no polygon become class 0 (person) and polygon "
        "holes are filled. The `paul` arm trains on those masks; the `fixed-grouped` arm trains "
        "on the repository render of the same polygon JSONs (holes cut out, uncovered pixels "
        "ignored). Counts over all 314 images, from each prepared dataset's "
        "`audit/label-audit.json` (masks_machine versus the repository render):",
        "",
    ]
    audits, names = {}, {}
    for arm in rad_report.ARMS:
        base = datasets / rad_report.DATASET.format(arm=arm)
        if (base / "audit/label-audit.json").is_file():
            audits[arm] = read_json(base / "audit/label-audit.json")
            if not names and (base / "classes.json").is_file():
                names = {
                    str(c["id"]): c["name"] for c in read_json(base / "classes.json")["classes"]
                }
    if not audits:
        return [*lines, "No prepared dataset found.", ""]
    groups: list[tuple[list[str], dict]] = []
    for arm, audit in audits.items():
        # Per-image rows carry each arm's split; the counted quantities do not depend on it.
        fields = ("totals", "per_class_totals", "images_with_disagreement")
        key = [audit.get(k) for k in (*fields, "images_with_uncovered_px")]
        for members, other in groups:
            if [other.get(k) for k in (*fields, "images_with_uncovered_px")] == key:
                members.append(arm)
                break
        else:
            groups.append(([arm], audit))

    def quantities(audit: dict) -> list[str]:
        totals, per_class = audit.get("totals", {}), audit.get("per_class_totals", {})
        pixels = sum(int(v.get("paul_px", 0)) for v in per_class.values())
        disagreement = int(totals.get("disagreement_px", 0))
        mud = per_class.get("13", {})
        return [
            str(audit.get("images_with_disagreement", "?")),
            str(audit.get("images_with_uncovered_px", "?")),
            f"{int(totals.get('uncovered_px', 0)):,} / "
            f"{int(totals.get('paul_zero_uncovered_px', 0)):,}",
            f"{int(totals.get('hole_px_changed', 0)):,}",
            f"{disagreement:,} ({100 * disagreement / pixels:.2f}%)" if pixels else "—",
            f"{int(totals.get('person_px_rendered', 0)):,} / "
            f"{int(totals.get('person_px_paul', 0)):,}",
            f"{int(mud.get('paul_px_differing', 0)):,} / "
            f"{int(mud.get('rendered_px_differing', 0)):,} of {int(mud.get('paul_px', 0)):,}",
        ]

    titles = [
        "Images with any disagreement",
        "Images with pixels covered by no polygon",
        "Pixels covered by no polygon / of those labelled person in masks_machine",
        "Pixels changed by ignoring polygon holes",
        "Total disagreement pixels",
        "Person pixels, repository render / masks_machine",
        "Mud-pumping pixels differing, masks_machine / render (of all mud pixels)",
    ]
    columns = [quantities(audit) for _, audit in groups]
    headers = ["Quantity", *(", ".join(f"`{a}`" for a in members) for members, _ in groups)]
    rows = [[title, *(col[i] for col in columns)] for i, title in enumerate(titles)]
    lines += reports.table(headers, rows).splitlines()
    per_class = groups[0][1].get("per_class_totals", {})
    worst = sorted(
        (
            (max(int(v.get("paul_px_differing", 0)), int(v.get("rendered_px_differing", 0))), k)
            for k, v in per_class.items()
            if k != "255"
        ),
        reverse=True,
    )[:5]
    sources = ", ".join(f"`{a}` {x.get('label_source', '?')}" for a, x in audits.items())
    lines += [
        "",
        f"Trained labels (`label_source`): {sources}. The two renders compared are the same for "
        "every arm. Classes with the most differing pixels (larger of the two directions): "
        + ", ".join(f"{names.get(k, k)} {n:,}" for n, k in worst)
        + ".",
        "",
    ]
    return lines


def guide_ref(path: Path, title: str, guides: frozenset[Path], up: str = "../../") -> str:
    """A link to a guide the publisher clone carries, else its path as text."""
    if path in guides:
        return f"[{title}]({up}{path.relative_to('docs')})"
    return f"{title}: `{path}`"


def legacy_layout(splits: dict[str, Split]) -> bool:
    """Every split shown from a best-checkpoint campaign that superseded none: the pages read
    as before final-checkpoint runs (a newer campaign without a finished run only adds its
    coverage line and its row in details.md)."""
    return all(s.current.checkpoint == "best" and not s.earlier for s in splits.values())


def runs_text(campaign: Campaign) -> str:
    """``41 models (149 jobs, seed 0, ...)``: a campaign's catalog and checkpoint policy."""
    seeds = sorted({int(j.get("seed", 0)) for j in campaign.plan.get("jobs", [])})
    policy = (
        "the final checkpoint after the full step budget, no early stopping"
        if campaign.checkpoint == "final"
        else "checkpoint selection and early stopping on validation mud-pumping IoU with "
        "pixels pooled over all validation images"
    )
    return (
        f"{len(campaign.models)} models ({campaign.total} jobs, seed "
        f"{', '.join(map(str, seeds)) or '?'}, {policy})"
    )


@dataclass
class EarlierRun:
    """A superseded campaign of a split, scored with ``rad_report`` for details.md."""

    split: Split
    campaign: Campaign
    report: rad_report.Report | None
    error: str | None
    costs: dict[tuple[str, str, str], Cost] = field(default_factory=dict)

    @property
    def csv(self) -> str:
        return f"earlier-runs/{self.campaign.root.name}.csv"


def earlier_section(run: EarlierRun) -> list[str]:
    c = run.campaign
    heading = earlier_heading(run.split, c)
    current = run.split.current
    lines = [
        f"## {heading}",
        "",
        f"Source `{c.root}` (code `{str(c.record.get('code_sha', '?'))[:12]}`), {c.done} of "
        f"{c.total} runs done. Replaced on the study page by `{current.root.name}` "
        f"({current.describe()}). Best starting point per model by train-camera mud-pumping "
        "IoU on the same validation images"
        + (
            "; the checkpoint itself was selected (and training early stopped) on those images, "
            "by the mud IoU with pixels pooled over all of them, so these numbers are optimistic"
            if c.checkpoint == "best"
            else ""
        )
        + ". Percent, every class counted only on the images that contain it."
        + (f" [All its runs (CSV)]({run.csv})." if run.report is not None else ""),
        "",
    ]
    if run.report is None:
        return [*lines, f"Not rendered this cycle: {run.error}", ""]
    return [*lines, *split_table(run.report, c.arm, run.costs, {}, c)]


def study_details(
    arms: dict[str, dict],
    report: rad_report.Report | None,
    report_error: str | None,
    forks: list[dict],
    datasets: Path,
    guides: frozenset[Path],
    splits: dict[str, Split] | None = None,
    earlier: list[EarlierRun] | None = None,
) -> str:
    """The full study record (``details.md``) behind the short study page."""
    splits, earlier = splits or {}, earlier or []
    guide = guide_ref(GUIDE, "Dataset preparation and split decisions", guides)
    if legacy_layout(splits):
        trained = (
            "trained two ways with the same 10-model x 4-initialization-path catalog (40 jobs "
            "per arm, seed 0, checkpoint selection and early stopping on validation mud-pumping "
            "IoU with pixels pooled over all validation images), plus Paul "
            "Stanik's two paper recipes, retrained by us with his fork code."
        )
    else:
        trained = (
            "trained two ways, "
            + "; ".join(f"`{arm}` with {runs_text(s.current)}" for arm, s in splits.items())
            + ", plus Paul Stanik's two paper recipes, retrained by us with his fork code."
            + "".join(
                f" The [{earlier_heading(run.split, run.campaign)[0].lower()}"
                f"{earlier_heading(run.split, run.campaign)[1:]}]"
                f"({anchor(earlier_heading(run.split, run.campaign))}) is summarised below."
                for run in earlier
            )
        )
    lines = [
        "# RAD 9/24 study: full details",
        "",
        "[Short summary](README.md) · " + guide_ref(CASE_GUIDE, "Mud IoU case document", guides),
        "",
        "The `rad_9_24_2026` delivery (314 rail images with polygon labels) " + trained + " "
        "The question: how much "
        "does Paul's random stratified split flatter the results compared with a scene-grouped "
        "split (`paul` vs `fixed-grouped`)? The two arms also differ in labels. "
        + rad_report.LABEL_ARM_STOPPED_POOLED
        + " Validation only; the test split is held out and never read. Mud-pumping IoU and "
        "mIoU below count each class only on the validation images that contain it (see *How "
        "to read this*); the pixel-pooled numbers are in the CSV.",
        "",
        guide + (" · [Comparison CSV](rad-comparison.csv)" if report is not None else ""),
        "",
        "## Arms (splits) and progress",
        "",
    ]
    rows = []
    for arm in rad_report.ARMS:
        labels, split = ARM_TEXT[arm]
        data = arms.get(arm)
        if data is None:
            rows.append([f"`{arm}`", labels, split, "—", "not initialized", "—"])
            continue
        jobs = data["jobs"]
        status = Counter(r["status"] for r in jobs)
        sizes = reports.split_sizes(data["campaign"])
        others = ", ".join(f"{k} {v}" for k, v in sorted(status.items()) if k != "completed")
        group = splits.get(arm)
        several = group is not None and (group.earlier or group.upcoming)
        rows.append(
            [
                f"[`{arm}`]({arm}/README.md)"
                + (f": {group.current.describe()}, shown" if group and several else ""),
                labels,
                f"{split}; {sizes['train']}/{sizes['val']}/{sizes['test']}",
                f"{status.get('completed', 0)}/{len(jobs)}",
                others or "—",
                f"`{data['campaign'].get('code_sha', '?')[:12]}`",
            ]
        )
        if group is None:
            continue
        for campaign, role in [
            *((c, "superseded") for c in group.earlier),
            *((c, "shown once its first run finishes") for c in group.upcoming),
        ]:
            sizes = reports.split_sizes(campaign.record)
            others = ", ".join(
                f"{k} {v}" for k, v in sorted(campaign.statuses.items()) if k != "completed"
            )
            rows.append(
                [
                    f"`{arm}`: {campaign.describe()}, {role}",
                    labels,
                    f"{split}; {sizes['train']}/{sizes['val']}/{sizes['test']}",
                    f"{campaign.done}/{campaign.total}",
                    others or "—",
                    f"`{str(campaign.record.get('code_sha', '?'))[:12]}`",
                ]
            )
    headers = ["arm", "labels", "split; train/val/test", "completed", "other jobs", "code"]
    lines += reports.table(headers, rows).splitlines()
    lines += [
        "",
        "Each arm page has the per-model reports, `results.csv`, `status.json` and the "
        "downloadable evidence exactly as for [RTIS v2](../paul-test-rtis/v2/README.md). Fork "
        f"progress is in the [paper-recipe section]({FORK_ANCHOR}).",
        "",
    ]
    lines += caveats(report, {arm: s.current.checkpoint for arm, s in splits.items()})
    lines += label_defects(datasets)
    if report is not None:
        lines += [*comparison_markdown(report, set(arms)).splitlines(), ""]
    else:
        lines += [
            "## Cab-view comparison (validation split)",
            "",
            f"Not rendered this cycle: {report_error}",
            "",
        ]
    for run in earlier:
        lines += earlier_section(run)
    lines += fork_section(forks)
    lines += [
        "## About this page",
        "",
        "Generated by `scripts/publish_rad_results.py` from the HDRFS campaign records, the "
        "prepared datasets and the fork run directories, which it only reads. Absolute paths "
        "are provenance on HDRFS, not links. Prediction masks are not published.",
        "",
        f"- Publisher code: `{publisher_version()}`",
        f"- Campaign records last changed: {records_changed(arms)}",
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


# ----------------------------------------------------------------------------- cross-validation


@dataclass
class CrossValidation:
    """cv_report's report of the CV campaign plus every planned model x protocol x seed."""

    report: cv_report.Report
    planned: list[tuple[str, str, int]]
    rows: list[dict[str, Any]] = field(default_factory=list)
    # Inference cost per model x protocol x seed over its folds' performance records.
    costs: dict[tuple[str, str, int], Cost] = field(default_factory=dict)


def cv_why(error: Exception) -> str:
    if isinstance(error, cv_report.CvReportError):
        return str(error)
    return f"{type(error).__name__}: {error}"


def cv_build(root: Path, viewpoints: Path) -> CrossValidation:
    report = cv_report.build(root, viewpoints, None, [])
    report.table_subsets = [s for s in CV_TABLE_SUBSETS if s in report.subsets]
    jobs = read_json(root / "plan.json")["jobs"]
    planned = sorted({(j["model"], j["protocol"], int(j["seed"])) for j in jobs})
    cv = CrossValidation(report, planned)
    cv.rows = pooled_rows(cv)
    measured: dict[tuple[str, str, int], list[Cost]] = {}
    for job in jobs:
        path = root / "performance" / f"{job['name']}.json"
        cost = cost_of(read_json(path)) if path.is_file() else None
        if cost is not None:
            measured.setdefault((job["model"], job["protocol"], int(job["seed"])), []).append(cost)
    cv.costs = {key: c for key, found in measured.items() if (c := combined_cost(found))}
    return cv


def cv_rows(cv: CrossValidation) -> list[dict[str, Any]]:
    return cv.rows


def pooled_rows(cv: CrossValidation) -> list[dict[str, Any]]:
    """Per planned model x protocol x seed: folds done and the pooled primary (final) metrics."""
    groups = cv_report.groups_of(cv.report)
    rows = []
    for key in sorted(set(cv.planned) | set(groups)):
        runs = groups.get(key, {})
        rows.append(
            {
                "model": key[0],
                "protocol": key[1],
                "seed": key[2],
                "done": len(runs),
                "complete": bool(runs) and set(runs) == set(cv.report.folds),
                "pool": cv_report.pooled(runs, cv_report.PRIMARY, cv.report) if runs else None,
            }
        )
    return rows


def cv_value(row: dict[str, Any], subset: str, name: str) -> float | None:
    pool = row["pool"] or {}
    return (pool.get(subset) or {}).get(name)


def cv_jobs(cv: CrossValidation) -> tuple[int, int]:
    coverage = cv.report.coverage.values()
    return sum(c.get("completed", 0) for c in coverage), sum(sum(c.values()) for c in coverage)


def fold_caveat(cv: CrossValidation, short: bool = False) -> str | None:
    """A fold holding over half of the scored images with focus-class ground truth, on all
    images or on train-camera images (every such image weighs the same in the present-image
    metrics); None when no fold does or while a fold has no scored run yet. Counted from the
    scored images themselves (labels only, the same for every model)."""
    report, focus = cv.report, cv.report.focus
    scored = {run.fold for run in report.runs if cv_report.PRIMARY in run.images}
    if focus is None or not set(report.folds) <= scored:
        return None
    found = []
    for subset, kind in (("all", ""), (rad_report.CAB, "train-camera ")):
        if subset != "all" and subset not in report.subsets:
            continue
        by_fold = cv_report.focus_images(report, subset)
        total = sum(len(images) for images in by_fold.values())
        if not total:
            continue
        fold, images = max(by_fold.items(), key=lambda kv: (len(kv[1]), -kv[0]))
        if 2 * len(images) <= total:
            continue  # no fold dominates this subset's pooled numbers
        groups = sorted({i.group for i in images if i.group})
        where = (
            f", all from one scene (`{groups[0]}`)"
            if len(groups) == 1
            else f", from {len(groups)} scenes ({', '.join(f'`{g}`' for g in groups)})"
            if groups
            else ""
        )
        numbers = "all-images" if subset == "all" else "train-camera"
        one = len(groups) == 1
        found.append(
            (
                f"fold {fold} holds {len(images)} of the {total} scored {kind}images with "
                f"{focus}{where}",
                f"the {numbers} numbers mostly measure {'that scene' if one else 'those scenes'}",
                "it" if one else "them",
            )
        )
    if not found:
        return None
    if short:
        return "; ".join(f"{fact}, so {effect}" for fact, effect, _ in found) + "."
    return " ".join(
        f"{fact[0].upper()}{fact[1:]}. Pooled, {effect}, scored by models that never trained "
        f"on {it}."
        for fact, effect, it in found
    )


def cv_readme(cv: CrossValidation, guides: frozenset[Path]) -> str:
    """cv_report's page without its timestamp, under a plain summary of the primary results."""
    report = cv.report
    focus = (report.focus or "focus class").capitalize()
    done, total = cv_jobs(cv)
    k = len(report.folds)
    spec = (report.spec or {}).get("report") or {}
    source = ((report.spec or {}).get("source") or {}).get("dataset")
    pool = (
        f"the {spec['scored_images']} scored images in {spec['cv_groups']} scenes"
        + (f" of `{source}`" if source else "")
        if spec
        else "the scored images"
    )
    rows = []
    for row in cv_rows(cv):
        mark = "" if row["complete"] else "*"

        def cell(subset: str, name: str, row: dict[str, Any] = row, mark: str = mark) -> str:
            value = cv_value(row, subset, name)
            return "—" if value is None else cv_report.pct(value) + mark

        rows.append(
            [
                f"`{row['model']}`",
                START.get(row["protocol"], row["protocol"])
                + (f", seed {row['seed']}" if len({p[2] for p in cv.planned}) > 1 else ""),
                f"{row['done']}/{k}",
                cell(rad_report.CAB, "focus_present_iou"),
                cell(rad_report.CAB, "focus_present_precision"),
                cell(rad_report.CAB, "focus_present_recall"),
                cell("all", "present_miou"),
            ]
        )
    with_focus = "mud" if report.focus == "mud-pumping" else report.focus
    n_cab = sum(len(i) for i in cv_report.focus_images(report, rad_report.CAB).values())
    headers = [
        "Model",
        "Starting point",
        "Folds done",
        f"{focus} IoU, train-camera images with {with_focus} (n={n_cab})",
        f"Precision, train-camera images with {with_focus}",
        f"Recall, train-camera images with {with_focus}",
        f"{MIOU}, all images",
    ]
    caveat = fold_caveat(cv)
    lines = [
        f"# RAD 9/24: cross-validation over scenes (`{report.campaign.get('dataset', '?')}`)",
        "",
        "[RAD 9/24 study](../README.md) · "
        + guide_ref(CV_GUIDE, "How the cross-validation works", guides, up="../../../")
        + " · [All metrics (CSV)](cv-report.csv)",
        "",
        "## Summary",
        "",
        f"Stratified group {k}-fold cross-validation: {pool} are divided into {k} folds of whole "
        "scenes, balanced on the rare classes. Each model trains on the other folds and is "
        "scored on its own, so every image is scored once by a model that never trained on its "
        "scene (*pooled* results average over all those images). The result is the final checkpoint "
        "after the full training budget, so nothing is picked on the scored images. The test "
        "images are never used.",
        "",
        f"Percent, final checkpoint. {done} of {total} runs done; `*` = not all folds done yet "
        "(pooled over the finished folds only, not comparable). Train-camera images: a forward "
        f"view from a camera on the train, the real use case. {focus} IoU is the per-image IoU "
        f"averaged over the scored images with {with_focus} (images without it are not "
        "counted); precision and recall sum pixels over those images; mIoU scores each class "
        "on the images that contain it, then averages over the classes.",
        "",
        *reports.table(headers, rows).splitlines(),
        "",
    ]
    if caveat:
        lines += [f"**Fold caveat:** {caveat}", ""]
    entries = []
    for row in cv_rows(cv):
        mark = "" if row["complete"] else "*"
        entries.append(
            (
                [f"`{row['model']}`", START.get(row["protocol"], row["protocol"]) + mark],
                (row["pool"] or {}).get("all"),
            )
        )
    lines += [
        f"## {PER_CLASS}",
        "",
        f"Pooled over all scored images, final checkpoint. {PER_CLASS_NOTE}",
        "",
        *per_class_table(["Model", "Starting point"], entries, pct=cv_report.pct),
        "",
    ]
    for line in cv_report.render(report, "").splitlines():
        if line.startswith(("Generated:", "# ")):
            continue
        if line.startswith("## "):
            line = "## Full report: " + line[3:]
        if line == "Every metric, subset, fold and checkpoint is in `cv-report.csv`.":
            line = (
                "Every metric, subset, fold and checkpoint is in [`cv-report.csv`](cv-report.csv)."
            )
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


# ----------------------------------------------------------------------------- study page


def median(values: list[float | None]) -> float | None:
    found = [v for v in values if v is not None]
    return statistics.median(found) if found else None


def best(values: list[float | None]) -> float | None:
    found = [v for v in values if v is not None]
    return max(found) if found else None


def spread(values: list[float | None]) -> str:
    if median(values) is None:
        return "—"
    return f"median {rad_report.pct(median(values))} (best {rad_report.pct(best(values))})"


# Inference memory of a performance record: the whole process including the CUDA context when
# recorded (``process_total_bytes``), else PyTorch's allocator peak reserved bytes, which
# exclude the context and are marked ALLOCATOR_MARK on the page.
TOTAL_MEMORY = "process_total_bytes"
ALLOCATOR_MEMORY = "peak_reserved_bytes"
ALLOCATOR_MARK = "†"
ALLOCATOR_NOTE = (
    f"{ALLOCATOR_MARK} Allocator only (PyTorch peak reserved memory in the speed benchmark): "
    "excludes the CUDA context (driver overhead, a few hundred MB)."
)
COST_HEADERS = ["Speed (FPS)", "GPU memory, total (GB)", "Parameters (M)"]


@dataclass(frozen=True)
class Cost:
    """Inference cost from a performance record (or the mean/max over several)."""

    fps: float
    memory_bytes: int | None
    total_memory: bool  # memory_bytes includes the CUDA context
    parameters: int | None

    def cells(self) -> list[str]:
        memory = "—"
        if self.memory_bytes is not None:
            memory = f"{self.memory_bytes / 1e9:.2f}" + (
                "" if self.total_memory else ALLOCATOR_MARK
            )
        params = "—" if self.parameters is None else f"{self.parameters / 1e6:.1f}"
        return [f"{self.fps:.1f}", memory, params]


def cost_of(perf: dict) -> Cost | None:
    measurements = perf.get("measurements") or {}
    fps = (measurements.get("latency") or {}).get("fps")
    if perf.get("status") != "complete" or fps is None:
        return None
    total = measurements.get(TOTAL_MEMORY)
    memory = total if total is not None else measurements.get(ALLOCATOR_MEMORY)
    return Cost(
        float(fps),
        None if memory is None else int(memory),
        total is not None,
        (perf.get("model") or {}).get("parameter_count"),
    )


def combined_cost(costs: list[Cost]) -> Cost | None:
    """Several measurements of one model (e.g. one per CV fold): mean FPS, largest memory."""
    if not costs:
        return None
    memories = [c for c in costs if c.memory_bytes is not None]
    top = max(memories, key=lambda c: (c.memory_bytes or 0, not c.total_memory), default=None)
    return Cost(
        statistics.fmean(c.fps for c in costs),
        None if top is None else top.memory_bytes,
        top is not None and all(c.total_memory for c in memories),
        costs[0].parameters,
    )


def cost_cells(cost: Cost | None) -> list[str]:
    return cost.cells() if cost is not None else ["—"] * len(COST_HEADERS)


def allocator_note(rows: list[list[str]]) -> list[str]:
    """The footnote for marked memory cells, when a table has any."""
    return [ALLOCATOR_NOTE, ""] if any(ALLOCATOR_MARK in c for r in rows for c in r) else []


def performance_of(arms: dict[str, dict]) -> tuple[dict[tuple[str, str, str], Cost], str | None]:
    """Inference cost per (split, model, protocol) and the benchmark settings, from the arms'
    performance records."""
    costs, settings = {}, None
    for arm, data in arms.items():
        for row in data["jobs"]:
            perf = row.get("performance") or {}
            cost = cost_of(perf)
            if cost is None:
                continue
            costs[(arm, row["model"], row["protocol"])] = cost
            contract, gpu = perf.get("contract") or {}, (perf.get("hardware") or {}).get("gpu_name")
            shape = contract.get("input_shape_nchw") or []
            if settings is None and gpu and len(shape) == 4:
                precision = str(contract.get("precision", "?")).removesuffix("_autocast").upper()
                settings = (
                    f"model-only forward passes on one {gpu}, batch "
                    f"{contract.get('batch_size', shape[0])}, {shape[2]}x{shape[3]} input, "
                    f"{precision}"
                    + (
                        ", without data loading or pre-processing"
                        if contract.get("includes_preprocessing") is False
                        else ""
                    )
                )
    return costs, settings


def split_results(report: rad_report.Report | None, arm: str) -> list[rad_report.Result]:
    if report is None:
        return []
    return [r for r in report.results if r.source == "segmentary" and r.arm == arm]


def best_per_model(results: list, value) -> list:
    """Per model the result with the highest ``value`` (None last), best model first."""
    chosen: dict[str, Any] = {}
    for result in results:
        model = result["model"] if isinstance(result, dict) else result.model
        current = chosen.get(model)
        if current is None or (value(result) or -1.0) > (value(current) or -1.0):
            chosen[model] = result
    return sorted(chosen.values(), key=lambda r: -(value(r) or -1.0))


def model_link(model: str, arm: str, files: dict[str, str | bytes]) -> str:
    page = f"{arm}/models/{model}/README.md"
    return f"[{model}]({page})" if page in files else model


ONLY_START = " (only starting point)"


def split_table(
    report: rad_report.Report,
    arm: str,
    costs: dict[tuple[str, str, str], Cost],
    files: dict[str, str | bytes],
    campaign: Campaign | None = None,
) -> list[str]:
    """Every model of a split with its best starting point. With the ``campaign`` the model
    is marked ``*`` while some of its planned starting points are unfinished, and a model
    planned from a single starting point says so."""
    results = split_results(report, arm)
    planned = campaign.models if campaign is not None else {}
    # "Only starting point" means fewer than the other models of the split have.
    widest = max((len(p) for p in planned.values()), default=0)
    finished: dict[str, set[str]] = {}
    for r in results:
        finished.setdefault(r.model, set()).add(r.protocol)

    def cab(r: rad_report.Result) -> float | None:
        return rad_report.metric(r, rad_report.CAB, "mud_present_iou")

    rows = [
        [
            model_link(r.model, arm, files)
            + ("*" if not set(planned.get(r.model, [])) <= finished[r.model] else ""),
            START.get(r.protocol, r.protocol)
            + (ONLY_START if len(planned.get(r.model, [])) == 1 < widest else ""),
            rad_report.pct(cab(r)),
            rad_report.pct(rad_report.metric(r, "all", "mud_present_iou")),
            rad_report.pct(rad_report.metric(r, "all", "present_miou")),
            *cost_cells(costs.get((arm, r.model, r.protocol))),
        ]
        for r in best_per_model(results, cab)
    ]
    if not rows:
        return ["No finished run yet.", ""]
    headers = ["Model", "Best starting point", MUD_CAB, MUD_ALL, MIOU, *COST_HEADERS]
    waiting = sorted(m for m in planned if m not in finished)
    pending = []
    if waiting:
        pending = [
            (
                "No finished run yet: " + ", ".join(f"`{m}`" for m in waiting) + "."
                if len(waiting) <= 10
                else f"{len(waiting)} more models have no finished run yet."
            ),
            "",
        ]
    return [*reports.table(headers, rows).splitlines(), "", *allocator_note(rows), *pending]


def cv_table(cv: CrossValidation) -> list[str]:
    k = len(cv.report.folds)
    rows = cv_rows(cv)
    # Best starting point per model among the finished ones; unfinished only when none is.
    finished = {r["model"] for r in rows if r["complete"]}
    candidates = [r for r in rows if r["complete"] or r["model"] not in finished]

    def cab(r: dict[str, Any]) -> float | None:
        return cv_value(r, rad_report.CAB, "focus_present_iou")

    out = []
    for r in best_per_model(candidates, cab):
        mark = "" if r["complete"] else "*"

        def cell(subset: str, name: str, r: dict[str, Any] = r, mark: str = mark) -> str:
            value = cv_value(r, subset, name)
            return "—" if value is None else cv_report.pct(value) + mark

        out.append(
            [
                r["model"],
                START.get(r["protocol"], r["protocol"]) if r["done"] else "—",
                cell(rad_report.CAB, "focus_present_iou"),
                cell("all", "focus_present_iou"),
                cell("all", "present_miou"),
                *cost_cells(cv.costs.get((r["model"], r["protocol"], r["seed"]))),
                f"{r['done']}/{k}",
            ]
        )
    headers = ["Model", "Best starting point", MUD_CAB, MUD_ALL, MIOU, *COST_HEADERS, "Folds done"]
    return [*reports.table(headers, out).splitlines(), "", *allocator_note(out)]


def key_table(
    report: rad_report.Report | None,
    cv: CrossValidation | None,
    splits: dict[str, Split] | None = None,
) -> tuple[list[str], dict[str, list[float | None]]]:
    """One row per split: median (best) over every finished model x starting point."""
    rows, cab_values = [], {}
    for arm in rad_report.ARMS:
        results = split_results(report, arm)
        cab = [rad_report.metric(r, rad_report.CAB, "mud_present_iou") for r in results]
        cab_values[arm] = cab
        split = (splits or {}).get(arm)
        runs = str(len(results)) if results else "—"
        if results and split is not None and len(results) < split.current.total:
            runs = f"{len(results)} of {split.current.total} done"
        rows.append(
            [
                SPLIT_NAME[arm],
                runs,
                spread([rad_report.metric(r, "all", "mud_present_iou") for r in results]),
                spread(cab),
                spread([rad_report.metric(r, "all", "present_miou") for r in results]),
            ]
        )
    planned = cv_rows(cv) if cv is not None else []
    finished = [r for r in planned if r["complete"]]
    cab_values["cv"] = [cv_value(r, rad_report.CAB, "focus_present_iou") for r in finished]
    rows.append(
        [
            "Cross-validation over scenes",
            f"{len(finished)} of {len(planned)} with all folds done" if planned else "—",
            spread([cv_value(r, "all", "focus_present_iou") for r in finished]),
            spread(cab_values["cv"]),
            spread([cv_value(r, "all", "present_miou") for r in finished]),
        ]
    )
    headers = ["Split", "Model runs", MUD_ALL, MUD_CAB, MIOU]
    return reports.table(headers, rows).splitlines(), cab_values


def takeaway(report: rad_report.Report | None, cab_values: dict[str, list]) -> str:
    comp = report.composition if report is not None else {}
    paul = comp.get("paul")
    parts = []
    all_paul = [
        rad_report.metric(r, "all", "mud_present_iou") for r in split_results(report, "paul")
    ]
    if report is not None and paul and median(all_paul) is not None:
        text = (
            f"Paul's split looks good (median {rad_report.pct(median(all_paul))} on all images "
            "with mud-pumping"
        )
        if median(cab_values.get("paul", [])) is not None:
            text += f", {rad_report.pct(median(cab_values['paul']))} on train-camera ones"
        text += ")"
        if paul["val_groups"] and paul["val_groups_in_train"] == paul["val_groups"]:
            text += " because every validation scene of that split also has images in training"
        with_mud = sum(v["with_mud"] for v in paul["viewpoints"].values())
        if paul["group_images_with_mud"]:
            text += (
                f"; {paul['group_images_with_mud']} of its {with_mud} validation images with "
                f"mud-pumping come from one scene, `{rad_report.subsets.EXCLUDED_GROUP}`"
            )
        parts.append(text + ".")
    unseen = []
    if median(cab_values.get("fixed-grouped", [])) is not None:
        unseen.append(f"{spread(cab_values['fixed-grouped'])} with the scene-grouped split")
    if median(cab_values.get("cv", [])) is not None:
        unseen.append(f"{spread(cab_values['cv'])} in cross-validation")
    if unseen:
        parts.append(
            "On scenes the models never trained on, mud-pumping IoU on train-camera images is "
            + " and ".join(unseen)
            + "."
        )
    return " ".join(parts) or "No finished run yet."


def paper_model(forks: list[dict]) -> list[str]:
    from scripts.paul_forks.score_predictions import ScoreError, parse_label

    parsed: dict[tuple[str, str], dict[str, dict]] = {}
    for row in forks:
        try:
            base, arm, recipe = parse_label(row["label"])
        except ScoreError:
            continue
        if row["status"].startswith("excluded"):
            continue
        parsed.setdefault((base, recipe), {}).setdefault(arm, row)
    keys = [k for k, by_arm in parsed.items() if any(r["result"] for r in by_arm.values())]
    if not keys:
        keys = [k for k in parsed if k[0] == "paper-hrnet__rs19-paul"][:1]
    rows = []
    for base, recipe in sorted(keys):
        name = FORK_BASE.get(base, base)
        if not recipe.startswith("paul-shared"):
            name += f" (recipe variant `{recipe}`)"
        for arm in rad_report.ARMS:
            entry = parsed[(base, recipe)].get(arm)
            result = entry["result"] if entry else None
            if result is None:
                status = entry["status"] if entry else "not started"
                if "not yet scored" in status:
                    status = "trained, not scored yet"
                elif not status.startswith("not"):
                    status = f"not scored yet ({status})"
                rows.append([name, SPLIT_NAME[arm], status, "—", "—"])
                continue
            rows.append(
                [
                    name,
                    SPLIT_NAME[arm],
                    rad_report.pct(rad_report.metric(result, rad_report.CAB, "mud_present_iou")),
                    rad_report.pct(rad_report.metric(result, "all", "mud_present_iou")),
                    rad_report.pct(rad_report.metric(result, "all", "present_miou")),
                ]
            )
    if not rows:
        return ["No retraining of Paul's recipes has started yet.", ""]
    headers = ["Paul's recipe, retrained by us", "Split", MUD_CAB, MUD_ALL, MIOU]
    return [*reports.table(headers, rows).splitlines(), ""]


def dataset_facts(arms: dict[str, dict], datasets: Path) -> tuple[int | None, int | None]:
    images = None
    for data in arms.values():
        images = sum(reports.split_sizes(data["campaign"]).values())
        break
    classes = None
    for arm in rad_report.ARMS:
        path = datasets / rad_report.DATASET.format(arm=arm) / "classes.json"
        if path.is_file():
            classes = len(read_json(path)["classes"])
            break
    return images, classes


def study_readme(
    arms: dict[str, dict],
    report: rad_report.Report | None,
    report_error: str | None,
    forks: list[dict],
    datasets: Path,
    files: dict[str, str | bytes],
    guides: frozenset[Path],
    cv: CrossValidation | None,
    cv_error: str | None,
    splits: dict[str, Split] | None = None,
    earlier: list[EarlierRun] | None = None,
) -> str:
    """The short study page: what was tested, the key result, results per split, caveats."""
    splits, earlier = splits or {}, earlier or []
    images, classes = dataset_facts(arms, datasets)
    models = sorted({r.model for r in report.results if r.source == "segmentary"}) if report else []
    starts = (
        sorted({r.protocol for r in report.results if r.source == "segmentary"}) if report else []
    )
    # Models planned from fewer starting points than the others (e.g. recipe weights only).
    planned: dict[str, set[str]] = {}
    for split in splits.values():
        for model, protocols in split.current.models.items():
            planned.setdefault(model, set()).update(protocols)
    widest = max((len(planned[m]) for m in models if m in planned), default=0)
    fewer = sorted(m for m in models if m in planned and len(planned[m]) < widest)
    each = "each from"
    if fewer:
        starts = sorted(set(starts) | {p for m in models for p in planned.get(m, ())})
        only = sorted({p for m in fewer for p in planned[m]})
        each = "each from up to"
        fewer_text = (
            f"; {len(fewer)} of them only from {START.get(only[0], only[0])}"
            if len(only) == 1 and all(len(planned[m]) == 1 for m in fewer)
            else f"; {len(fewer)} of them from fewer"
        )
    else:
        fewer_text = ""
    data = "Paul Stanik's `rad_9_24_2026` rail images"
    if images and classes:
        data = f"Paul Stanik's `rad_9_24_2026` set: {images} rail images labelled with {classes} classes"
    k = len(cv.report.folds) if cv else 5
    lines = [
        "# RAD 9/24: can segmentation models find mud-pumping in rail scenes they have not seen?",
        "",
        "## What we tested",
        "",
        f"- **Data:** {data}, including mud-pumping (the track defect we look for).",
        "- **Question:** how well do models find mud-pumping in scenes (videos) they did *not* "
        "see in training? We score mud-pumping IoU (overlap of predicted and true mud-pumping "
        "pixels, in percent; 100 = perfect) on each validation image that contains mud-pumping "
        "and average it over those images: all of them, and the train-camera ones (a forward "
        "view from a camera on the train, the real use case).",
        "- **Three ways to split the images into training and validation:** (a) Paul's split, "
        "random by image, so frames of one video can be on both sides; (b) a scene-grouped "
        "split that keeps whole scenes on one side; (c) "
        f"{k}-fold cross-validation over scenes, where every scene is scored once by a model "
        "that never trained on it (the most reliable).",
        (
            f"- **Models:** {len(models)} segmentation models, {each} {len(starts)} starting "
            f"points (pretraining before training on these images){fewer_text}. Test images are "
            "never used."
            if models
            else "- **Models:** segmentation models from several starting points (pretraining "
            "before training on these images). Test images are never used."
        ),
        "",
        "## Key result",
        "",
    ]
    table, cab_values = key_table(report, cv, splits)
    lines += [
        takeaway(report, cab_values),
        "",
        *table,
        "",
        "Median and best over every finished model and starting point of each split. mIoU "
        "scores each class on the images that contain it, then averages over the classes.",
        "",
        "## Results by split",
        "",
        "Each table shows every model with its best starting point, picked by train-camera "
        "mud-pumping IoU on the same validation images (so slightly flattering). Starting points: "
        + ", ".join(START.values())
        + " (public street and rail datasets).",
    ]
    costs, settings = performance_of(arms)
    if settings:
        lines[-1] += f" Speed and memory: {settings}."
    lines.append("")
    for arm in rad_report.ARMS:
        data_arm = arms.get(arm)
        lines += [f"### {SPLIT_NAME[arm]}", ""]
        sizes = reports.split_sizes(data_arm["campaign"]) if data_arm else None
        comp = (report.composition if report else {}).get(arm) or {}
        if arm == "paul":
            what = "Images assigned to training and validation at random, balanced by class"
            if comp.get("val_groups"):
                what += (
                    f"; {comp['val_groups_in_train']} of its {comp['val_groups']} validation "
                    "scenes also have images in training"
                )
        else:
            what = "Whole scenes kept on one side"
            if comp.get("val_groups"):
                what += (
                    f"; {comp['val_groups_in_train']} of its {comp['val_groups']} validation "
                    "scenes have images in training"
                )
        if sizes:
            what += f" ({sizes['train']} training, {sizes['val']} validation images)"
        what += "."
        split = splits.get(arm)
        current = split.current if split else None
        if current is not None and not legacy_layout(splits):
            what += f" {len(current.models)} models"
            what += (
                ", each at its final checkpoint after the full training budget, so nothing is "
                "picked on the validation images."
                if current.checkpoint == "final"
                else ", each at its best-on-validation checkpoint (flattering)."
            )
        if current is not None and current.done < current.total:
            what += (
                f" {current.done} of {current.total} runs done; `*` = not all starting points "
                "of that model done yet."
            )
        link = (
            f" [Every model and starting point]({arm}/README.md); "
            f"[IoU of every class]({arm}/README.md{PER_CLASS_ANCHOR})."
            if data_arm
            else ""
        )
        lines += [what + link, ""]
        if report is None:
            lines += [f"Not available this cycle: {report_error}", ""]
        else:
            lines += split_table(report, arm, costs, files, current)
        for upcoming in split.upcoming if split else []:
            lines += [
                f"A newer run on this split ({upcoming.describe()}) has {upcoming.done} of "
                f"{upcoming.total} runs done; this table switches to it once its first run "
                "finishes.",
                "",
            ]
        for run in earlier:
            if run.campaign.arm == arm:
                heading = earlier_heading(run.split, run.campaign)
                lines += [
                    f"The {heading[0].lower()}{heading[1:]} is in "
                    f"[the details]({DETAILS}{anchor(heading)}).",
                    "",
                ]
    lines += ["### Cross-validation over scenes", ""]
    cv_page = f"{CV_DIR}/README.md" in files
    if cv is not None:
        done, total = cv_jobs(cv)
        lines += [
            f"The scenes of the scene-grouped data are divided into {k} folds; each model "
            f"trains on {k - 1} folds and is scored on the remaining one, so every image is "
            "scored once by a model that never saw its scene. The result is the final "
            "checkpoint, so nothing is picked on the scored images. "
            f"{done} of {total} runs done; `*` = not all folds done yet. "
            f"[Full report]({CV_DIR}/README.md); "
            f"[IoU of every class]({CV_DIR}/README.md{PER_CLASS_ANCHOR}).",
            "",
            *cv_table(cv),
        ]
    elif cv_error:
        lines += [
            f"Not refreshed this cycle: {cv_error}."
            + (f" The [last published report]({CV_DIR}/README.md) is kept." if cv_page else ""),
            "",
        ]
    else:
        lines += ["Not published yet.", ""]
    lines += [
        "## Paul's paper model",
        "",
        "Paul's own recipes, retrained by us with his code on each split and scored with the "
        "same code as above. Paul's finished model is never scored here: it may have trained on "
        "our validation images.",
        "",
        *paper_model(forks),
    ]
    checkpoints = {arm: s.current.checkpoint for arm, s in splits.items()}
    lines += ["## Caveats", "", *short_caveats(report, cv, checkpoints)]
    details = [
        *(
            f"[{SPLIT_NAME[a]}: every model and starting point]({a}/README.md)"
            for a in rad_report.ARMS
            if a in arms
        ),
        *(
            [f"[Cross-validation report]({CV_DIR}/README.md) and its [CSV]({CV_DIR}/cv-report.csv)"]
            if cv_page
            else []
        ),
        guide_ref(CASE_GUIDE, "Why Paul's split looks so good (case document)", guides),
        f"[Full details]({DETAILS}): label defects in the delivered masks, all comparison "
        "tables, every retraining run of Paul's recipes, provenance",
        *(["[Comparison CSV](rad-comparison.csv)"] if report is not None else []),
        guide_ref(GUIDE, "Dataset preparation and split decisions", guides),
        f"Generated by `scripts/publish_rad_results.py` (code `{publisher_version()}`) from the "
        f"HDRFS records, which it only reads; records last changed {records_changed(arms)}.",
    ]
    lines += ["## Details", "", *(f"- {d}" for d in details), ""]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def selection_caveat(checkpoints: dict[str, str]) -> str:
    """Which splits report a checkpoint chosen on their validation images; the
    "selected on validation" caveat is never applied to a final-checkpoint split."""
    best = [a for a in rad_report.ARMS if checkpoints.get(a, "best") == "best"]
    final = [SPLIT_PHRASE[a] for a in rad_report.ARMS if a not in best] + ["cross-validation"]
    final_text = " and ".join(final) + (" reports" if len(final) == 1 else " report")
    final_text += " the final checkpoint"
    if len(final) > 1:
        final_text += " after the full training budget, so nothing is picked on their scored images"
    if not best:
        return f"- {final_text[0].upper()}{final_text[1:]}."
    names = " and ".join(
        SPLIT_NAME[best[0]] if i == 0 else SPLIT_PHRASE[a] for i, a in enumerate(best)
    )
    return (
        f"- {names} {'reports' if len(best) == 1 else 'report'} the checkpoint that scored best "
        "on the same validation images (flattering), and that checkpoint was still selected on "
        "the older mud-pumping IoU with pixels pooled over all validation images (training is "
        f"unchanged); {final_text}."
    )


def short_caveats(
    report: rad_report.Report | None,
    cv: CrossValidation | None,
    checkpoints: dict[str, str] | None = None,
) -> list[str]:
    comp = report.composition if report is not None else {}
    lines = [
        "- One training run per model and starting point (seed 0): differences of a few points "
        "are not established.",
        "- Images without mud-pumping are not counted, so mud predicted on clean track does "
        "not lower the mud-pumping IoU.",
        selection_caveat(checkpoints or {}),
    ]
    counts = []
    for arm, c in comp.items():
        count = f"{SPLIT_PHRASE[arm]} {c['viewpoints'][rad_report.CAB]['with_mud']}"
        scenes = list(c.get("cab_mud_groups") or {})
        if arm != "paul" and len(scenes) == 1:
            count += f" (all from one scene, `{scenes[0]}`)"
        counts.append(count)
    if counts:
        lines.append(
            "- Few train-camera validation images have mud-pumping: " + ", ".join(counts) + "."
        )
    caveat = fold_caveat(cv, short=True) if cv is not None else None
    if caveat:
        lines.append("- In cross-validation, " + caveat)
    lines.append(
        "- Paul's split and the scene-grouped split also differ in labels (Paul's masks vs our "
        "re-render); scenes are grouped by eye, not from recording records."
    )
    return [*lines, ""]


def publisher_version() -> str:
    """The frozen snapshot's commit (``SNAPSHOT_COMMIT``), else the code checkout's HEAD."""
    marker = CODE / "SNAPSHOT_COMMIT"
    if marker.is_file():
        return marker.read_text().strip()[:12] or "unrecorded"
    try:
        return git(CODE, "rev-parse", "--short=12", "HEAD").strip()
    except (GitError, OSError):
        return "unrecorded"


def records_changed(arms: dict[str, dict]) -> str:
    """Newest campaign state-record mtime (deterministic while nothing changes)."""
    times = [
        path.stat().st_mtime
        for data in arms.values()
        if data.get("root")
        for path in [
            Path(data["root"]) / "campaign.json",
            *sorted((Path(data["root"]) / "state").glob("*.json")),
        ]
        if path.is_file()
    ]
    if not times:
        return "unknown"
    return datetime.fromtimestamp(max(times), ZoneInfo("America/Los_Angeles")).strftime(
        "%Y-%m-%d %I:%M %p %Z"
    )


def caveats(
    report: rad_report.Report | None, checkpoints: dict[str, str] | None = None
) -> list[str]:
    """details.md's caveats; ``checkpoints`` is each split's primary checkpoint."""
    comp = report.composition if report else {}
    finals = [a for a in rad_report.ARMS if (checkpoints or {}).get(a) == "final"]
    selected = [a for a in rad_report.ARMS if a not in finals]
    optimistic = (
        "- **Optimistic validation numbers.** Checkpoints are selected (and training early "
        "stopped) on the same val split that is reported, by the mud IoU with pixels pooled over "
        "all val images rather than the present-image mud IoU shown; fork runs pick their epoch "
        "on that split too."
    )
    if finals:
        optimistic = (
            "- **Optimistic validation numbers.** "
            + (
                f"For {' and '.join(f'`{a}`' for a in selected)} checkpoints are selected (and "
                "training early stopped) on the same val split that is reported, by the mud IoU "
                "with pixels pooled over all val images rather than the present-image mud IoU "
                "shown; fork runs pick their epoch on that split too. "
                if selected
                else "Fork runs pick their epoch on the val split that is reported. "
            )
            + " and ".join(f"`{a}`" for a in finals)
            + (" reports" if len(finals) == 1 else " report")
            + " the final checkpoint after the full step budget (no early stopping), so nothing "
            "is selected on the val split it is scored on."
        )
    cab = ", ".join(
        f"`{arm}` n={c['viewpoints']['cab-view']['with_mud']}" for arm, c in comp.items()
    )
    shared = ", ".join(
        f"`{arm}` {c['val_groups_in_train']} of {c['val_groups']}"
        for arm, c in comp.items()
        if arm != "fixed-grouped"
    )
    return [
        "## Caveats",
        "",
        "- **Single seed.** Every result is one training run (seed 0); there are no repeats or "
        "confidence intervals, so differences of a few IoU points are not established.",
        optimistic,
        "- **Small cab-view subsets.** Val images with mud ground truth behind the "
        "deployment-relevant cab-view mud IoU: " + (cab or "not available yet") + ".",
        "- **The stratified split shares scenes.** Frames of one recording can sit in train and "
        "val; scene groups of the val split that also have train images: "
        + (shared or "not available yet")
        + ". `paul`-arm numbers measure same-recording generalisation; only "
        "`fixed-grouped` keeps scene groups apart (groups are visually assigned).",
        "",
    ]


def render_tree(
    campaigns: list[Path],
    fork_runs: Path | None,
    datasets: Path,
    viewpoints: Path,
    guides: frozenset[Path] | None = None,
    cv_campaign: Path | None = None,
    cv_previous: dict[str, str | bytes] | None = None,
) -> tuple[dict[str, str | bytes], str | None, str | None]:
    """All files of the published tree (paths relative to it), any comparison error and any
    cross-validation error. ``guides`` are the guide pages the clone carries (default: all).
    When the CV report fails, ``cv_previous`` (the published ``cross-validation/`` files) is
    kept as it is."""
    guides = frozenset((GUIDE, CASE_GUIDE, CV_GUIDE)) if guides is None else guides
    files: dict[str, str | bytes] = {}
    arms: dict[str, dict] = {}
    splits = choose([campaign_of(r) for r in campaigns if (r / "campaign.json").is_file()])
    roots = [split.current.root for split in splits.values()]
    for arm, split in splits.items():
        arms[arm] = reports.capture(split.current.root)
    report, error = None, None
    try:
        report = rad_report.build(roots, fork_runs, datasets, viewpoints, [])
        files["rad-comparison.csv"] = rad_report.csv_text(report)
    except (rad_report.ReportError, ValueError, OSError, KeyError) as exc:
        error = rad_report.why(exc)
    for arm, split in splits.items():
        files.update(arm_files(arms[arm], arm, report))
        arms[arm] = {**arms[arm], "root": str(split.current.root)}
    earlier = earlier_runs(splits, datasets, viewpoints)
    for run in earlier:
        if run.report is not None:
            files[run.csv] = rad_report.csv_text(run.report)
    forks = fork_rows(fork_runs if fork_runs and fork_runs.is_dir() else None, report)
    cv, cv_error = None, None
    cv_files: dict[str, str | bytes]
    if cv_campaign is not None:
        try:
            cv = cv_build(cv_campaign, viewpoints)
            cv_files = {
                f"{CV_DIR}/README.md": cv_readme(cv, guides),
                f"{CV_DIR}/cv-report.csv": cv_report.csv_text(cv.report),
            }
        except Exception as exc:  # any failure keeps the published pages; retried next cycle
            cv, cv_error = None, cv_why(exc)
            cv_files = dict(cv_previous or {})
        files.update(cv_files)
    files[DETAILS] = study_details(arms, report, error, forks, datasets, guides, splits, earlier)
    files["README.md"] = study_readme(
        arms, report, error, forks, datasets, files, guides, cv, cv_error, splits, earlier
    )
    check_paths(files)
    return files, error, cv_error


def earlier_runs(splits: dict[str, Split], datasets: Path, viewpoints: Path) -> list[EarlierRun]:
    """Every superseded campaign with a finished run, scored on its own; a failure is shown in
    its details section and never stops the cycle."""
    out = []
    for split in splits.values():
        for campaign in split.earlier:
            if not campaign.done:
                continue
            report, error = None, None
            try:
                report = rad_report.build([campaign.root], None, datasets, viewpoints, [])
            except (rad_report.ReportError, ValueError, OSError, KeyError) as exc:
                error = rad_report.why(exc)
            costs = {}
            for job in campaign.plan.get("jobs", []):
                path = campaign.root / "performance" / f"{job['name']}.json"
                cost = cost_of(read_json(path)) if path.is_file() else None
                if cost is not None:
                    costs[(campaign.arm, job["model"], job["protocol"])] = cost
            out.append(EarlierRun(split, campaign, report, error, costs))
    return out


def published_cv(checkout: Path) -> dict[str, str | bytes]:
    """The cross-validation pages on the remote branch, to keep when this cycle's CV fails."""
    root = checkout / TREE / CV_DIR
    if not root.is_dir():
        return {}
    return {
        f"{CV_DIR}/{path.relative_to(root)}": path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def check_paths(files: dict[str, str | bytes]) -> None:
    for name in files:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError(f"unsafe published path {name!r}")
        if PREDICTION_PARTS & {p.lower() for p in path.parts[:-1]}:
            raise ValueError(f"prediction directory in published path {name!r}")
        if any(TEST_PART.search(p) for p in path.parts[:-1]):
            raise ValueError(f"test-split directory in published path {name!r}")
        if not path.name.lower().endswith(PUBLISHED_SUFFIXES):
            raise ValueError(f"unpublished file type {name!r}")


def docs_check(checkout: Path) -> None:
    """The repository's documentation tests, applied to the rendered tree before staging:
    the legacy environment name only inside arm ``models/*/record.json`` interpreter paths
    (exempted by ``tests/test_documentation.py``, which must already carry that exemption),
    every relative Markdown link resolving inside the checkout, and no ``±`` in Markdown
    (``tests/test_model_comparison_results.py``)."""
    legacy = re.compile("rail" + "yard", re.IGNORECASE)
    needs_exemption, problems = False, []
    docs_test = checkout / "tests/test_documentation.py"
    exempt = docs_test.is_file() and f"{TREE}/" in docs_test.read_text()
    for path in sorted((checkout / TREE).rglob("*")):
        if not path.is_file() or path.name.endswith(".gz") or path.suffix == ".jpg":
            continue
        relative = path.relative_to(checkout)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if relative.match(f"{TREE}/*/models/*/record.json") and LEGACY_ENV in text:
            needs_exemption = True
            text = text.replace(LEGACY_ENV, "/recorded-env/")
        if legacy.search(text):
            problems.append(f"legacy name in {relative}")
    for document in [*sorted((checkout / TREE).rglob("*.md")), checkout / INDEX]:
        if not document.is_file():
            continue
        if "±" in document.read_text(encoding="utf-8"):
            problems.append(f"± in {document.relative_to(checkout)}")
        for raw in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            target = raw.strip().strip("<>").split(' "', 1)[0]
            if target.startswith(("http://", "https://", "mailto:", "data:", "#")):
                continue
            local = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if local and not (document.parent / local).exists():
                problems.append(f"{document.relative_to(checkout)} -> {raw}")
    if needs_exemption and not exempt:
        raise Refusal(
            f"published record.json files keep {LEGACY_ENV} but {docs_test.relative_to(checkout)} "
            f"on {checkout.name} has no {TREE} exemption; push that exemption first"
        )
    if problems:
        raise DocsError(f"rendered tree fails the docs checks: {problems[:10]}")


# ----------------------------------------------------------------------------- git


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/").removesuffix(".git")
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.removeprefix("git@github.com:")
    if "://" not in url and not url.startswith("git@"):
        url = str(Path(url).expanduser().resolve()).removesuffix(".git")
    return url


def managed(path: str) -> bool:
    return path == str(INDEX) or path.startswith(f"{TREE}/")


def pending_paths(checkout: Path) -> list[str]:
    raw = git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries, paths = raw.split("\0"), []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if not entry:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":  # rename/copy: the next entry is the original path
            paths.append(entries[i])
            i += 1
    return paths


def check_checkout(args: argparse.Namespace) -> Path:
    checkout = args.checkout.resolve()
    if not checkout.is_dir():
        raise Refusal(f"{checkout} does not exist")
    top = Path(git(checkout, "rev-parse", "--show-toplevel").strip()).resolve()
    if top != checkout:
        raise Refusal(f"{checkout} is not a git top level ({top})")
    if checkout == CODE or checkout in CODE.parents or CODE in checkout.parents:
        raise Refusal("the publisher clone must be separate from the code checkout running this")
    for frozen in args.frozen_checkout:
        if checkout == frozen.resolve():
            raise Refusal(f"{checkout} is the campaign code checkout")
    inputs = [*args.campaign, *([args.fork_runs] if args.fork_runs else []), args.datasets_root]
    for root in [*inputs, *([args.cv_campaign] if args.cv_campaign else [])]:
        root = root.resolve()
        if checkout == root or root in checkout.parents or checkout in root.parents:
            raise Refusal(f"{checkout} overlaps input {root}")
    head = git(checkout, "rev-parse", "HEAD").strip()
    for root in args.campaign:
        if (root / "campaign.json").is_file() and head == read_json(root / "campaign.json").get(
            "code_sha"
        ):
            raise Refusal(f"{checkout} is at a campaign's frozen code_sha; use a fresh clone")
    branch = git(checkout, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
    if branch != args.branch:
        raise Refusal(f"{checkout} is on {branch!r}, not {args.branch!r}")
    expected = args.dry_run_remote or args.target_url
    for direction in ([], ["--push"]):
        # --push applies pushurl and pushInsteadOf; every listed push URL must be the target.
        for url in git(checkout, "remote", "get-url", "--all", *direction, args.remote).split():
            if normalize_url(url) != normalize_url(expected):
                raise Refusal(f"{args.remote} is {url}, not the target {expected}")
    return checkout


def sync(checkout: Path, remote: str, branch: str) -> None:
    """Refuse foreign local work; otherwise reset the clone to the remote branch."""
    foreign = [p for p in pending_paths(checkout) if not managed(p)]
    if foreign:
        raise Refusal(f"local changes outside {TREE}: {foreign[:10]}")
    git(checkout, "fetch", "--quiet", remote, branch)
    upstream = f"{remote}/{branch}"
    if git(checkout, "rev-list", f"{upstream}..HEAD").strip():
        changed = git(checkout, "diff", "--name-only", f"{upstream}...HEAD").splitlines()
        foreign = [p for p in changed if not managed(p)]
        if foreign:
            raise Refusal(f"unpushed commits touch paths outside {TREE}: {foreign[:10]}")
    git(checkout, "reset", "--quiet", "--hard", upstream)


def add_index_row(checkout: Path) -> None:
    path = checkout / INDEX
    if not path.is_file():
        return
    lines = path.read_text().splitlines()
    if any(f"{TREE.name}/README.md" in line for line in lines):
        return
    start = next((i for i, line in enumerate(lines) if line.startswith("|")), None)
    if start is None:
        lines += ["", INDEX_ROW]
    else:
        end = start
        while end + 1 < len(lines) and lines[end + 1].startswith("|"):
            end += 1
        lines.insert(end + 1, INDEX_ROW)
    path.write_text("\n".join(lines) + "\n")


def write_tree(checkout: Path, files: dict[str, str | bytes]) -> None:
    target = checkout / TREE
    if target.exists():
        shutil.rmtree(target)
    for name, content in files.items():
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(content)


def size_guard(checkout: Path, max_tree: int, max_file: int) -> tuple[int, int]:
    total, count = 0, 0
    for path in (checkout / TREE).rglob("*"):
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > max_file:
            raise SizeError(f"{path.relative_to(checkout)} is {size / 2**20:.1f} MiB")
        total += size
        count += 1
    if total > max_tree:
        raise SizeError(f"{TREE} is {total / 2**20:.1f} MiB, over {max_tree / 2**20:.0f} MiB")
    return total, count


def push(checkout: Path, remote: str, branch: str) -> None:
    for attempt in range(1, PUSH_ATTEMPTS + 1):
        try:
            git(checkout, "push", "--quiet", remote, f"HEAD:refs/heads/{branch}")
            return
        except GitError as error:
            text = str(error)
            if not re.search(r"non-fast-forward|fetch first|rejected", text):
                raise
            if attempt == PUSH_ATTEMPTS:
                raise GitError(f"push rejected {PUSH_ATTEMPTS} times: {text}") from error
        git(checkout, "fetch", "--quiet", remote, branch)
        try:
            git(checkout, "rebase", "--quiet", f"{remote}/{branch}")
        except GitError:
            git(checkout, "rebase", "--abort")
            raise


def publish_once(args: argparse.Namespace) -> dict[str, Any]:
    checkout = check_checkout(args)
    sync(checkout, args.remote, args.branch)
    files, comparison_error, cv_error = render_tree(
        args.campaign,
        args.fork_runs,
        args.datasets_root,
        args.viewpoints,
        guides=frozenset(g for g in (GUIDE, CASE_GUIDE, CV_GUIDE) if (checkout / g).is_file()),
        cv_campaign=args.cv_campaign,
        cv_previous=published_cv(checkout),
    )
    if comparison_error and (checkout / TREE / "rad-comparison.csv").is_file():
        raise ComparisonError(
            f"comparison not rendered ({comparison_error}); kept the published one"
        )
    write_tree(checkout, files)
    add_index_row(checkout)
    size, count = size_guard(checkout, args.max_tree_mb << 20, args.max_file_mb << 20)
    docs_check(checkout)
    paths = [str(TREE)] + ([str(INDEX)] if (checkout / INDEX).is_file() else [])
    git(checkout, "add", "--all", "--", *paths)
    foreign = [p for p in pending_paths(checkout) if not managed(p)]
    if foreign:
        raise Refusal(f"unexpected changes outside {TREE}: {foreign[:10]}")
    staged = git(checkout, "diff", "--cached", "--name-only").splitlines()
    result = {
        "files": count,
        "tree_bytes": size,
        "comparison_error": comparison_error,
        "cv_error": cv_error,
        "changed_files": len(staged),
    }
    if staged:
        git(checkout, "commit", "--quiet", "-m", COMMIT_MESSAGE)
        push(checkout, args.remote, args.branch)
    result["commit"] = git(checkout, "rev-parse", "HEAD").strip()
    result["pushed"] = bool(staged)
    return result


# ----------------------------------------------------------------------------- loop


def outside_inputs(path: Path, args: argparse.Namespace) -> bool:
    path = path.resolve()
    roots = [*args.campaign, *([args.fork_runs] if args.fork_runs else []), args.checkout]
    roots += [args.cv_campaign] if args.cv_campaign else []
    return not any(path == r.resolve() or r.resolve() in path.parents for r in roots)


def wait(seconds: float, stop: Path) -> bool:
    """Sleep up to ``seconds``; True when STOP appeared."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if stop.exists():
            return True
        time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))
    return stop.exists()


def run(args: argparse.Namespace) -> int:
    state = args.state_dir
    state.mkdir(parents=True, exist_ok=True)
    stop, status_path = state / "STOP", state / "publisher-status.json"
    with (state / "publisher.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("publish_rad_results: another publisher holds the lock", file=sys.stderr)
            return 3
        status = read_json(status_path) if status_path.is_file() else {}
        last = status.get("last_attempt")
        if last and not args.once:
            elapsed = time.time() - datetime.fromisoformat(last).timestamp()
            if wait(max(0.0, args.interval_seconds - elapsed), stop):
                return 0
        while not stop.exists():
            status["last_attempt"] = now()
            code = 0
            try:
                result = publish_once(args)
            except Refusal as error:
                status.update(error=f"refused: {error}", stopped=True)
                code = 2
            except Exception as error:
                status.update(error=f"{type(error).__name__}: {error}", stopped=False)
                code = 1
            else:
                status.update(result, error=None, stopped=False, last_success=now())
                if result["pushed"]:
                    status["last_push"] = status["last_success"]
            write_json(status_path, status)
            print(f"publish_rad_results: {json.dumps(status, sort_keys=True)}", flush=True)
            if code == 2 or args.once:
                return code
            if wait(args.interval_seconds, stop):
                break
        return 0


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--checkout", type=Path, required=True, help="separate publisher clone")
    p.add_argument(
        "--campaign",
        type=Path,
        action="append",
        help="repeat; default HDRFS r2. Several on one split: the newest with a finished run is "
        "the split's pages, older ones are summarised in details.md",
    )
    p.add_argument("--fork-runs", type=Path, default=rad_report.DEFAULT_FORK_RUNS)
    p.add_argument("--no-forks", action="store_true")
    p.add_argument("--datasets-root", type=Path, default=rad_report.DEFAULT_DATASETS)
    p.add_argument("--viewpoints", type=Path, default=rad_report.DEFAULT_VIEWPOINTS)
    p.add_argument(
        "--cv-campaign",
        type=Path,
        help="cross-validation campaign root, rendered into cross-validation/ (optional)",
    )
    p.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    p.add_argument("--interval-seconds", type=int, default=10800)
    p.add_argument("--once", action="store_true")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="main")
    p.add_argument("--target-url", default=TARGET_URL, help=argparse.SUPPRESS)
    p.add_argument("--dry-run-remote", help="expected remote URL instead of GitHub (tests)")
    p.add_argument(
        "--frozen-checkout",
        type=Path,
        action="append",
        default=[
            Path("/data/izadia1/projects/segmentary-rad-d864b72b"),
            Path("/data/izadia1/projects/segmentary-rad-cv-e7154e71"),
            Path("/data/izadia1/projects/segmentary-rad-fgall-fce0ea0a"),
        ],
        help="campaign code checkouts the clone must not be",
    )
    p.add_argument("--max-tree-mb", type=int, default=200)
    p.add_argument("--max-file-mb", type=int, default=20)
    args = p.parse_args(argv)
    args.campaign = args.campaign or list(rad_report.DEFAULT_CAMPAIGNS)
    args.fork_runs = None if args.no_forks else args.fork_runs
    if args.interval_seconds < 1 or args.max_tree_mb < 1 or args.max_file_mb < 1:
        p.error("interval and size caps must be positive")
    if not outside_inputs(args.state_dir, args):
        p.error("--state-dir must lie outside the campaign roots, fork runs and checkout")
    return args


def main(argv: list[str] | None = None) -> int:
    return run(parse(argv))


if __name__ == "__main__":
    sys.exit(main())
