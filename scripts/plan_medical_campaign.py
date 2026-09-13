#!/usr/bin/env python3
"""Freeze the declared 28-arm scratch CT comparison; never launch training.

Fixed preset: all 27 versioned Torch architectures, standard capacity, seed 0,
100 epochs x 100 updates, batch 8, bf16, AdamW 3e-4 / weight decay 1e-5.
2D architectures receive five same-examination slices and 256x256 patches;
3D architectures receive 96x96x96 patches. Shared RAS spacing is 1.5/1.5/2.5mm,
HU window -100..240, native validation at epoch1/every10/final, inference batch8.
Official nnU-Net ResEnc L keeps its separate 2.8.1 baseline protocol (normally
1000 epochs x 250 updates); its planner/optimizer/loss/budget are not matched.

The output directory must not exist and must be outside the clean source tree.
Source model options are preserved, except the explicitly chosen Mamba scan
backend and pure-mixer activation checkpointing enabled for all three Mamba
architectures. All Torch arms enable ordered CPU batch prefetch. Native kernels
must already be verified in the harness environment;
this planner does not install packages, allocate GPUs, or inspect test payloads.
"""

from __future__ import annotations

import argparse
import dataclasses
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
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from segmentary.medical.backend import NNUNetConfig, _lock
from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.geometry import sha256_file
from segmentary.medical.torch_config import TorchConfig

# Heavy/long volumetric jobs go first; the remaining GPUs take the explicit
# queue as jobs complete. Ordering is a scheduling heuristic, not a speed claim.
TORCH_ORDER = (
    "umamba_enc",
    "segmamba",
    "umamba_bot",
    "swin_unetr",
    "unetr",
    "transunet_3d",
    "medformer",
    "mednext_v1",
    "dynunet",
    "segresnet",
    "unet_3d",
    "mask2former",
    "maskformer",
    "dpt",
    "swin_upernet",
    "convnext_upernet",
    "segformer_b2",
    "hrnet_ocr",
    "unet_plus_plus",
    "deeplabv3_plus",
    "fpn",
    "unet_2d",
    "segformer_b0",
    "pidnet",
    "ddrnet",
    "bisenetv2",
    "lraspp",
)
MAMBA = {"umamba_bot", "umamba_enc", "segmamba"}
COMMON_GROUP = "torch_common_scratch_seed0_10000_steps"
NNUNET_GROUP = "nnunet_official_resenc_l_seed0"


def _clean_source(root: Path) -> str:
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True
    ).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or status:
        raise ValueError("source-root must be a clean checkout with a full pinned Git commit")
    return commit


def _interpreter(path: Path) -> str:
    # Resolving a venv's python symlink can silently select the base interpreter.
    path = path.expanduser().absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"Interpreter must exist and be executable: {path}")
    return str(path)


def _reject_pretrained(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "pretrained",
                "weights",
                "encoder_weights",
                "checkpoint",
                "pretrained_path",
                "weights_path",
            } and item not in (None, False):
                raise ValueError("Campaign source recipes must not request pretrained weights")
            if key == "initialization" and item != "scratch":
                raise ValueError("Campaign source recipes must require scratch initialization")
            _reject_pretrained(item)
    elif isinstance(value, list):
        for item in value:
            _reject_pretrained(item)


