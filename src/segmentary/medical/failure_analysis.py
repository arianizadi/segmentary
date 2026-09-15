"""Read-only native prediction diagnostics, with immutable input evidence.

This module never imports a trainer, loads a checkpoint, or opens reserved test
payloads. Output contains pseudonymous keys and CT panels: keep it in approved
research storage, not in a public repository.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from .backend import _digest, _documents
from .evaluation import _affine, _decode_labels, _read_volume, _same_geometry
from .failure_panels import canonical, render_panels, select_planes
from .geometry import sha256_file


def read_json(path: Path) -> dict:
    value = json.loads(
        path.read_text(), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s))
    )
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def token(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode()).hexdigest()[:24]


def write_json(path: Path, value: dict) -> None:
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _dice(ref: np.ndarray, pred: np.ndarray) -> float | None:
    return float(2 * np.count_nonzero(ref & pred) / (ref.sum() + pred.sum())) if ref.any() else None


def _models(spec: dict, manifest: dict, splits: dict, watched: dict) -> list[dict]:
    models = spec.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("At least one explicit model is required")
    seen = set()
    ids = set(splits[spec["partition"]])
    prepared = []
    primary_protocol = None

    def watch(path: Path) -> dict:
        digest = sha256_file(path)
        value = read_json(path)
        if sha256_file(path) != digest:
            raise ValueError("Metadata changed while being read")
        watched[str(path)] = digest
        return value

    for model in models:
        name = model.get("id")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("Models need unique nonempty IDs")
        seen.add(name)
        pred = Path(model["prediction_dir"]).resolve()
        nnunet_layout = not (pred / "prediction-status.json").exists()
        if pred.parent.name != "predictions" or not (
            pred.name == spec["partition"]
            or (nnunet_layout and re.fullmatch(re.escape(spec["partition"]) + r"-\d+", pred.name))
        ):
            raise ValueError("Use original workspace/predictions/partition directory")
        workspace = pred.parent.parent
        binding = watch(workspace / "binding.json")
        for key in ("manifest", "splits"):
            if binding.get(f"{key}_sha256") != watched[str(Path(spec[key]))]:
                raise ValueError("Prediction binding does not match requested cohort")
        report = watch(Path(model["evaluation_report"]))
        if report.get("manifest_fingerprint") != manifest["fingerprint"]:
            raise ValueError("Primary evaluation belongs to another manifest")
        if report.get("protocol", {}).get("pancreas_include_mass") is not True:
            raise ValueError("Primary evaluation must use whole-pancreas union")
        score_protocol = {
            k: v
            for k, v in report.get("protocol", {}).items()
            if k not in {"bootstrap_samples", "seed"}
        }
        if primary_protocol is None:
            primary_protocol = score_protocol
        elif score_protocol != primary_protocol:
            raise ValueError("Primary evaluation protocols differ across models")
        rows = report.get("cases", [])
        if len(rows) != len(ids) or {r["case_id"] for r in rows} != ids:
            raise ValueError("Primary evaluation must cover exactly the selected partition")
        index = watch(workspace / "checkpoint-index.json")
        statusfile = pred / "prediction-status.json"
        nnunet = not statusfile.exists()
        status = watch(pred / "prediction-record.json" if nnunet else statusfile)
        if status.get("partition") != spec["partition"]:
            raise ValueError("Prediction receipt partition mismatch")
        checkpoint = status.get("checkpoint_sha256")
        if (
            not isinstance(checkpoint, str)
            or len(checkpoint) != 64
            or any(x not in "0123456789abcdef" for x in checkpoint)
        ):
            raise ValueError("Prediction checkpoint hash missing")
        if nnunet:
            plan = watch(workspace / "plan-binding.json")
            if (
                plan.get("binding_digest") != _digest(binding)
                or status.get("status") != "validated"
                or status.get("cases") != len(ids)
            ):
                raise ValueError("Incomplete nnU-Net prediction provenance")
            identity = _digest({"binding": binding, "runtime": plan["runtime"]})
            candidates = [
                v for v in index.values() if isinstance(v, dict) and v.get("identity") == identity
            ]
            if Path(status.get("output", "")).resolve() != pred:
                raise ValueError("nnU-Net receipt output mismatch")
        else:
            identity = _digest(binding)
            if (
                status.get("identity") != identity
                or index.get("identity") != identity
                or index.get("initialization") != "scratch"
            ):
                raise ValueError("Prediction identity/scratch provenance mismatch")
            candidates = list(index.get("files", {}).values())
            statuses = status.get("cases", [])
            if len(statuses) != len(ids) or {r["case_id"] for r in statuses} != ids:
                raise ValueError("Prediction receipt must cover complete partition")
        if not any(v.get("sha256") == checkpoint for v in candidates):
            raise ValueError("Prediction checkpoint is not in its original bound index")
        roi = None
        config_path = workspace / "resolved-config.json"
        config = binding.get("config", {})
        if config_path.exists() and watch(config_path) != config:
            raise ValueError("Resolved config differs from immutable run binding")
        if model.get("seed") is not None and model["seed"] != config.get("seed"):
            raise ValueError("Declared seed differs from trained run binding")
        if model.get("roi_manifest"):
            if config.get("roi_manifest_sha256") != model.get("roi_manifest_sha256"):
                raise ValueError("ROI does not match the model training recipe")
            roi_path = Path(model["roi_manifest"])
            roi = watch(roi_path)
            if (
                watched[str(roi_path)] != model.get("roi_manifest_sha256")
                or roi.get("manifest_sha256") != binding["manifest_sha256"]
                or roi.get("splits_sha256") != binding["splits_sha256"]
            ):
                raise ValueError("ROI provenance mismatch")
            if (
                roi.get("reference_labels_used") is not False
                or roi.get("kind") != "predicted_pancreas_native_bbox"
            ):
                raise ValueError("Only prediction-derived native ROI manifests are permitted")
        if config.get("roi_manifest") and roi is None:
            raise ValueError("The model trained with ROI; its bound crop manifest is required")
        prepared.append(
            {
                **model,
                "seed": config.get("seed"),
                "primary_protocol": score_protocol,
                "prediction_dir": pred,
                "rows": {r["case_id"]: r for r in rows},
                "roi": roi,
                "receipt": status,
                "nnunet": nnunet,
                "checkpoint_sha256": checkpoint,
                "binding_sha256": watched[str(workspace / "binding.json")],
            }
        )
    return prepared


def analyze(
    spec: dict,
    output: Path,
    *,
    review_limit: int = 8,
    review_random: int = 2,
    slices_per_plane: int = 3,
    seed: int = 0,
) -> dict:
    from .failure_metrics import (
        aggregate_failure_buckets,
        case_failure_metrics,
        roi_coverage_metrics,
    )
    from .failure_review import write_failure_review
    from .failure_tables import write_failure_tables

    if spec.get("partition", "val") not in {"train", "val"}:
        raise ValueError("Failure discovery is restricted to train/val; reserved test is locked")
    spec = {**spec, "partition": spec.get("partition", "val")}
    for name, value in (
        ("review_limit", review_limit),
        ("review_random", review_random),
        ("slices_per_plane", slices_per_plane),
    ):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if output.exists():
        raise FileExistsError("Use a fresh output directory; old evidence must remain immutable")
    watched = {str(Path(spec[k])): sha256_file(spec[k]) for k in ("manifest", "splits")}
    manifest, splits = _documents(spec["manifest"], spec["splits"])
    ids = sorted(splits[spec["partition"]])
    if not ids:
        raise ValueError("Empty analysis partition")
    models = _models(spec, manifest, splits, watched)
    cohort_cases = {c["case_id"]: c for c in manifest["cases"] if c["case_id"] in ids}
    namespace = manifest["fingerprint"]
    casekeys = {key: token(namespace, key) for key in ids}
    protocol = {
        "version": 1,
        "space": "native_full_volume",
        "lesion_iou_threshold": 0.1,
        "connectivity": 26,
        "minimum_prediction_volume_mm3": 0.0,
        "mass_empty_policy": "reference-empty Dice unavailable; retain false positives",
        "pancreas": "union labels 1 and 2",
        "slice_spacing": "canonical RAS superior-inferior voxel spacing",
        "failure_categories": "automatic review triggers, not diagnoses or label corrections",
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "medical_failure_analysis",
        "partition": spec["partition"],
        "cohort": {
            "manifest_sha256": watched[str(Path(spec["manifest"]))],
            "splits_sha256": watched[str(Path(spec["splits"]))],
            "partition": spec["partition"],
            "reference_fingerprint": _digest(
                [
                    [
                        key,
                        cohort_cases[key]["patient_id"],
                        cohort_cases[key]["image_sha256"],
                        cohort_cases[key]["label_sha256"],
                    ]
                    for key in ids
                ]
            ),
            "grouping_status": splits.get("grouping_status", "unverified"),
        },
        "protocol": {**protocol, "primary_metrics": models[0]["primary_protocol"]},
        "models": [
            {
                "id": m["id"],
                "seed": m.get("seed"),
                "checkpoint_sha256": m["checkpoint_sha256"],
                "binding_sha256": m["binding_sha256"],
            }
            for m in models
        ],
        "cases": [],
        "limitations": [
            "Connected components are proxies for lesions, not adjudicated tumor instances.",
            "Image gradients, confidence and low Dice cannot establish annotation error or malignancy.",
            "Pseudonymous keys and CT panels remain research data; this is not a de-identification determination.",
            "No scanner/site/contrast-phase labels are inferred from pixel appearance.",
            "Training-only and validation error discovery are exploratory; reserved test remains unopened.",
            "Crop reference coverage is computed after prediction for analysis only; never used to generate or repair crops.",
        ],
    }
    output.mkdir(parents=True)
    private_errors = []

    def progress(phase: str, completed: int, total: int) -> None:
        temporary = output / "progress.json.tmp"
        temporary.write_text(
            json.dumps({"phase": phase, "completed_cases": completed, "total_cases": total})
        )
        temporary.replace(output / "progress.json")

    progress("metrics", 0, len(ids))
    raw: dict[str, list[dict]] = {m["id"]: [] for m in models}

    def checked(path: str | Path, expected: str, role: str):
        if sha256_file(path) != expected:
            raise ValueError(f"{role} hash mismatch")
        volume = _read_volume(Path(path), role)
        return volume

    for case_index, key in enumerate(ids):
        progress("metrics", case_index, len(ids))
        case = cohort_cases[key]
        row: dict[str, Any] = {
            "case_key": casekeys[key],
            "patient_key": token(namespace, str(case["patient_id"])),
            "status": "ok",
            "features": {},
            "models": {},
        }
        report["cases"].append(row)
        try:
            if case["annotation_status"] != "labeled":
                raise ValueError("Fully annotated masses required")
            if sha256_file(case["image"]) != case["image_sha256"]:
                raise ValueError("Source CT hash mismatch")
            reference_volume = checked(case["label"], case["label_sha256"], "reference")
            affine = _affine(reference_volume)
            if tuple(case["shape"]) != reference_volume.shape or not np.allclose(
                case["affine"], affine, atol=1e-4, rtol=0
            ):
                raise ValueError("Reference differs from native audited geometry")
            reference = _decode_labels(reference_volume, {0, 1, 2})
            spacing = np.linalg.norm(affine[:3, :3], axis=0)
            ras_spacing = nib.affines.voxel_sizes(nib.as_closest_canonical(reference_volume).affine)
            row["features"] = {
                "spacing_xyz_mm": spacing.tolist(),
                "ras_spacing_mm": ras_spacing.tolist(),
                "slice_spacing_mm": float(ras_spacing[2]),
                "mass_volume_ml": float(
                    np.count_nonzero(reference == 2) * abs(np.linalg.det(affine[:3, :3])) / 1000
                ),
                "image_sha256": case["image_sha256"],
                "reference_sha256": case["label_sha256"],
            }
        except (ValueError, OSError, KeyError) as exc:
            private_errors.append({"case_id": key, "stage": "reference", "error": str(exc)})
            row["status"] = "invalid_reference"
            row["models"] = {
                m["id"]: {
                    "status": "invalid_reference",
                    "flags": ["invalid_reference"],
                    "panels": {},
                }
                for m in models
            }
            continue
        for m in models:
            result: dict[str, Any] = {"status": "invalid_prediction", "flags": [], "panels": {}}
            row["models"][m["id"]] = result
            try:
                previous = m["rows"][key]
                if (
                    previous.get("status") != "ok"
                    or previous.get("patient_id") != case["patient_id"]
                    or previous.get("reference_sha256") != case["label_sha256"]
                ):
                    raise ValueError("Primary evaluation case identity failed")
                if (
                    not m["nnunet"]
                    and next(r for r in m["receipt"]["cases"] if r["case_id"] == key).get("status")
                    != "completed"
                ):
                    raise ValueError("Prediction stage did not complete case")
                path = m["prediction_dir"] / f"{key}.nii.gz"
                prediction_volume = checked(path, previous["prediction_sha256"], "prediction")
                _same_geometry(reference_volume, prediction_volume)
                prediction = _decode_labels(prediction_volume, {0, 1, 2})
                detail = case_failure_metrics(reference, prediction, spacing)
                # Bucket slice spacing is superior-inferior after canonical orientation.
                detail["bucket_ras_spacing_mm"] = ras_spacing.tolist()
                raw[m["id"]].append(detail)
                mass = _dice(reference == 2, prediction == 2)
                pancreas = _dice(reference > 0, prediction > 0)
                saved = previous["metrics"]
                for name, score in (("mass", mass), ("pancreas", pancreas)):
                    if score is not None and not math.isclose(
                        score, saved[name]["dice"], abs_tol=1e-8
                    ):
                        raise ValueError("Primary Dice does not match these native masks")
                detection = detail["lesion_detection"]
                result.update(
                    status="ok",
                    mass_dice=mass,
                    pancreas_dice=pancreas,
                    hd95_mm=saved["mass"].get("hd95_mm"),
                    hd95_status=saved["mass"].get("hd95_status"),
                    surface_dice=saved["mass"].get("surface_dice"),
                    missed_lesions=detection["false_negatives"],
                    false_positive_lesions=detection["false_positives"],
                    diagnostics=detail,
                    prediction_sha256=previous["prediction_sha256"],
                )
                if detection["false_negatives"]:
                    result["flags"].append("missed_or_underlocalized_lesion")
                if detection["false_positives"]:
                    result["flags"].append("unmatched_prediction_component")
                if mass is not None and mass < 0.5:
                    result["flags"].append("low_mass_overlap")
                if isinstance(result["hd95_mm"], (float, int)) and result["hd95_mm"] > 10:
                    result["flags"].append("large_surface_distance")
                if m["roi"]:
                    roi = m["roi"]["cases"][key]
                    if roi.get("image_sha256") != case["image_sha256"]:
                        raise ValueError("ROI source image differs")
                    result["roi"] = roi_coverage_metrics(reference, spacing, roi["bbox_xyz"])
                    result["roi"]["empty_prediction_fallback"] = roi["empty_prediction_fallback"]
                if sha256_file(path) != previous["prediction_sha256"]:
                    raise ValueError("Prediction changed during analysis")
            except (ValueError, OSError, KeyError, StopIteration) as exc:
                private_errors.append(
                    {"case_id": key, "model": m["id"], "stage": "prediction", "error": str(exc)}
                )
                result.clear()
                result.update(
                    status="invalid_prediction",
                    flags=["invalid_prediction_or_provenance"],
                    panels={},
                )
        if sha256_file(case["label"]) != case["label_sha256"]:
            raise ValueError("Reference changed during analysis")
    # Entire cohort stays visible. Invalid cases cannot disappear from denominators.
    for m in models:
        valid = [r for r in report["cases"] if r["models"][m["id"]]["status"] == "ok"]
        raw[m["id"]] = [r["models"][m["id"]]["diagnostics"] for r in valid]
    report["summaries"] = {
        m["id"]: {
            "eligible_cases": len(ids),
            "valid_cases": len(raw[m["id"]]),
            "complete": len(raw[m["id"]]) == len(ids),
            "buckets": aggregate_failure_buckets(
                [{**d, "spacing_mm": d["bucket_ras_spacing_mm"]} for d in raw[m["id"]]]
            ),
        }
        for m in models
    }

    def severity(row):
        return max(
            (
                100 * v.get("missed_lesions", 0)
                + v.get("false_positive_lesions", 0)
                + 1
                - (v.get("mass_dice") or 0)
                for v in row["models"].values()
            ),
            default=0,
        )

    ranked = sorted(report["cases"], key=lambda r: (-severity(r), r["case_key"]))
    selected = [r["case_key"] for r in ranked[:review_limit]]
    remaining = [r["case_key"] for r in ranked if r["case_key"] not in selected]
    selected += list(
        np.random.default_rng(seed).choice(
            remaining, min(review_random, len(remaining)), replace=False
        )
    )
    report["review_selection"] = {
        "ranked_cases": review_limit,
        "random_remainder_cases": review_random,
        "seed": seed,
        "selected_case_keys": selected,
        "slices_per_plane": slices_per_plane,
        "scope": "all slices"
        if slices_per_plane == 0
        else "selected slices; not full-volume inspection",
    }
    for case_index, key in enumerate(ids):
        progress("panels", case_index, len(ids))
        row = next(r for r in report["cases"] if r["case_key"] == casekeys[key])
        if row["case_key"] not in selected or row["status"] != "ok":
            continue
        case = cohort_cases[key]
        try:
            image_volume = checked(case["image"], case["image_sha256"], "image")
            ref_volume = checked(case["label"], case["label_sha256"], "reference")
            _same_geometry(image_volume, ref_volume)
            ct = np.asarray(nib.as_closest_canonical(image_volume).dataobj)
            if not np.isfinite(ct).all():
                raise ValueError("Nonfinite CT")
            ref = canonical(_decode_labels(ref_volume, {0, 1, 2}), image_volume.affine)
            preds = {}
            for m in models:
                result = row["models"][m["id"]]
                if result["status"] != "ok":
                    continue
                v = checked(
                    m["prediction_dir"] / f"{key}.nii.gz", result["prediction_sha256"], "prediction"
                )
                _same_geometry(image_volume, v)
                preds[m["id"]] = canonical(_decode_labels(v, {0, 1, 2}), image_volume.affine)
            planes = select_planes(ref, list(preds.values()), slices_per_plane)
            row["review_planes"] = planes
            for mid, pred in preds.items():
                paths = render_panels(
                    ct,
                    ref,
                    pred,
                    np.array(row["features"]["ras_spacing_mm"]),
                    planes,
                    output / "panels" / row["case_key"] / token("model", mid),
                )
                row["models"][mid]["panels"] = {
                    plane: [str(p.relative_to(output)) for p in values]
                    for plane, values in paths.items()
                }
                row["models"][mid]["panel_sha256"] = {
                    str(p.relative_to(output)): sha256_file(p)
                    for values in paths.values()
                    for p in values
                }
            if (
                sha256_file(case["image"]) != case["image_sha256"]
                or sha256_file(case["label"]) != case["label_sha256"]
            ):
                raise ValueError("CT/reference changed during rendering")
            for m in models:
                result = row["models"][m["id"]]
                if (
                    result["status"] == "ok"
                    and sha256_file(m["prediction_dir"] / f"{key}.nii.gz")
                    != result["prediction_sha256"]
                ):
                    raise ValueError("Prediction changed during rendering")
        except (ValueError, OSError, KeyError) as exc:
            private_errors.append({"case_id": key, "stage": "panels", "error": str(exc)})
            row["review_error"] = "image_or_panel_validation_failed"
            for result in row["models"].values():
                result["panels"] = {}
    for path, digest in watched.items():
        if sha256_file(path) != digest:
            raise ValueError("Input metadata changed; discard partial analysis and retry fresh")
    report["provenance"] = {
        "input_metadata_sha256": {token("metadata", k): v for k, v in watched.items()},
        "implementation_sha256": {
            p.name: sha256_file(p) for p in Path(__file__).parent.glob("failure_*.py")
        },
    }
    report["report_id"] = _digest(report)
    write_json(output / "report.json", report)
    # Local mapping kept separately; never embedded in the browser review.
    write_json(
        output / "private-source-map.json",
        {"case_keys": {casekeys[k]: k for k in ids}, "inputs": spec, "metadata": watched},
    )
    write_json(output / "private-errors.json", {"errors": private_errors})
    write_failure_review(output, report)
    write_failure_tables(output, report)
    with (output / "cases.csv").open("x", newline="") as stream:
        fields = [
            "case_key",
            "patient_key",
            "model",
            "status",
            "mass_dice",
            "pancreas_dice",
            "missed_lesions",
            "false_positive_lesions",
            "hd95_mm",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in report["cases"]:
            for mid, result in row["models"].items():
                writer.writerow(
                    {
                        "case_key": row["case_key"],
                        "patient_key": row["patient_key"],
                        "model": mid,
                        **{k: result.get(k) for k in fields[3:]},
                    }
                )
    overview = [
        "# Medical failure analysis",
        "",
        "Open [failure-patterns.md](failure-patterns.md) for findings, [review.html](review.html) for blinded review, and [cases.csv](cases.csv) for case-level results.",
        "",
        f"Partition: {spec['partition']}. Cases: {len(ids)}. All metrics use native full scans.",
        "",
        "## Coverage",
        "",
        "| Model | Valid / eligible |",
        "| --- | --- |",
    ]
    overview += [
        f"| {m['id']} | {report['summaries'][m['id']]['valid_cases']} / {len(ids)} |"
        for m in models
    ]
    overview += [
        "",
        "Automatic categories are review triggers. Selected panels do not establish annotation errors. Partial-cohort bucket summaries are descriptive only. Report JSON retains denominators, lesion details, crop coverage and evidence hashes.",
        "",
        "CT panels, pseudonymous keys, reviewer notes and private-source-map.json belong in approved research storage; do not publish this directory automatically.",
    ]
    (output / "README.md").write_text("\n".join(overview) + "\n")
    progress("completed", len(ids), len(ids))
    return report
