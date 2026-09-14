"""Generate aggregate Markdown for a medical campaign without reading image data.

The queue is not a leaderboard: live validation remains explicitly provisional.
Only complete, equal-budget groups with matching native evaluation cohorts can
receive screening ranks. No patient identifiers or workstation paths are emitted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from segmentary.medical_reporting import (
    clinical_metrics,
    collect_performance,
    metric_history,
    model_performance_markdown,
    performance_assets,
)


def _reject_constant(value: str) -> None:
    raise ValueError(f"Nonfinite JSON number: {value}")


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(), parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _number(value: Any, *, unit: float = 1) -> str:
    if value is None:
        return "—"
    return f"{value / unit:.4f}" if unit == 1 else f"{value / unit:.2f}"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    return "\n".join(
        "| " + " | ".join(_cell(item) for item in row) + " |"
        for row in [headers, ["---"] * len(headers), *rows]
    )


def _recipe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = _read(path) if path.suffix == ".json" else yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Expected a recipe mapping")
    return value


def _score(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Dice must be a finite scalar")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Dice outside [0,1]")
    return float(value)


def _sanitize_pipeline(value: dict) -> dict:
    """Only named numerical measurements, fixed labels and summary hashes leave the host."""
    fields = {
        "data": {
            "model",
            "size_rank",
            "iterations",
            "npz_seconds",
            "mmap_seconds",
            "old_sample_seconds",
            "new_sample_seconds",
            "exact_samples_and_rng",
        },
        "training": {
            "model",
            "warmup_steps",
            "measured_steps",
            "barriers",
            "profiler",
            "sample_seconds",
            "host_to_device_seconds",
            "forward_seconds",
            "backward_seconds",
            "optimizer_seconds",
            "whole_step_seconds",
        },
        "inference": {
            "model",
            "batch_size",
            "batch_1_seconds",
            "batched_seconds",
            "argmax_disagreement_voxels",
            "native_voxels",
        },
        "inverse": {"size_rank", "sequential_seconds", "threaded_seconds", "exact_channels"},
        "prefetch": {
            "warmup_steps",
            "measured_steps",
            "synchronous_seconds",
            "prefetched_seconds",
            "exact_weights",
            "exact_rng",
            "maximum_parameter_difference",
        },
        "cache": {
            "training_cases",
            "bytes",
            "host_ram_bytes",
            "host_available_bytes",
            "io_some_avg10",
            "io_full_avg10",
        },
    }
    booleans = {
        "exact_samples_and_rng",
        "barriers",
        "profiler",
        "exact_channels",
        "exact_weights",
        "exact_rng",
    }
    models = {"unet_3d", "segformer_b2", "medformer"}

    def row(item: dict, allowed: set[str]) -> dict:
        result = {}
        for key in allowed & item.keys():
            datum = item[key]
            if key == "model":
                if datum not in models:
                    raise ValueError("Unknown pipeline profiling model")
            elif key == "size_rank":
                if datum not in {"smallest", "median", "largest"}:
                    raise ValueError("Unknown pipeline size category")
            elif key in booleans:
                if type(datum) is not bool:
                    raise ValueError("Pipeline equality/scope evidence must be boolean")
            elif type(datum) not in (int, float) or not math.isfinite(datum) or datum < 0:
                raise ValueError(
                    "Pipeline timing/count evidence must be finite nonnegative numbers"
                )
            result[key] = datum
        return result

    result = {
        name: row(value.get(name, {}), allowed)
        if name in {"prefetch", "cache"}
        else [row(item, allowed) for item in value.get(name, [])]
        for name, allowed in fields.items()
    }
    hashes = value.get("source_summaries_sha256", [])
    if any(
        not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest) for digest in hashes
    ):
        raise ValueError("Pipeline evidence requires SHA256 summary digests")
    result["source_summaries_sha256"] = hashes
    return result


def _pipeline_markdown(pipeline: dict) -> str:
    if not any(pipeline.get(key) for key in ("data", "training", "inverse", "prefetch", "cache")):
        return (
            "## Pipeline measurements\n\nNo detailed pipeline evidence supplied in this snapshot.\n"
        )
    chunks = [
        "## Warm cache loading and patch sampling",
        "",
        "Medians from repeated warm reads; the OS page cache was not dropped. Mapping setup defers page faults, so it is not a claim that an entire CT was read in the mapping time. Patch sampling includes touching the needed mapped pages. All cases come from the training partition.",
        "",
        _table(
            [
                "Model",
                "Training size",
                "Reads",
                "NPZ load ms",
                "NPY mapping ms",
                "Old patch ms",
                "New patch ms",
                "Exact patch/RNG",
            ],
            [
                [
                    row.get("model"),
                    row.get("size_rank"),
                    row.get("iterations"),
                    *[
                        _number(row.get(key), unit=0.001)
                        for key in (
                            "npz_seconds",
                            "mmap_seconds",
                            "old_sample_seconds",
                            "new_sample_seconds",
                        )
                    ],
                    row.get("exact_samples_and_rng"),
                ]
                for row in pipeline.get("data", [])
            ],
        ),
        "",
        "## Instrumented training stages",
        "",
        "These measurements synchronize CUDA around every stage and may include profiler overhead. They diagnose where time goes; they are not uninstrumented steady campaign throughput. Forward includes the loss; host-to-device includes stacking CPU patches. Warmup/measured counts are stated for each model.",
        "",
        _table(
            [
                "Model",
                "Warmup/measured",
                "Barriers/profiler",
                "Sample ms",
                "Stack+H2D ms",
                "Forward ms",
                "Backward ms",
                "Optimizer ms",
                "Whole step ms",
            ],
            [
                [
                    row.get("model"),
                    f"{row.get('warmup_steps')}/{row.get('measured_steps')}",
                    f"{row.get('barriers')}/{row.get('profiler')}",
                    *[
                        _number(row.get(key), unit=0.001)
                        for key in (
                            "sample_seconds",
                            "host_to_device_seconds",
                            "forward_seconds",
                            "backward_seconds",
                            "optimizer_seconds",
                            "whole_step_seconds",
                        )
                    ],
                ]
                for row in pipeline.get("training", [])
            ],
        ),
        "",
        "## CPU prefetch and compact transfers",
        "",
    ]
    prefetch = pipeline.get("prefetch", {})
    if prefetch:
        ratio = (
            prefetch.get("synchronous_seconds", 0) / prefetch["prefetched_seconds"]
            if prefetch.get("prefetched_seconds")
            else None
        )
        chunks += [
            _table(
                [
                    "Synchronous ms",
                    "Prefetch ms",
                    "Throughput ratio",
                    "Warmup/measured",
                    "Exact weights/RNG",
                    "Maximum parameter difference",
                ],
                [
                    [
                        _number(prefetch.get("synchronous_seconds"), unit=0.001),
                        _number(prefetch.get("prefetched_seconds"), unit=0.001),
                        _number(ratio),
                        f"{prefetch.get('warmup_steps')}/{prefetch.get('measured_steps')}",
                        f"{prefetch.get('exact_weights')}/{prefetch.get('exact_rng')}",
                        _number(prefetch.get("maximum_parameter_difference")),
                    ]
                ],
            ),
            "",
            "UNet3D, batch 8, BF16, 96-cubed patches, one median-size training CT and a warm mapped cache. This separate experiment times whole steps without per-stage barriers or a profiler; it synchronizes at the end of each step. It excludes initial cache construction, full-volume validation and checkpoint publication. Equality applies to this measured training comparison, not every optimization.",
            "",
        ]
    chunks += [
        "## Native reconstruction and inference batching",
        "",
        _table(
            [
                "Training size",
                "Sequential inverse s",
                "Three-thread inverse s",
                "Exact probability channels",
            ],
            [
                [
                    row.get("size_rank"),
                    _number(row.get("sequential_seconds")),
                    _number(row.get("threaded_seconds")),
                    row.get("exact_channels"),
                ]
                for row in pipeline.get("inverse", [])
            ],
        ),
        "",
        "The inverse transform evaluates three independent probability channels with unchanged interpolation. Its equality test is separate from model inference batching.",
        "",
        _table(
            [
                "Model",
                "Inference batch",
                "Batch-1 s",
                "Batched s",
                "Changed argmax voxels",
                "Native voxels",
                "Changed percent",
            ],
            [
                [
                    row.get("model"),
                    row.get("batch_size"),
                    _number(row.get("batch_1_seconds")),
                    _number(row.get("batched_seconds")),
                    row.get("argmax_disagreement_voxels"),
                    row.get("native_voxels"),
                    _number(100 * row.get("argmax_disagreement_voxels", 0) / row["native_voxels"])
                    if row.get("native_voxels")
                    else "—",
                ]
                for row in pipeline.get("inference", [])
            ],
        ),
        "",
        "Tile batching preserves coverage and the blending order, but BF16 kernels can change rounding and argmax labels. These early scratch predictions are a numerical comparison, not quality scores. Freeze inference_batch_size before training and keep it consistent across the comparison. Do not describe all optimizations as bitwise invariant.",
        "",
    ]
    cache = pipeline.get("cache", {})
    if cache:
        chunks += [
            "## Shared cache and host capacity",
            "",
            _table(
                [
                    "Training cases",
                    "Cache GiB",
                    "Host RAM GiB",
                    "Available RAM GiB",
                    "I/O some/full avg10",
                ],
                [
                    [
                        cache.get("training_cases"),
                        _number(cache.get("bytes"), unit=2**30),
                        _number(cache.get("host_ram_bytes"), unit=2**30),
                        _number(cache.get("host_available_bytes"), unit=2**30),
                        f"{cache.get('io_some_avg10')}/{cache.get('io_full_avg10')}",
                    ]
                ],
            ),
            "",
            "RAM availability and Linux pressure-stall averages are a point-in-time host snapshot. A cache fitting in RAM does not guarantee every page remains resident, and zero measured I/O pressure does not establish future absence of contention.",
            "",
        ]
    chunks += [
        "These tables are generated from sanitized numerical records. Original trace files, scan names and server paths remain on the host. Source summary SHA256 digests:",
        "",
        *[f"- `{digest}`" for digest in pipeline.get("source_summaries_sha256", [])],
        "",
        "Method references: [PyTorch 2.11 profiler](https://docs.pytorch.org/docs/2.11/profiler.html) and [official Mamba implementation](https://github.com/state-spaces/mamba).",
        "",
    ]
    return "\n".join(chunks)


def _evaluation(report: dict, expected_ids: list[str]) -> dict:
    """Retain aggregate scores and a reference-sensitive cohort digest only."""
    if not report:
        return {}
    cases = report["cases"]
    identifiers = [case["case_id"] for case in cases]
    if len(set(identifiers)) != len(identifiers) or set(identifiers) != set(expected_ids):
        raise ValueError("Evaluation cases differ from the frozen validation partition")
    references = []
    for case in cases:
        if not case.get("reference_sha256") or not case.get("patient_id"):
            raise ValueError("Evaluation lacks reference or patient provenance")
        references.append(
            {
                key: case[key]
                for key in ("case_id", "patient_id", "annotation_status", "reference_sha256")
            }
        )
    coverage = report["coverage"]
    if coverage["eligible_cases"] != len(expected_ids):
        raise ValueError("Evaluation coverage denominator differs from validation partition")
    complete = bool(expected_ids) and all(case["status"] == "ok" for case in cases)
    complete = complete and all(
        coverage.get(key) == len(expected_ids)
        for key in ("annotated_cases", "valid_reference_cases", "valid_prediction_cases")
    )
    regions = report["regions"]
    result: dict[str, Any] = {
        "cohort_fingerprint": _digest(sorted(references, key=lambda row: row["case_id"])),
        "manifest_fingerprint": report["manifest_fingerprint"],
        "protocol_fingerprint": _digest(report["protocol"]),
        "protocol": report["protocol"],
        "coverage": coverage,
        "complete_coverage": complete,
    }
    for region in ("pancreas", "mass"):
        summary = regions[region]
        result[region] = {
            "dice": _score(summary["dice"]["mean"]),
            "dice_ci": summary["dice"].get("ci"),
            "surface_dice": _score(summary["surface_dice"]["mean"]),
            "hd95_mm": summary["hd95_mm"]["mean"],
            "hd95_coverage": summary["hd95_mm"].get("coverage"),
            "reference_positive_cases": summary["reference_positive_cases"],
            "reference_empty_cases": summary["reference_empty_cases"],
            "reference_empty_prediction_nonempty_cases": summary[
                "reference_empty_prediction_nonempty_cases"
            ],
        }
    return result


def _resources(workspace: Path, now: float) -> dict:
    # Outcome files are immutable per stage invocation: resumed stages add cost
    # instead of overwriting the earlier timing history.
    outcomes = [_read(path) for path in sorted((workspace / "stages").glob("*/outcome.json"))]
    retained_hours = sum(outcome.get("allocated_gpu_hours", 0) for outcome in outcomes)
    active = _read(workspace / "active-stage.json")
    active_seconds = 0.0
    if active.get("status") == "running" and active.get("action") in {"train", "predict"}:
        active_seconds = max(0, now - active["started_at"])
    return {
        "finished_stage_gpu_hours": retained_hours if outcomes else None,
        "active_stage_allocated_hours_estimate": active_seconds / 3600 if active_seconds else None,
        "recorded_stage_invocations": len(outcomes),
        "active_stage_status": active.get("status"),
        "timing_definition": "Finished stage allocation plus separately shown active-stage wall estimate; not GPU utilization",
    }


def _collect_run(
    run: dict, state: dict, state_dir: Path, expected_ids: list[str], now: float
) -> dict:
    config_path = Path(state.get("config", run["config"]))
    config = _recipe(config_path)
    workspace = Path(state.get("workspace", config.get("workspace", run.get("workspace", ""))))
    binding = _read(workspace / "binding.json") if workspace.is_dir() else {}
    if binding.get("config"):
        config = binding["config"]
    backend = config.get("backend", run.get("backend", "nnunet"))
    history = metric_history(workspace, binding, reader=_read)
    metrics = [metric for _, metric in history]
    epochs, steps = set(), -1
    curves = []
    for metric in metrics:
        if metric["epoch"] in epochs or metric["step"] <= steps:
            raise ValueError("Epoch metrics contain duplicate epochs or non-increasing steps")
        epochs.add(metric["epoch"])
        steps = metric["step"]
        validation = metric.get("validation") or {}
        validation_cases = validation.get("cases", [])
        if validation and (
            validation.get("space") != "native_full_volume"
            or len(validation_cases) != len(expected_ids)
            or {case["case_id"] for case in validation_cases} != set(expected_ids)
        ):
            raise ValueError("In-training validation differs from the complete native cohort")
        values = {
            "epoch": metric["epoch"],
            "step": metric["step"],
            "loss": metric["loss"],
            "learning_rate": metric["learning_rate"],
            "mass_dice": _score(validation.get("mean_mass_dice")),
            "pancreas_dice": _score(validation.get("mean_pancreas_dice")),
            "validation_cases": len(validation_cases) if validation else None,
            "peak_allocated_bytes": metric.get("peak_allocated_bytes"),
            "peak_reserved_bytes": metric.get("peak_reserved_bytes"),
            "epoch_training_seconds": metric.get("epoch_training_seconds"),
            "epoch_validation_seconds": metric.get("epoch_validation_seconds"),
            "epoch_checkpoint_seconds": metric.get("epoch_checkpoint_seconds"),
        }
        curves.append(values)
    progress = _read(workspace / "progress.json")
    training = _read(workspace / "training-result.json")
    origin = _read(workspace / "scratch-origin.json")
    result: dict[str, Any] = {
        "id": run["id"],
        "model": config.get("model", run.get("model", run["id"])),
        "backend": backend,
        "comparison_group": run.get("comparison_group", backend),
        "status": state.get("status", "queued"),
        "stage": state.get("stage"),
        "gpu": state.get("gpu"),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "last_update": state.get("updated_at"),
        "seed": config.get("seed"),
        "initialization": binding.get("initialization", config.get("initialization")),
        "scratch_origin_verified": origin.get("initialization") == "scratch"
        and origin.get("external_weight_loads") == 0,
        "parameters": origin.get("parameters"),
        "training_complete": training.get("completed", False),
        "completed_steps": training.get("steps", curves[-1]["step"] if curves else 0),
        "live_step": progress.get("step"),
        "live_phase": progress.get("phase"),
        "budget_steps": config["epochs"] * config["steps_per_epoch"]
        if backend == "torch" and "epochs" in config and "steps_per_epoch" in config
        else None,
        "recipe": {
            key: value
            for key, value in config.items()
            if key
            in {
                "model",
                "backend",
                "mode",
                "context_slices",
                "patch_size",
                "spacing_mm",
                "hu_window",
                "model_options",
                "seed",
                "batch_size",
                "epochs",
                "steps_per_epoch",
                "learning_rate",
                "weight_decay",
                "foreground_probability",
                "overlap",
                "precision",
                "deterministic",
                "augment",
                "gradient_clip",
                "validation_interval",
                "progress_interval",
                "inference_batch_size",
                "prefetch_batches",
                "workers",
                "purpose",
                "resenc",
                "configuration",
                "fold",
                "num_epochs",
                "num_iterations_per_epoch",
            }
        },
        "objective": binding.get("architecture", {}).get(
            "objective", binding.get("architecture", {}).get("training_loss", {}).get("name")
        ),
        "checkpoint_selection": binding.get("checkpoint_selection"),
        "selected_checkpoint": state.get("checkpoint"),
        "selected_checkpoint_sha256": state.get("selected_checkpoint_sha256"),
        "manifest_fingerprint": binding.get("manifest_fingerprint"),
        "split_fingerprint": binding.get("split_fingerprint"),
        "code_fingerprint": _digest(binding["code"]) if "code" in binding else None,
        "runtime_fingerprint": _digest(binding["runtime"]) if "runtime" in binding else None,
        "performance": collect_performance(workspace, binding, history, expected_ids),
        "curves": curves,
        "latest_validation": next(
            (c for c in reversed(curves) if c["mass_dice"] is not None), None
        ),
        "resources": _resources(workspace, now),
        "evaluation": _evaluation(
            _read(state_dir / "evaluations" / run["id"] / "report.json"), expected_ids
        ),
        "screening_rank": None,
        "report_issues": [],
        # Failures are surfaced without copying traceback paths or scan names.
        "failure_recorded": bool(state.get("error"))
        or state.get("status") in {"failed", "interrupted"},
    }
    result["peak_allocated_bytes"] = (
        max((c["peak_allocated_bytes"] or 0 for c in curves), default=0) or None
    )
    result["peak_reserved_bytes"] = (
        max((c["peak_reserved_bytes"] or 0 for c in curves), default=0) or None
    )
    result["clinical_metrics"] = clinical_metrics(
        workspace / "clinical-detection/report.json",
        len(expected_ids),
        result.get("selected_checkpoint_sha256")
        or result.get("performance", {}).get("prediction", {}).get("checkpoint_sha256"),
    )
    if backend == "nnunet":
        from segmentary.medical_progress import parse_nnunet, tail

        logs = sorted(
            workspace.glob("nnUNet_results/**/training_log_*.txt"),
            key=lambda path: path.stat().st_mtime,
        )
        result["nnunet_patch_history"] = parse_nnunet(tail(logs[-1])) if logs else {}
    return result


def _rank_groups(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["comparison_group"]].append(row)
    conclusions = {}
    for name, members in groups.items():
        reasons = []
        if any(row["status"] != "completed" for row in members):
            reasons.append("Not all planned runs have completed")
        if any(row.get("report_issues") for row in members):
            reasons.append("A result record failed validation")
        if any(not row.get("evaluation", {}).get("complete_coverage") for row in members):
            reasons.append("Native validation coverage is incomplete")
        if any(
            not row.get("training_complete") or not row.get("scratch_origin_verified")
            for row in members
        ):
            reasons.append("Complete scratch training evidence is unavailable")
        if any(
            not all(
                row.get(key)
                for key in (
                    "code_fingerprint",
                    "split_fingerprint",
                    "checkpoint_selection",
                    "selected_checkpoint_sha256",
                )
            )
            for row in members
        ):
            reasons.append("Required source, split or checkpoint provenance is unavailable")
        if any(row.get("selected_checkpoint") != "checkpoint_best.pth" for row in members):
            reasons.append("Evaluation is not bound to the declared best validation checkpoint")
        if any(
            row.get("budget_steps") is None or row.get("completed_steps") != row.get("budget_steps")
            for row in members
        ):
            reasons.append("Declared optimization budget has not been completed")
        signatures = set()
        for row in members:
            evaluation = row.get("evaluation", {})
            signatures.add(
                _digest(
                    {
                        "cohort": evaluation.get("cohort_fingerprint"),
                        "evaluation": evaluation.get("protocol_fingerprint"),
                        "manifest": evaluation.get("manifest_fingerprint"),
                        "split": row.get("split_fingerprint"),
                        "code": row.get("code_fingerprint"),
                        "budget": row.get("budget_steps"),
                        "seed": row.get("seed"),
                        "selection": row.get("checkpoint_selection"),
                        "batch_size": row.get("recipe", {}).get("batch_size"),
                        "inference_batch_size": row.get("recipe", {}).get("inference_batch_size"),
                        "precision": row.get("recipe", {}).get("precision"),
                        "overlap": row.get("recipe", {}).get("overlap"),
                    }
                )
            )
        if len(signatures) != 1:
            reasons.append(
                "Cohort, protocol, source, split, seed, budget, batch, or selection differs"
            )
        if any(row.get("evaluation", {}).get("mass", {}).get("dice") is None for row in members):
            reasons.append("Mass Dice is unavailable")
        conclusions[name] = {
            "ranked": not reasons,
            "reasons": reasons,
            "planned_runs": len(members),
        }
        if not reasons:
            ordered = sorted(
                members, key=lambda row: (-row["evaluation"]["mass"]["dice"], row["id"])
            )
            previous = None
            rank = 0
            for index, row in enumerate(ordered, 1):
                value = row["evaluation"]["mass"]["dice"]
                if value != previous:
                    rank = index
                row["screening_rank"] = rank
                previous = value
    return conclusions


def collect(campaign: Path, state_dir: Path, *, now: float | None = None) -> dict:
    """Collect a report snapshot; malformed individual records remain failures."""
    now = time.time() if now is None else now
    spec = _read(campaign)
    if spec.get("schema_version") != 1 or not spec.get("runs"):
        raise ValueError("Expected a nonempty medical campaign schema version 1")
    ids = [run["id"] for run in spec["runs"]]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[a-zA-Z0-9_-]+", name) for name in ids):
        raise ValueError("Run IDs must be unique safe filenames")
    splits = _read(Path(spec["splits"]))
    expected_ids = splits["val"]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("Validation partition contains duplicate cases")
    rows = []
    for run in spec["runs"]:
        try:
            state = _read(state_dir / "runs" / f"{run['id']}.json")
            row = _collect_run(run, state, state_dir, expected_ids, now)
            row["expected_validation_cases"] = len(expected_ids)
            if not row["clinical_metrics"].get("available"):
                row["clinical_metrics"] = clinical_metrics(
                    campaign.parent / "clinical-detection" / run["id"] / "report.json",
                    len(expected_ids),
                    row.get("selected_checkpoint_sha256")
                    or row.get("performance", {}).get("prediction", {}).get("checkpoint_sha256"),
                )
            if row.get("backend") == "nnunet":
                protocol = spec.get("protocol", {}).get("nnunet", {})
                recipe = row.get("recipe", {})
                epochs = recipe.get("num_epochs") or protocol.get("expected_default_epochs")
                updates = recipe.get("num_iterations_per_epoch") or protocol.get(
                    "expected_default_updates_per_epoch"
                )
                if epochs and updates:
                    row["budget_steps"] = epochs * updates
                    completed = row.get("nnunet_patch_history", {}).get("epochs", [])
                    if completed:
                        row["completed_steps"] = completed[-1]["epoch"] * updates
        except (KeyError, ValueError, TypeError, OSError) as exc:
            row = {
                "id": run["id"],
                "model": run.get("model", run["id"]),
                "comparison_group": run.get("comparison_group", run.get("backend", "unknown")),
                "status": "invalid_report",
                "report_issues": [type(exc).__name__],
                "screening_rank": None,
                "curves": [],
                "evaluation": {},
                "resources": {},
            }
        rows.append(row)
    optimization = _read(state_dir / "optimization.json")
    return {
        "schema_version": 1,
        "campaign_id": spec["campaign_id"],
        "generated_at": datetime.fromtimestamp(now, UTC).isoformat(),
        "source_commit": spec.get("source_commit"),
        "split_sha256": hashlib.sha256(Path(spec["splits"]).read_bytes()).hexdigest(),
        "split_counts": {name: len(splits.get(name, [])) for name in ("train", "val", "test")},
        "grouping_status": splits.get(
            "grouping_status", splits.get("_grouping_status", "dataset_case_unverified")
        ),
        "gpus": spec.get("gpus", []),
        "groups": _rank_groups(rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "optimization": {
            "pipeline": _sanitize_pipeline(optimization.get("pipeline", {})),
            "measurement_scope": optimization.get("measurement_scope"),
            "warmup_steps": optimization.get("warmup_steps"),
            "measured_steps": optimization.get("measured_steps"),
            "gpu_name": optimization.get("gpu_name"),
            "rows": [
                {
                    key: value
                    for key, value in row.items()
                    if key
                    in {
                        "model",
                        "status",
                        "batch_size",
                        "patch_size",
                        "precision",
                        "train_step_seconds",
                        "peak_allocated_bytes",
                        "peak_reserved_bytes",
                        "scan_backend",
                        "checkpoint_mamba",
                    }
                }
                for row in optimization.get("rows", [])
            ],
        },
        "runs": rows,
    }


_INTERPRETATION = """All scores are on a 0-1 scale; — means unavailable, never zero. This is an
exploratory seed-0 screening study, with no claim of a clinical or publishable
winner. Dataset case grouping has not independently established patient identity.
Task07 mass masks are segmentation targets; they do not establish PDAC diagnosis.
The held-out test partition and 139 unannotated Task07 scans are not scored here.

