#!/usr/bin/env python3
"""Publish the whole RAD 9/24 study to docs/results/rad_9_24_2026 from a separate clone.

    PYTHONPATH=<code checkout>:<code checkout>/src python scripts/publish_rad_results.py \\
        --checkout <publisher clone> [--once] [--interval-seconds 1800] \\
        [--campaign <root> ...] [--fork-runs <dir>] [--datasets-root <dir>] \\
        [--state-dir <dir>] [--max-tree-mb 200] [--max-file-mb 20] \\
        [--remote origin] [--branch main] [--dry-run-remote <git url>]

One cycle (every ``--interval-seconds``, default three hours to bound public history):

1. Check the publisher clone: a git top level, not this code checkout and not a campaign's
   frozen code checkout, on ``--branch``, whose ``--remote`` fetch and push URLs are the target
   (``https://github.com/arianizadi/segmentary.git``, or ``--dry-run-remote`` for tests).
   Local changes or unpushed commits touching anything outside ``docs/results/rad_9_24_2026``
   (and the ``docs/results/README.md`` index) are refused and stop the loop. Otherwise fetch
   and hard-reset to ``<remote>/<branch>``.
2. Render ``docs/results/rad_9_24_2026``: the study page (``README.md``), the cab-view
   comparison (``scripts/rad_report.py``) and its ``rad-comparison.csv``, and one directory
   per arm rendered by ``scripts/publish_rtis_results.py`` exactly as for RTIS v2.
3. Size guard (tree and per-file caps); prediction directories, test-split evidence and
   file types other than the evidence formats are never published. The repository's docs
   checks (legacy name, resolving links) run on the rendered tree before anything is staged.
   When the cab-view comparison fails after one was published, the cycle publishes nothing
   rather than removing it.
4. Stage only the tree (and the index line when missing), verify nothing else changed,
   commit "Update RAD 9/24 results" when anything changed and push; a non-fast-forward
   rejection is fetched and rebased, at most three times. Never forced.

Campaign, fork-run and dataset directories are only read. ``publisher-status.json``,
``publisher.lock`` (one instance) and ``STOP`` (ends the loop) live in ``--state-dir``.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from scripts import publish_rtis_results as reports
from scripts import rad_report

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


def arm_files(data: dict, arm: str) -> dict[str, str | bytes]:
    """The RTIS v2 rendering of one arm, with the page title and dataset facts of RAD."""
    files = reports.artifacts(data)
    grouping = data["campaign"].get("grouping_status", "unrecorded")
    labels, split = ARM_TEXT[arm]
    intro = (
        f"# RAD 9/24: `{arm}` arm\n\n"
        f"Our 10-model x 4-initialization-path campaign on the `{arm}` arm (labels: {labels}; "
        f"split: {split}). The arm name describes the labels and split, not who trained: every "
        "model on this page was trained by us. Protocol names keep the RTIS publisher's wording, "
        'where `rtis` is the final RAD training stage: "RTIS only" is pretrained backbone → '
        'RAD, "City → Rail → RTIS" is Cityscapes → RailSem19 → RAD.'
    )
    files["README.md"] = (
        files["README.md"]
        .replace("# RTIS model comparison", intro, 1)
        .replace("[Dataset and preparation](../README.md)", "[RAD 9/24 study](../README.md)", 1)
        .replace(
            "Validation groups are provisional and lack person, truck and on-rails ground truth.",
            f"Split grouping status: `{grouping}`.",
            1,
        )
    )
    for name, content in files.items():
        if re.fullmatch(r"models/[^/]+/README\.md", name) and isinstance(content, str):
            files[name] = content.replace(
                "[RTIS comparison](../../README.md)", f"[RAD 9/24 `{arm}` arm](../../README.md)", 1
            )
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
        "scored: GT-class mIoU / mud IoU / mud IoU cab / img-mean mud IoU cab",
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


def study_readme(
    arms: dict[str, dict],
    report: rad_report.Report | None,
    report_error: str | None,
    forks: list[dict],
    datasets: Path,
    guide_link: bool,
) -> str:
    guide = (
        f"[Dataset preparation and split decisions](../../{GUIDE.relative_to('docs')})"
        if guide_link
        else f"Dataset preparation: `{GUIDE}`"
    )
    lines = [
        "# RAD 9/24 study: split policy and Paul Stanik's paper recipes",
        "",
        "The `rad_9_24_2026` delivery (314 rail images with polygon labels) trained two ways "
        "with the same 10-model x 4-initialization-path catalog (40 jobs per arm, seed 0, "
        "checkpoint selection and early stopping on validation mud-pumping IoU), plus Paul "
        "Stanik's two paper recipes, retrained by us with his fork code. The question: how much "
        "does Paul's random stratified split flatter the results compared with a scene-grouped "
        "split (`paul` vs `fixed-grouped`)? The two arms also differ in labels. "
        + rad_report.LABEL_ARM_STOPPED
        + " Validation only; the test split is held out and never read.",
        "",
        guide + (" · [Comparison CSV](rad-comparison.csv)" if report is not None else ""),
        "",
        "## Arms and progress",
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
        rows.append(
            [
                f"[`{arm}`]({arm}/README.md)",
                labels,
                f"{split}; {sizes['train']}/{sizes['val']}/{sizes['test']}",
                f"{status.get('completed', 0)}/{len(jobs)}",
                others or "—",
                f"`{data['campaign'].get('code_sha', '?')[:12]}`",
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
    lines += caveats(report)
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
    return datetime.fromtimestamp(max(times), UTC).strftime("%Y-%m-%d %H:%M UTC")


def caveats(report: rad_report.Report | None) -> list[str]:
    comp = report.composition if report else {}
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
        "- **Optimistic validation numbers.** Checkpoints are selected (and training early "
        "stopped) on the same val split that is reported; fork runs pick their epoch on it too.",
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
    guide_link: bool = True,
) -> tuple[dict[str, str | bytes], str | None]:
    """All files of the published tree (paths relative to it) and any comparison error."""
    files: dict[str, str | bytes] = {}
    arms: dict[str, dict] = {}
    roots = []
    for root in campaigns:
        if not (root / "campaign.json").is_file():
            continue
        arm = arm_of(root)
        if arm in arms:
            raise ValueError(f"two campaign roots for the {arm} arm")
        arms[arm] = reports.capture(root)
        files.update(arm_files(arms[arm], arm))
        arms[arm] = {**arms[arm], "root": str(root)}
        roots.append(root)
    report, error = None, None
    try:
        report = rad_report.build(roots, fork_runs, datasets, viewpoints, [])
        files["rad-comparison.csv"] = rad_report.csv_text(report)
    except (rad_report.ReportError, ValueError, OSError, KeyError) as exc:
        error = rad_report.why(exc)
    forks = fork_rows(fork_runs if fork_runs and fork_runs.is_dir() else None, report)
    files["README.md"] = study_readme(arms, report, error, forks, datasets, guide_link)
    check_paths(files)
    return files, error


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
    and every relative Markdown link resolving inside the checkout."""
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
    for root in [*args.campaign, *([args.fork_runs] if args.fork_runs else []), args.datasets_root]:
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
    files, comparison_error = render_tree(
        args.campaign,
        args.fork_runs,
        args.datasets_root,
        args.viewpoints,
        guide_link=(checkout / GUIDE).is_file(),
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
    p.add_argument("--campaign", type=Path, action="append", help="repeat; default HDRFS r2")
    p.add_argument("--fork-runs", type=Path, default=rad_report.DEFAULT_FORK_RUNS)
    p.add_argument("--no-forks", action="store_true")
    p.add_argument("--datasets-root", type=Path, default=rad_report.DEFAULT_DATASETS)
    p.add_argument("--viewpoints", type=Path, default=rad_report.DEFAULT_VIEWPOINTS)
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
        default=[Path("/data/izadia1/projects/segmentary-rad-d864b72b")],
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