def plan_campaign(
    *,
    source_root: Path,
    campaign_dir: Path,
    python: Path,
    nnunet_python: Path,
    manifest: Path,
    splits: Path,
    cache_root: Path,
    gpus: list[str],
    scan_backend: str = "native",
) -> dict:
    source_root = source_root.expanduser().resolve()
    campaign_dir = campaign_dir.expanduser().resolve()
    cache_root = cache_root.expanduser().resolve()
    manifest, splits = manifest.expanduser().resolve(), splits.expanduser().resolve()
    if campaign_dir.exists() or campaign_dir.is_symlink():
        raise FileExistsError("Campaign output must not already exist")
    if campaign_dir.is_relative_to(source_root) or cache_root.is_relative_to(source_root):
        raise ValueError(
            "Campaign and cache directories must stay outside the clean source checkout"
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", campaign_dir.name):
        raise ValueError("Campaign directory name must be a filesystem-safe campaign identifier")
    if scan_backend not in {"native", "torch"}:
        raise ValueError("scan_backend must explicitly be native or torch")
    if (
        not gpus
        or len(gpus) != len(set(gpus))
        or any(not re.fullmatch(r"0|[1-9][0-9]*", gpu) for gpu in gpus)
    ):
        raise ValueError("gpus must be unique physical numeric GPU strings")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited is not None and not set(gpus).issubset(inherited.split(",")):
        raise ValueError("Campaign GPUs exceed inherited CUDA_VISIBLE_DEVICES")
    commit = _clean_source(source_root)
    harness, official = _interpreter(python), _interpreter(nnunet_python)
    input_hashes = {"manifest": sha256_file(manifest), "splits": sha256_file(splits)}
    metadata = load_manifest(manifest, verify_files=False)
    split_record = json.loads(splits.read_text())
    validate_splits(metadata, split_record)
    if any(not split_record.get(partition) for partition in ("train", "val", "test")):
        raise ValueError(
            "A campaign requires nonempty train/val partitions and a reserved test partition"
        )
    lookup = {case["case_id"]: case for case in metadata["cases"]}
    for key in split_record["train"] + split_record["val"]:
        if lookup[key]["annotation_status"] != "labeled" or not lookup[key].get("label"):
            raise ValueError("Training and validation require full pancreas and mass annotations")
    preset_root = source_root / "configs" / "medical" / "torch"
    presets = {path.stem: path for path in preset_root.glob("*.yaml")}
    if set(presets) != set(TORCH_ORDER):
        raise ValueError("Source must contain exactly the declared 27 standard Torch model recipes")
    recipes: dict[str, dict] = {}
    base_hashes = {}
    for name in TORCH_ORDER:
        raw = yaml.safe_load(presets[name].read_text())
        if not isinstance(raw, dict) or raw.get("model") != name or raw.get("backend") != "torch":
            raise ValueError(f"Source recipe does not match its architecture: {name}")
        _reject_pretrained(raw)
        if raw.get("initialization") != "scratch" or raw.get("mode") not in {"2d", "3d"}:
            raise ValueError(
                "Source preset must declare scratch initialization and a supported dimension"
            )
        is_volume = raw["mode"] == "3d"
        options = dict(raw.get("model_options", {}))
        if name in MAMBA:
            options["scan_backend"] = scan_backend
            options["checkpoint_mamba"] = True
        resolved = TorchConfig(
            **{
                **raw,
                "workspace": str(campaign_dir / "runs" / f"{name}-seed0"),
                "backend_python": harness,
                "gpu": gpus[0],
                "mode": "3d" if is_volume else "2.5d",
                "context_slices": 1 if is_volume else 5,
                "patch_size": (96, 96, 96) if is_volume else (256, 256),
                "spacing_mm": (1.5, 1.5, 2.5),
                "hu_window": (-100.0, 240.0),
                "model_options": options,
                "batch_size": 8,
                "precision": "bf16",
                "workers": 4,
                "seed": 0,
                "epochs": 100,
                "steps_per_epoch": 100,
                "learning_rate": 3e-4,
                "weight_decay": 1e-5,
                "validation_interval": 10,
                "inference_batch_size": 8,
                "progress_interval": 10,
                "cache_root": str(cache_root),
                "prefetch_batches": True,
                "foreground_probability": 0.5,
                "overlap": 0.5,
                "deterministic": False,
                "augment": True,
                "gradient_clip": 12.0,
                "purpose": "baseline",
            }
        )
        recipes[name] = dataclasses.asdict(resolved)
        base_hashes[name] = sha256_file(presets[name])
    official_model = "nnunet_resenc_l"
    official_config = NNUNetConfig(
        workspace=str(campaign_dir / "runs" / f"{official_model}-seed0"),
        backend_python=official,
        resenc="L",
        dataset_id=707,
        workers=4,
        seed=0,
        gpu=gpus[0],
        purpose="baseline",
    )
    recipes[official_model] = {"backend": "nnunet", **dataclasses.asdict(official_config)}
    spec: dict[str, Any] = {
        "schema_version": 1,
        "campaign_id": campaign_dir.name,
        "source_root": str(source_root),
        "source_commit": commit,
        "python": harness,
        "manifest": str(manifest),
        "splits": str(splits),
        "gpus": gpus,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "description": "All 27 standard scratch Torch architectures plus a separate official nnU-Net ResEnc L comparator. Validation ranks candidates; the reserved test is never used by the campaign runner.",
        "protocol": {
            "preset": "task07_all_architectures_scratch_v1",
            "torch": {
                "optimizer_steps": 10000,
                "batch_size": 8,
                "sampled_patches": 80000,
                "precision": "bf16",
                "seed": 0,
                "mode_2d": "2.5d: five adjacent slices",
                "patch_2d_yx": [256, 256],
                "patch_3d_zyx": [96, 96, 96],
                "spacing_ras_xyz_mm": [1.5, 1.5, 2.5],
                "hu_window": [-100, 240],
                "optimizer": "AdamW",
                "learning_rate": 3e-4,
                "weight_decay": 1e-5,
                "validation_epochs": "1,10,20,30,40,50,60,70,80,90,100",
                "checkpoint_selection": "highest mean native per-case mass Dice on validation",
                "augmentation": "spatial flips",
                "mamba_scan_backend": scan_backend,
                "prefetch_batches": True,
                "mamba_activation_checkpointing": "all three Mamba arms recompute only pure SSM mixers with non-reentrant checkpointing; same weights and effective batch",
                "native_kernel_runtime_verified_by_planner": False,
            },
            "nnunet": {
                "version": "2.8.1",
                "resenc": "L",
                "expected_default_epochs": 1000,
                "expected_default_updates_per_epoch": 250,
                "runtime_overrides": None,
                "planning_cohort": "train and validation; reserved test excluded",
                "comparison": "separate official protocol, not matched optimizer/objective/compute",
            },
            "manifest_sha256": input_hashes["manifest"],
            "splits_sha256": input_hashes["splits"],
            "manifest_fingerprint": metadata["fingerprint"],
            "splits_fingerprint": split_record["fingerprint"],
            "partition_counts": {key: len(split_record[key]) for key in ("train", "val", "test")},
            "grouping_status": metadata.get("grouping_status", "unspecified"),
            "source_recipe_sha256": base_hashes,
            "limitations": [
                "Single seed, fixed starting budgets; not evidence of convergence or a paper reproduction",
                "2.5D and 3D consume different context and compute; native model objectives also differ",
                "Task07 mass masks are not a verified malignancy diagnosis",
                "Dataset case grouping may not establish verified patient identity",
                "No pretrained weights or test scoring; no automatic recipe downsizing after failures",
            ],
        },
        "runs": [
            {
                "id": f"{name}-seed0",
                "config": str(campaign_dir / "recipes" / f"{name}.json"),
                "model": name,
                "backend": recipes[name]["backend"],
                "workspace": recipes[name]["workspace"],
                "comparison_group": NNUNET_GROUP if name == official_model else COMMON_GROUP,
            }
            for name in (official_model, *TORCH_ORDER)
        ],
        "evaluation": {
            "bootstrap_samples": 1000,
            "seed": 0,
            "surface_tolerance_mm": 2.0,
            "review_overlays": False,
        },
    }
    # All input checks and recipe construction precede any output publication.
    campaign_dir.parent.mkdir(parents=True, exist_ok=True)
    with _lock(campaign_dir.parent / f".{campaign_dir.name}.planning.lock"):
        if campaign_dir.exists() or campaign_dir.is_symlink():
            raise FileExistsError("Campaign output appeared while planning")
        staging = Path(
            tempfile.mkdtemp(prefix=f".{campaign_dir.name}.building-", dir=campaign_dir.parent)
        )
        try:
            for name, recipe in recipes.items():
                atomic_write_json(staging / "recipes" / f"{name}.json", recipe)
            atomic_write_json(staging / "campaign.json", spec)
            # Validate the runner's exact schema before publishing. Only recipe
            # read paths temporarily refer to staging; run workspaces stay final.
            runner_path = source_root / "scripts" / "run_medical_campaign.py"
            module_spec = importlib.util.spec_from_file_location(
                "planned_medical_runner", runner_path
            )
            if module_spec is None or module_spec.loader is None:
                raise ValueError("Pinned source has no loadable medical campaign runner")
            runner = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(runner)
            validation_spec = {
                **spec,
                "runs": [
                    {**run, "config": str(staging / "recipes" / Path(run["config"]).name)}
                    for run in spec["runs"]
                ],
            }
            atomic_write_json(staging / "schema-check.json", validation_spec)
            runner.load_spec(staging / "schema-check.json")
            (staging / "schema-check.json").unlink()
            if _clean_source(source_root) != commit:
                raise ValueError("Source commit changed while building campaign")
            if (
                sha256_file(manifest) != input_hashes["manifest"]
                or sha256_file(splits) != input_hashes["splits"]
            ):
                raise ValueError("Manifest or split content changed while building campaign")
            if campaign_dir.exists() or campaign_dir.is_symlink():
                raise FileExistsError("Campaign output appeared before publication")
            staging.rename(campaign_dir)
            directory_fd = os.open(campaign_dir.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    for name in (
        "source-root",
        "campaign-dir",
        "python",
        "nnunet-python",
        "manifest",
        "splits",
        "cache-root",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--gpus", nargs="+", required=True)
    parser.add_argument("--scan-backend", choices=("native", "torch"), default="native")
    args = parser.parse_args()
    spec = plan_campaign(**vars(args))
    print(
        json.dumps(
            {
                "campaign": str(args.campaign_dir.expanduser().resolve() / "campaign.json"),
                "source_commit": spec["source_commit"],
                "runs": len(spec["runs"]),
                "gpus": spec["gpus"],
                "status": "planned; nothing launched",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
