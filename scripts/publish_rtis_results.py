"""Publish RTIS model reports without modifying the frozen training checkout."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import statistics
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime

REPORT = runtime.REPORT
MUD = "mud-pumping"


def pct(value):
    return "—" if value is None else f"{100 * value:.2f}"


def number(value, divisor=1):
    return "—" if value is None else f"{value / divisor:.2f}"


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    )


def fixed_miou(metrics):
    values = [
        metrics.get("per_class_iou", {}).get(name)
        for name, support in metrics.get("support", {}).items()
        if support > 0
    ]
    return sum(values) / len(values) if values and all(v is not None for v in values) else None


def peak(record):
    return max(record.get("peak_vram_bytes", {}).values(), default=None)


def capture(root):
    data = runtime.snapshot(root)
    plan = {job["name"]: job for job in runtime.read(root / "plan.json")["jobs"]}
    for row in data["jobs"]:
        job = plan[row["name"]]
        row["resolved_config"] = yaml.safe_load(Path(job["config"]).read_text())
        run = root / "future-runs" / f"{row['name']}_seed{row['seed']}" / "rtis"
        # Supplement frozen worker records with every logged class curve.
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

        events = sorted(run.rglob("events.out.tfevents.*"))
        curves = {}
        for directory in sorted({path.parent for path in events}):
            acc = EventAccumulator(str(directory), size_guidance={"scalars": 0}).Reload()
            for tag in acc.Tags().get("scalars", []):
                if tag.startswith(("val/", "val_")) or tag == "train/loss":
                    curves.setdefault(tag, []).extend(
                        {"step": int(v.step), "value": float(v.value)} for v in acc.Scalars(tag)
                    )
        if curves:
            row["learning_curve"] = curves
            # Only active runs receive a live step; queued abandoned attempts stay queued.
            if row["status"] == "training":
                row["observed_step"] = max(v["step"] for vs in curves.values() for v in vs)
        for anchor in row.get("checkpoints", {}).values():
            path = Path(anchor["path"])
            anchor["bytes"] = path.stat().st_size if path.is_file() else None
        perf = root / "performance" / f"{row['name']}.json"
        row["performance"] = (
            runtime.read(perf)
            if perf.exists()
            else {
                "status": "waiting_for_idle_gpu",
                "contract": "L40S; batch 1; 1024x1024; BF16; 20 warmup; 100 timed forwards",
            }
        )
    return data


def initial_weights(cfg):
    model = cfg.get("model", {})
    defaults = {
        "eomt_large": "tue-mps/coco_panoptic_eomt_large_640 (DINOv2-based ViT-L, COCO panoptic)",
        "eomt_dinov3_large": "tue-mps/eomt-dinov3-coco-panoptic-large-640 (DINOv3 ViT-L/16, COCO panoptic)",
        "upernet_convnext": "openmmlab/upernet-convnext-small",
        "segformer_b0": "nvidia/mit-b0",
        "segformer_b2": "nvidia/mit-b2",
        "segformer_b5": "nvidia/mit-b5",
        "hrnet_w48_ocr": "timm hrnet_w48 pretrained ImageNet backbone; fresh OCR head",
    }
    return (
        model.get("checkpoint")
        or defaults.get(model.get("arch"))
        or json.dumps(model, sort_keys=True)
    )


def summary_row(row, linked=True):
    metrics = row.get("evaluation", {}).get("metrics", {})
    name = row["model"]
    if linked:
        name = f"[{name}](models/{name}/README.md)"
    return [
        name,
        row["protocol"],
        row.get("seed", 0),
        row["status"],
        row.get("final_step", row.get("observed_step", "—")),
        row.get("checkpoints", {}).get("best", {}).get("global_step", "—"),
        pct(metrics.get("per_class_iou", {}).get(MUD)),
        pct(metrics.get("per_class_precision", {}).get(MUD)),
        pct(metrics.get("per_class_recall", {}).get(MUD)),
        pct(row.get("training", {}).get("metrics", {}).get("per_class_iou", {}).get(MUD)),
        pct(metrics.get("miou")),
        pct(fixed_miou(metrics)),
    ]


HEADERS = [
    "Model",
    "Initialization path",
    "Seed",
    "Status",
    "Steps",
    "Best step",
    "Mud IoU (%)",
    "Mud precision (%)",
    "Mud recall (%)",
    "Final mud IoU (trainer val, %)",
    "mIoU (%)",
    "Fixed GT-class mIoU (%)",
]


def performance_table(performance):
    latency = performance.get("measurements", {}).get("latency", {})
    model = performance.get("model", {})
    return table(
        ["Status", "Parameters", "Weight MiB", "FPS", "p50 ms", "p95 ms", "Peak reserved GiB"],
        [
            [
                performance.get("status", "waiting_for_idle_gpu"),
                model.get("parameter_count", "—"),
                number(model.get("resident_parameter_bytes"), 2**20),
                number(latency.get("fps")),
                number(latency.get("p50_ms")),
                number(latency.get("p95_ms")),
                number(performance.get("measurements", {}).get("peak_reserved_bytes"), 2**30),
            ]
        ],
    )


def model_report(model, rows, campaign):
    lines = [
        f"# {model} — paul-test-rtis",
        "",
        "[RTIS comparison](../../README.md) · [Full model records](record.json)",
        "",
        "Primary selection and early stopping: **mud-pumping validation IoU**. A job is complete only after full statistics and isolated profiling are verified."
        if campaign.get("collection_contract")
        else "Mud-pumping detection is the primary application. Current pilot checkpoints were selected by overall validation mIoU, **not mud IoU**. All numbers here describe that existing policy; a mud-focused experiment must be explicitly versioned.",
        "",
        table(HEADERS, [summary_row(r, False) for r in rows]),
        "",
        f"Training: 220 images. Validation: 37 images. Test: 50 held out. Seeds: {sorted({r.get('seed', 0) for r in rows})}. Seed variation measures optimization variability, not independent-recording uncertainty. Historical source checkpoints stay fixed across adaptation seeds.",
        "",
        f"Training code: `{campaign['code_sha']}`. Split SHA-256: `{campaign['split_sha256']}`.",
    ]
    for row in rows:
        cfg = row.get("resolved_config", {})
        evaluation = row.get("evaluation", {})
        metrics = evaluation.get("metrics", {})
        training = row.get("training", {})
        final = training.get("metrics", {})
        lines += [
            "",
            f"## {row['protocol']} — seed {row.get('seed', 0)}",
            "",
            f"Status: **{row['status']}**. Started: {row.get('started_at', '—')}. Finished: {row.get('finished_at', '—')}.",
            "",
            f"Recipe pretrained initializer: `{initial_weights(cfg)}`.",
            "",
            "`rtis_only` uses the recipe initializer, which may include pretrained segmentation components. Transfer paths load the exact historical source checkpoint below and reset the classifier; they do not reset all query/decoder features.",
            "",
            f"Source checkpoint: `{row.get('source_checkpoint') or 'Recipe pretrained initialization'}`.",
            "",
            f"Config SHA-256: `{row.get('config_sha256', '—')}`. Weights used for validation: `{evaluation.get('config', {}).get('evaluation', {}).get('weights', '—')}`.",
        ]
        if row.get("error"):
            lines += ["", f"Failure: {row['error']}"]
        lines += [
            "",
            "### Mud-pumping and aggregate quality",
            "",
            table(
                ["Metric", "Selected checkpoint", "Final training validation"],
                [
                    [
                        title,
                        pct(
                            metrics.get(key, {}).get(MUD)
                            if key.startswith("per_class")
                            else metrics.get(key)
                        ),
                        pct(
                            final.get(key, {}).get(MUD)
                            if key.startswith("per_class")
                            else final.get(key)
                        ),
                    ]
                    for title, key in [
                        ("Mud IoU", "per_class_iou"),
                        ("Mud precision", "per_class_precision"),
                        ("Mud recall", "per_class_recall"),
                        ("Mud Dice/F1", "per_class_dice"),
                        ("mIoU", "miou"),
                        ("Mean accuracy", "macc"),
                        ("Mean precision", "mprecision"),
                        ("Mean Dice", "mdice"),
                        ("Mean specificity", "mspecificity"),
                        ("Pixel accuracy", "pixel_accuracy"),
                        ("Frequency-weighted IoU", "freqw_iou"),
                    ]
                ]
                + [
                    [
                        "Fixed GT-present class mIoU",
                        pct(fixed_miou(metrics)),
                        pct(fixed_miou(final)),
                    ],
                    [
                        "Boundary F1",
                        pct(metrics.get("boundary", {}).get("macro_f1")),
                        pct(final.get("boundary", {}).get("macro_f1")),
                    ],
                ],
            ),
            "",
            "The selected checkpoint has independent evaluation evidence. Final values are the trainer's final validation record, not a new independent evaluation. mIoU averages classes with nonzero union, so false positives on absent classes can change its denominator. The fixed GT-class mean is supplementary and excludes absent classes; their false positives remain in the confusion matrix.",
        ]
        lines += [
            "",
            "### Resource usage and timing",
            "",
            table(
                ["Measurement", "Value"],
                [
                    [
                        "Peak training VRAM, retained training invocation (GiB)",
                        number(peak(training), 2**30),
                    ],
                    ["Peak evaluation VRAM (GiB)", number(peak(evaluation), 2**30)],
                    [
                        "Retained training invocation wall time (seconds)",
                        number(training.get("wall_clock_s")),
                    ],
                    [
                        "Retained training invocation GPU-hours (one GPU)",
                        number(training.get("wall_clock_s"), 3600),
                    ],
                    ["Evaluation wall time (seconds)", number(evaluation.get("wall_clock_s"))],
                    [
                        "Full evaluation pipeline images/second",
                        number(
                            evaluation.get("dataset_sizes", {}).get("eval", 0)
                            / evaluation["wall_clock_s"]
                        )
                        if evaluation.get("wall_clock_s", 0) > 0
                        else "—",
                    ],
                    [
                        "Best full-state checkpoint (MiB)",
                        number(row.get("checkpoints", {}).get("best", {}).get("bytes"), 2**20),
                    ],
                    [
                        "Final full-state checkpoint (MiB)",
                        number(row.get("checkpoints", {}).get("final", {}).get("bytes"), 2**20),
                    ],
                    [
                        "Audited periodic checkpoints removed (GiB)",
                        number(row.get("checkpoint_bytes_removed"), 2**30),
                    ],
                ],
            ),
            "",
            "VRAM uses the recorded allocator high-water mark; it is not total device usage including CUDA context. Resumed jobs' retained training invocation times and peaks are **not whole-campaign totals**. Earlier invocation resource records are not reconstructed here. Evaluation throughput includes loader, sliding-window inference and metrics; it is not model-only latency/FPS. Missing measurements are shown as —, never inferred from another dataset's run.",
            "",
            "### Standardized inference performance",
            "",
            "Dedicated model-only profiling waits for an idle worker-locked L40S: BF16, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed public forwards. It excludes loading, preprocessing, tiling and metrics.",
            "",
            performance_table(row.get("performance", {})),
            "",
            "```json",
            json.dumps(
                row.get(
                    "performance",
                    {
                        "status": "waiting_for_idle_gpu",
                        "contract": "L40S; batch 1; 1024x1024; BF16; 20 warmup; 100 timed forwards",
                    },
                ),
                indent=2,
            ),
            "```",
            "",
            "### Per-class validation results",
            "",
            table(
                [
                    "Class",
                    "GT pixels",
                    "IoU (%)",
                    "Precision (%)",
                    "Recall (%)",
                    "Dice (%)",
                    "Boundary F1 (%)",
                ],
                [
                    [
                        name,
                        support,
                        pct(metrics.get("per_class_iou", {}).get(name)),
                        pct(metrics.get("per_class_precision", {}).get(name)),
                        pct(metrics.get("per_class_recall", {}).get(name)),
                        pct(metrics.get("per_class_dice", {}).get(name)),
                        pct(metrics.get("boundary", {}).get("per_class_f1", {}).get(name)),
                    ]
                    for name, support in metrics.get("support", {}).items()
                ],
            ),
        ]
        lines += collection_section(row)
        curves = row.get("learning_curve", {})
        vals = {v["step"]: v["value"] for v in curves.get("val/miou", [])}
        mud = {v["step"]: v["value"] for v in curves.get("val_iou/mud-pumping", [])}
        lines += [
            "",
            "### Validation tracking",
            "",
            table(
                ["Logged step", "Overall mIoU (%)", "Mud IoU (%)"],
                [
                    [step, pct(vals.get(step)), pct(mud.get(step))]
                    for step in sorted(vals.keys() | mud.keys())
                ],
            ),
            "",
            "All retained scalar curves, including training loss and per-class IoU, are in record.json. Observed best mud on a curve is not necessarily a retained checkpoint: the pilot saved its selection-metric-best and final checkpoints. Step logging and checkpoint global_step may differ by one.",
            "",
            "### Stopping and checkpoint provenance",
            "",
            "```json",
            json.dumps(
                {k: row.get(k) for k in ["stopping", "checkpoints", "cleanup_error"]}, indent=2
            ),
            "```",
            "",
            "### Resolved training, initialization and evaluation settings",
            "",
            "The optimizer block is the base configuration. Stage LR scales are applied at runtime, and stage warmup is capped at min(base warmup, floor(stage budget / 10), stage budget - 1): 400 steps for this 4,000-step pilot. Model-internal native input grids may differ from augmentation crops (EoMT uses its 640 grid).",
            "",
            "```json",
            json.dumps(cfg, indent=2),
            "```",
            "",
            "### Hardware and software provenance",
            "",
            "```json",
            json.dumps(
                {"training": training.get("env"), "evaluation": evaluation.get("env")}, indent=2
            ),
            "```",
        ]
    return "\n".join(lines) + "\n"


def artifact_prefix(row):
    value = f"{row['protocol']}--seed-{row.get('seed', 0)}"
    if not re.fullmatch(r"[a-z0-9_-]+", value):
        raise ValueError("Unsafe run report path")
    return value


def collection_section(row):
    collection = row.get("collection", {})
    if not collection:
        return []
    resources = collection.get("resources", {})
    lines = [
        "",
        "### Full-run accounting",
        "",
        table(
            ["Measurement", "Value"],
            [
                [
                    "Full GPU-reserved wall seconds, all recorded worker attempts",
                    number(resources.get("total_reserved_gpu_wall_seconds")),
                ],
                ["Full reserved GPU-hours", number(resources.get("total_reserved_gpu_hours"))],
                [
                    "Whole-run timing complete",
                    resources.get("whole_run_accounting_complete", False),
                ],
            ],
        ),
        "",
        table(
            ["Phase", "Wall seconds including failed attempts"],
            [
                [k, number(v)]
                for k, v in resources.get(
                    "phase_wall_seconds_including_failed_attempts", {}
                ).items()
            ],
        ),
        "",
        "GPU-reserved time includes model loading, training, validation, collection, profiling, checkpoint I/O and orchestration while the worker owns one GPU. It is not GPU kernel-active time. Phase timings and sampled device memory/power/utilization are retained separately; sampled device memory is not the allocator high-water mark.",
        "",
        "### Train/validation and raw/EMA diagnostics",
        "",
        table(
            [
                "Checkpoint / weights / split",
                "Images",
                "Mud IoU (%)",
                "Mud precision (%)",
                "Mud recall (%)",
            ],
            [
                [
                    key + " / " + r["weights"],
                    r["images"],
                    pct(r["mud"]["iou"]),
                    pct(r["mud"]["precision"]),
                    pct(r["mud"]["recall"]),
                ]
                for key, r in collection.get("diagnostics", {}).get("results", {}).items()
            ],
        ),
        "",
        "Train uses the evaluation transform without augmentation. Compare mud train/validation metrics for the same selected weights. Alternate EMA on running-stat BatchNorm is explicitly uncalibrated and is diagnostic only. Score-threshold curves use uncalibrated normalized scores and are pixel-level diagnostics, not event detection rates or a selected deployment operating point.",
        "",
        "### Downloadable evidence",
        "",
    ]
    prefix = artifact_prefix(row)
    for section, artifacts in collection.get("artifacts", {}).items():
        links = []
        for name in artifacts:
            if name == "examples.jpg" and section != "best-auto-val":
                continue
            url = f"{prefix}/{section}/{name}"
            links.append(f"[{name}]({url})")
        lines.append(f"- {section}: " + " · ".join(links))
    if "examples.jpg" in collection.get("artifacts", {}).get("best-auto-val", {}):
        lines += [
            "",
            f"![Selected-checkpoint validation examples]({prefix}/best-auto-val/examples.jpg)",
            "",
            "Examples are two lowest and two highest mud-IoU positive images, plus up to two negative images with the most false-positive mud pixels. They are targeted diagnostic examples, not random samples. Green: true positive; red: false positive; yellow: false negative. Full predictions remain on HDRFS.",
        ]
    return lines


def comparison_table(jobs, metric, percent=True):
    protocols = [
        "rtis_only",
        "cityscapes_to_rtis",
        "railsem19_to_rtis",
        "cityscapes_to_railsem19_to_rtis",
    ]
    rows = []
    for model in sorted({r["model"] for r in jobs}):
        planned = [r for r in jobs if r["model"] == model]
        row = [
            f"[{model}](models/{model}/README.md)",
            f"{sum(r['status'] == 'completed' for r in planned)}/{len(planned)}",
        ]
        for protocol in protocols:
            group = [r for r in planned if r["protocol"] == protocol]
            values = [metric(r) for r in group if r["status"] == "completed"]
            values = [v for v in values if v is not None]
            fmt = pct if percent else number
            cell = fmt(statistics.mean(values)) if values else "—"
            row.append(cell)
        rows.append(row)
    return table(
        [
            "Model",
            "Completed runs",
            "RTIS only",
            "City → RTIS",
            "Rail → RTIS",
            "City → Rail → RTIS",
        ],
        rows,
    )


def seed_summary(jobs):
    return comparison_table(jobs, lambda r: r.get("evaluation", {}).get("metrics", {}).get("miou"))


def artifacts(data):
    jobs = data["jobs"]
    full = bool(data["campaign"].get("collection_contract"))
    models = sorted({r["model"] for r in jobs})
    if any(not re.fullmatch(r"[a-z0-9_]+", m) for m in models):
        raise ValueError("Unsafe model report path")
    done = sum(r["status"] == "completed" for r in jobs)
    lines = [
        "# RTIS model comparison",
        "",
        f"**{done}/{len(jobs)} completed · {sum(r['status'] == 'failed' for r in jobs)} failed**",
        "",
        "Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling."
        if full
        else "Overall segmentation quality and mud-pumping results across four initialization paths. This pilot selects checkpoints by overall validation mIoU.",
        "",
        "[Dataset and preparation](../README.md) · [Mathematical mud-pumping audit](../mud-pumping-audit/README.md) · [CSV results](results.csv) · [Full machine records](status.json)",
        "",
        f"{len(models)} models; four initialization paths; seeds {sorted({r.get('seed', 0) for r in jobs})}. Train/val/test: 220/37/50 images. Test is held out. Validation groups are provisional and lack person, truck and on-rails ground truth. Seed variation does not establish independent-recording generalization.",
        "",
        "## Quality",
        "",
        "Validation **mIoU (%)** across classes. Cells show the mean over completed seeds. Per-seed values are retained on model pages and in machine records. Partial groups are provisional; — means unavailable. These are the existing selected-checkpoint evaluations, not newly selected mIoU-best checkpoints. Raw/EMA settings are recorded on each model page.",
        "",
        seed_summary(jobs),
        "",
        "## Mud-pumping",
        "",
        "Validation **mud-pumping IoU (%)** for the same checkpoints. Precision, recall, per-class scores and examples are on each model page and in the CSV.",
        "",
        comparison_table(
            jobs,
            lambda r: r.get("evaluation", {}).get("metrics", {}).get("per_class_iou", {}).get(MUD),
        ),
        "",
        "## Standardized model-only inference",
        "",
        "**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.",
        "",
        comparison_table(
            jobs,
            lambda r: (
                r.get("performance", {}).get("measurements", {}).get("latency", {}).get("fps")
            ),
            percent=False,
        ),
        "",
        "<details>",
        "<summary>Individual runs: quality, mud precision/recall, steps and status</summary>",
        "",
        "Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.",
        "",
        table(HEADERS, [summary_row(r) for r in jobs]),
        "",
        "</details>",
        "",
        "## Training specification and interpretation",
        "",
        "This campaign selects checkpoints and early-stops by **mud-pumping validation IoU**. Both overall mIoU and mud IoU above describe that same selected checkpoint. This report layout does not change the training objective or selection policy. mIoU averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty."
        if full
        else "The current best checkpoint maximizes mIoU over classes with nonzero union. False positives on an absent class add a zero-IoU class to the mean. Fixed GT-class mIoU uses the same 18 ground-truth-present validation classes and is supplementary; it does not excuse false positives. Mud IoU, precision and recall are pixel-level segmentation measures, not event-level detection rates.",
        "",
        "`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.",
        "",
        "Validation approximately every 250 optimizer steps; stop after five checks without a 0.1 percentage-point mud-IoU improvement. At most 4,000 steps. Keep mud-selected and final full-state checkpoints; remove periodic snapshots only after complete verified collection."
        if full
        else "Validation approximately every 250 optimizer steps; stop after three checks without 0.2 percentage-point mIoU improvement. At most 4,000 steps. Keep aggregate-best and final full-state checkpoints; periodic checkpoints are removed only after successful evaluation, with an audit.",
        "",
        f"Frozen training code: `{data['campaign']['code_sha']}`. Split SHA-256: `{data['campaign']['split_sha256']}`.",
        "",
        "## Training cost",
        "",
        "<details>",
        "<summary>Per-run training and evaluation memory and time</summary>",
        "",
        table(
            [
                "Model",
                "Initialization",
                "Seed",
                "Train peak GiB (retained invocation)",
                "Eval peak GiB",
                "Train seconds (retained invocation)",
                "Eval seconds",
            ],
            [
                [
                    f"[{r['model']}](models/{r['model']}/README.md)",
                    r["protocol"],
                    r.get("seed", 0),
                    number(peak(r.get("training", {})), 2**30),
                    number(peak(r.get("evaluation", {})), 2**30),
                    number(r.get("training", {}).get("wall_clock_s")),
                    number(r.get("evaluation", {}).get("wall_clock_s")),
                ]
                for r in jobs
            ],
        ),
        "",
        "</details>",
        "",
        "Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.",
    ]
    if full:
        previous = data["campaign"].get("previous_report_commit")
        if previous:
            lines += [
                "",
                f"[Preserved original aggregate-selected pilot](https://github.com/arianizadi/segmentary/blob/{previous}/docs/results/paul-test-rtis/live/README.md)",
            ]
    machine = (
        data
        if not full
        else {
            "campaign": data["campaign"],
            "jobs": [
                {
                    **{
                        k: r.get(k)
                        for k in (
                            "name",
                            "model",
                            "protocol",
                            "seed",
                            "status",
                            "final_step",
                            "observed_step",
                        )
                    },
                    "record": f"models/{r['model']}/record.json",
                }
                for r in jobs
            ],
        }
    )
    files = {
        "README.md": "\n".join(lines) + "\n",
        "status.json": json.dumps(machine, indent=2, allow_nan=False) + "\n",
    }
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADERS)
    writer.writerows(summary_row(r, False) for r in jobs)
    files["results.csv"] = buf.getvalue()
    for model in models:
        rows = [r for r in jobs if r["model"] == model]
        files[f"models/{model}/README.md"] = model_report(model, rows, data["campaign"])
        files[f"models/{model}/record.json"] = (
            json.dumps({"campaign": data["campaign"], "jobs": rows}, indent=2, allow_nan=False)
            + "\n"
        )
    for row in jobs:
        for section, artifacts in row.get("collection", {}).get("artifacts", {}).items():
            if not re.fullmatch(r"[a-z0-9_-]+", section):
                raise ValueError("Unsafe evidence section")
            for name, info in artifacts.items():
                if name == "examples.jpg" and section != "best-auto-val":
                    continue
                if Path(name).name != name:
                    raise ValueError("Unsafe evidence filename")
                path = Path(info["path"])
                if runtime.digest(path) != info["sha256"]:
                    raise RuntimeError(f"Evidence hash changed: {path}")
                files[f"models/{row['model']}/{artifact_prefix(row)}/{section}/{name}"] = (
                    path.read_bytes()
                )
    return files


def publish_once(root, checkout):
    files = artifacts(capture(root))
    allowed = {str(REPORT / name) for name in files}
    checkout = checkout.resolve()
    if checkout == Path(__file__).resolve().parents[1]:
        raise RuntimeError("Publisher requires a separate checkout")
    git = runtime.git
    pending = set()
    for args in [
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ]:
        pending.update(git(checkout, *args).splitlines())
    if pending - allowed:
        raise RuntimeError("Publisher checkout has unrelated edits; leaving them intact")
    tracked = set(git(checkout, "ls-files").splitlines())
    for path in pending & tracked:
        git(checkout, "restore", "--source=HEAD", "--staged", "--worktree", "--", path)
    git(checkout, "fetch", "origin", "main")
    if git(checkout, "rev-list", "origin/main..HEAD"):
        if set(git(checkout, "diff", "--name-only", "origin/main...HEAD").splitlines()) - allowed:
            raise RuntimeError("Unpublished commits include unrelated changes")
        git(checkout, "rebase", "origin/main")
        git(checkout, "push", "origin", "HEAD:main")
    else:
        git(checkout, "merge", "--ff-only", "origin/main")
    for name, content in files.items():
        dest = checkout / REPORT / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(content)
    git(checkout, "add", "--", *sorted(allowed))
    if not git(checkout, "diff", "--cached", "--name-only"):
        return
    git(checkout, "commit", "-m", "Update RTIS comparison and per-model reports")
    git(checkout, "push", "origin", "HEAD:main")
    runtime.write(
        root / "publisher-status.json",
        {
            "last_success": runtime.now(),
            "commit": git(checkout, "rev-parse", "HEAD"),
            "reporter": "publish_rtis_results.py",
        },
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--checkout", type=Path, required=True)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    with runtime.lock(args.campaign / "locks/publisher.lock") as acquired:
        if not acquired:
            raise RuntimeError("Publisher already running")
        last_signature = None
        last_publish = 0.0
        while True:
            try:
                signature = [
                    (p.name, runtime.read(p).get("status"))
                    for p in sorted((args.campaign / "state").glob("*.json"))
                ]
                signature += [
                    (p.name, p.stat().st_mtime_ns)
                    for p in sorted((args.campaign / "performance").glob("*.json"))
                ]
                if (
                    args.once
                    or signature != last_signature
                    or time.monotonic() - last_publish >= 600
                ):
                    publish_once(args.campaign, args.checkout)
                    last_signature = signature
                    last_publish = time.monotonic()
            except Exception as error:
                runtime.write(
                    args.campaign / "publisher-error.json",
                    {"at": runtime.now(), "error": str(error)},
                )
                if args.once:
                    raise
            if args.once or (args.campaign / "STOP_PUBLISHER").exists():
                return
            time.sleep(60)


if __name__ == "__main__":
    main()
