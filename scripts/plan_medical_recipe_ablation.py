#!/usr/bin/env python3
"""Freeze six fresh DynUNet recipe arms from the original Task07 control.

Planning writes a new campaign only: no GPU allocation, training, checkpoint
import or test-payload access. Use the normal medical campaign runner afterward;
its latest/best checkpoint retention and owned dashboard cleanup remain active.
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

from scripts.plan_medical_campaign import _clean_source, _interpreter, _reject_pretrained
from scripts.run_medical_campaign import absolute_path, load_recipe, read_json

from segmentary.medical.backend import _lock
from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.geometry import sha256_file
from segmentary.medical.recipe_ablation import recipe_fingerprint
from segmentary.medical.torch_config import TorchConfig

GROUP = "dynunet_recipe_ablation_seed0_10000_steps"
ARMS: dict[str, tuple[str, dict[str, Any]]] = {
    "control": ("Original uniform-volume/foreground sampler and flips", {}),
    "mass50": (
        "Uniform-volume/pancreas/mass center probabilities 0.25/0.25/0.50",
        {"foreground_probability": None, "center_probabilities": [0.25, 0.25, 0.5]},
    ),
    "class111": (
        "Exact background/pancreas/mass class centers, weights 1:1:1",
        {"foreground_probability": None, "class_center_weights": [1.0, 1.0, 1.0]},
    ),
    "class115": (
        "Exact background/pancreas/mass class centers, weights 1:1:5",
        {"foreground_probability": None, "class_center_weights": [1.0, 1.0, 5.0]},
    ),
    "rotation": (
        "Original sampler and flips plus in-plane rotation",
        {
            "rotation_probability": 0.25,
            "rotation_degrees": [-15.0, 15.0],
            "rotation_padding_value": 0.0,
        },
    ),
    "intensity": (
        "Original sampler and flips plus normalized-image intensity scaling",
        {"intensity_scale_probability": 0.5, "intensity_scale_range": [0.9, 1.1]},
    ),
}
EXPECTED_CONTROL = {
    "model": "dynunet",
    "backend": "torch",
    "initialization": "scratch",
    "mode": "3d",
    "context_slices": 1,
    "patch_size": [96, 96, 96],
    "spacing_mm": [1.5, 1.5, 2.5],
    "hu_window": [-100.0, 240.0],
    "seed": 0,
    "batch_size": 8,
    "epochs": 100,
    "steps_per_epoch": 100,
    "validation_interval": 10,
    "inference_batch_size": 8,
    "learning_rate": 3e-4,
    "weight_decay": 1e-5,
    "foreground_probability": 0.5,
    "overlap": 0.5,
    "precision": "bf16",
    "deterministic": False,
    "augment": True,
    "gradient_clip": 12.0,
    "purpose": "baseline",
}


def _json_config(config: dict) -> dict:
    """Normalize tuple/list representation through the exact current config schema."""
    return json.loads(json.dumps(dataclasses.asdict(TorchConfig(**config))))


def plan_ablation(
    *,
    source_root: Path,
    campaign_dir: Path,
    reference_campaign: Path,
    python: Path,
    cache_root: Path,
    gpus: list[str],
    reference_run_id: str = "dynunet-seed0",
    seeds: list[int] | None = None,
) -> dict:
    seeds = [0] if seeds is None else seeds
    if (
        not seeds
        or len(set(seeds)) != len(seeds)
        or any(type(seed) is not int or not 0 <= seed < 2**32 for seed in seeds)
    ):
        raise ValueError("seeds must be nonempty unique uint32 integers")
    source_root = source_root.expanduser().resolve()
    campaign_dir = campaign_dir.expanduser().resolve()
    reference_campaign = reference_campaign.expanduser().resolve()
    cache_root = cache_root.expanduser().resolve()
    if campaign_dir.exists() or campaign_dir.is_symlink():
        raise FileExistsError("Campaign output must not already exist")
    if any(path.is_relative_to(source_root) for path in (campaign_dir, cache_root)):
        raise ValueError("Campaign and cache must be outside the clean source checkout")
    if campaign_dir.is_relative_to(reference_campaign.parent):
        raise ValueError("Ablation output must be outside the immutable reference campaign")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", campaign_dir.name):
        raise ValueError("Campaign identifier must be filesystem safe")
    if (
        not gpus
        or len(set(gpus)) != len(gpus)
        or any(not re.fullmatch(r"0|[1-9][0-9]*", gpu) for gpu in gpus)
    ):
        raise ValueError("gpus must be unique physical numeric GPU strings")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited is not None and not set(gpus).issubset(inherited.split(",")):
        raise ValueError("Campaign GPUs exceed inherited CUDA_VISIBLE_DEVICES")
    commit = _clean_source(source_root)
    harness = _interpreter(python)
    reference_hash = sha256_file(reference_campaign)
    reference = read_json(reference_campaign)
    # The historical campaign may have used other GPUs and other model recipes;
    # neither is an allocation request for this new bounded campaign.
    if reference.get("schema_version") != 1 or not re.fullmatch(
        r"[a-f0-9]{40}", str(reference.get("source_commit", ""))
    ):
        raise ValueError("Reference campaign must have a pinned source commit")
    for key in ("manifest", "splits"):
        absolute_path(reference.get(key), f"reference {key}")
    matches = [run for run in reference["runs"] if run["id"] == reference_run_id]
    if len(matches) != 1:
        raise ValueError("Reference campaign must contain the exact requested control run")
    reference_path = absolute_path(matches[0].get("config"), "reference recipe")
    reference_recipe_hash = sha256_file(reference_path)
    reference_binding_path = reference_campaign.parent / "state" / "campaign-binding.json"
    reference_binding_hash = sha256_file(reference_binding_path)
    reference_binding = read_json(reference_binding_path)
    if (
        reference_binding.get("spec_sha256") != reference_hash
        or reference_binding.get("recipes", {}).get(reference_run_id) != reference_recipe_hash
    ):
        raise ValueError("Reference recipe or campaign differs from its original runner binding")
    raw = load_recipe(reference_path)
    _reject_pretrained(raw)
    baseline = _json_config(raw)
    if any(baseline.get(key) != value for key, value in EXPECTED_CONTROL.items()):
        raise ValueError("Reference recipe differs from the declared original DynUNet control")
    for field in ("center_probabilities", "class_center_weights"):
        if baseline.get(field) is not None:
            raise ValueError("Reference control must retain the original foreground sampler")
    if any(
        baseline.get(field, 0) != 0
        for field in ("rotation_probability", "intensity_scale_probability")
    ):
        raise ValueError("Reference control must retain flips-only augmentation")
    manifest, splits = Path(reference["manifest"]), Path(reference["splits"])
    input_hashes = {"manifest": sha256_file(manifest), "splits": sha256_file(splits)}
    metadata = load_manifest(manifest, verify_files=False)
    split_record = json.loads(splits.read_text())
    validate_splits(metadata, split_record)
    counts = {key: len(split_record.get(key, [])) for key in ("train", "val", "test")}
    if counts != {"train": 197, "val": 42, "test": 42}:
        raise ValueError("Use the original Task07 197/42/42 train/validation/reserved-test split")
    for key in ("manifest", "splits"):
        if (
            reference.get("protocol", {}).get(f"{key}_sha256") != input_hashes[key]
            or reference_binding.get(f"{key}_sha256") != input_hashes[key]
        ):
            raise ValueError("Reference manifest or split no longer matches its frozen hash")
    lookup = {case["case_id"]: case for case in metadata["cases"]}
    for identifier in split_record["train"] + split_record["val"]:
        case = lookup[identifier]
        if case["annotation_status"] != "labeled" or not case.get("label"):
            raise ValueError("Training and validation require complete pancreas/mass labels")

    recipes, runs, declarations = {}, [], {}
    for seed in seeds:
        for arm, (description, changes) in ARMS.items():
            identifier = f"dynunet-{arm}-seed{seed}"
            config = _json_config(
                {
                    **baseline,
                    **changes,
                    "seed": seed,
                    "workspace": str(campaign_dir / "runs" / identifier),
                    "backend_python": harness,
                    "cache_root": str(cache_root),
                    "gpu": gpus[0],
                }
            )
            recipes[identifier] = config
            runs.append(
                {
                    "id": identifier,
                    "config": str(campaign_dir / "recipes" / f"{identifier}.json"),
                    "model": "dynunet",
                    "backend": "torch",
                    "workspace": config["workspace"],
                    "comparison_group": GROUP.replace("seed0", f"seed{seed}"),
                    "description": description,
                }
            )
            declarations[identifier] = {
                "arm": arm,
                "control_run_id": f"dynunet-control-seed{seed}",
                "description": description,
                "changes_from_control": changes,
                "scientific_recipe_sha256": recipe_fingerprint(config),
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
        "description": "Six fresh scratch DynUNet recipe variants per declared seed; validation-only fixed-budget ingredient screen.",
        "protocol": {
            "preset": "task07_dynunet_recipe_ablation_v1",
            "manifest_sha256": input_hashes["manifest"],
            "splits_sha256": input_hashes["splits"],
            "manifest_fingerprint": metadata["fingerprint"],
            "splits_fingerprint": split_record["fingerprint"],
            "partition_counts": counts,
            "grouping_status": metadata.get("grouping_status", "unspecified"),
            "recipe_ablation": {
                "schema_version": 1,
                "model": "dynunet",
                "comparison_groups": {
                    str(seed): GROUP.replace("seed0", f"seed{seed}") for seed in seeds
                },
                "control_run_id": f"dynunet-control-seed{seeds[0]}",
                "seeds": seeds,
                "reference_campaign_sha256": reference_hash,
                "reference_recipe_sha256": reference_recipe_hash,
                "reference_binding_sha256": reference_binding_hash,
                "reference_source_commit": reference["source_commit"],
                "reference_run_id": reference_run_id,
                "arms": declarations,
            },
            "optimizer_steps_per_arm": 10000,
            "sampled_patches_per_arm": 80000,
            "validation_epochs": [1, *range(10, 101, 10)],
            "checkpoint_selection": "highest mean native per-case mass Dice on validation",
            "checkpoint_retention": "latest and selected best; unindexed intermediate generations pruned atomically",
            "resume": "Own latest checkpoint with optimizer/scheduler/scaler/RNG; never import historical weights",
            "dashboard_cleanup": "Normal runner owns dashboard panes and closes only unchanged owned panes after all runs complete",
            "limitations": [
                "Fixed starting budget and declared seeds; not convergence or a paper reproduction",
                "Control uses current frozen source; historical source differs and deterministic algorithms are disabled",
                "Class111 versus class115 isolates weights; exact-background sampling differs from uniform-volume sampling",
                "Requested crop centers are not equivalent to observed tumor-containing crop frequency",
                "Augmentation changes the RNG stream and adds compute; equal updates are not equal GPU-hours",
                "Original validation frequency includes epoch 1 (100 updates), then every 1000 and final",
                "Reserved test is not opened or scored; mass labels are not verified malignancy diagnoses",
                "42 positive validation examinations cannot estimate specificity or patient ROC AUC",
            ],
        },
        "runs": runs,
        "evaluation": dict(reference.get("evaluation", {})),
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
            shutil.copyfile(reference_path, staging / f"reference-recipe{reference_path.suffix}")
            atomic_write_json(staging / "campaign.json", spec)
            # Validate with the pinned runner, not a second permissive schema.
            module_spec = importlib.util.spec_from_file_location(
                "recipe_ablation_runner", source_root / "scripts/run_medical_campaign.py"
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
            if _clean_source(source_root) != commit:
                raise ValueError("Source changed while planning")
            if (
                sha256_file(reference_campaign) != reference_hash
                or sha256_file(reference_path) != reference_recipe_hash
                or sha256_file(reference_binding_path) != reference_binding_hash
                or sha256_file(manifest) != input_hashes["manifest"]
                or sha256_file(splits) != input_hashes["splits"]
            ):
                raise ValueError("Frozen reference inputs changed while planning")
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
    for name in ("source-root", "campaign-dir", "reference-campaign", "python", "cache-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--reference-run-id", default="dynunet-seed0")
    parser.add_argument("--gpus", nargs="+", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    args = parser.parse_args()
    spec = plan_ablation(**vars(args))
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
