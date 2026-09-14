#!/usr/bin/env python3
"""Separate, fixed-protocol mass-detection diagnostics for saved native masks.

Never trains, loads checkpoints, chooses a checkpoint, or changes primary scores.
A primary native evaluation report binds the exact cohort and mask hashes. Class
2 is an annotated mass, not a confirmed cancer diagnosis. See the companion guide.
"""

from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from segmentary.medical.backend import _digest, _documents
from segmentary.medical.evaluation import (
    _affine,
    _decode_labels,
    _read_volume,
    _same_geometry,
    lesion_detection_metrics,
)
from segmentary.medical.geometry import sha256_file

DEFAULT_PROTOCOL = {
    "schema_version": 1,
    "name": "exploratory_mass_detection_v1",
    "connectivity": 26,
    "iou_threshold": 0.1,
    "minimum_prediction_volume_mm3": 10.0,
    "patient_reference_rule": "any_annotated_class2_voxel_in_any_group_scan",
    "patient_prediction_rule": "any_retained_class2_component_in_any_group_scan_regardless_of_location",
    "lesion_matching": "maximum_cardinality_one_to_one_then_maximum_total_iou",
    "reference_component_filter": "none",
    "mass_score_definition": "maximum_native_class2_probability",
    "patient_score_aggregation": "maximum_across_group_scans",
    "dice_aggregation": "equal_weight_group_means_over_reference_positive_scans_without_component_filter",
    "threshold_selection": "fixed_before_this_diagnostic_evaluation_not_tuned_on_test",
}
METRICS = (
    "patient_sensitivity",
    "tumor_sensitivity",
    "specificity",
    "auc",
    "mass_dsc",
    "pancreas_dsc",
)
REASONS = {
    "incomplete_cohort": "At least one planned native reference or prediction is unavailable or invalid.",
    "no_reference_positives": "This cohort has no reference-positive groups or components.",
    "no_reference_negatives": "This cohort has no fully annotated reference-negative groups.",
    "auc_requires_both_classes": "ROC AUC requires reference-positive and reference-negative groups.",
    "continuous_scores_unavailable": "At least one scan lacks a valid image-only continuous mass score.",
}


def _json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _metric(numerator: float | None, denominator: int, reason: str | None = None) -> dict:
    return {
        "value": numerator / denominator
        if reason is None and denominator and numerator is not None
        else None,
        "numerator": numerator,
        "denominator": denominator,
        "status": "unavailable" if reason else "available",
        "reason_code": reason,
        "reason": REASONS.get(reason) if reason else None,
    }


def _auc(targets: list[bool], scores: list[float]) -> float:
    """Mann-Whitney ROC area with half credit for ties; no threshold fitting."""
    from scipy.stats import rankdata

    positive = np.asarray(targets, dtype=bool)
    p, n = int(positive.sum()), int((~positive).sum())
    if not p or not n:
        raise ValueError("ROC AUC requires both reference classes")
    ranks = rankdata(np.asarray(scores), method="average")
    return float((ranks[positive].sum() - p * (p + 1) / 2) / (p * n))


def _validate_protocol(protocol: dict) -> dict:
    protocol = copy.deepcopy(protocol)
    if set(protocol) != set(DEFAULT_PROTOCOL):
        raise ValueError("Unexpected diagnostic protocol fields")
    for key in set(protocol) - {"connectivity", "iou_threshold", "minimum_prediction_volume_mm3"}:
        if protocol[key] != DEFAULT_PROTOCOL[key]:
            raise ValueError("Unsupported diagnostic protocol definition")
    if type(protocol["connectivity"]) is not int or protocol["connectivity"] not in (6, 18, 26):
        raise ValueError("Connectivity must be 6, 18 or 26")
    for key in ("iou_threshold", "minimum_prediction_volume_mm3"):
        if type(protocol[key]) not in (int, float) or not math.isfinite(protocol[key]):
            raise ValueError("Thresholds must be finite numbers")
    if not 0 < protocol["iou_threshold"] <= 1 or protocol["minimum_prediction_volume_mm3"] < 0:
        raise ValueError("Invalid diagnostic threshold")
    return protocol


