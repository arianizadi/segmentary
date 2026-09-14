"""Portable medical timing records; never open scans, labels, or checkpoints."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from collections.abc import Callable
from pathlib import Path
from typing import Any

COMPONENTS = (
    "preprocess_seconds",
    "inference_seconds",
    "reconstruction_seconds",
    "export_seconds",
    "metrics_seconds",
)
CACHE_COUNTERS = (
    "loads",
    "source_verifications",
    "cache_verifications",
    "builds",
    "memory_hits",
    "disk_hits",
    "open_cases",
    "verified_cases",
)
CLINICAL_METRICS = (
    "patient_sensitivity",
    "tumor_sensitivity",
    "specificity",
    "auc",
    "mass_dsc",
    "pancreas_dsc",
)
CLINICAL_REASONS = {
    "not_run": "Diagnostic has not run yet.",
    "incomplete_cohort": "At least one planned native reference or prediction is unavailable or invalid.",
    "no_reference_positives": "No reference-positive groups or components.",
    "no_reference_negatives": "No fully annotated reference-negative groups.",
    "auc_requires_both_classes": "ROC AUC requires positive and negative reference groups.",
    "continuous_scores_unavailable": "Continuous image-only mass scores are unavailable for at least one case.",
}


def clinical_metrics(path: Path, expected_cases: int, checkpoint_sha256: str | None) -> dict:
    raw = _read(path)
    if not raw:
        return {
            "available": False,
            "cohort_complete": False,
            "metrics": {
                name: {
                    "value": None,
                    "status": "unavailable",
                    "reason_code": "not_run",
                    "reason": CLINICAL_REASONS["not_run"],
                    "numerator": None,
                    "denominator": None,
                }
                for name in CLINICAL_METRICS
            },
        }
    if (
        raw.get("schema_version") != 1
        or raw.get("kind") != "medical_detection_diagnostic"
        or raw.get("partition") != "val"
    ):
        raise ValueError("Clinical diagnostic schema or partition differs")
    counts = {
        key: number(value)
        for key, value in raw.get("counts", {}).items()
        if key
        in {
            "eligible_cases",
            "valid_cases",
            "patient_groups",
            "complete_patient_groups",
            "reference_positive_groups",
            "reference_negative_groups",
            "patient_true_positives",
            "patient_false_negatives",
            "patient_true_negatives",
            "patient_false_positives",
            "reference_components",
            "matched_components",
            "prediction_components",
            "lesion_false_positives",
            "lesion_false_negatives",
        }
    }
    if counts.get("eligible_cases") != expected_cases:
        raise ValueError("Clinical diagnostic cohort differs")
    provenance = {
        key: value
        for key, value in raw.get("provenance", {}).items()
        if isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    }
    if checkpoint_sha256 and provenance.get("prediction_checkpoint_sha256") != checkpoint_sha256:
        raise ValueError("Clinical diagnostic checkpoint differs")
    complete = raw.get("cohort_complete") is True
    if complete and (
        counts.get("valid_cases") != expected_cases
        or counts.get("complete_patient_groups") != counts.get("patient_groups")
    ):
        raise ValueError("Clinical complete-cohort claim differs from retained coverage")
    metrics = {}
    for name in CLINICAL_METRICS:
        item = raw["metrics"][name]
        value = number(item.get("value"))
        denominator, numerator = number(item.get("denominator")), number(item.get("numerator"))
        reason = item.get("reason_code")
        if value is not None and value > 1:
            raise ValueError("Clinical metric is outside [0,1]")
        if not complete:
            value, reason = None, "incomplete_cohort"
        if name == "specificity" and not counts.get("reference_negative_groups"):
            value, reason = None, "no_reference_negatives"
        if name == "auc" and (
            not counts.get("reference_negative_groups")
            or not counts.get("reference_positive_groups")
        ):
            value, reason = None, "auc_requires_both_classes"
        if value is not None and (not denominator or item.get("status") != "available"):
            raise ValueError("Clinical metric has no valid denominator or status")
        if value is not None and (
            numerator is None
            or denominator is None
            or denominator <= 0
            or not math.isclose(value, numerator / denominator, rel_tol=1e-8, abs_tol=1e-10)
        ):
            raise ValueError("Clinical metric differs from numerator and denominator")
        if value is None and reason not in CLINICAL_REASONS:
            raise ValueError("Clinical metric has no recognized unavailable reason")
        metrics[name] = {
            "value": value,
            "status": "available" if value is not None else "unavailable",
            "reason_code": reason,
            "reason": CLINICAL_REASONS.get(reason),
            "numerator": numerator,
            "denominator": denominator,
        }
    protocol = raw.get("protocol", {})
    return {
        "available": True,
        "cohort_complete": complete,
        "metrics": metrics,
        "counts": counts,
        "provenance": provenance,
        "protocol": {
            key: number(protocol.get(key))
            for key in ("connectivity", "iou_threshold", "minimum_prediction_volume_mm3")
        },
        "protocol_sha256": _digest(protocol),
        "grouping_status": "verified"
        if raw.get("patient_grouping_status") == "verified_patient_identity"
        else "unverified_case_groups",
    }


def standardized_inference(workspace: Path, binding: dict) -> dict:
    raw = _read(workspace / "standard-inference.json")
    if not raw:
        return {
            "status": "not_recorded",
            "scope": "No standardized CUDA-event forward benchmark has been recorded; CT case timings cannot substitute.",
        }
    if raw.get("status") != "completed" or raw.get("input_scope") != "synthetic_model_only":
        return {
            "status": "not_complete",
            "scope": "Standardized model benchmark has no completed result.",
        }
    if raw.get("model") != binding.get("config", {}).get("model") or raw.get("batch_size") != 1:
        raise ValueError("Standardized inference model or batch contract differs")
    config = binding.get("config", {})
    for key in ("patch_size", "context_slices", "precision"):
        if raw.get(key) != config.get(key):
            raise ValueError("Standardized inference input recipe differs")
    result: dict[str, Any] = {
        "status": "completed",
        "input_scope": "synthetic_model_only",
        "scope": "B1 public model forward on declared synthetic patch and precision; excludes CT loading, resampling, tiling, native reconstruction, argmax, and clinical metrics.",
    }
    for key in (
        "batch_size",
        "warmup_iterations",
        "measured_iterations",
        "patches_per_second",
        "parameters",
        "model_weight_bytes",
        "peak_allocated_bytes",
        "peak_reserved_bytes",
    ):
        result[key] = number(raw.get(key))
    result["latency_ms"] = {
        key: number(raw.get("latency_ms", {}).get(key))
        for key in ("mean", "p50", "p95", "min", "max")
    }
    for key in (
        "checkpoint_sha256",
        "config_fingerprint",
        "code_fingerprint",
        "runtime_fingerprint",
    ):
        value = raw.get(key)
        result[key] = (
            value
            if isinstance(value, str)
            and len(value) == 64
            and all(c in "0123456789abcdef" for c in value)
            else None
        )
    if not result["checkpoint_sha256"]:
        raise ValueError("Standardized inference lacks checkpoint provenance")
    for field, document in (
        ("config_fingerprint", "config"),
        ("code_fingerprint", "code"),
        ("runtime_fingerprint", "runtime"),
    ):
        if document not in binding or result[field] != _digest(binding[document]):
            raise ValueError("Standardized inference fingerprint differs from bound run")
    if raw.get("binding_identity") is not None and raw["binding_identity"] != _digest(binding):
        raise ValueError("Standardized inference binding identity differs")
    index = _read(workspace / "checkpoint-index.json")
    if index and result["checkpoint_sha256"] != index.get("files", {}).get(
        "checkpoint_best.pth", {}
    ).get("sha256"):
        raise ValueError("Standardized inference benchmark is bound to another checkpoint")
    samples = [number(value) for value in raw.get("sample_latencies_ms", [])]
    if (
        not samples
        or len(samples) != result["measured_iterations"]
        or any(value is None or value <= 0 for value in samples)
    ):
        raise ValueError("Standardized inference needs positive measured sample latencies")
    measured = _summary([value for value in samples if value is not None])
    for field in ("mean", "p50", "p95", "min", "max"):
        actual = result["latency_ms"][field]
        if actual is None or not math.isclose(actual, measured[field], rel_tol=1e-5, abs_tol=1e-6):
            raise ValueError("Standardized inference latency summary differs from samples")
    if result["patches_per_second"] is None or not math.isclose(
        result["patches_per_second"], 1000 / measured["mean"], rel_tol=1e-5, abs_tol=1e-6
    ):
        raise ValueError("Standardized inference throughput differs from measured latency")
    result["sample_latencies_ms"] = samples
    result["patch_size"] = raw["patch_size"]
    result["context_slices"] = raw["context_slices"]
    result["precision"] = raw["precision"]
    gpu_name = raw.get("gpu_name")
    result["gpu_name"] = (
        gpu_name
        if isinstance(gpu_name, str)
        and len(gpu_name) < 128
        and "/" not in gpu_name
        and "\n" not in gpu_name
        else None
    )
    result["physical_gpu"] = (
        str(raw["physical_gpu"]) if str(raw.get("physical_gpu", "")).isdigit() else None
    )
    return result


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Expected a medical reporting object")
    return value


def number(value: Any) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("Resource measurements must be finite nonnegative numbers")
    return float(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _components(value: dict) -> dict:
    return {key: number(value[key]) for key in COMPONENTS if key in value}


def _prediction_statistics(value: dict) -> dict:
    if not value:
        return {}
    if value.get("mass_score_definition") != "maximum_native_class2_probability":
        raise ValueError("Unknown image-only mass score definition")
    maximum = number(value.get("mass_probability_max"))
    native = number(value.get("native_voxels"))
    predicted = number(value.get("predicted_mass_voxels"))
    if (
        maximum is None
        or maximum > 1
        or native is None
        or native <= 0
        or predicted is None
        or predicted > native
    ):
        raise ValueError("Invalid native prediction statistics")
    return {
        "mass_probability_max": maximum,
        "native_voxels": native,
        "predicted_mass_voxels": predicted,
        "mass_score_definition": "maximum_native_class2_probability",
    }


def _counters(value: dict) -> dict:
    result = {}
    for key in CACHE_COUNTERS:
        if key in value:
            if type(value[key]) is not int or value[key] < 0:
                raise ValueError("Cache counters must be nonnegative integers")
            result[key] = value[key]
    return result


def metric_history(
    workspace: Path, binding: dict, *, depth: int = 0, reader: Callable[[Path], dict] = _read
) -> list[tuple[str, dict]]:
    """Recover parent epochs only through a hash-verified continuation binding.

    Parent rows stop at the preserved checkpoint step; discarded post-checkpoint
    work cannot masquerade as retained training. Segments remain distinguishable.
    No epoch is counted twice and no continuation becomes another independent seed.
    """
    if depth > 8:
        raise ValueError("Continuation history exceeds the supported depth")
    rows: list[tuple[str, dict]] = []
    continuation = reader(workspace / "continuation.json")
    if continuation:
        parent = continuation["parent"]
        if not binding.get("continuation_lineage") or binding["continuation_lineage"][-1] != parent:
            raise ValueError("Continuation history differs from bound parent lineage")
        parent_root = Path(parent["workspace"])
        parent_path = parent_root / "binding.json"
        if (
            not parent_path.is_file()
            or hashlib.sha256(parent_path.read_bytes()).hexdigest() != parent["binding_sha256"]
        ):
            # A portable report can still describe its local continuation when
            # the original workspace is unavailable. Its missing history is explicit.
            pass
        else:
            old = reader(parent_path)
            if _digest(old) != parent["binding_identity"]:
                raise ValueError("Continuation parent binding identity differs")
            checkpoint_step = number(continuation["resume_step"])
            if continuation.get("action") == "predict":
                completion_path = parent_root / "training-result.json"
                expected = parent.get("artifact_sha256", {}).get("training-result.json")
                if (
                    not expected
                    or not completion_path.is_file()
                    or hashlib.sha256(completion_path.read_bytes()).hexdigest() != expected
                ):
                    raise ValueError("Prediction continuation lacks verified parent completion")
                completion = reader(completion_path)
                if completion.get("completed") is not True:
                    raise ValueError("Prediction continuation parent training is incomplete")
                checkpoint_step = number(completion.get("steps"))
            if checkpoint_step is None:
                raise ValueError("Continuation history has no preserved training frontier")
            for scope, metric in metric_history(parent_root, old, depth=depth + 1, reader=reader):
                if metric["step"] <= checkpoint_step:
                    rows.append((f"parent/{scope}", metric))
    rows.extend(
        ("current", reader(path)) for path in sorted((workspace / "metrics").glob("epoch-*.json"))
    )
    return rows


def _summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "min": None, "max": None}
    ordered = sorted(values)
    # Inclusive linear percentile, stated so small cohorts remain reproducible.
    position = 0.95 * (len(ordered) - 1)
    lower = int(position)
    p95 = ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (
        position - lower
    )
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "p50": statistics.median(values),
        "p95": p95,
        "min": min(values),
        "max": max(values),
    }


def collect_performance(
    workspace: Path, binding: dict, history: list[tuple[str, dict]], expected_ids: list[str]
) -> dict:
    """Retain numerical logs with stable case ordinals instead of scan identifiers."""
    positions = {case_id: index + 1 for index, case_id in enumerate(expected_ids)}
    epoch_rows = []
    validation_rows = []
    for scope, metric in history:
        validation = metric.get("validation") or {}
        row = {"segment": scope, "epoch": metric["epoch"], "step": metric["step"]}
        for name in (
            "epoch_training_seconds",
            "epoch_validation_seconds",
            "epoch_checkpoint_seconds",
            "wall_seconds",
            "peak_allocated_bytes",
            "peak_reserved_bytes",
        ):
            row[name] = number(metric.get(name))
        row["validation_components"] = _components(validation.get("component_seconds", {}))
        row["inference_cache"] = _counters(validation.get("inference_cache", {}))
        epoch_rows.append(row)
        for case in validation.get("cases", []):
            if case["case_id"] not in positions:
                raise ValueError("Validation timing case is outside the frozen cohort")
            item = {
                "segment": scope,
                "epoch": metric["epoch"],
                "step": metric["step"],
                "case_number": positions[case["case_id"]],
                "mass_dice": number(case.get("mass_dice")),
                "pancreas_dice": number(case.get("pancreas_dice")),
                "mass_present": case.get("mass_present")
                if type(case.get("mass_present")) is bool
                else None,
                "predicted_mass_voxels": number(case.get("predicted_mass_voxels")),
                "wall_seconds": number(case.get("wall_seconds")),
                **_components(case.get("component_seconds", {})),
                **_prediction_statistics(case.get("prediction_statistics", {})),
            }
            if any(
                item[key] is not None and item[key] > 1 for key in ("mass_dice", "pancreas_dice")
            ):
                raise ValueError("Per-case Dice is outside [0,1]")
            validation_rows.append(item)
    segments = []
    for scope in dict.fromkeys(row["segment"] for row in epoch_rows):
        epochs = [row for row in epoch_rows if row["segment"] == scope]
        totals = {}
        for field in (
            "epoch_training_seconds",
            "epoch_validation_seconds",
            "epoch_checkpoint_seconds",
        ):
            values = [row[field] for row in epochs if row[field] is not None]
            totals[field] = {
                "seconds": sum(values) if values else None,
                "recorded_epochs": len(values),
                "segment_epochs": len(epochs),
            }
        segments.append(
            {
                "segment": scope,
                "first_step": min(row["step"] for row in epochs),
                "last_step": max(row["step"] for row in epochs),
                "epochs": len(epochs),
                "totals": totals,
            }
        )

    status = _read(workspace / "predictions/val/prediction-status.json")
    samples = []
    seen = set()
    for case in status.get("cases", []):
        identifier = case["case_id"]
        if identifier not in positions or identifier in seen:
            raise ValueError("Prediction timing cohort is duplicate or outside validation")
        seen.add(identifier)
        if case.get("status") not in {"completed", "failed"}:
            raise ValueError("Prediction timing status is unknown")
        samples.append(
            {
                "case_number": positions[identifier],
                "status": case["status"],
                "wall_seconds": number(case.get("wall_seconds")),
                **_components(case.get("component_seconds", {})),
                **_prediction_statistics(case.get("prediction_statistics", {})),
            }
        )
    if status and status.get("partition") != "val":
        raise ValueError("Only validation inference belongs in this report")
    completed = sum(row["status"] == "completed" for row in samples)
    failures = sum(row["status"] == "failed" for row in samples)
    perf = status.get("performance", {})
    wall = number(perf.get("wall_seconds"))
    known_scope = perf.get("scope") == "model_ready_to_last_case_including_cache_export"
    full = (
        bool(expected_ids)
        and completed == len(expected_ids)
        and not failures
        and perf.get("completed") is True
    )
    latency = _summary(
        [
            row["wall_seconds"]
            for row in samples
            if row["status"] == "completed" and row["wall_seconds"] is not None
        ]
    )
    stage_rows = []
    for path in sorted((workspace / "stages").glob("*/outcome.json")):
        outcome = _read(path)
        stage_rows.append(
            {
                "action": outcome.get("action")
                if outcome.get("action") in {"preprocess", "train", "predict"}
                else "other",
                "status": outcome.get("status")
                if outcome.get("status") in {"completed", "failed", "cancelled"}
                else "unknown",
                "wall_seconds": number(outcome.get("wall_seconds")),
                "allocated_gpu_hours": number(outcome.get("allocated_gpu_hours")),
            }
        )
    lineage = [
        {
            key: item.get(key)
            for key in (
                "binding_sha256",
                "binding_identity",
                "code_digest",
                "origin_sha256",
                "policy_digest",
                "action",
            )
        }
        for item in binding.get("continuation_lineage", [])
    ]
    continuation = _read(workspace / "continuation.json")
    return {
        "epochs": epoch_rows,
        "training_segments": segments,
        "validation_cases": validation_rows,
        "stage_invocations": stage_rows,
        "lineage": {
            "is_continuation": bool(lineage),
            "independent_training_replicate": not bool(lineage),
            "parents": lineage,
            "continued_from_step": number(continuation.get("resume_step")),
            "action": continuation.get("action")
            if continuation.get("action") in {"predict", "resume"}
            else None,
            "parent_history_available": any(row["segment"] != "current" for row in epoch_rows)
            if lineage
            else None,
        },
        "prediction": {
            "available": bool(status),
            "expected_cases": len(expected_ids),
            "recorded_cases": len(samples),
            "completed_cases": completed,
            "failed_cases": failures,
            "complete_cohort": full,
            "cases": samples,
            "case_latency_seconds": latency,
            "case_latency_scope": "overlapped admission-to-export including queue time"
            if status.get("timing_scope")
            else "legacy serial case wall including preprocessing and export; excludes status/checkpoint hash writes",
            "pipeline_wall_seconds": wall,
            "pipeline_scope": "model_ready_to_last_case_including_cache_export"
            if known_scope
            else "not_recorded",
            "scans_per_second": completed / wall
            if full and known_scope and wall and wall > 0
            else None,
            "peak_allocated_bytes": number(perf.get("peak_allocated_bytes")),
            "peak_reserved_bytes": number(perf.get("peak_reserved_bytes")),
            "cache": _counters(perf.get("cache", {})),
            "checkpoint_sha256": status.get("checkpoint_sha256"),
        },
        "model_only_inference": standardized_inference(workspace, binding),
        "definitions": {
            "epoch_totals": "Observed committed epoch logs only; missing checkpoint times remain missing. Parent and current segments are separate, not independent seeds.",
            "stage_cost": "Current workspace invocations only, including failures/cancellations. Allocation is not utilization. Parent allocation is not copied or double-counted.",
            "case_numbers": "One-based positions in frozen validation partition; no scan or patient identifiers published.",
            "inference_seconds": "Tiled pipeline including host/device transfers, model forward, softmax and CPU blending; not model-only latency.",
            "percentiles": "Inclusive linear p95 over recorded case wall times; heterogeneous CT sizes and queue time prevent a standardized model-speed claim.",
        },
    }


def _fmt(value: Any, *, unit: float = 1) -> str:
    return "—" if value is None else f"{value / unit:.3f}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    return "\n".join(
        "| " + " | ".join(cell(value) for value in row) + " |"
        for row in [headers, ["---"] * len(headers), *rows]
    )


def model_performance_markdown(row: dict) -> str:
    performance = row.get("performance", {})
    prediction = performance.get("prediction", {})
    latency = prediction.get("case_latency_seconds", {})
    model = performance.get("model_only_inference", {})
    lines = [
        "## Recorded training and inference data",
        "",
        "[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/"
        + row["id"]
        + ".json)",
        "",
    ]
    lines += [
        _table(
            ["Measurement", "Value"],
            [
                [
                    "Native predictions completed / expected / failed",
                    f"{prediction.get('completed_cases', 0)} / {prediction.get('expected_cases', '—')} / {prediction.get('failed_cases', 0)}",
                ],
                [
                    "Measured prediction pipeline wall seconds",
                    _fmt(prediction.get("pipeline_wall_seconds")),
                ],
                ["Complete-cohort scans per second", _fmt(prediction.get("scans_per_second"))],
                [
                    "Recorded case latency mean / p50 / p95 seconds",
                    " / ".join(_fmt(latency.get(key)) for key in ("mean", "p50", "p95")),
                ],
                [
                    "Prediction allocated / reserved peak GiB",
                    f"{_fmt(prediction.get('peak_allocated_bytes'), unit=2**30)} / {_fmt(prediction.get('peak_reserved_bytes'), unit=2**30)}",
                ],
                ["Standardized model-only benchmark", model.get("status", "not_recorded")],
                [
                    "Model-only patches/s; p50 / p95 ms",
                    f"{_fmt(model.get('patches_per_second'))}; {_fmt(model.get('latency_ms', {}).get('p50'))} / {_fmt(model.get('latency_ms', {}).get('p95'))}",
                ],
            ],
        ),
        "",
        "Case latency includes preprocessing, tiled inference, native reconstruction and export; in overlapped runs it also includes queue time. It is neither model-only latency nor an additive stage wall time. No speed is inferred from GPU utilization snapshots.",
        "",
    ]
    lineage = performance.get("lineage", {})
    if lineage.get("is_continuation"):
        lines += [
            f"This is a **{lineage.get('action')} continuation**, starting from preserved step {lineage.get('continued_from_step')}. It is not an independent training replicate. Parent and current timing segments stay separate. Parent epoch history available: **{lineage.get('parent_history_available')}**.",
            "",
        ]
    return "\n".join(lines)


def performance_assets(rows: list[dict], metadata: str) -> dict[str, str]:
    """Generate readable cross-model tables and lossless numerical CSV subsets."""
    files = {}
    costs, inference, model_only, clinical = [], [], [], []
    epochs: list[dict] = []
    validation: list[dict] = []
    predictions: list[dict] = []
    stages: list[dict] = []
    for row in rows:
        prefix = {"run_id": row["id"], "model": row["model"]}
        perf = row.get("performance", {})
        link = f"[{row['model']}](models/{row['id']}.md)"
        segments = perf.get("training_segments", [])
        for segment in segments or [{"segment": "current", "totals": {}, "epochs": 0}]:
            totals = segment["totals"]
            values = []
            for name in (
                "epoch_training_seconds",
                "epoch_validation_seconds",
                "epoch_checkpoint_seconds",
            ):
                metric = totals.get(name, {})
                values.append(
                    f"{_fmt(metric.get('seconds'))} ({metric.get('recorded_epochs', 0)}/{segment['epochs']} epochs)"
                )
            costs.append(
                [
                    link,
                    row["status"],
                    segment["segment"],
                    *values,
                    _fmt(row.get("resources", {}).get("finished_stage_gpu_hours"))
                    if segment["segment"] == "current"
                    else "—",
                ]
            )
        pred = perf.get("prediction", {})
        latency = pred.get("case_latency_seconds", {})
        inference.append(
            [
                link,
                row["status"],
                f"{pred.get('completed_cases', 0)}/{pred.get('expected_cases', row.get('expected_validation_cases', '—'))}",
                pred.get("failed_cases", 0),
                _fmt(pred.get("pipeline_wall_seconds")),
                _fmt(pred.get("scans_per_second")),
                _fmt(latency.get("p50")),
                _fmt(latency.get("p95")),
                _fmt(pred.get("peak_reserved_bytes"), unit=2**30),
            ]
        )
        standard = perf.get("model_only_inference", {})
        model_only.append(
            [
                link,
                standard.get("status", "not_recorded"),
                standard.get("patch_size", row.get("recipe", {}).get("patch_size", "—")),
                standard.get("precision", row.get("recipe", {}).get("precision", "—")),
                _fmt(standard.get("patches_per_second")),
                _fmt(standard.get("latency_ms", {}).get("p50")),
                _fmt(standard.get("latency_ms", {}).get("p95")),
                standard.get("parameters", row.get("parameters", "—")),
                _fmt(standard.get("model_weight_bytes"), unit=2**20),
                _fmt(standard.get("peak_reserved_bytes"), unit=2**30),
            ]
        )
        detection = row.get("clinical_metrics", {})
        clinical_values = detection.get("metrics", {})
        reasons = sorted(
            {
                metric.get("reason")
                for metric in clinical_values.values()
                if metric.get("value") is None and metric.get("reason")
            }
        )
        clinical.append(
            [
                link,
                row["status"],
                detection.get("cohort_complete", False),
                *[_fmt(clinical_values.get(name, {}).get("value")) for name in CLINICAL_METRICS],
                "; ".join(reasons) or ("—" if detection else "Diagnostic has not run yet."),
            ]
        )
        epochs.extend(
            {**prefix, **{key: value for key, value in item.items() if not isinstance(value, dict)}}
            for item in perf.get("epochs", [])
        )
        validation.extend({**prefix, **item} for item in perf.get("validation_cases", []))
        predictions.extend({**prefix, **item} for item in pred.get("cases", []))
        stages.extend(
            {**prefix, "invocation_number": index + 1, **item}
            for index, item in enumerate(perf.get("stage_invocations", []))
        )
        files[f"records/{row['id']}.json"] = json.dumps(row, indent=2, allow_nan=False) + "\n"
    files["training-cost.md"] = "\n".join(
        [
            "# Recorded training cost",
            "",
            metadata,
            "",
            "All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.",
            "",
            _table(
                [
                    "Model",
                    "Status",
                    "History segment",
                    "Training seconds (coverage)",
                    "Validation seconds (coverage)",
                    "Checkpoint seconds (coverage)",
                    "Current finished-stage GPU-h",
                ],
                costs,
            ),
            "",
            "[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)",
            "",
            "The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.",
            "",
        ]
    )
    files["inference.md"] = "\n".join(
        [
            "# Native CT pipeline and standardized model inference",
            "",
            metadata,
            "",
            "## Native CT prediction",
            "",
            "This measures heterogeneous full CT examinations. Case p50/p95 includes CPU work and, in overlapped runs, queue time. Scans/s is reported only from a complete successful cohort and a measured aggregate pipeline wall timer; overlapping case latencies are never summed to infer throughput. Failed and missing cases remain visible. Peak memory is Torch allocator memory, excluding the CUDA context.",
            "",
            _table(
                [
                    "Model",
                    "Status",
                    "Cases",
                    "Failed",
                    "Pipeline wall s",
                    "Scans/s",
                    "Case p50 s",
                    "Case p95 s",
                    "Peak reserved GiB",
                ],
                inference,
            ),
            "",
            "[Per-case numerical timings](inference-cases.csv) use stable validation case ordinals. They contain preprocessing, tiled inference, reconstruction and export when recorded. Tiled inference includes copies, softmax and CPU blending; it is not model-only forward latency.",
            "",
            "## Standardized model-only forward",
            "",
            "B1 synthetic inputs use each model's declared patch, context and precision. Warmup/sample counts and checkpoint/source/runtime fingerprints are retained in model records. The benchmark keeps inference-mode/autocast active across its warmup and measured calls, including a warm autocast weight cache; the clinical tile pipeline may enter autocast separately for each batch. Patches/s is the reciprocal of mean CUDA-event forward latency, not complete CT scans/s. Different 2D and 3D patch dimensions are separate workloads. Unmeasured models remain marked not_recorded until their benchmark executes.",
            "",
            _table(
                [
                    "Model",
                    "Benchmark",
                    "Patch",
                    "Precision",
                    "Patches/s",
                    "p50 ms",
                    "p95 ms",
                    "Parameters",
                    "Weight MiB",
                    "Peak reserved GiB",
                ],
                model_only,
            ),
            "",
            "[Training cost](training-cost.md) · [Comparison](comparison.md)",
            "",
        ]
    )
    files["clinical-metrics.md"] = "\n".join(
        [
            "# Exploratory mass detection and segmentation metrics",
            "",
            metadata,
            "",
            "All metrics use a 0-1 scale. P-Sen flags a positive group when any retained mass component is predicted, even at the wrong location. T-Sen requires one-to-one localization matches to reference connected components. Spe is the true-negative fraction among fully annotated negative groups. AUC requires continuous image-only scores and both reference classes. DSC is segmentation overlap. These definitions are separate from clinical diagnosis.",
            "",
            _table(
                [
                    "Model",
                    "Status",
                    "Complete cohort",
                    "P-Sen (group proxy)",
                    "T-Sen",
                    "Spe",
                    "AUC",
                    "Mass DSC",
                    "Pancreas DSC",
                    "Unavailable reasons",
                ],
                clinical,
            ),
            "",
            "**Task07 limitations:** the current frozen 42-case validation cohort contains 42 mass-positive examinations and no fully annotated mass-negative examinations. Specificity and ROC AUC therefore cannot be estimated on this cohort. Unlabeled scans and organ-only labels are not verified negative controls. Dataset-case grouping is not established patient linkage, so P-Sen is a case/group proxy; connected components are not independently annotated lesion identities.",
            "",
            "The diagnostic uses its recorded fixed component threshold, connectivity and IoU matching protocol. Per-model JSON records retain metric numerators/denominators, thresholds and source/checkpoint hashes. A failed or missing native reference/prediction withholds complete-cohort values. No PanTS leaderboard comparison is claimed without matching its cohort and official protocol. Class 2 means an annotated mass, not confirmed pancreatic cancer.",
            "",
            "[All numerical records](records/) · [Primary native Dice comparison](comparison.md) · [Inference](inference.md)",
            "",
        ]
    )
    exports = {
        "epochs.csv": (
            epochs,
            [
                "run_id",
                "model",
                "segment",
                "epoch",
                "step",
                "epoch_training_seconds",
                "epoch_validation_seconds",
                "epoch_checkpoint_seconds",
                "wall_seconds",
                "peak_allocated_bytes",
                "peak_reserved_bytes",
            ],
        ),
        "validation-cases.csv": (
            validation,
            [
                "run_id",
                "model",
                "segment",
                "epoch",
                "step",
                "case_number",
                "mass_dice",
                "pancreas_dice",
                "mass_present",
                "predicted_mass_voxels",
                "mass_probability_max",
                "native_voxels",
                "mass_score_definition",
                "wall_seconds",
                *COMPONENTS,
            ],
        ),
        "inference-cases.csv": (
            predictions,
            [
                "run_id",
                "model",
                "case_number",
                "status",
                "wall_seconds",
                *COMPONENTS,
                "mass_probability_max",
                "native_voxels",
                "predicted_mass_voxels",
                "mass_score_definition",
            ],
        ),
        "stage-invocations.csv": (
            stages,
            [
                "run_id",
                "model",
                "invocation_number",
                "action",
                "status",
                "wall_seconds",
                "allocated_gpu_hours",
            ],
        ),
    }
    for name, (csv_rows, fields) in exports.items():
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)
        files[name] = stream.getvalue()
    return files
