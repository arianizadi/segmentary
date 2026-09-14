#!/usr/bin/env python3
"""Predict development CTs with an immutable own-scratch stage-one checkpoint.

Writes fresh native predictions and a provenance receipt; never initializes a
new training model with these weights and never opens reference label payloads.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from benchmark_medical_inference import check_idle
from medical_checkpoint_diagnostic import sha256, verified_historical_checkpoint

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segmentary.medical.backend import _lock
from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gpu", required=True)
    args = parser.parse_args()
    if args.output.exists() or args.gpu == "0":
        raise ValueError("Use a fresh output and an unreserved GPU")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited is not None and args.gpu not in inherited.split(","):
        raise ValueError("Requested GPU exceeds inherited visibility")
    revision = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    if subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip():
        raise ValueError("Localizer inference requires committed clean source")
    with verified_historical_checkpoint(args.campaign, args.run_id) as verified:
        binding = verified["binding"]
        manifest = load_manifest(Path(binding["manifest_path"]), verify_files=False)
        splits = json.loads(Path(binding["splits_path"]).read_text())
        validate_splits(manifest, splits)
        allowed = splits["train"] + splits["val"]
        if len(allowed) != 239 or set(allowed) & set(splits["test"]):
            raise ValueError("Expected exactly the 197+42 development CTs")
        lookup = {case["case_id"]: case for case in manifest["cases"]}
        # Deliberately remove label paths before handing cases to inference.
        cases = [{k: v for k, v in lookup[key].items() if k != "label"} for key in allowed]
        for case in cases:
            if sha256(Path(case["image"])) != case["image_sha256"]:
                raise ValueError("Stage-one image differs from audited manifest")
        for protected in (
            ROOT,
            Path(verified["config"]["workspace"]),
            Path(verified["training_source_root"]),
        ):
            if args.output.resolve().is_relative_to(protected.resolve()):
                raise ValueError("Output must be separate from source and historical training")
        lockroot = Path(
            os.environ.get(
                "SEGMENTARY_MEDICAL_LOCK_DIR",
                str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
            )
        )
        with _lock(lockroot / f"gpu-{args.gpu}.lock"):
            check_idle(args.gpu)
            import torch

            from segmentary.medical.model_registry import build_model
            from segmentary.medical.torch_backend import _seed
            from segmentary.medical.torch_config import TorchConfig
            from segmentary.medical.torch_data import iter_predictions

            if torch.cuda.is_initialized():
                raise RuntimeError("CUDA was initialized before GPU binding")
            os.environ.update(
                CUDA_VISIBLE_DEVICES=args.gpu,
                CUDA_DEVICE_ORDER="PCI_BUS_ID",
                HF_HUB_OFFLINE="1",
                CUBLAS_WORKSPACE_CONFIG=":4096:8",
            )
            config = dataclasses.replace(TorchConfig(**verified["config"]), gpu=args.gpu)
            if config.roi_manifest is not None:
                raise ValueError("Stage one must be a full-image localizer")
            _seed(config)
            model = build_model(
                config.model,
                in_channels=config.context_slices,
                patch_size=config.patch_size,
                model_options=config.model_options,
            )
            model.load_state_dict(verified["state"]["model"], strict=True)
            del verified["state"]
            model.to("cuda:0").eval()
            args.output.mkdir(parents=True)
            predictions = args.output / "predictions"
            predictions.mkdir()
            start = time.time()
            with contextlib.closing(
                iter_predictions(
                    model, cases, config, torch.device("cuda:0"), output_directory=predictions
                )
            ) as results:
                for index, result in enumerate(results, 1):
                    if result.error is not None:
                        raise result.error
                    atomic_write_json(
                        args.output / "case-timings" / f"{result.case['case_id']}.json",
                        {
                            "case_id": result.case["case_id"],
                            "wall_seconds": result.wall_seconds,
                            "timings": result.timings,
                            "statistics": result.statistics,
                            "prediction_sha256": sha256(
                                predictions / f"{result.case['case_id']}.nii.gz"
                            ),
                        },
                    )
                    atomic_write_json(
                        args.output / "progress.json",
                        {
                            "status": "running",
                            "completed_cases": index,
                            "total_cases": len(cases),
                            "elapsed_seconds": time.time() - start,
                        },
                    )
                    print(
                        json.dumps({"completed_cases": index, "total_cases": len(cases)}),
                        flush=True,
                    )
            workspace = Path(config.workspace)
            receipt = {
                "initialization": "scratch",
                "training_prediction_policy": "in_sample_exploratory",
                "prediction_case_ids": allowed,
                "reference_labels_opened": False,
                "checkpoint": verified["checkpoint_path"],
                "checkpoint_sha256": verified["checkpoint_sha256"],
                "training_source_commit": verified["training_source_commit"],
                "inference_source_commit": revision,
                "verification": verified["verification"],
                "binding": str(workspace / "binding.json"),
                "binding_sha256": sha256(workspace / "binding.json"),
                "resolved_config": str(workspace / "resolved-config.json"),
                "resolved_config_sha256": sha256(workspace / "resolved-config.json"),
                "stage_two_initialization": "independent scratch; this checkpoint is only used for ROI prediction",
            }
            atomic_write_json(args.output / "provenance.json", receipt)
            atomic_write_json(
                args.output / "progress.json",
                {
                    "status": "completed",
                    "completed_cases": len(cases),
                    "total_cases": len(cases),
                    "elapsed_seconds": time.time() - start,
                },
            )


if __name__ == "__main__":
    main()
