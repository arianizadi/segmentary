#!/usr/bin/env python3
"""Freeze three scratch architectures inside one full nnU-Net training recipe.

This Task07-specific planner reads metadata only. It does not allocate GPUs,
copy caches, import checkpoints, open image/label payloads or launch training.
The backend independently verifies all bound cache payloads during import.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.plan_medical_campaign import _clean_source, _interpreter

from segmentary.medical.backend import NNUNetConfig, _digest, _lock
from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.geometry import sha256_file

GROUP = "nnunet_frozen_plan_scratch_seed0_250000_steps"
ARMS = {
    "resenc": ("nnunet_resenc_l", "Fresh official ResEnc L matched control"),
    "plainconv": ("nnunet_planned_plainconv", "Planned plain U-Net; two convolutions per stage"),
    "dynunet": ("nnunet_planned_dynunet", "Planned DynUNet; basic two-convolution blocks"),
}
EXPECTED_COUNTS = {"train": 197, "val": 42, "test": 42}
METADATA_NAMES = (
    "nnUNetResEncUNetLPlans.json",
    "splits_final.json",
    "dataset.json",
    "dataset_fingerprint.json",
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def reference_metadata(
    workspace: Path, metadata: dict, splits: dict, input_hashes: dict[str, str]
) -> tuple[dict[str, Any], dict[Path, str]]:
    """Verify a frozen reference using small metadata files, never CT payloads."""
    binding_path, plan_binding_path = workspace / "binding.json", workspace / "plan-binding.json"
    binding, plan_binding = _read(binding_path), _read(plan_binding_path)
    watched = {path: sha256_file(path) for path in (binding_path, plan_binding_path)}
    if plan_binding.get("binding_digest") != _digest(binding):
        raise ValueError("Reference plan binding does not match its prepared experiment")
    if any(binding.get(f"{key}_sha256") != digest for key, digest in input_hashes.items()):
        raise ValueError("Reference manifest or split differs from the requested cohort")
    if (
        binding.get("planning_scope") != "train_and_val_only"
        or binding.get("ontology") != metadata.get("ontology")
        or sorted(binding.get("development_cases", [])) != sorted(splits["train"] + splits["val"])
        or sorted(binding.get("held_out_cases", [])) != sorted(splits["test"])
    ):
        raise ValueError("Reference planning scope, ontology or group membership differs")
    config = binding.get("config", {})
    required = {
        "workspace": str(workspace),
        "resenc": "L",
        "configuration": "3d_fullres",
        "dataset_id": 707,
        "dataset_name": "Pancreas",
        "fold": 0,
        "seed": 0,
        "purpose": "baseline",
        "nnunet_version": "2.8.1",
        "use_mirroring": False,
        "tile_step_size": 0.5,
    }
    if (
        any(config.get(key) != value for key, value in required.items())
        or config.get("architecture", "resenc") != "resenc"
        or config.get("reference_workspace") is not None
        or any(
            config.get(key) is not None
            for key in ("num_epochs", "num_iterations_per_epoch", "num_val_iterations_per_epoch")
        )
    ):
        raise ValueError("Reference must be the original full-budget Task07 ResEnc L recipe")
    prepared = workspace / "nnUNet_preprocessed" / "Dataset707_Pancreas"
    for name in METADATA_NAMES:
        path = prepared / name
        digest = sha256_file(path)
        if plan_binding.get("files", {}).get(name) != digest:
            raise ValueError(f"Reference metadata changed: {name}")
        watched[path] = digest
    plan = _read(prepared / METADATA_NAMES[0])
    config_plan = plan["configurations"]["3d_fullres"]
    expected_plan = {
        "batch_size": 2,
        "patch_size": [56, 320, 256],
        "spacing": [2.5, 0.8125, 0.8125],
        "batch_dice": False,
        "preprocessor_name": "DefaultPreprocessor",
        "normalization_schemes": ["CTNormalization"],
    }
    if any(config_plan.get(key) != value for key, value in expected_plan.items()):
        raise ValueError("Reference plan differs from the audited full-resolution geometry/loss")
    fold = json.loads((prepared / "splits_final.json").read_text())
    if fold != [{"train": splits["train"], "val": splits["val"]}]:
        raise ValueError("Reference nnU-Net fold differs from the fixed development split")
    dataset = _read(prepared / "dataset.json")
    if dataset.get("labels") != metadata["ontology"] or dataset.get("numTraining") != 239:
        raise ValueError("Reference dataset ontology or development count differs")
    return {
        "binding_sha256": watched[binding_path],
        "plan_binding_sha256": watched[plan_binding_path],
        "metadata_sha256": {name: watched[prepared / name] for name in METADATA_NAMES},
        "planning_scope": "train_and_val_only",
        "configuration": config_plan,
        "intensity_properties": plan["foreground_intensity_properties_per_channel"],
        "cache_payload_verification": "deferred to mandatory backend import; planner reads metadata only",
    }, watched


def plan_campaign(
    *,
    source_root: Path,
    campaign_dir: Path,
    python: Path,
    nnunet_python: Path,
    manifest: Path,
    splits: Path,
    reference_workspace: Path,
    gpus: list[str],
) -> dict:
    source_root = source_root.expanduser().resolve()
    campaign_dir = campaign_dir.expanduser().resolve()
    reference_workspace = reference_workspace.expanduser().resolve()
    manifest, splits = manifest.expanduser().resolve(), splits.expanduser().resolve()
    if campaign_dir.exists() or campaign_dir.is_symlink():
        raise FileExistsError("Campaign output must not already exist")
    if (
        campaign_dir.is_relative_to(source_root)
        or campaign_dir.is_relative_to(reference_workspace)
        or reference_workspace.is_relative_to(campaign_dir)
    ):
        raise ValueError("Campaign output must be separate from source and reference workspace")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", campaign_dir.name):
        raise ValueError("Campaign identifier must be filesystem safe")
    if (
        len(gpus) != 3
        or len(set(gpus)) != 3
        or any(not isinstance(gpu, str) or not re.fullmatch(r"0|[1-9][0-9]*", gpu) for gpu in gpus)
    ):
        raise ValueError("Specify exactly three distinct physical numeric GPU strings")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited is not None and not set(gpus).issubset(inherited.split(",")):
        raise ValueError("Campaign GPUs exceed inherited CUDA_VISIBLE_DEVICES")
    commit = _clean_source(source_root)
    harness, official = _interpreter(python), _interpreter(nnunet_python)
    input_hashes = {"manifest": sha256_file(manifest), "splits": sha256_file(splits)}
    metadata, split_record = load_manifest(manifest, verify_files=False), _read(splits)
    validate_splits(metadata, split_record)
    counts = {key: len(split_record.get(key, [])) for key in EXPECTED_COUNTS}
    if counts != EXPECTED_COUNTS:
        raise ValueError("Use the original Task07 197/42/42 split")
    lookup = {case["case_id"]: case for case in metadata["cases"]}
    for identifier in split_record["train"] + split_record["val"]:
        case = lookup[identifier]
        if case["annotation_status"] != "labeled" or not case.get("label"):
            raise ValueError("Development cases require complete pancreas/mass labels")
    reference, watched = reference_metadata(
        reference_workspace, metadata, split_record, input_hashes
    )
    watched.update({manifest: input_hashes["manifest"], splits: input_hashes["splits"]})
    recipes, runs = {}, []
    for architecture, (model, description) in ARMS.items():
        identifier = f"{model}-seed0"
        config = NNUNetConfig(
            workspace=str(campaign_dir / "runs" / identifier),
            backend_python=official,
            architecture=architecture,
            reference_workspace=str(reference_workspace),
            resenc="L",
            configuration="3d_fullres",
            dataset_id=707,
            dataset_name="Pancreas",
            workers=4,
            seed=0,
            gpu=gpus[0],
            purpose="baseline",
            use_mirroring=False,
            tile_step_size=0.5,
        )
        recipes[identifier] = {"backend": "nnunet", **dataclasses.asdict(config)}
        runs.append(
            {
                "id": identifier,
                "config": str(campaign_dir / "recipes" / f"{identifier}.json"),
                "model": model,
                "backend": "nnunet",
                "workspace": config.workspace,
                "comparison_group": GROUP,
                "description": description,
            }
        )
    spec = {
        "schema_version": 1,
        "campaign_id": campaign_dir.name,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_root": str(source_root),
        "source_commit": commit,
        "python": harness,
        "manifest": str(manifest),
        "splits": str(splits),
        "gpus": gpus,
        "description": "Three scratch architectures under the frozen full nnU-Net recipe and fixed Task07 validation split.",
        "protocol": {
            "preset": "task07_nnunet_strong_recipe_v1",
            "manifest_sha256": input_hashes["manifest"],
            "splits_sha256": input_hashes["splits"],
            "manifest_fingerprint": metadata["fingerprint"],
            "splits_fingerprint": split_record["fingerprint"],
            "partition_counts": counts,
            "grouping_status": metadata.get("grouping_status", "unspecified"),
            "reference": reference,
            "optimizer_steps_per_arm": 250000,
            "batch_size": 2,
            "sampled_patches_per_arm": 500000,
            "seed": 0,
            "maximum_concurrent_runs": 3,
            "early_stopping": False,
            "checkpoint_selection": "official_ema_foreground_dice; same rule across all arms",
            "checkpoint_retention": "named latest, selected best and terminal checkpoint; no periodic archive",
            "resume": "own same-recipe checkpoint only, including optimizer/scheduler/scaler/RNG",
            "dashboard": "normal medical campaign runner with owned pane cleanup",
            "inference": "native nnU-Net Gaussian logit blending, tile step 0.5, no mirroring or ensemble",
            "primary_metric": "equal-case mean native mass Dice on all 42 validation cases",
            "secondary_metrics": [
                "native pancreas union Dice",
                "zero mass overlap",
                "lesion metrics",
                "surface Dice and HD95",
                "coverage",
                "training and inference wall time",
                "peak CUDA memory",
                "per-case inference latency",
            ],
            "limitations": [
                "Single seed; architecture screening, not independent-seed robustness or SOTA evidence",
                "Planning uses train plus validation; preprocessing is not fitted on training alone",
                "Dataset-case grouping is not independently verified patient identity",
                "Equal updates, patches and input size do not equal FLOPs, memory, wall time or parameter count",
                "Architectures retain declared block depths, normalization and initialization differences",
                "No imported learned weights, reserved test scoring, TTA or ensembles",
                "All-positive validation cannot estimate specificity or patient ROC AUC",
            ],
        },
        "runs": runs,
        "evaluation": {
            "bootstrap_samples": 1000,
            "seed": 0,
            "surface_tolerance_mm": 2.0,
            "lesion_iou_threshold": 0.1,
            "review_overlays": False,
        },
    }
    campaign_dir.parent.mkdir(parents=True, exist_ok=True)
    with _lock(campaign_dir.parent / f".{campaign_dir.name}.planning.lock"):
        if campaign_dir.exists() or campaign_dir.is_symlink():
            raise FileExistsError("Campaign output appeared while planning")
        staging = Path(
            tempfile.mkdtemp(prefix=f".{campaign_dir.name}.building-", dir=campaign_dir.parent)
        )
        try:
            for identifier, recipe in recipes.items():
                atomic_write_json(staging / "recipes" / f"{identifier}.json", recipe)
            atomic_write_json(staging / "campaign.json", spec)
            module_spec = importlib.util.spec_from_file_location(
                "strong_recipe_runner", source_root / "scripts/run_medical_campaign.py"
            )
            if module_spec is None or module_spec.loader is None:
                raise ValueError("Pinned source has no loadable medical campaign runner")
            runner = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(runner)
            atomic_write_json(
                staging / "schema-check.json",
                {
                    **spec,
                    "runs": [
                        {**run, "config": str(staging / "recipes" / Path(run["config"]).name)}
                        for run in runs
                    ],
                },
            )
            runner.load_spec(staging / "schema-check.json")
            (staging / "schema-check.json").unlink()
            if _clean_source(source_root) != commit or any(
                sha256_file(path) != digest for path, digest in watched.items()
            ):
                raise ValueError("Frozen source or reference inputs changed while planning")
            if campaign_dir.exists() or campaign_dir.is_symlink():
                raise FileExistsError("Campaign output appeared before publication")
            staging.rename(campaign_dir)
            fd = os.open(campaign_dir.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "source-root",
        "campaign-dir",
        "python",
        "nnunet-python",
        "manifest",
        "splits",
        "reference-workspace",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--gpus", nargs="+", required=True)
    args = parser.parse_args()
    spec = plan_campaign(**vars(args))
    print(
        json.dumps(
            {
                "campaign": str(args.campaign_dir / "campaign.json"),
                "source_commit": spec["source_commit"],
                "runs": len(spec["runs"]),
                "status": "planned; nothing launched",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
