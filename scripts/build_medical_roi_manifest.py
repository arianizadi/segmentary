#!/usr/bin/env python3
"""Bind native stage-one predictions to image-only cascade crops; never read labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.geometry import sha256_file, validate_nifti
from segmentary.medical.torch_roi import predicted_bbox


def build(
    manifest: Path, splits: Path, predictions: Path, provenance: Path, margin: float, output: Path
) -> dict:
    if output.exists():
        raise FileExistsError(output)
    data = load_manifest(manifest, verify_files=False)
    partition = json.loads(splits.read_text())
    validate_splits(data, partition)
    source = json.loads(provenance.read_text())
    if (
        source.get("initialization") != "scratch"
        or source.get("training_prediction_policy") != "in_sample_exploratory"
    ):
        raise ValueError(
            "Stage-one provenance must declare scratch origin and in-sample training predictions"
        )
    for key in ("checkpoint", "binding", "resolved_config"):
        if sha256_file(Path(source[key])) != source[f"{key}_sha256"]:
            raise ValueError(f"Stage-one {key} changed")
    allowed = set(partition["train"] + partition["val"])
    if set(source["prediction_case_ids"]) != allowed:
        raise ValueError(
            "Stage-one predictions must cover exactly train and val, never reserved test"
        )
    records = {}
    for case in data["cases"]:
        identifier = case["case_id"]
        if identifier not in allowed:
            continue
        if sha256_file(Path(case["image"])) != case["image_sha256"]:
            raise ValueError("Audited source image changed")
        prediction_path = predictions / f"{identifier}.nii.gz"
        validate_nifti(prediction_path, is_label=True, allowed_labels=(0, 1, 2))
        image = nib.load(case["image"])
        prediction = nib.load(prediction_path)
        if image.shape != prediction.shape or not np.allclose(
            image.affine, prediction.affine, atol=1e-4, rtol=0
        ):
            raise ValueError("Stage-one prediction is not on the original native grid")
        bounds, fallback = predicted_bbox(
            np.asarray(prediction.dataobj), nib.affines.voxel_sizes(image.affine), margin
        )
        records[identifier] = {
            "image_sha256": case["image_sha256"],
            "prediction_sha256": sha256_file(prediction_path),
            "bbox_xyz": bounds,
            "empty_prediction_fallback": fallback,
            "retained_image_fraction": float(
                np.prod([hi - lo for lo, hi in bounds]) / np.prod(image.shape)
            ),
        }
    document = {
        "schema_version": 1,
        "kind": "predicted_pancreas_native_bbox",
        "reference_labels_used": False,
        "empty_prediction_policy": "full_ct",
        "margin_mm": margin,
        "stage_one": source,
        "provenance_sha256": sha256_file(provenance),
        "manifest_sha256": sha256_file(manifest),
        "splits_sha256": sha256_file(splits),
        "cases": records,
        "evaluation": "Full original native CT; outside crop is background; no patients excluded",
        "limitation": "Stage-one training predictions are in-sample, not out-of-fold; exploratory validation only",
    }
    atomic_write_json(output, document)
    return {
        "output": str(output),
        "sha256": sha256_file(output),
        "cases": len(records),
        "fallback_cases": sum(record["empty_prediction_fallback"] for record in records.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "splits", "predictions", "provenance", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--margin", required=True, type=float)
    print(json.dumps(build(**vars(parser.parse_args())), indent=2))


if __name__ == "__main__":
    main()
