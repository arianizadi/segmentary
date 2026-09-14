#!/usr/bin/env python3
"""Compare uniform and Gaussian inference on an unchanged historical checkpoint.

Only the frozen validation cohort is predicted and scored. The best checkpoint
remains the one selected with the original uniform validation protocol; Gaussian
is an inference-only comparison, not a retrospectively selected training run.
Outputs are new, private diagnostic artifacts; the old workspace stays read-only.
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark_medical_inference import check_idle
from medical_checkpoint_diagnostic import sha256, verified_historical_checkpoint

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def validate_output(output: Path, workspace: Path, source: Path) -> None:
    """Diagnostics cannot overwrite or nest in the old scientific artifacts."""
    if output.exists():
        raise FileExistsError("Use a new diagnostic output directory")
    for protected in (workspace.resolve(), source.resolve()):
        if output.resolve() == protected or protected in output.resolve().parents:
            raise ValueError("Diagnostic output must be separate from historical source/workspace")


def validation_cases(binding: dict) -> list[dict]:
    from segmentary.medical.backend import _documents

    manifest, splits = _documents(binding["manifest_path"], binding["splits_path"])
    ids = splits["val"]
    if set(ids) & set(splits["train"] + splits["test"]):
        raise ValueError("Validation overlaps a forbidden partition")
    lookup = {case["case_id"]: case for case in manifest["cases"]}
    cases = [lookup[case_id] for case_id in ids]
    if any(case["annotation_status"] != "labeled" for case in cases):
        raise ValueError("Blending comparison requires complete validation annotations")
    return cases


def compare_uniform_reference(actual: dict, expected: dict) -> dict:
    """Require identical native Dice before interpreting an inference change."""
    if actual["manifest_fingerprint"] != expected["manifest_fingerprint"]:
        raise ValueError("Original uniform evaluation has a different manifest")
    for field in ("pancreas_include_mass", "aggregation", "empty_policy"):
        if actual["protocol"].get(field) != expected["protocol"].get(field):
            raise ValueError("Original uniform evaluation uses a different metric protocol")
    left = {row["case_id"]: row for row in actual["cases"]}
    right = {row["case_id"]: row for row in expected["cases"]}
    if (
        len(left) != len(actual["cases"])
        or len(right) != len(expected["cases"])
        or left.keys() != right.keys()
    ):
        raise ValueError("Original uniform evaluation cohort differs")
    maximum = 0.0
    for case_id, row in left.items():
        prior = right[case_id]
        if (
            row["status"] != "ok"
            or prior["status"] != "ok"
            or row["reference_sha256"] != prior["reference_sha256"]
        ):
            raise ValueError("Original uniform evaluation has missing or different references")
        for region in ("mass", "pancreas"):
            current, old = row["metrics"][region]["dice"], prior["metrics"][region]["dice"]
            if current is None or old is None:
                if current != old:
                    raise ValueError(
                        "Original uniform evaluation has different metric availability"
                    )
            else:
                maximum = max(maximum, abs(current - old))
    if maximum > 1e-12:
        raise ValueError(f"Uniform native Dice changed from historical output by {maximum}")
    return {"cases": len(left), "maximum_absolute_dice_difference": maximum, "passed": True}


def _predict_modes(model: Any, cases: list[dict], config: Any, device: Any, output: Path) -> dict:
    import torch

    from segmentary.medical.backend import _atomic_json
    from segmentary.medical.torch_blending import InferenceBlending
    from segmentary.medical.torch_data import iter_predictions

    outcomes: dict[str, list] = {"uniform": [], "gaussian": []}
    for mode in outcomes:
        (output / mode / "predictions").mkdir(parents=True)
    # Alternating order shares warm OS file caches without always favoring one
    # mode. There is no cross-case prefetch in this paired diagnostic; both use
    # exactly the same per-case prediction path, batch size and worker count.
    for index, case in enumerate(cases):
        order = ("uniform", "gaussian") if index % 2 == 0 else ("gaussian", "uniform")
        for mode in order:
            torch.cuda.synchronize(device)
            torch.cuda.reset_peak_memory_stats(device)
            started = time.monotonic()
            with contextlib.closing(
                iter_predictions(
                    model,
                    [case],
                    config,
                    device,
                    output_directory=output / mode / "predictions",
                    blending=InferenceBlending(mode),
                )
            ) as stream:
                result = next(stream)
            torch.cuda.synchronize(device)
            if result.error is not None:
                raise result.error
            outcomes[mode].append(
                {
                    "case_id": case["case_id"],
                    "mode_position": order.index(mode),
                    "wall_seconds": time.monotonic() - started,
                    "component_seconds": result.timings,
                    "prediction_statistics": result.statistics,
                    "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
                    "peak_reserved_bytes": torch.cuda.max_memory_reserved(device),
                }
            )
            del result
            _atomic_json(
                output / "progress.json",
                {
                    "phase": "prediction",
                    "updated_at": time.time(),
                    "completed_predictions": sum(map(len, outcomes.values())),
                    "total_predictions": 2 * len(cases),
                    "current_mode": mode,
                },
            )
        _atomic_json(output / "timings.json", outcomes)
    return outcomes


def run(args: argparse.Namespace) -> dict:
    import torch

    from segmentary.medical.backend import _atomic_json, _lock
    from segmentary.medical.evaluation import evaluate_predictions, paired_comparison
    from segmentary.medical.model_registry import build_model
    from segmentary.medical.torch_backend import _code, _seed, _state_hash
    from segmentary.medical.torch_blending import InferenceBlending
    from segmentary.medical.torch_config import TorchConfig

    if not args.gpu.isdigit() or str(int(args.gpu)) != args.gpu:
        raise ValueError("GPU must be a canonical physical numeric index")
    if args.gpu == "0":
        raise ValueError("GPU 0 is reserved for the ongoing nnU-Net campaign")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited is not None and args.gpu not in inherited.split(","):
        raise ValueError("Requested GPU is outside inherited CUDA visibility")
    source = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True
    ).strip():
        raise ValueError("Commit diagnostic source before running a scientific comparison")
    original_code = _code()
    output = args.output.resolve()
    with verified_historical_checkpoint(args.campaign, args.run_id) as verified:
        config = TorchConfig(**verified["config"])
        validate_output(output, config.root, Path(verified["training_source_root"]))
        cases = validation_cases(verified["binding"])
        for case in cases:
            for kind in ("image", "label"):
                if sha256(Path(case[kind])) != case[f"{kind}_sha256"]:
                    raise ValueError(f"Validation {kind} changed from manifest")
        lockroot = Path(
            os.environ.get(
                "SEGMENTARY_MEDICAL_LOCK_DIR",
                str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
            )
        )
        with _lock(lockroot / f"gpu-{args.gpu}.lock"):
            check_idle(args.gpu)
            os.environ.update(
                CUDA_VISIBLE_DEVICES=args.gpu,
                CUDA_DEVICE_ORDER="PCI_BUS_ID",
                HF_HUB_OFFLINE="1",
                CUBLAS_WORKSPACE_CONFIG=":4096:8",
            )
            _seed(config)
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is unavailable")
            device = torch.device("cuda:0")
            model = build_model(
                config.model,
                in_channels=config.context_slices,
                patch_size=config.patch_size,
                model_options=config.model_options,
            )
            model.load_state_dict(verified["state"]["model"], strict=True)
            del verified["state"]
            model.to(device).eval()
            initial_hash = _state_hash(model)
            output.mkdir(parents=True)
            receipt = {
                **verified,
                "diagnostic_source_commit": revision,
                "diagnostic_code": original_code,
                "diagnostic_script_sha256": sha256(Path(__file__)),
                "physical_gpu": args.gpu,
            }
            _atomic_json(output / "provenance.json", receipt)
            # Identical synthetic warmup before paired full-volume inference.
            dtype = torch.bfloat16 if config.precision == "bf16" else torch.float16
            inputs = torch.zeros(
                (config.inference_batch_size, config.context_slices, *config.patch_size),
                device=device,
            )
            with (
                torch.inference_mode(),
                torch.autocast("cuda", dtype=dtype, enabled=config.precision != "fp32"),
            ):
                for _ in range(3):
                    warm = model(inputs)
            del warm, inputs
            torch.cuda.synchronize(device)
            outcomes = _predict_modes(model, cases, config, device, output)
            if _state_hash(model) != initial_hash:
                raise ValueError("Inference changed model parameters or buffers")
            del model
            torch.cuda.empty_cache()
        reports = {}
        for mode in ("uniform", "gaussian"):
            reports[mode] = evaluate_predictions(
                verified["binding"]["manifest_path"],
                output / mode / "predictions",
                output / mode / "evaluation",
                case_ids=[case["case_id"] for case in cases],
                pancreas_include_mass=True,
                surface_tolerance_mm=2.0,
                bootstrap_samples=10000,
                seed=20260914,
                review_overlays=True,
                lesion_iou_threshold=0.1,
            )
            if reports[mode]["coverage"]["valid_prediction_cases"] != len(cases):
                raise ValueError("Inference comparison has incomplete prediction coverage")
        reference_agreement = None
        if args.reference_report:
            reference_agreement = compare_uniform_reference(
                reports["uniform"], json.loads(args.reference_report.read_text())
            )
            reference_agreement["reference_report_sha256"] = sha256(args.reference_report)
        if _code() != original_code:
            raise ValueError("Diagnostic source changed while running")
        result = {
            "schema_version": 1,
            "status": "completed",
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "protocol": {
                "partition": "val",
                "cases": len(cases),
                "checkpoint": "original_best_under_uniform_validation",
                "blending": {mode: dataclasses.asdict(InferenceBlending(mode)) for mode in reports},
                "gaussian_floor": float(__import__("numpy").finfo("float32").eps),
                "weighting_space": "softmax_probabilities_before_native_resampling_and_argmax",
                "timing_scope": "per-case preprocessing, inference, reconstruction and NIfTI export; alternating mode order; no cross-case pipeline overlap; warmup excluded; evaluation excluded",
                "same_model_state_before_after": initial_hash,
                "inference_batch_size": config.inference_batch_size,
                "overlap": config.overlap,
                "precision": config.precision,
            },
            "checkpoint_sha256": verified["checkpoint_sha256"],
            "historical_uniform_agreement": reference_agreement,
            "paired": {
                region: paired_comparison(
                    reports["uniform"],
                    reports["gaussian"],
                    region=region,
                    bootstrap_samples=10000,
                    seed=20260914,
                )
                for region in ("mass", "pancreas")
            },
            "regions": {mode: report["regions"] for mode, report in reports.items()},
            "inference_seconds": {
                mode: sum(row["wall_seconds"] for row in rows) for mode, rows in outcomes.items()
            },
            "limitations": [
                "Validation-guided exploratory comparison; no test access and no independent generalization claim.",
                "No Gaussian checkpoint reselection or training; original best checkpoint is held fixed.",
                "One checkpoint and one hardware/runtime pair; timing includes alternating cache-order effects.",
                "Connected components are lesion proxies; masses are not necessarily confirmed malignant tumors.",
            ],
        }
    # Only publish completion after the original artifact immutability checks.
    _atomic_json(output / "comparison.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--gpu", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-report", type=Path)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({"status": result["status"], "paired": result["paired"]}), flush=True)


if __name__ == "__main__":
    main()
