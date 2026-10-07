#!/usr/bin/env python3
"""Freeze ResEnc L seed and cross-validation-fold runs on one frozen nnU-Net plan.

Every run uses the original full-budget ResEnc L 3d_fullres recipe of the
verified preprocessing reference (scratch, no mirroring, tile step 0.5) and a
development CV manifest whose fold 0 is the frozen train/validation split. Each
run is pinned to one GPU. Like the strong-recipe planner, this reads metadata
only: it does not allocate GPUs, copy caches, open CT payloads or launch work.
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
from scripts.plan_medical_strong_recipe import EXPECTED_COUNTS, reference_metadata

from segmentary.gpu_policy import refuse_forbidden
from segmentary.medical.backend import NNUNetConfig, _lock
from segmentary.medical.cv_splits import validate_cv_splits
from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.geometry import sha256_file

MODEL = "nnunet_resenc_l"
ARM = re.compile(r"^(0|[1-9][0-9]*):(0|[1-9][0-9]?):([0-9]+)$")


def parse_arm(text: str) -> tuple[str, int, int]:
    """``GPU:FOLD:SEED``, for example ``6:1:0``."""
    match = ARM.fullmatch(text)
    if not match:
        raise ValueError(f"Runs are GPU:FOLD:SEED, got {text!r}")
    return match.group(1), int(match.group(2)), int(match.group(3))


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def plan_campaign(
    *,
    source_root: Path,
    campaign_dir: Path,
    python: Path,
    nnunet_python: Path,
    manifest: Path,
    splits: Path,
    cv_splits: Path,
    reference_workspace: Path,
    runs: list[str],
) -> dict:
    source_root = source_root.expanduser().resolve()
    campaign_dir = campaign_dir.expanduser().resolve()
    reference_workspace = reference_workspace.expanduser().resolve()
    manifest, splits = manifest.expanduser().resolve(), splits.expanduser().resolve()
    cv_splits = cv_splits.expanduser().resolve()
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
    arms = [parse_arm(text) for text in runs]
    if not arms or len({(fold, seed) for _, fold, seed in arms}) != len(arms):
        raise ValueError("Each fold/seed pair must be declared exactly once")
    gpus = sorted({gpu for gpu, _, _ in arms}, key=int)
    refuse_forbidden(gpus)
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
    cv_sha256 = sha256_file(cv_splits)
    cv = _read(cv_splits)
    validate_cv_splits(metadata, split_record, cv)
    if cv.get("base_splits_sha256") != input_hashes["splits"]:
        raise ValueError("Cross-validation manifest was derived from a different split file")
    if any(fold >= len(cv["folds"]) for _, fold, _ in arms):
        raise ValueError("A requested fold is outside the cross-validation manifest")
    reference, watched = reference_metadata(
        reference_workspace, metadata, split_record, input_hashes
    )
    watched.update(
        {manifest: input_hashes["manifest"], splits: input_hashes["splits"], cv_splits: cv_sha256}
    )
    recipes, run_records = {}, []
    for gpu, fold, seed in arms:
        identifier = f"{MODEL}-fold{fold}-seed{seed}"
        config = NNUNetConfig(
            workspace=str(campaign_dir / "runs" / identifier),
            backend_python=official,
            architecture="resenc",
            reference_workspace=str(reference_workspace),
            reference_plan_binding_sha256=reference["plan_binding_sha256"],
            resenc="L",
            configuration="3d_fullres",
            dataset_id=707,
            dataset_name="Pancreas",
            workers=4,
            seed=seed,
            fold=fold,
            gpu=gpu,
            purpose="baseline",
            use_mirroring=False,
            tile_step_size=0.5,
            cv_splits=str(cv_splits),
            cv_splits_sha256=cv_sha256,
        )
        recipes[identifier] = {"backend": "nnunet", **dataclasses.asdict(config)}
        run_records.append(
            {
                "id": identifier,
                "config": str(campaign_dir / "recipes" / f"{identifier}.json"),
                "model": MODEL,
                "backend": "nnunet",
                "workspace": config.workspace,
                "gpu": gpu,
                "comparison_group": f"{MODEL}_fold{fold}_scratch_250000_steps",
                "description": f"ResEnc L scratch, CV fold {fold}, seed {seed}",
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
        "description": "ResEnc L seeds on fold 0 and development CV folds under one frozen nnU-Net plan.",
        "protocol": {
            "preset": "task07_nnunet_seed_folds_v1",
            "manifest_sha256": input_hashes["manifest"],
            "splits_sha256": input_hashes["splits"],
            "cv_splits": str(cv_splits),
            "cv_splits_sha256": cv_sha256,
            "cv_fingerprint": cv["fingerprint"],
            "manifest_fingerprint": metadata["fingerprint"],
            "splits_fingerprint": split_record["fingerprint"],
            "partition_counts": counts,
            "fold_validation_counts": [len(item["val"]) for item in cv["folds"]],
            "grouping_status": metadata.get("grouping_status", "unspecified"),
            "reference": reference,
            "nnunet": {
                "expected_default_epochs": 1000,
                "expected_default_updates_per_epoch": 250,
            },
            "optimizer_steps_per_run": 250000,
            "batch_size": 2,
            "early_stopping": False,
            "checkpoint_selection": "official_ema_foreground_dice",
            "primary_checkpoint": "checkpoint_final.pth",
            "secondary_checkpoint": "checkpoint_best.pth (selected on the scored fold; optimistic)",
            "inference": "native nnU-Net Gaussian logit blending, tile step 0.5, no mirroring or ensemble",
            "primary_metric": "equal-case mean native mass Dice on the run's validation fold",
            "limitations": [
                "Seeds change initialization and sampling but CUDA/augmentation remain nondeterministic",
                "Planning uses all 239 development cases; folds 1-4 validate on cases seen by the planner",
                "Dataset-case grouping is not independently verified patient identity",
                "No imported learned weights, reserved test scoring, TTA or ensembles",
            ],
        },
        "runs": run_records,
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
                "seed_fold_runner", source_root / "scripts/run_medical_campaign.py"
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
                        for run in run_records
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
        "cv-splits",
        "reference-workspace",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument(
        "--run", dest="runs", action="append", required=True, help="GPU:FOLD:SEED, repeatable"
    )
    args = parser.parse_args()
    spec = plan_campaign(**vars(args))
    print(
        json.dumps(
            {
                "campaign": str(args.campaign_dir / "campaign.json"),
                "source_commit": spec["source_commit"],
                "runs": {run["id"]: run["gpu"] for run in spec["runs"]},
                "status": "planned; nothing launched",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
