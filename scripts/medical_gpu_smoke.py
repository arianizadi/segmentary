#!/usr/bin/env python3
"""Exercise the medical pipeline and real interruption/resume on one GPU.

Uses two small labeled source volumes in a separate immutable smoke workspace.
This checks execution and exports, not overfit success or clinical performance.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import subprocess
import sys
import time
from pathlib import Path

from segmentary.medical.backend import (
    NNUNetConfig,
    cancel,
    plan_and_preprocess,
    predict,
    prepare_dataset,
    train,
)
from segmentary.medical.data import load_manifest, make_splits, subset_manifest
from segmentary.medical.evaluation import evaluate_predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend-python", required=True)
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a new output directory for each smoke")
    args.output.mkdir(parents=True)
    manifest = load_manifest(args.manifest)
    candidates = sorted(
        (case for case in manifest["cases"] if case["annotation_status"] == "labeled"),
        key=lambda case: (math.prod(case["shape"]), case["case_id"]),
    )
    if len(candidates) < 2:
        raise ValueError("Two labeled independent groups are required")
    chosen = [candidates[0]]
    for candidate in candidates[1:]:
        if candidate["patient_id"] != chosen[0]["patient_id"]:
            chosen.append(candidate)
            break
    if len(chosen) != 2:
        raise ValueError("Could not select two distinct patient groups")
    subset, split = args.output / "manifest.json", args.output / "splits.json"
    subset_manifest(args.manifest, subset, [case["case_id"] for case in chosen])
    make_splits(subset, split, train_fraction=0.5, val_fraction=0.5, seed=0)
    config = NNUNetConfig(
        workspace=str(args.output / "run"),
        backend_python=args.backend_python,
        gpu=args.gpu,
        resenc="M",
        purpose="smoke",
        workers=2,
        deterministic=False,
        num_epochs=3,
        num_iterations_per_epoch=2,
        num_val_iterations_per_epoch=1,
    )
    config_path = args.output / "config.json"
    config_path.write_text(json.dumps(dataclasses.asdict(config), indent=2))
    prepare_dataset(subset, split, config)
    print("prepared", flush=True)
    plan_and_preprocess(config)
    print("preprocessed", flush=True)
    with (args.output / "initial-train.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "segmentary.medical.cli", "train", "--config", str(config_path)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 1200
        interrupted = False
        try:
            while process.poll() is None:
                if (config.root / "checkpoint-index.json").exists():
                    cancel(config)
                    interrupted = True
                    break
                if time.monotonic() >= deadline:
                    cancel(config)
                    raise TimeoutError("No recovery checkpoint within 20 minutes")
                time.sleep(0.25)
            returncode = process.wait(timeout=60)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=60)
            raise
    if not interrupted or returncode == 0:
        raise RuntimeError("Did not observe an interrupted run; inspect the initial training log")
    print("interruption_verified", flush=True)
    recovery = train(config, resume=True)
    print("resumed_and_completed", flush=True)
    prediction = predict(config, partition="val")
    splits = json.loads(split.read_text())
    report = evaluate_predictions(
        subset,
        prediction["output"],
        args.output / "evaluation",
        case_ids=splits["val"],
        bootstrap_samples=20,
        review_overlays=True,
    )
    passed = (config.fold_folder / "checkpoint_final.pth").is_file() and report["coverage"][
        "valid_prediction_cases"
    ] == len(splits["val"])
    result = {
        "passed": passed,
        "purpose": "execution_smoke_not_quality_estimate",
        "source_manifest_fingerprint": manifest["fingerprint"],
        "selected_cases": [case["case_id"] for case in chosen],
        "selection": "two small labeled volumes with distinct declared patient groups",
        "interrupted_returncode": returncode,
        "resumed": True,
        "recovery": recovery,
        "prediction": prediction,
        "evaluation_coverage": report["coverage"],
        "limitations": "Three epochs with two updates each do not establish overfit success or model quality.",
    }
    (args.output / "smoke-result.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({"passed": passed, "result": str(args.output / "smoke-result.json")}))
    if not passed:
        raise RuntimeError("Smoke evaluation did not have complete valid predictions")


if __name__ == "__main__":
    main()