In-training Dice is a mean over complete native validation examinations, counting
both-empty mass masks as 1. Final evaluation instead averages patient means over
reference-positive cases and excludes both-empty masks. These two columns answer
different questions and must not be substituted. A completed screening rank uses
the final evaluator's mass Dice only, after every planned run in that group has
finished on matching references, native evaluation protocol, source, split,
seed, optimizer-step budget, batch size, and checkpoint-selection rule.

Models use their declared objectives, including query and auxiliary losses.
Therefore the comparison tests architecture and objective together. 2.5D and 3D
inputs also have different spatial context. Equal optimizer steps are not equal
GPU-hours, voxels seen, or an architecture-specific tuning budget. Loss magnitudes
are useful within a run; they are not an accuracy ranking across objectives.
"""


def render(snapshot: dict) -> dict[str, str]:
    """Return portable files containing aggregate records only."""
    rows = snapshot["runs"]
    counts = ", ".join(
        f"{count} {status}" for status, count in sorted(snapshot["status_counts"].items())
    )
    metadata = f"Generated: {snapshot['generated_at']}. Source: `{snapshot.get('source_commit')}`."
    comparison_rows = []
    curve_sections = [
        "# Training and native validation curves",
        "",
        metadata,
        "",
        "Each row is a completed training epoch. Blank validation cells mean validation was not scheduled. The step count, rather than wall-clock order, is the comparison axis. No values are interpolated.",
        "",
    ]
    files = {}
    for row in rows:
        latest = row.get("latest_validation") or {}
        evaluation = row.get("evaluation", {})
        comparison_rows.append(
            [
                f"[{row['model']}](models/{row['id']}.md)",
                row["status"],
                row.get("stage") or "—",
                f"{row.get('completed_steps', 0)}/{row.get('budget_steps') or '—'}",
                latest.get("step", "—"),
                f"{latest.get('validation_cases', 0)}/{row.get('expected_validation_cases', '—')}",
                _number(latest.get("mass_dice")),
                _number(latest.get("pancreas_dice")),
                _number(evaluation.get("mass", {}).get("dice")),
                _number(evaluation.get("pancreas", {}).get("dice")),
                f"{evaluation.get('coverage', {}).get('valid_prediction_cases', 0)}/{row.get('expected_validation_cases', '—')}",
                row.get("screening_rank") or "—",
            ]
        )
        curve_table = _table(
            [
                "Epoch",
                "Step",
                "Training loss",
                "Learning rate",
                "Native pancreas Dice",
                "Native mass Dice",
                "Training s",
                "Validation s",
                "Checkpoint s",
            ],
            [
                [
                    curve["epoch"],
                    curve["step"],
                    _number(curve["loss"]),
                    f"{curve['learning_rate']:.7g}",
                    _number(curve["pancreas_dice"]),
                    _number(curve["mass_dice"]),
                    _number(curve.get("epoch_training_seconds")),
                    _number(curve.get("epoch_validation_seconds")),
                    _number(curve.get("epoch_checkpoint_seconds")),
                ]
                for curve in row["curves"]
            ],
        )
        curve_sections += [f"## {row['model']}", "", curve_table, ""]
        resources = row["resources"]
        per_run = [
            f"# {row['model']}",
            "",
            "[All models](../comparison.md) · [Reading guide](../README.md)",
            "",
            metadata,
            "",
            f"Status: **{row['status']}**. Stage: **{row.get('stage') or '—'}**. GPU: **{row.get('gpu', '—')}**.",
            "",
        ]
        if row.get("failure_recorded") or row["report_issues"]:
            per_run += [
                "**Needs investigation.** A worker failure or invalid result record was recorded. Its full diagnostic log remains on the training server; this page does not expose scan names or server paths.",
                "",
            ]
        per_run += [
            "## Recipe and resources",
            "",
            _table(
                ["Setting", "Value"],
                [
                    [
                        "Started / finished",
                        f"{row.get('started_at') or '—'} / {row.get('finished_at') or '—'}",
                    ],
                    ["Last worker update", row.get("last_update") or "—"],
                    [
                        "Completed / budget steps",
                        f"{row.get('completed_steps', 0)} / {row.get('budget_steps') or '—'}",
                    ],
                    [
                        "Live step / phase",
                        f"{row.get('live_step') or '—'} / {row.get('live_phase') or '—'}",
                    ],
                    ["Parameters", row.get("parameters") or "—"],
                    ["Objective", row.get("objective") or "—"],
                    ["Checkpoint selection", row.get("checkpoint_selection") or "—"],
                    ["Selected checkpoint SHA256", row.get("selected_checkpoint_sha256") or "—"],
                    [
                        "Finished-stage allocated GPU-hours",
                        _number(resources.get("finished_stage_gpu_hours")),
                    ],
                    [
                        "Active-stage allocated hours (estimate)",
                        _number(resources.get("active_stage_allocated_hours_estimate")),
                    ],
                    [
                        "Peak allocated / reserved GiB",
                        f"{_number(row.get('peak_allocated_bytes'), unit=2**30)} / {_number(row.get('peak_reserved_bytes'), unit=2**30)}",
                    ],
                ],
            ),
            "",
            "Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.",
            "",
            "```json",
            json.dumps(row.get("recipe", {}), indent=2),
            "```",
            "",
            "## Native validation",
            "",
            curve_table,
            "",
            "## Final validation evaluation",
            "",
        ]
        if evaluation:
            per_run += [
                _table(
                    [
                        "Region",
                        "Patient mean Dice",
                        "95% bootstrap interval",
                        "Surface Dice",
                        "HD95 mm",
                        "HD95 case coverage",
                    ],
                    [
                        [
                            region,
                            _number(evaluation[region]["dice"]),
                            " to ".join(_number(n) for n in evaluation[region]["dice_ci"])
                            if evaluation[region]["dice_ci"]
                            else "—",
                            _number(evaluation[region]["surface_dice"]),
                            _number(evaluation[region]["hd95_mm"]),
                            _number(evaluation[region]["hd95_coverage"]),
                        ]
                        for region in ("pancreas", "mass")
                    ],
                ),
                "",
                f"Complete prediction/reference coverage: **{evaluation['complete_coverage']}**. Native reference cohort: `{evaluation['cohort_fingerprint']}`.",
                "",
                "HD95 excludes undefined/infinite distances; use its coverage alongside Dice so missed masses cannot disappear from interpretation.",
            ]
        else:
            per_run += [
                "Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation."
            ]
        per_run += ["", model_performance_markdown(row)]
        if row.get("nnunet_patch_history"):
            per_run += [
                "",
                "## Official nnU-Net patch telemetry",
                "",
                "These patch pseudo-Dice values are not native full-volume Dice and are never substituted in the comparison quality columns.",
                "",
                _table(
                    [
                        "Completed epoch",
                        "Training loss",
                        "Mass PATCH pseudo-Dice",
                        "Pancreas CLASS PATCH pseudo-Dice",
                        "Epoch seconds",
                    ],
                    [
                        [
                            item["epoch"],
                            _number(item.get("loss")),
                            _number(item.get("mass_pseudo")),
                            _number(item.get("pancreas_pseudo")),
                            _number(item.get("seconds")),
                        ]
                        for item in row["nnunet_patch_history"].get("epochs", [])
                    ],
                ),
            ]
        files[f"models/{row['id']}.md"] = "\n".join(per_run) + "\n"
    group_text = []
    for name, group in snapshot["groups"].items():
        description = (
            "Completed exploratory ranking available; seed replication and external evaluation remain outstanding."
            if group["ranked"]
            else "No ranking: " + "; ".join(group["reasons"]) + "."
        )
        group_text.append(f"- **{name}** ({group['planned_runs']} planned runs): {description}")
    files["comparison.md"] = (
        "\n".join(
            [
                "# Task07 model comparison",
                "",
                metadata,
                "",
                f"**{counts}.**",
                "",
                "Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.",
                "",
                _table(
                    [
                        "Model",
                        "Status",
                        "Stage",
                        "Committed steps / budget",
                        "Validated step",
                        "Interim cases",
                        "Interim mass Dice",
                        "Interim pancreas Dice",
                        "Final mass Dice",
                        "Final pancreas Dice",
                        "Final cases",
                        "Screening rank",
                    ],
                    comparison_rows,
                ),
                "",
                *group_text,
                "",
                _INTERPRETATION,
            ]
        )
        + "\n"
    )
    files["learning-curves.md"] = "\n".join(curve_sections)
    files["README.md"] = (
        "\n".join(
            [
                "# Pancreas Task07: training every scratch model",
                "",
                metadata,
                "",
                f"**{counts}.** GPU queue: {', '.join(str(gpu) for gpu in snapshot['gpus']) or 'not recorded'}.",
                "",
                "1. Open [comparison.md](comparison.md) for model status and comparable validation results.",
                "2. Open [learning-curves.md](learning-curves.md) to check whether each model is learning.",
                "3. Follow a model link for its recipe, objective, timing, memory, coverage, and evaluation interval.",
                "4. Read [optimization.md](optimization.md) for the throughput investigation and measurement limits.",
                "5. Open [training-cost.md](training-cost.md) and [inference.md](inference.md) for separate training, validation, checkpoint, full-CT and model-only measurements.",
                "6. Use [results.csv](results.csv), [epochs.csv](epochs.csv), [validation-cases.csv](validation-cases.csv), [inference-cases.csv](inference-cases.csv), and [stage-invocations.csv](stage-invocations.csv) for spreadsheets. [status.json](status.json) and [records/](records/) retain numerical evidence and provenance.",
                "7. Read [clinical-metrics.md](clinical-metrics.md) for P-Sen, T-Sen, specificity, AUC and DSC, including why some metrics cannot be estimated on Task07.",
                "",
                "```text",
                "scratch-screen-20260913/",
                "  README.md              reading guide and interpretation",
                "  comparison.md          all models, status, validation, ranking gates",
                "  learning-curves.md     recorded epochs; no interpolated values",
                "  optimization.md        throughput changes and measured evidence",
                "  training-cost.md       retained epoch phases and allocation cost",
                "  inference.md           native CT and model-only speed/memory",
                "  clinical-metrics.md    detection/DSC metrics and unavailable reasons",
                "  models/<run>.md        per-model recipe, resources and evaluation",
                "  records/<run>.json     full numerical model record and lineage",
                "  epochs.csv             training/validation/checkpoint timings",
                "  validation-cases.csv   per-epoch native Dice by case ordinal",
                "  inference-cases.csv    native prediction phase timings",
                "  stage-invocations.csv  completed/failed/cancelled stage costs",
                "  results.csv            one aggregate row per run",
                "  status.json            aggregate evidence and comparison gates",
                "```",
                "",
                f"Frozen split counts: {snapshot['split_counts']['train']} training, {snapshot['split_counts']['val']} validation, {snapshot['split_counts']['test']} held-out test. Grouping status: `{snapshot['grouping_status']}`. Split SHA256: `{snapshot['split_sha256']}`.",
                "",
                "The scheduler runs one job on each available GPU and advances through the explicit queue. A completed run means its training, native validation prediction and evaluation have finished. Queued, failed and incomplete runs remain visible. No pretrained weights are allowed; resuming an existing scratch-origin run is allowed.",
                "",
                _INTERPRETATION,
                "[Medical model guide](../../../../guides/medical-models.md) · [Results by dataset](../../../README.md)",
            ]
        )
        + "\n"
    )
    stream = io.StringIO()
    fields = [
        "id",
        "model",
        "status",
        "stage",
        "gpu",
        "completed_steps",
        "budget_steps",
        "validated_step",
        "interim_mass_dice",
        "final_mass_dice",
        "final_pancreas_dice",
        "screening_rank",
        "finished_stage_gpu_hours",
        "peak_allocated_bytes",
        "interim_pancreas_dice",
        "validation_cases",
        "expected_validation_cases",
        "final_cases",
        "parameters",
        "peak_reserved_bytes",
        "prediction_complete",
        "prediction_pipeline_wall_seconds",
        "prediction_scans_per_second",
        "prediction_case_p50_seconds",
        "prediction_case_p95_seconds",
        "prediction_peak_reserved_bytes",
        "model_only_patches_per_second",
        "model_only_p50_ms",
        "model_only_p95_ms",
        "patient_sensitivity",
        "tumor_sensitivity",
        "specificity",
        "auc",
        "code_fingerprint",
        "runtime_fingerprint",
        "continuation_action",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        latest = row.get("latest_validation") or {}
        evaluation = row.get("evaluation", {})
        perf = row.get("performance", {})
        prediction = perf.get("prediction", {})
        standard = perf.get("model_only_inference", {})
        writer.writerow(
            {
                **{key: row.get(key) for key in fields[:8]},
                "validated_step": latest.get("step"),
                "interim_mass_dice": latest.get("mass_dice"),
                "final_mass_dice": evaluation.get("mass", {}).get("dice"),
                "final_pancreas_dice": evaluation.get("pancreas", {}).get("dice"),
                "screening_rank": row.get("screening_rank"),
                "finished_stage_gpu_hours": row["resources"].get("finished_stage_gpu_hours"),
                "peak_allocated_bytes": row.get("peak_allocated_bytes"),
                "interim_pancreas_dice": latest.get("pancreas_dice"),
                "validation_cases": latest.get("validation_cases"),
                "expected_validation_cases": row.get("expected_validation_cases"),
                "final_cases": evaluation.get("coverage", {}).get("valid_prediction_cases"),
                "parameters": row.get("parameters"),
                "peak_reserved_bytes": row.get("peak_reserved_bytes"),
                "prediction_complete": prediction.get("complete_cohort"),
                "prediction_pipeline_wall_seconds": prediction.get("pipeline_wall_seconds"),
                "prediction_scans_per_second": prediction.get("scans_per_second"),
                "prediction_case_p50_seconds": prediction.get("case_latency_seconds", {}).get(
                    "p50"
                ),
                "prediction_case_p95_seconds": prediction.get("case_latency_seconds", {}).get(
                    "p95"
                ),
                "prediction_peak_reserved_bytes": prediction.get("peak_reserved_bytes"),
                "model_only_patches_per_second": standard.get("patches_per_second"),
                "model_only_p50_ms": standard.get("latency_ms", {}).get("p50"),
                "model_only_p95_ms": standard.get("latency_ms", {}).get("p95"),
                **{
                    name: row.get("clinical_metrics", {})
                    .get("metrics", {})
                    .get(name, {})
                    .get("value")
                    for name in ("patient_sensitivity", "tumor_sensitivity", "specificity", "auc")
                },
                "code_fingerprint": row.get("code_fingerprint"),
                "runtime_fingerprint": row.get("runtime_fingerprint"),
                "continuation_action": perf.get("lineage", {}).get("action"),
            }
        )
    files["results.csv"] = stream.getvalue()
    optimization = snapshot.get("optimization", {})
    profile_rows = optimization.get("rows", [])
    files["optimization.md"] = (
        "\n".join(
            [
                "# Training throughput and resource checks",
                "",
                metadata,
                "",
                "The throughput investigation checks data loading, CPU work, GPU training, full-volume validation and durable result writing separately. The aim is to reduce repeated work while preserving the split, physical image geometry, objective and scratch initialization.",
                "",
                "| Area | Campaign implementation | How to interpret it |",
                "| --- | --- | --- |",
                "| Repeated preprocessing | Content-addressed, immutable shared preprocessed arrays | Models share fixed image/label preprocessing; caches are bound to source and recipe hashes |",
                "| Repeated volume decompression | Read-only NumPy memory maps with a bounded open-case cache | Avoid loading and decompressing an entire CT for every randomly chosen training patch |",
                "| Foreground sampling | Cache foreground coordinates; select and crop the required patch | Preserve sampling semantics while reducing full-volume scans and padding |",
                "| Validation cost | Full native validation at the first epoch, configured interval, and final epoch | Less frequent validation saves compute; it also changes checkpoint-selection opportunities, so cadence is recorded |",
                "| Inference overhead | Configurable batches of sliding-window tiles | This batches the same coverage and blending; it does not replace native evaluation with crop scores |",
                "| GPU scheduling | One job per GPU with existing GPU locks and an explicit queue | Ten GPUs run different models concurrently; this is not ten-GPU data parallelism for each model |",
                "| Live diagnostics | Per-step progress, per-epoch metrics, stage logs, allocator peaks | Logs distinguish slow training from full-volume validation; allocator memory differs from total device usage |",
                "",
                "## Measured model profiles",
                "",
                f"Measurement scope: {optimization.get('measurement_scope') or 'No profile records supplied in this snapshot'}. GPU: {optimization.get('gpu_name') or 'not recorded'}. Warmup / measured steps: {optimization.get('warmup_steps', 'not recorded')} / {optimization.get('measured_steps', 'not recorded')}.",
                "",
                _table(
                    [
                        "Model",
                        "Status",
                        "Precision",
                        "Batch",
                        "Patch",
                        "Scan / recompute",
                        "Seconds / training step",
                        "Peak allocated GiB",
                        "Peak reserved GiB",
                    ],
                    [
                        [
                            row.get("model"),
                            row.get("status"),
                            row.get("precision"),
                            row.get("batch_size"),
                            row.get("patch_size"),
                            f"{row.get('scan_backend') or '—'} / {row.get('checkpoint_mamba', '—')}",
                            _number(row.get("train_step_seconds")),
                            _number(row.get("peak_allocated_bytes"), unit=2**30),
                            _number(row.get("peak_reserved_bytes"), unit=2**30),
                        ]
                        for row in profile_rows
                    ],
                ),
                "",
                "A short profile measures runtime feasibility, not model quality. These values do not estimate whole-campaign runtime unless their measurement scope includes the cache, CPU transfers, native validation and checkpoint writes. Do not extrapolate small-patch SGD smoke tests to full AdamW training. Recheck real epoch timings after launch; concurrent jobs share CPU, memory and storage bandwidth.",
                "",
                "GPU utilization snapshots, vmstat, process CPU/RSS, file descriptors and, when needed, a bounded NVIDIA Nsight Systems trace can identify stalls. A profiler being installed is not evidence that a trace was captured or analyzed. The model pages retain actual stage allocation times and memory evidence; missing measurements remain unknown.",
                "",
                "[All model results](comparison.md) · [Learning curves](learning-curves.md)",
            ]
        )
        + "\n"
    )
    files["status.json"] = json.dumps(snapshot, indent=2, allow_nan=False) + "\n"
    files["optimization.md"] += "\n" + _pipeline_markdown(optimization.get("pipeline", {}))
    files.update(performance_assets(rows, metadata))
    overview = []
    for row in rows:
        final = row.get("evaluation", {})
        latest = row.get("latest_validation") or {}
        complete = final.get("complete_coverage", False)
        overview.append(
            [
                f"[{row['model']}](models/{row['id']}.md)",
                row["status"],
                f"{row.get('live_step') or row.get('completed_steps', 0)}/{row.get('budget_steps') or '—'}",
                _number(final.get("mass", {}).get("dice") if complete else latest.get("mass_dice")),
                _number(
                    final.get("pancreas", {}).get("dice")
                    if complete
                    else latest.get("pancreas_dice")
                ),
                "final reference-positive mean"
                if complete
                else f"in-training step {latest.get('step', '—')}",
                f"{final.get('coverage', {}).get('valid_prediction_cases', 0) if complete else latest.get('validation_cases', 0)}/{row.get('expected_validation_cases', '—')}",
            ]
        )
    files["README.md"] += (
        "\n## All models at a glance\n\n"
        + _table(
            [
                "Model",
                "Status",
                "Steps / budget",
                "Native mass Dice",
                "Native pancreas Dice",
                "Score scope",
                "Cases",
            ],
            overview,
        )
        + "\n"
    )
    return files


def write_report(campaign: Path, state_dir: Path, output: Path) -> dict:
    snapshot = collect(campaign, state_dir)
    for name, contents in render(snapshot).items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(contents)
        temporary.replace(path)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    snapshot = write_report(args.campaign, args.state_dir, args.out)
    print(
        json.dumps(
            {"campaign_id": snapshot["campaign_id"], "status_counts": snapshot["status_counts"]}
        )
    )


if __name__ == "__main__":
    main()