def _continuous_score(record: dict, prediction: np.ndarray) -> float | None:
    # Deliberately receives prediction only. Never derives a score from reference
    # masks, Dice, true-positive matches, or the binary patient decision.
    stats = record.get("prediction_statistics", {})
    if not isinstance(stats, dict):
        return None
    value = stats.get("mass_probability_max")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if (
        stats.get("mass_score_definition") != DEFAULT_PROTOCOL["mass_score_definition"]
        or type(value) not in (int, float)
        or not math.isfinite(value)
        or not 0 <= value <= 1
        or stats.get("native_voxels") != prediction.size
        or stats.get("predicted_mass_voxels") != int(np.count_nonzero(prediction == 2))
    ):
        return None
    return float(value)


def _dice(reference: np.ndarray, prediction: np.ndarray) -> float | None:
    if not reference.any():
        return None
    return float(
        2 * np.count_nonzero(reference & prediction) / (reference.sum() + prediction.sum())
    )


def _prediction_provenance(
    prediction_dir: Path, status: dict, nnunet: bool, manifest_path: Path, splits_path: Path
) -> tuple[dict, list[Path]]:
    """Bind telemetry to its existing run without importing or loading a model."""
    workspace = prediction_dir.resolve().parent.parent
    if prediction_dir.resolve().parent.name != "predictions":
        raise ValueError("Use the original bound workspace/predictions/partition directory")
    binding_path, index_path = workspace / "binding.json", workspace / "checkpoint-index.json"
    binding, index = _json(binding_path), _json(index_path)
    for name, path in (("manifest", manifest_path), ("splits", splits_path)):
        if binding.get(f"{name}_sha256") != sha256_file(path):
            raise ValueError("Prediction workspace is bound to different manifest/splits")
    files = [binding_path, index_path]
    if nnunet:
        plan_path = workspace / "plan-binding.json"
        plan = _json(plan_path)
        if plan.get("binding_digest") != _digest(binding):
            raise ValueError("nnU-Net plan belongs to a different binding")
        identity = _digest({"binding": binding, "runtime": plan["runtime"]})
        aliases = index
        if Path(status.get("output", "")).resolve() != prediction_dir.resolve():
            raise ValueError("nnU-Net prediction record belongs to a different output directory")
        files.append(plan_path)
    else:
        identity = _digest(binding)
        if status.get("identity") != identity or index.get("identity") != identity:
            raise ValueError("Prediction telemetry/checkpoint index belongs to a different run")
        if index.get("initialization") != "scratch":
            raise ValueError("Prediction checkpoint index is not scratch-origin")
        aliases = index.get("files", {})
    selected = [
        name
        for name, record in aliases.items()
        if name in {"checkpoint_latest.pth", "checkpoint_best.pth", "checkpoint_final.pth"}
        and record.get("sha256") == status["checkpoint_sha256"]
        and (not nnunet or record.get("identity") == identity)
    ]
    if not selected:
        raise ValueError("Prediction checkpoint is absent from its bound checkpoint index")
    return {
        "prediction_binding_identity": identity,
        "prediction_checkpoint_aliases": sorted(selected),
        "binding_sha256": sha256_file(binding_path),
        "checkpoint_index_sha256": sha256_file(index_path),
    }, files


