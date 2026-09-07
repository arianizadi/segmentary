"""Measure audit fault detection using disposable copies of one real RTIS sample."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scripts.audit_annotations import audit


def validate(dataset: Path, output: Path, key: str = "trackside-maintenance/57") -> dict:
    dataset = dataset.resolve()
    if output.exists() or output.resolve().is_relative_to(dataset):
        raise ValueError("Choose a new output outside the source dataset")
    rows = json.loads((dataset / "audit/samples.json").read_text())
    row = copy.deepcopy(next(r for r in rows if r["key"] == key))
    for field in ("source_annotation", "source_image"):
        row[field] = str(Path(row[field]).resolve())
    cases = {
        "clean_control": None,
        "unknown_label_id": "unknown_training_class_ids:",
        "shifted_labels": "training_mask_differs_from_native_render",
        "all_void_labels": "training_mask_differs_from_native_render",
        "wrong_mask_size": "audit_error",
        "changed_packaged_image": "packaged_image_differs_from_native_source",
        "reversed_source_order": "source_annotation_changed_since_packaging",
    }
    results = []
    output.mkdir(parents=True)
    for name, expected in cases.items():
        root = output / name / "dataset"
        (root / "audit").mkdir(parents=True)
        shutil.copyfile(dataset / "classes.json", root / "classes.json")
        mask = root / f"masks/{row['split']}/{key}.png"
        image = root / f"images/{row['split']}/{key}{Path(row['source_image']).suffix}"
        for path in (mask, image):
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dataset / path.relative_to(root), path)
        sample = copy.deepcopy(row)
        if name in ("unknown_label_id", "shifted_labels", "all_void_labels", "wrong_mask_size"):
            with Image.open(mask) as handle:
                pixels = np.array(handle)
            if name == "unknown_label_id":
                pixels[:20, :20] = 250
            elif name == "shifted_labels":
                pixels = np.roll(pixels, 25, axis=1)
            elif name == "all_void_labels":
                pixels[:] = 255
            else:
                pixels = pixels[:-1]
            Image.fromarray(pixels).save(mask)
        if name == "changed_packaged_image":
            with Image.open(image) as handle:
                pixels = np.array(handle.convert("RGB"))
            pixels[:20, :20] = 255 - pixels[:20, :20]
            Image.fromarray(pixels).save(image)
        if name == "reversed_source_order":
            annotation = json.loads(Path(row["source_annotation"]).read_text())
            annotation["objects"].reverse()
            changed = root / "source.json"
            changed.write_text(json.dumps(annotation))
            sample["source_annotation"] = str(changed.resolve())
        (root / "audit/samples.json").write_text(json.dumps([sample]))
        report = audit(root, output / name / "audit", focus_class="mud-pumping")
        observed = report["samples"][0]
        passed = (
            any(flag.startswith(expected) for flag in observed["flags"])
            if expected
            else report["errors"] == 0
            and observed["mismatch_pixels"] == 0
            and report["review"]["priority_counts"]["integrity"] == 0
        )
        results.append(
            {
                "case": name,
                "expected_flag": expected,
                "observed_flags": observed["flags"],
                "mismatch_pixels": observed.get("mismatch_pixels"),
                "passed": passed,
            }
        )
    result = {
        "schema": "annotation-audit-fault-validation-v1",
        "source_sample": key,
        "source_dataset": str(dataset),
        "mutations": "disposable copies only",
        "cases": results,
        "passed": all(r["passed"] for r in results),
        "limitation": "Tests integrity fault detection; does not estimate sensitivity or precision for semantic labeling errors.",
    }
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--key", default="trackside-maintenance/57")
    args = parser.parse_args()
    result = validate(args.dataset, args.out, args.key)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
