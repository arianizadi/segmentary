#!/usr/bin/env python3
"""Measure frozen predicted crops against development labels; never repair boxes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from segmentary.medical.backend import _documents
from segmentary.medical.evaluation import _affine, _decode_labels, _read_volume
from segmentary.medical.failure_analysis import read_json, token, write_json
from segmentary.medical.failure_metrics import roi_coverage_metrics
from segmentary.medical.geometry import sha256_file


def audit(
    manifest: Path, splits: Path, roi: Path, expected_sha256: str, partition: str = "val"
) -> dict:
    if partition not in {"train", "val"}:
        raise ValueError("Reserved test is locked for development diagnostics")
    files = {str(p): sha256_file(p) for p in (manifest, splits, roi)}
    data, split = _documents(manifest, splits)
    document = read_json(roi)
    if (
        files[str(roi)] != expected_sha256
        or document.get("manifest_sha256") != files[str(manifest)]
        or document.get("splits_sha256") != files[str(splits)]
    ):
        raise ValueError("ROI/cohort identity mismatch")
    if (
        document.get("kind") != "predicted_pancreas_native_bbox"
        or document.get("reference_labels_used") is not False
    ):
        raise ValueError("Only frozen prediction-derived crops are supported")
    rows = []
    for case in data["cases"]:
        key = case["case_id"]
        if key not in split[partition]:
            continue
        if case["annotation_status"] != "labeled":
            raise ValueError("Fully labeled reference required; organ-only is not a negative")
        record = document["cases"][key]
        if (
            record["image_sha256"] != case["image_sha256"]
            or sha256_file(case["label"]) != case["label_sha256"]
        ):
            raise ValueError("Source identity changed")
        volume = _read_volume(Path(case["label"]), "reference")
        affine = _affine(volume)
        if tuple(case["shape"]) != volume.shape or not np.allclose(
            case["affine"], affine, atol=1e-4, rtol=0
        ):
            raise ValueError("Reference geometry differs from audit")
        value = roi_coverage_metrics(
            _decode_labels(volume, {0, 1, 2}),
            np.linalg.norm(affine[:3, :3], axis=0),
            record["bbox_xyz"],
        )
        rows.append(
            {
                "case_key": token(data["fingerprint"], key),
                "patient_key": token(data["fingerprint"], case["patient_id"]),
                "reference_sha256": case["label_sha256"],
                "empty_prediction_fallback": record["empty_prediction_fallback"],
                **value,
            }
        )
        if sha256_file(case["label"]) != case["label_sha256"]:
            raise ValueError("Reference changed during audit")
    if any(sha256_file(p) != sha for p, sha in files.items()):
        raise ValueError("Metadata changed during audit")
    return {
        "kind": "medical_roi_coverage_audit",
        "schema_version": 1,
        "partition": partition,
        "margin_mm": document["margin_mm"],
        "cases": rows,
        "eligible_cases": len(split[partition]),
        "valid_cases": len(rows),
        "inputs": files,
        "limitation": document.get("limitation"),
        "policy": "Read-only reference comparison after image-only localization; no box correction or training recipe change",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("manifest", "splits", "roi", "output"):
        p.add_argument(f"--{k}", type=Path, required=True)
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--partition", choices=["train", "val"], default="val")
    a = p.parse_args()
    out = a.output
    delattr(a, "output")
    if out.exists():
        raise FileExistsError(out)
    report = audit(**vars(a))
    write_json(out, report)
    print(json.dumps({"valid_cases": report["valid_cases"], "output": str(out)}))


if __name__ == "__main__":
    main()