def summarize(rows: list[dict], *, complete: bool) -> tuple[dict, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["patient_id"]].append(row)
    valid = [row for row in rows if row["status"] == "ok"]
    complete_groups = [
        items for items in groups.values() if all(x["status"] == "ok" for x in items)
    ]
    labels = [any(x["reference_positive"] for x in items) for items in complete_groups]
    decisions = [any(x["prediction_positive"] for x in items) for items in complete_groups]
    scores = [
        max(x["continuous_mass_score"] for x in items)
        if all(x["continuous_mass_score"] is not None for x in items)
        else None
        for items in complete_groups
    ]
    tp = sum(t and p for t, p in zip(labels, decisions, strict=True))
    tn = sum(not t and not p for t, p in zip(labels, decisions, strict=True))
    positives, negatives = sum(labels), len(labels) - sum(labels)
    reference_components = sum(x["lesions"]["reference_components"] for x in valid)
    matched = sum(x["lesions"]["true_positives"] for x in valid)
    counts = {
        "eligible_cases": len(rows),
        "valid_cases": len(valid),
        "patient_groups": len(groups),
        "complete_patient_groups": len(complete_groups),
        "reference_positive_groups": positives,
        "reference_negative_groups": negatives,
        "patient_true_positives": tp,
        "patient_false_negatives": positives - tp,
        "patient_true_negatives": tn,
        "patient_false_positives": negatives - tn,
        "reference_components": reference_components,
        "matched_components": matched,
        "prediction_components": sum(x["lesions"]["prediction_components"] for x in valid),
        "lesion_false_positives": sum(x["lesions"]["false_positives"] for x in valid),
        "lesion_false_negatives": reference_components - matched,
        "status_counts": dict(Counter(x["status"] for x in rows)),
        "counts_scope": "full_cohort" if complete else "observed_valid_cases_only",
    }
    metrics = {
        "patient_sensitivity": _metric(
            tp, positives, None if positives else "no_reference_positives"
        ),
        "specificity": _metric(tn, negatives, None if negatives else "no_reference_negatives"),
        "tumor_sensitivity": _metric(
            matched,
            reference_components,
            None if reference_components else "no_reference_positives",
        ),
    }
    for region in ("mass", "pancreas"):
        means = [
            float(np.mean([x[f"{region}_dsc"] for x in items if x[f"{region}_dsc"] is not None]))
            for items in complete_groups
            if any(x[f"{region}_dsc"] is not None for x in items)
        ]
        metrics[f"{region}_dsc"] = _metric(
            sum(means), len(means), None if means else "no_reference_positives"
        )
    if not positives or not negatives:
        metrics["auc"] = _metric(None, len(groups), "auc_requires_both_classes")
    elif any(score is None for score in scores):
        metrics["auc"] = _metric(None, len(groups), "continuous_scores_unavailable")
    else:
        pairs = positives * negatives
        metrics["auc"] = _metric(
            _auc(labels, [float(score) for score in scores if score is not None]) * pairs, pairs
        )
    if not complete:
        metrics = {
            name: _metric(None, item["denominator"], "incomplete_cohort")
            for name, item in metrics.items()
        }
    return counts, metrics


