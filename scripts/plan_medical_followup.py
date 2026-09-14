#!/usr/bin/env python3
"""Freeze three fresh DynUNet budget/resolution arms; never start training.

Uses the same 197/42/42 Task07 split and original control recipe. Source,
runtime, reference campaign/binding, and recipes are recorded before launch.
No image or label payloads, checkpoints, or GPU allocations are opened here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.plan_medical_campaign import _clean_source, _interpreter, _reject_pretrained
from scripts.plan_medical_recipe_ablation import EXPECTED_CONTROL, _json_config
from scripts.run_medical_campaign import absolute_path, load_recipe, read_json

from segmentary.medical.backend import _lock
from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.followup import (
    CASCADE_PRESET,
    DEEP_PRESET,
    PRESET,
    RECIPE_PRESET,
    arm_id,
    arms_for,
    validate_declared_followup,
)
from segmentary.medical.geometry import sha256_file
from segmentary.medical.recipe_ablation import recipe_fingerprint


def _runtime_record(source: Path, python: str) -> dict:
    probe = """
import importlib.metadata, json, pathlib, platform, sys
sys.path.insert(0, sys.argv[1])
import segmentary.medical.torch_config as config
import torch
print(json.dumps({
    "python": platform.python_version(), "executable": sys.executable,
    "config_module": str(pathlib.Path(config.__file__).resolve()),
    "torch_cuda": torch.version.cuda,
    "packages": {name: importlib.metadata.version(name) for name in
        ("torch", "monai", "numpy", "scipy", "nibabel")},
}))
"""
    result = subprocess.run(
        [python, "-c", probe, str(source / "src")],
        text=True,
        check=True,
        capture_output=True,
        timeout=120,
        env=dict(os.environ)
        | {
            "PYTHONPATH": str(source / "src"),
            "PYTHONNOUSERSITE": "1",
            "HF_HUB_OFFLINE": "1",
        },
    )
    record = json.loads(result.stdout)
    if (
        not record["python"].startswith("3.11.")
        or Path(record["config_module"]) != source / "src/segmentary/medical/torch_config.py"
    ):
        raise ValueError("Training interpreter must load Python 3.11 and the pinned source")
    return record


def plan_followup(
    *,
    source_root: Path,
    campaign_dir: Path,
    reference_campaign: Path,
    python: Path,
    cache_root: Path,
    gpus: list[str],
    reference_run_id: str = "dynunet-control-seed0",
    experiment: str = "budget-resolution",
    roi_manifests: dict | None = None,
) -> dict:
    if experiment not in {
        "budget-resolution",
        "deep-supervision",
        "recipe-explorations",
        "cascade",
    }:
        raise ValueError("Unknown follow-up experiment")
    deep_supervision = experiment == "deep-supervision"
    preset = {
        "budget-resolution": PRESET,
        "deep-supervision": DEEP_PRESET,
        "recipe-explorations": RECIPE_PRESET,
        "cascade": CASCADE_PRESET,
    }[experiment]
    selected_arms = arms_for(preset, roi_manifests)
    source_root = source_root.expanduser().resolve()
    campaign_dir = campaign_dir.expanduser().resolve()
    reference_campaign = reference_campaign.expanduser().resolve()
    cache_root = cache_root.expanduser().resolve()
    if campaign_dir.exists() or campaign_dir.is_symlink():
        raise FileExistsError("Campaign output must not already exist")
    if (
        any(path.is_relative_to(source_root) for path in (campaign_dir, cache_root))
        or campaign_dir.is_relative_to(reference_campaign.parent)
        or cache_root.is_relative_to(reference_campaign.parent)
        or cache_root.is_relative_to(campaign_dir)
        or campaign_dir.is_relative_to(cache_root)
    ):
        raise ValueError("Source, new campaign, cache, and immutable reference must be separate")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", campaign_dir.name):
        raise ValueError("Campaign identifier must be filesystem safe")
    if (
        not gpus
        or len(set(gpus)) != len(gpus)
        or any(not isinstance(gpu, str) or not re.fullmatch(r"0|[1-9][0-9]*", gpu) for gpu in gpus)
    ):
        raise ValueError("gpus must be unique physical numeric GPU strings")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited is not None and not set(gpus).issubset(inherited.split(",")):
        raise ValueError("Campaign GPUs exceed inherited CUDA_VISIBLE_DEVICES")
    commit = _clean_source(source_root)
    harness = _interpreter(python)
    runtime = _runtime_record(source_root, harness)
    source_hashes = {
        name: sha256_file(source_root / name)
        for name in (
            "scripts/plan_medical_followup.py",
            "scripts/run_medical_campaign.py",
            "src/segmentary/medical/followup.py",
            "src/segmentary/medical/torch_config.py",
            "src/segmentary/medical/torch_cache.py",
        )
    }
    for name in ("scripts/plan_medical_followup.py", "src/segmentary/medical/followup.py"):
        if sha256_file(ROOT / name) != source_hashes[name]:
            raise ValueError("Planner implementation must match the pinned source")
    reference = read_json(reference_campaign)
    reference_hash = sha256_file(reference_campaign)
    if reference.get("schema_version") != 1 or not re.fullmatch(
        r"[a-f0-9]{40}", str(reference.get("source_commit", ""))
    ):
        raise ValueError("Reference campaign must have a pinned source commit")
    manifest = absolute_path(reference.get("manifest"), "reference manifest")
    splits = absolute_path(reference.get("splits"), "reference splits")
    matches = [run for run in reference["runs"] if run["id"] == reference_run_id]
    if len(matches) != 1:
        raise ValueError("Reference campaign must contain the exact requested control run")
    reference_path = absolute_path(matches[0].get("config"), "reference recipe")
    binding_path = reference_campaign.parent / "state/campaign-binding.json"
    hashes = {
        "reference_campaign": reference_hash,
        "reference_recipe": sha256_file(reference_path),
        "reference_binding": sha256_file(binding_path),
        "manifest": sha256_file(manifest),
        "splits": sha256_file(splits),
    }
    binding = read_json(binding_path)
    if (
        binding.get("spec_sha256") != hashes["reference_campaign"]
        or binding.get("recipes", {}).get(reference_run_id) != hashes["reference_recipe"]
        or any(
            binding.get(f"{key}_sha256") != hashes[key]
            or reference.get("protocol", {}).get(f"{key}_sha256") != hashes[key]
            for key in ("manifest", "splits")
        )
    ):
        raise ValueError("Reference campaign, recipe, or split differs from its frozen binding")
    raw = load_recipe(reference_path)
    _reject_pretrained(raw)
    baseline = _json_config(raw)
    if any(baseline.get(key) != value for key, value in EXPECTED_CONTROL.items()):
        raise ValueError("Reference differs from the declared original DynUNet control")
    if any(
        baseline.get(key) is not None for key in ("center_probabilities", "class_center_weights")
    ):
        raise ValueError("Reference must use the original foreground sampler")
    if any(
        baseline.get(key, 0) != 0 for key in ("rotation_probability", "intensity_scale_probability")
    ):
        raise ValueError("Reference must use the original flips-only augmentation")
    if baseline.get("inference_blending", "uniform") != "uniform":
        raise ValueError("Training follow-up must retain the original uniform inference blending")
    metadata = load_manifest(manifest, verify_files=False)
    partition = read_json(splits)
    validate_splits(metadata, partition)
    counts = {key: len(partition.get(key, [])) for key in ("train", "val", "test")}
    if counts != {"train": 197, "val": 42, "test": 42}:
        raise ValueError("Use the original Task07 197/42/42 train/validation/reserved-test split")
    lookup = {case["case_id"]: case for case in metadata["cases"]}
    for identifier in partition["train"] + partition["val"]:
        if lookup[identifier]["annotation_status"] != "labeled" or not lookup[identifier].get(
            "label"
        ):
            raise ValueError("Training and validation require complete pancreas/mass labels")

    recipes, runs, declarations = {}, [], {}
    control_id = "dynunet-control10k-seed0"
    for name, arm in selected_arms.items():
        identifier = arm_id(name, arm)
        recipe = _json_config(
            {
                **baseline,
                **arm["changes"],
                "workspace": str(campaign_dir / "runs" / identifier),
                "backend_python": harness,
                "cache_root": str(cache_root),
                "gpu": gpus[0],
            }
        )
        recipes[identifier] = recipe
        runs.append(
            {
                "id": identifier,
                "config": str(campaign_dir / "recipes" / f"{identifier}.json"),
                "model": recipe["model"],
                "backend": "torch",
                "workspace": recipe["workspace"],
                "comparison_group": arm["group"],
                "description": arm["description"],
            }
        )
        declarations[identifier] = {
            "arm": name,
            "control_run_id": control_id,
            "description": arm["description"],
            "changes_from_control": json.loads(json.dumps(arm["changes"])),
            "scientific_recipe_sha256": recipe_fingerprint(recipe),
            "optimizer_steps": recipe["epochs"] * recipe["steps_per_epoch"],
            "sampled_patches": recipe["epochs"] * recipe["steps_per_epoch"] * recipe["batch_size"],
            "nominal_crop_extent_mm_xyz": [
                n * spacing
                for n, spacing in zip(recipe["patch_size"][::-1], recipe["spacing_mm"], strict=True)
            ],
            "validation_epochs": [1, *range(10, recipe["epochs"] + 1, 10)],
        }
    spec = {
        "schema_version": 1,
        "campaign_id": campaign_dir.name,
        "source_root": str(source_root),
        "source_commit": commit,
        "python": harness,
        "manifest": str(manifest),
        "splits": str(splits),
        "gpus": gpus,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "description": "Fresh scratch DynUNet control, longer schedule, and finer in-plane grid; validation only.",
        "protocol": {
            "preset": preset,
            "manifest_sha256": hashes["manifest"],
            "splits_sha256": hashes["splits"],
            "manifest_fingerprint": metadata["fingerprint"],
            "splits_fingerprint": partition["fingerprint"],
            "partition_counts": counts,
            "grouping_status": metadata.get("grouping_status", "unspecified"),
            "followup_experiments": {
                "schema_version": 1,
                "model": "dynunet",
                "seed": 0,
                "control_run_id": control_id,
                "control_scientific_recipe_sha256": recipe_fingerprint(recipes[control_id]),
                "reference_source_commit": reference["source_commit"],
                "reference_run_id": reference_run_id,
                **{
                    f"{key}_sha256": hashes[key]
                    for key in ("reference_campaign", "reference_recipe", "reference_binding")
                },
                "arms": declarations,
                "planned_contrasts": [
                    {
                        "candidate": "dynunet-long30k-seed0",
                        "control": control_id,
                        "factor": "declared polynomial-schedule duration and training budget",
                    },
                    {
                        "candidate": "dynunet-fine10k-seed0",
                        "control": control_id,
                        "factor": "in-plane voxel spacing and voxel crop dimensions at equal nominal physical extent",
                    },
                ],
            },
            "runtime_at_planning": runtime,
            "source_files_sha256": source_hashes,
            "checkpoint_selection": "highest mean native per-case mass Dice on validation",
            "checkpoint_retention": "latest and selected best; normal runner retention",
            "resume": "Own latest checkpoint only; never import historical weights or alter its scientific schedule",
            "limitations": [
                "One seed; differing budgets or grids remain in separate ordinary comparison groups",
                "Long30k has a slower polynomial decay from the first update; this tests the longer recipe, not only extra updates",
                "Best-of-more validation checks favors the longer arm; report fixed endpoint and curves as well as selected best",
                "Fine10k processes 2.25 times as many voxels per patch and has different compute; equal updates are not equal GPU-hours",
                "Nominal physical crop extent is voxel count times spacing, not the distance between first and last voxel centers",
                "No external weights; source and runtime differ from historical runs, hence a fresh matched control",
                "Reserved test payloads are not opened or scored; mass is not a verified malignancy diagnosis",
                "All-positive validation cannot estimate patient specificity or ROC AUC",
            ],
        },
        "runs": runs,
        "evaluation": dict(reference.get("evaluation", {})),
    }
    if deep_supervision:
        from segmentary.medical.torch_deep_supervision import supervision_metadata

        spec["description"] = (
            "Fresh scratch DynUNet control versus two native decoder auxiliary losses; "
            "matched 10,000-update schedule, sampling, geometry and primary inference."
        )
        spec["protocol"]["followup_experiments"]["planned_contrasts"] = [
            {
                "candidate": "dynunet-deep10k-seed0",
                "control": control_id,
                "factor": "two auxiliary decoder heads and normalized multi-scale training loss",
            }
        ]
        spec["protocol"]["deep_supervision"] = supervision_metadata()["deep_supervision"]
        spec["protocol"]["limitations"] = [
            "One exploratory seed; validation selects checkpoints and is not independent testing",
            "Auxiliary heads add training parameters and compute; equal steps are not equal GPU-hours",
            "Primary initialization and post-construction RNG are matched; full state hashes differ because auxiliary heads exist only in the candidate",
            "Each scale uses existing CE plus batch foreground Dice; weights are 4/7, 2/7 and 1/7",
            "Nearest-neighbor coarse targets can lose tiny mass components; audit auxiliary target coverage before launch",
            "Only primary logits run at inference; no Gaussian blending, mirroring or other inference change",
            "This controlled auxiliary-loss implementation does not reproduce the full nnU-Net recipe",
            "No external weights; reserved test payloads remain untouched",
            "All-positive validation cannot estimate patient specificity or ROC AUC",
        ]
    if experiment in {"recipe-explorations", "cascade"}:
        spec["description"] = (
            "Fresh controlled Task07 recipe experiments; full-native validation only"
        )
        declaration = spec["protocol"]["followup_experiments"]
        declaration["planned_contrasts"] = [
            {"candidate": arm_id(name, arm), "control": control_id, "factor": arm["description"]}
            for name, arm in selected_arms.items()
            if name != "control10k"
        ]
        if roi_manifests is not None:
            declaration["roi_manifests"] = roi_manifests
            for roi in roi_manifests.values():
                document = read_json(Path(roi["path"]))
                if (
                    document.get("manifest_sha256") != hashes["manifest"]
                    or document.get("splits_sha256") != hashes["splits"]
                    or set(document["cases"]) != set(partition["train"] + partition["val"])
                ):
                    raise ValueError(
                        "ROI cohort must match exactly this training and validation partition"
                    )
        spec["protocol"]["limitations"] = [
            "One seed and multiple exploratory comparisons; no independent test or architecture-winner claim",
            "All arms use 10,000 updates, 80,000 patches; compute and voxel exposure differ",
            "Isotropic arm preserves nominal physical crop extent, not physical receptive field; interpolated slices add no acquired information",
            "Focal alpha is a global coefficient, not class weights; gamma=2; Dice definition unchanged",
            "Raw per-volume min-max is image-only and can be distorted by extreme intensities; fixed HU min-max is already the control",
            "Swin24 repeats the architecture already screened; Swin48 adds capacity and activation checkpointing; no pretrained weights",
            "Deep supervision has auxiliary heads at half/quarter resolution weighted 4/7,2/7,1/7; tiny labels can disappear at coarse scales",
            "Cascade uses frozen own-scratch stage-one predictions, in-sample for training patients; out-of-fold training crops remain a future confirmation",
            "Cascade evaluates the entire native CT, counting outside-ROI mass as missed; empty localization falls back to full CT",
            "No early stopping; record endpoint and selected-best validation results; keep latest/best only",
            "Reserved test remains untouched; all-positive validation cannot estimate patient specificity or AUC",
        ]
    validate_declared_followup(spec, recipes)
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
            for source, name in (
                (reference_campaign, "reference-campaign.json"),
                (reference_path, f"reference-recipe{reference_path.suffix}"),
                (binding_path, "reference-binding.json"),
            ):
                shutil.copyfile(source, staging / name)
            atomic_write_json(staging / "campaign.json", spec)
            runner_spec = importlib.util.spec_from_file_location(
                "followup_runner", source_root / "scripts/run_medical_campaign.py"
            )
            if runner_spec is None or runner_spec.loader is None:
                raise ValueError("Pinned source has no loadable medical campaign runner")
            runner = importlib.util.module_from_spec(runner_spec)
            runner_spec.loader.exec_module(runner)
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
            if (
                _clean_source(source_root) != commit
                or _runtime_record(source_root, harness) != runtime
            ):
                raise ValueError("Source or runtime changed while planning")
            for key, path in {
                "reference_campaign": reference_campaign,
                "reference_recipe": reference_path,
                "reference_binding": binding_path,
                "manifest": manifest,
                "splits": splits,
            }.items():
                if sha256_file(path) != hashes[key]:
                    raise ValueError("Frozen reference inputs changed while planning")
            if campaign_dir.exists() or campaign_dir.is_symlink():
                raise FileExistsError("Campaign output appeared before publication")
            staging.rename(campaign_dir)
            descriptor = os.open(campaign_dir.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-root", "campaign-dir", "reference-campaign", "python", "cache-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--reference-run-id", default="dynunet-control-seed0")
    parser.add_argument("--gpus", nargs="+", required=True)
    parser.add_argument(
        "--experiment",
        choices=("budget-resolution", "deep-supervision", "recipe-explorations", "cascade"),
        default="budget-resolution",
    )
    parser.add_argument("--roi-manifests", type=Path)
    args = parser.parse_args()
    options = vars(args).copy()
    options["roi_manifests"] = read_json(args.roi_manifests) if args.roi_manifests else None
    spec = plan_followup(**options)
    print(
        json.dumps(
            {
                "campaign": str(args.campaign_dir / "campaign.json"),
                "runs": len(spec["runs"]),
                "status": "planned; nothing launched",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
