#!/usr/bin/env python3
"""Audit resampling and crop composition using the training partition only.

No network is built and no optimizer is run. Selected arms must share preprocessing.
Published output uses training ordinals, never source scan IDs or file paths.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import inspect
import json
import math
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from nibabel.processing import resample_from_to
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from segmentary.medical.cli import _config
from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.followup import validate_declared_followup
from segmentary.medical.geometry import sha256_file, validate_nifti
from segmentary.medical.recipe_ablation import validate_declared_recipes
from segmentary.medical.torch_cache import build_cached_case, load_cached_case
from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import sample_patch


def execution_provenance(campaign: dict, arms: list[tuple[str, TorchConfig]]) -> dict:
    """Bind the actual audit process to the planned clean source and interpreter."""
    root = Path(__file__).resolve().parents[1]
    if Path(campaign["source_root"]).resolve() != root:
        raise ValueError("Audit must execute from the campaign source checkout")
    if (
        Path(inspect.getfile(sample_patch)).resolve()
        != root / "src/segmentary/medical/torch_data.py"
    ):
        raise ValueError("Audit sampler was imported from another source checkout")
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True
    ).strip()
    if status or commit != campaign["source_commit"]:
        raise ValueError("Audit requires the clean campaign source commit")
    # Preserve virtual-environment symlinks; resolving them selects base Python.
    if any(
        Path(config.backend_python).absolute() != Path(sys.executable).absolute()
        for _, config in arms
    ):
        raise ValueError("Audit must execute with every arm's configured Python runtime")
    packages = dict(
        sorted(
            (distribution.metadata["Name"], distribution.version)
            for distribution in importlib.metadata.distributions()
            if "Name" in distribution.metadata
        )
    )
    return {
        "source_commit": commit,
        "source_clean": True,
        "medical_source_sha256": {
            str(path.relative_to(root)): sha256_file(path)
            for path in sorted((root / "src/segmentary/medical").rglob("*.py"))
        },
        "python": sys.version,
        "packages": packages,
        "configured_interpreter_matches": True,
    }


def training_cases(manifest: dict, splits: dict) -> list[dict]:
    """Resolve metadata without accessing validation/test image or label files."""
    validate_splits(manifest, splits)
    lookup = {case["case_id"]: case for case in manifest["cases"]}
    cases = [lookup[key] for key in sorted(splits["train"])]
    if not cases or any(
        case["annotation_status"] != "labeled" or not case.get("label") for case in cases
    ):
        raise ValueError("Input auditing requires a nonempty fully labeled training partition")
    return cases


def mass_resampling(case: dict, data: dict) -> dict:
    """Track each native 26-connected mass component through label resampling.

    A component is a voxel-connectivity proxy, not a confirmed distinct tumor.
    IDs are resampled with exactly the label interpolation (nearest neighbor).
    """
    path = Path(case["label"])
    if sha256_file(path) != case["label_sha256"]:
        raise ValueError("Training reference changed since dataset audit")
    validate_nifti(path, is_label=True, allowed_labels=(0, 1, 2))
    reference: Any = nib.load(path)
    native_mass = np.asarray(reference.dataobj) == 2
    components, count = ndimage.label(native_mass, structure=np.ones((3, 3, 3)))
    native_counts = np.bincount(components.ravel(), minlength=count + 1)[1:]
    target_shape = tuple(reversed(data["label"].shape))
    component_image = nib.Nifti1Image(components.astype(np.int32), reference.affine)
    mapped = resample_from_to(component_image, (target_shape, data["affine"]), order=0, cval=0)
    mapped_ids = np.asarray(mapped.dataobj, dtype=np.int32)
    resampled_mass = np.asarray(data["label"]).transpose(2, 1, 0) == 2
    if not np.array_equal(mapped_ids > 0, resampled_mass):
        raise ValueError("Cached mass mask differs from independently resampled native labels")
    sampled_counts = np.bincount(mapped_ids.ravel(), minlength=count + 1)[1:]
    _, sampled_component_count = ndimage.label(resampled_mass, structure=np.ones((3, 3, 3)))
    native_voxel_mm3 = abs(float(np.linalg.det(reference.affine[:3, :3])))
    sampled_voxel_mm3 = abs(float(np.linalg.det(data["affine"][:3, :3])))
    native_volume = int(native_mass.sum()) * native_voxel_mm3
    sampled_volume = int(resampled_mass.sum()) * sampled_voxel_mm3
    return {
        "native_mass_voxels": int(native_mass.sum()),
        "resampled_mass_voxels": int(resampled_mass.sum()),
        "native_mass_mm3": native_volume,
        "resampled_mass_mm3": sampled_volume,
        "resampled_to_native_mass_volume_ratio": sampled_volume / native_volume
        if native_volume
        else None,
        "native_components": int(count),
        "resampled_components": int(sampled_component_count),
        "vanished_native_components": int(np.count_nonzero(sampled_counts == 0)),
        "native_component_mm3": (native_counts * native_voxel_mm3).tolist(),
        "native_component_resampled_mm3": (sampled_counts * sampled_voxel_mm3).tolist(),
    }


def crop_summary(data: dict, config: TorchConfig, samples: int, seed: int) -> dict:
    if samples < 1:
        raise ValueError("samples must be positive")
    rng = np.random.default_rng(seed)
    requested: Counter[str] = Counter()
    selected: Counter[str] = Counter()
    composition: Counter[str] = Counter()
    counts = np.zeros(3, dtype=np.int64)
    padding = fallbacks = rotations = intensity_scales = 0
    auxiliary_mass_losses: Counter[str] = Counter()
    fractions = []
    started = time.perf_counter()
    for _ in range(samples):
        diagnostic: dict[str, Any] = {}
        images, labels = sample_patch(data, config, rng, diagnostics=diagnostic)
        if not np.isfinite(images).all() or not set(np.unique(labels)) <= {0, 1, 2}:
            raise ValueError("Sampling produced nonfinite images or invalid target classes")
        if config.model_options.get("deep_supervision", False):
            for scale in (2, 4):
                # Aligned 2x/4x nearest-neighbor target reduction used by the model.
                coarse = labels[::scale, ::scale, ::scale]
                auxiliary_mass_losses[f"scale_{scale}_positive_patches"] += int(np.any(labels == 2))
                auxiliary_mass_losses[f"scale_{scale}_mass_vanished_patches"] += int(
                    np.any(labels == 2) and not np.any(coarse == 2)
                )
        voxels = np.bincount(labels.ravel(), minlength=3)
        counts += voxels
        composition["mass_present" if voxels[2] else "pancreas_only" if voxels[1] else "empty"] += 1
        requested[str(diagnostic["requested_center_branch"])] += 1
        selected[str(diagnostic["selected_center_branch"])] += 1
        padding += int(diagnostic["crop_padding_voxels"])
        fallbacks += int(bool(diagnostic["center_fallback"]))
        rotations += int(diagnostic["rotation_applied"])
        intensity_scales += int(diagnostic["intensity_scale_applied"])
        fractions.append(float(voxels[2] / labels.size))
    return {
        "auxiliary_target_audit": dict(auxiliary_mass_losses),
        "samples": samples,
        "seed": seed,
        "requested_centers": dict(requested),
        "selected_centers": dict(selected),
        "crop_composition": dict(composition),
        "final_label_voxels": {str(i): int(n) for i, n in enumerate(counts)},
        "mean_mass_voxel_fraction": float(np.mean(fractions)),
        "crop_padding_voxels_before_augmentation": padding,
        "center_fallbacks": fallbacks,
        "rotation_applied": rotations,
        "intensity_scale_applied": intensity_scales,
        "wall_seconds": time.perf_counter() - started,
    }


def _aggregate_crops(rows: list[dict], patch_voxels: int) -> dict:
    result: dict[str, Any] = {}
    for key in (
        "requested_centers",
        "selected_centers",
        "crop_composition",
        "final_label_voxels",
        "auxiliary_target_audit",
    ):
        counter: Counter[str] = Counter()
        for row in rows:
            counter.update(row.get(key, {}))
        result[key] = dict(counter)
    for key in (
        "samples",
        "crop_padding_voxels_before_augmentation",
        "center_fallbacks",
        "rotation_applied",
        "intensity_scale_applied",
        "wall_seconds",
    ):
        result[key] = sum(row[key] for row in rows)
    result["mass_containing_patch_fraction"] = (
        result["crop_composition"].get("mass_present", 0) / result["samples"]
    )
    result["mean_mass_voxel_fraction"] = result["final_label_voxels"].get("2", 0) / (
        result["samples"] * patch_voxels
    )
    return result


def audit(
    campaign_path: Path,
    output: Path,
    *,
    samples_per_case: int = 8,
    seed: int = 20260914,
    run_ids: list[str] | None = None,
) -> dict:
    if type(samples_per_case) is not int or samples_per_case < 1:
        raise ValueError("samples_per_case must be positive")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be uint32")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Use a fresh audit output directory")
    campaign = json.loads(campaign_path.read_text())
    manifest_path, splits_path = Path(campaign["manifest"]), Path(campaign["splits"])
    protocol = campaign.get("protocol", {})
    if (
        protocol.get("recipe_ablation") is not None
        or protocol.get("followup_experiments") is not None
        or protocol.get("preset")
        in {
            "task07_dynunet_recipe_ablation_v1",
            "task07_dynunet_followup_v1",
            "task07_dynunet_deep_supervision_v1",
            "task07_recipe_explorations_v1",
            "task07_predicted_roi_cascade_v1",
        }
    ):
        for key, path in (("manifest", manifest_path), ("splits", splits_path)):
            if protocol.get(f"{key}_sha256") != sha256_file(path):
                raise ValueError(f"Frozen campaign {key} changed after planning")
    manifest = load_manifest(manifest_path, verify_files=False)
    splits = json.loads(splits_path.read_text())
    cases = training_cases(manifest, splits)
    arms = [(run["id"], _config(Path(run["config"]))) for run in campaign["runs"]]
    if not arms or len({name for name, _ in arms}) != len(arms):
        raise ValueError("Audit requires unique explicit arm IDs")
    recipes = {arm: json.loads(json.dumps(dataclasses.asdict(config))) for arm, config in arms}
    validate_declared_recipes(campaign, recipes)
    validate_declared_followup(campaign, recipes)
    if run_ids is not None:
        if not run_ids or len(set(run_ids)) != len(run_ids) or set(run_ids) - set(recipes):
            raise ValueError("Audit run IDs must be nonempty, unique and present in the campaign")
        arms = [(arm, config) for arm, config in arms if arm in run_ids]
    base = arms[0][1]
    if any(not isinstance(config, TorchConfig) for _, config in arms) or base.cache_root is None:
        raise ValueError("Audit requires Torch recipes with an explicit shared cache")

    def geometry(c: TorchConfig) -> tuple:
        return (
            c.spacing_mm,
            c.hu_window,
            c.normalization,
            c.roi_manifest_sha256,
            c.patch_size,
            c.mode,
            c.context_slices,
            c.cache_root,
        )

    if any(geometry(config) != geometry(base) for _, config in arms):
        raise ValueError("Audit arms must share preprocessing, patch geometry and cache")
    provenance = execution_provenance(campaign, arms)
    hashes = {str(path): sha256_file(path) for path in [campaign_path, manifest_path, splits_path]}
    hashes.update({run["config"]: sha256_file(run["config"]) for run in campaign["runs"]})
    output.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    started = time.perf_counter()
    for ordinal, case in enumerate(cases, 1):
        record = build_cached_case(case, base, base.cache_root)
        data = load_cached_case(record)
        row: dict[str, Any] = {
            "training_ordinal": ordinal,
            "resampling": mass_resampling(case, data),
            "arms": {},
        }
        # Equal per-case coverage, independent RNG streams across cases. Each
        # arm starts with the same case seed; added transforms may consume RNG.
        case_seed = int(np.random.SeedSequence([seed, ordinal]).generate_state(1)[0])
        for arm, config in arms:
            row["arms"][arm] = crop_summary(data, config, samples_per_case, case_seed)
        records.append(row)
        atomic_write_json(output / "cases" / f"{ordinal:04d}.json", row)
        print(
            json.dumps({"training_cases_complete": ordinal, "training_cases_total": len(cases)}),
            flush=True,
        )
        del data
    if any(sha256_file(path) != digest for path, digest in hashes.items()):
        raise ValueError("Audit configuration or source metadata changed during execution")
    if execution_provenance(campaign, arms) != provenance:
        raise ValueError("Audit source or runtime changed during execution")
    sampling_fields = {field.name for field in dataclasses.fields(TorchConfig)} - {
        "workspace",
        "backend_python",
        "cache_root",
        "gpu",
    }
    ratios = [row["resampling"]["resampled_to_native_mass_volume_ratio"] for row in records]
    ratios = [ratio for ratio in ratios if ratio is not None]
    result = {
        "schema_version": 1,
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "campaign_id": campaign["campaign_id"],
        "source_commit": campaign["source_commit"],
        "execution": provenance,
        "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "manifest_fingerprint": manifest["fingerprint"],
        "split_fingerprint": splits["fingerprint"],
        "partition": "train",
        "training_cases": len(records),
        "samples_per_case_per_arm": samples_per_case,
        "seed": seed,
        "sampling_scope": "Equal per-case diagnostic coverage; not live optimizer sampling telemetry",
        "component_definition": "26-connected label-2 components; not independently annotated lesions",
        "resampling": {
            "native_mass_positive_cases": sum(
                row["resampling"]["native_mass_voxels"] > 0 for row in records
            ),
            "mass_positive_cases_lost": sum(
                row["resampling"]["native_mass_voxels"] > 0
                and row["resampling"]["resampled_mass_voxels"] == 0
                for row in records
            ),
            "native_components": sum(row["resampling"]["native_components"] for row in records),
            "vanished_native_components": sum(
                row["resampling"]["vanished_native_components"] for row in records
            ),
            "volume_ratio_min_median_max": [
                float(np.min(ratios)),
                float(np.median(ratios)),
                float(np.max(ratios)),
            ]
            if ratios
            else None,
        },
        "arms": {
            arm: {
                "recipe": {
                    key: value
                    for key, value in dataclasses.asdict(config).items()
                    if key in sampling_fields
                },
                "crop_statistics": _aggregate_crops(
                    [row["arms"][arm] for row in records], math.prod(config.patch_size)
                ),
            }
            for arm, config in arms
        },
        "wall_seconds": time.perf_counter() - started,
        "evaluation_files_opened": 0,
        "limitations": "Training-only diagnostic; no quality estimate or guarantee of clinically complete annotations. Padding count precedes added rotation.",
    }
    atomic_write_json(output / "report.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples-per-case", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260914)
    parser.add_argument("--run-ids", nargs="+", help="Audit one compatible geometry subset")
    args = parser.parse_args()
    audit(
        args.campaign,
        args.output,
        samples_per_case=args.samples_per_case,
        seed=args.seed,
        run_ids=args.run_ids,
    )


if __name__ == "__main__":
    main()