def evaluate_detection(
    manifest_path: str | Path,
    splits_path: str | Path,
    prediction_dir: str | Path,
    evaluation_report: str | Path,
    output_dir: str | Path,
    *,
    partition: str = "val",
    final_test: bool = False,
    protocol: dict | None = None,
) -> dict[str, Any]:
    protocol = _validate_protocol(DEFAULT_PROTOCOL if protocol is None else protocol)
    if partition not in ("train", "val", "test") or final_test != (partition == "test"):
        raise ValueError("Test diagnostics require an explicit final_test flag")
    manifest_path, splits_path, prediction_dir, evaluation_report, output_dir = map(
        Path, (manifest_path, splits_path, prediction_dir, evaluation_report, output_dir)
    )
    if output_dir.exists():
        raise FileExistsError("Diagnostic output must be new; preserve previous evidence")
    manifest, splits = _documents(manifest_path, splits_path)
    if manifest["ontology"] != {"background": 0, "pancreas": 1, "mass": 2}:
        raise ValueError("Diagnostic requires canonical background/pancreas/mass ontology")
    ids = splits[partition]
    if not ids:
        raise ValueError("Diagnostic cohort is empty")
    primary = _json(evaluation_report)
    if primary.get("manifest_fingerprint") != manifest["fingerprint"]:
        raise ValueError("Primary evaluation belongs to another manifest")
    primary_cases = primary.get("cases", [])
    if len(primary_cases) != len(ids) or {x["case_id"] for x in primary_cases} != set(ids):
        raise ValueError("Primary evaluation cohort differs from requested frozen partition")
    primary_lookup = {row["case_id"]: row for row in primary_cases}
    extra = {p.name for p in prediction_dir.glob("*.nii.gz")} - {f"{key}.nii.gz" for key in ids}
    if extra:
        raise ValueError("Prediction directory contains unexpected cohort members")
    status_path = prediction_dir / "prediction-status.json"
    nnunet = not status_path.is_file()
    if nnunet:
        status_path = prediction_dir / "prediction-record.json"
    status = _json(status_path)
    checkpoint_hash = status.get("checkpoint_sha256")
    if (
        not isinstance(checkpoint_hash, str)
        or len(checkpoint_hash) != 64
        or any(c not in "0123456789abcdef" for c in checkpoint_hash)
    ):
        raise ValueError("Prediction record requires a valid checkpoint SHA256")
    if status.get("partition") != partition:
        raise ValueError("Prediction record belongs to a different partition")
    status_lookup = {}
    if nnunet:
        if status.get("status") != "validated" or status.get("cases") != len(ids):
            raise ValueError("nnU-Net prediction record is not complete and validated")
    else:
        entries = status.get("cases", [])
        if len(entries) != len({x["case_id"] for x in entries}) or not {
            x["case_id"] for x in entries
        } <= set(ids):
            raise ValueError("Prediction status has duplicate or unexpected cohort members")
        status_lookup = {row["case_id"]: row for row in entries}
    bound_provenance, bound_files = _prediction_provenance(
        prediction_dir, status, nnunet, manifest_path, splits_path
    )
    input_hashes = {
        str(p.resolve()): sha256_file(p)
        for p in (manifest_path, splits_path, evaluation_report, status_path, *bound_files)
    }
    lookup = {case["case_id"]: case for case in manifest["cases"]}
    rows = []
    for case_id in ids:
        case, previous = lookup[case_id], primary_lookup[case_id]
        row: dict[str, Any] = {
            "case_id": case_id,
            "patient_id": case["patient_id"],
            "status": "invalid_reference",
        }
        rows.append(row)
        try:
            if case["annotation_status"] != "labeled" or previous.get(
                "reference_sha256"
            ) != case.get("label_sha256"):
                raise ValueError("A fully annotated, provenance-matched reference is required")
            label_path = Path(case["label"])
            label_hash = sha256_file(label_path)
            if label_hash != case["label_sha256"]:
                raise ValueError("Reference changed")
            reference_volume = _read_volume(label_path, "reference")
            affine = _affine(reference_volume)
            if tuple(case["shape"]) != reference_volume.shape or not np.allclose(
                case["affine"], affine, atol=1e-4, rtol=0
            ):
                raise ValueError("Reference differs from audited native geometry")
            reference = _decode_labels(reference_volume, {0, 1, 2})
            row.update(reference_sha256=label_hash, reference_positive=bool(np.any(reference == 2)))
            row["status"] = "invalid_prediction"
            if previous.get("status") != "ok" or previous.get("patient_id") != case["patient_id"]:
                raise ValueError("Primary evaluation does not verify this patient prediction")
            record = status_lookup.get(case_id, {})
            if not nnunet and record.get("status") != "completed":
                raise ValueError("Prediction stage did not complete this case")
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            prediction_hash = sha256_file(prediction_path)
            if prediction_hash != previous.get("prediction_sha256"):
                raise ValueError("Prediction differs from primary evaluation")
            prediction_volume = _read_volume(prediction_path, "prediction")
            _same_geometry(reference_volume, prediction_volume)
            prediction = _decode_labels(prediction_volume, {0, 1, 2})
            spacing = np.linalg.norm(affine[:3, :3], axis=0)
            lesions = lesion_detection_metrics(
                reference == 2,
                prediction == 2,
                spacing,
                protocol["iou_threshold"],
                protocol["connectivity"],
                protocol["minimum_prediction_volume_mm3"],
            )
            if (
                sha256_file(label_path) != label_hash
                or sha256_file(prediction_path) != prediction_hash
            ):
                raise ValueError("Mask changed while computing diagnostics")
            row.update(
                status="ok",
                prediction_sha256=prediction_hash,
                lesions=lesions,
                prediction_positive=lesions["prediction_components"] > 0,
                continuous_mass_score=_continuous_score(record, prediction),
                mass_dsc=_dice(reference == 2, prediction == 2),
                pancreas_dsc=_dice(reference > 0, prediction > 0),
            )
        except (OSError, ValueError, KeyError):
            row["reason_code"] = row["status"]
    complete = all(row["status"] == "ok" for row in rows)
    counts, metrics = summarize(rows, complete=complete)
    for path, digest in input_hashes.items():
        if sha256_file(path) != digest:
            raise ValueError("Diagnostic input metadata changed during evaluation")
    report = {
        "schema_version": 1,
        "kind": "medical_detection_diagnostic",
        "cohort_complete": complete,
        "dataset": manifest["dataset"],
        "partition": partition,
        "patient_grouping_status": splits.get("grouping_status", "unverified"),
        "protocol": protocol,
        "protocol_sha256": _digest(protocol),
        "counts": counts,
        "metrics": metrics,
        "provenance": {
            **bound_provenance,
            "manifest_sha256": sha256_file(manifest_path),
            "splits_sha256": sha256_file(splits_path),
            "manifest_fingerprint": manifest["fingerprint"],
            "split_fingerprint": splits["fingerprint"],
            "evaluation_report_sha256": sha256_file(evaluation_report),
            "prediction_status_sha256": sha256_file(status_path),
            "prediction_checkpoint_sha256": checkpoint_hash,
            "script_sha256": sha256_file(__file__),
            "evaluation_module_sha256": sha256_file(
                Path(lesion_detection_metrics.__code__.co_filename)
            ),
            "mask_integrity": "reference hashes match manifest; prediction hashes match primary evaluation; both rechecked after decoding",
            "software": {
                name: importlib.metadata.version(name) for name in ("numpy", "scipy", "nibabel")
            },
        },
        "limitations": [
            "Exploratory annotated-mass agreement, not PDAC diagnosis or screening validation.",
            "Provided patient groups may be unverified; connected components are not independently annotated lesion identities.",
            "No direct PanTS leaderboard comparison without the same cohort, labels, thresholds and official matching protocol.",
            "Specificity and AUC require annotated negatives; organ-only and unlabeled scans are not negative controls.",
            "AUC uses an image-only probability maximum, not a calibrated cancer risk; old masks alone cannot recover it.",
            "Any failed or missing case withholds the full-cohort metric values; valid-case counts remain diagnostic only.",
        ],
        "sources": [
            "https://github.com/MrGiovanni/PanTS#pants-benchmark-official-in-distribution-test-set",
            "https://arxiv.org/html/2507.01291v1",
            "https://github.com/MrGiovanni/R-Super/blob/main/rsuper_train/Merlin_demo.md",
        ],
        "cases": rows,
    }
    output_dir.mkdir(parents=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "splits", "predictions", "evaluation-report", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--partition", choices=("train", "val", "test"), default="val")
    parser.add_argument("--final-test", action="store_true")
    parser.add_argument(
        "--protocol",
        type=Path,
        help="Explicit frozen JSON protocol; default is exploratory_mass_detection_v1",
    )
    args = parser.parse_args()
    report = evaluate_detection(
        args.manifest,
        args.splits,
        args.predictions,
        args.evaluation_report,
        args.output,
        partition=args.partition,
        final_test=args.final_test,
        protocol=_json(args.protocol) if args.protocol else None,
    )
    print(
        json.dumps(
            {"cohort_complete": report["cohort_complete"], "metrics": report["metrics"]},
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
