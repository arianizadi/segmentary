"""Apply common reference-dataset mask checks to an immutable RTIS dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scripts.audit_annotations import safe_path
from scripts.audit_reference_datasets import mask_stats


def summarize(dataset: Path, audit_report: Path | None = None) -> dict:
    schema = json.loads((dataset / "classes.json").read_text())
    ignore = int(schema.get("ignore_index", 255))
    valid = {int(c["id"]) for c in schema["classes"]} | {ignore}
    ignored = {ignore}
    samples = json.loads((dataset / "audit/samples.json").read_text())
    splits: dict[str, dict[str, Any]] = {}
    for sample in samples:
        split = sample["split"]
        record = splits.setdefault(
            split,
            {
                "images": 0,
                "pixels": 0,
                "ignore_pixels": 0,
                "invalid_id_images": 0,
                "invalid_ids": [],
                "dominant_class_images": 0,
                "all_ignore_images": 0,
                "boundary_pairs": 0,
                "neighbor_pairs": 0,
                "class_pixels": Counter(),
            },
        )
        path = safe_path(dataset, f"masks/{split}/{sample['key']}.png")
        with Image.open(path) as image:
            mask = np.asarray(image)
        if mask.shape != (sample["height"], sample["width"]):
            raise ValueError(f"Mask shape does not match manifest: {sample['key']}")
        stats = mask_stats(mask, valid, ignored)
        record["images"] += 1
        for field in ["pixels", "ignore_pixels", "boundary_pairs", "neighbor_pairs"]:
            record[field] += stats[field]
        record["class_pixels"].update(stats["class_pixels"])
        record["invalid_id_images"] += bool(stats["invalid_ids"])
        record["invalid_ids"] = sorted(set(record["invalid_ids"]) | set(stats["invalid_ids"]))
        record["dominant_class_images"] += bool(stats["dominant_classes"])
        record["all_ignore_images"] += "all_ignore" in stats["flags"]
    for record in splits.values():
        record["class_pixels"] = dict(sorted(record["class_pixels"].items()))
        record["ignore_fraction"] = (
            record["ignore_pixels"] / record["pixels"] if record["pixels"] else 0
        )
        record["boundary_fraction"] = (
            record["boundary_pairs"] / record["neighbor_pairs"] if record["neighbor_pairs"] else 0
        )
    return {
        "schema_version": 1,
        "dataset": schema.get("name", dataset.name),
        "method": "scripts.audit_reference_datasets.mask_stats",
        "valid_class_ids": sorted(valid),
        "ignored_class_ids": sorted(ignored),
        "dominant_coverage_threshold": 0.85,
        "denominators": {
            "class_coverage": "All native image pixels, including ignore pixels; dominance excludes ignore classes.",
            "ignore_fraction": "Sum of ignore pixels divided by sum of all native pixels in the split.",
            "boundary_fraction": "Unequal horizontal/vertical neighbor pairs divided by all horizontal/vertical neighbor pairs; includes ignore transitions.",
            "image_counts": "Each manifest image counted once; no resized masks.",
        },
        "manifest_sha256": hashlib.sha256(
            (dataset / "audit/samples.json").read_bytes()
        ).hexdigest(),
        "class_schema_sha256": hashlib.sha256((dataset / "classes.json").read_bytes()).hexdigest(),
        "audit_report_sha256": hashlib.sha256(audit_report.read_bytes()).hexdigest()
        if audit_report
        else None,
        "images": len(samples),
        "splits": splits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path)
    args = parser.parse_args()
    if args.out.resolve().is_relative_to(args.dataset.resolve()):
        parser.error("Output must be outside the immutable dataset")
    result = summarize(args.dataset, args.audit_report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
