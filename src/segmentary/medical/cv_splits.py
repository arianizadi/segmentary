"""Deterministic development cross-validation that keeps the frozen split intact.

Fold 0 is exactly the frozen train/validation partition, in its original order.
The frozen training cases are divided into folds 1..k-1 by connected
patient/duplicate group. When every training case records label voxel counts
and spacing, groups are stratified by annotated lesion volume (the manifest
ontology's lesion: Task07 mass, LiTS/KiTS23 tumor, all label 2); otherwise a
seeded shuffle is used. Held-out test cases never enter any fold. The artifact is
written once and never replaces an existing file, including the frozen split.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

from .data import (
    _group_assignments,
    atomic_write_json,
    fingerprint,
    lesion_stratification,
    lesion_volume_ml,
    load_manifest,
    validate_splits,
)
from .dataset_profiles import PANCREAS, DatasetProfile, profile_for_ontology
from .geometry import MedicalDataError, sha256_file

SCHEMA = "segmentary.medical.development_cv"
DEFAULT_FOLDS = 5
MAX_FOLDS = 20


def _mass_ml(case: dict[str, Any]) -> float | None:
    """Task07 mass volume exactly as before transfer datasets: no label 2 count is ``None``.

    Kept byte-for-byte so a pancreas/mass manifest with mass-free training cases
    (PanTS-style) still falls back to the seeded shuffle and reproduces its CV.
    """
    counts, spacing = case.get("label_counts"), case.get("spacing_mm")
    if not isinstance(counts, dict) or not isinstance(spacing, list) or len(spacing) != 3:
        return None
    voxels = counts.get("2", counts.get(2))
    if isinstance(voxels, bool) or not isinstance(voxels, int) or voxels < 0:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in spacing):
        return None
    return voxels * math.prod(float(value) for value in spacing) / 1000.0


def _lesion_ml(case: dict[str, Any], profile: DatasetProfile) -> float | None:
    """Annotated lesion volume, or ``None`` when the case lacks usable metadata.

    For LiTS and KiTS23, audited label counts list every present label, so a
    lesion label absent from them (a lesion-free case) has zero volume.
    Pancreas/mass manifests keep the original Task07 rule (``_mass_ml``).
    """
    if profile is PANCREAS:
        return _mass_ml(case)
    try:
        return lesion_volume_ml(case, profile.lesion_labels)
    except MedicalDataError:
        return None


def make_cv_splits(
    manifest_path: str | Path,
    splits_path: str | Path,
    output: str | Path,
    *,
    folds: int = DEFAULT_FOLDS,
    seed: int = 0,
) -> dict[str, Any]:
    """Write a new k-fold development manifest whose fold 0 is the frozen split."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite {output}")
    if type(folds) is not int or not 2 <= folds <= MAX_FOLDS:
        raise MedicalDataError(f"folds must be an integer in [2, {MAX_FOLDS}]")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise MedicalDataError("seed must be an integer in [0, 2**32)")
    splits_path = Path(splits_path).resolve()
    if output.resolve() == splits_path:
        raise FileExistsError("refusing to overwrite the frozen split")
    manifest = load_manifest(manifest_path, verify_files=False)
    splits = read_splits(splits_path)
    validate_splits(manifest, splits)
    cases = {case["case_id"]: case for case in manifest["cases"]}
    components = _group_assignments(cases, manifest.get("inherited_group_assignments"))
    groups: dict[str, list[str]] = {}
    for case_id in splits["train"]:
        groups.setdefault(components[case_id], []).append(case_id)
    if len(groups) < folds - 1:
        raise MedicalDataError("not enough training groups for the requested folds")
    # Only training-case metadata is consulted; held-out records are never scored.
    profile = profile_for_ontology(manifest["ontology"])
    volumes = {case_id: _lesion_ml(cases[case_id], profile) for case_id in splits["train"]}
    stratified = all(value is not None for value in volumes.values())
    rng = random.Random(seed)
    keys = sorted(groups)
    rng.shuffle(keys)
    if stratified:
        totals = {key: sum(volumes[c] or 0.0 for c in members) for key, members in groups.items()}
        # Stable sort: equal volumes keep the seeded shuffle order.
        keys.sort(key=lambda key: totals[key])
    assignment: dict[str, int] = {}
    labels = list(range(1, folds))
    for start in range(0, len(keys), len(labels)):
        block = keys[start : start + len(labels)]
        order = labels[:]
        rng.shuffle(order)
        assignment.update(zip(block, order, strict=False))
    development = splits["train"] + splits["val"]
    partitions = [{"fold": 0, "train": list(splits["train"]), "val": list(splits["val"])}]
    for fold in labels:
        val = sorted(
            c for key, members in groups.items() if assignment[key] == fold for c in members
        )
        held = set(val)
        partitions.append(
            {"fold": fold, "train": [c for c in development if c not in held], "val": val}
        )
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": 1,
        "manifest_fingerprint": manifest["fingerprint"],
        "base_splits_fingerprint": splits["fingerprint"],
        "base_splits_sha256": sha256_file(splits_path),
        "grouping_status": splits.get("grouping_status", manifest.get("grouping_status")),
        "seed": seed,
        "fold_count": folds,
        "fold_0": "exact frozen train/validation partition",
        "assignment": {
            "unit": "connected patient/duplicate group of frozen training cases",
            "method": "seeded_shuffle_blocks",
            "stratification_variable": None,
            **(lesion_stratification(profile) if stratified else {}),
            "held_out_test": "excluded from every fold; only its count is recorded",
        },
        "development_cases": len(development),
        "held_out_test_cases": len(splits["test"]),
        "folds": partitions,
    }
    document["fingerprint"] = fingerprint(document)
    validate_cv_splits(manifest, splits, document)
    atomic_write_json(output, document)
    return document


def read_splits(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise MedicalDataError("split document must be a JSON object")
    return value


def fold_splits(splits: dict[str, Any], cv: dict[str, Any], fold: int) -> dict[str, Any]:
    """A standard split document for one fold; the held-out test list is unchanged."""
    if type(fold) is not int or not 0 <= fold < len(cv.get("folds", [])):
        raise MedicalDataError(f"fold must be an integer in [0, {len(cv.get('folds', []))})")
    partition = cv["folds"][fold]
    derived = {key: value for key, value in splits.items() if key not in {"group_counts"}}
    derived.update(
        train=list(partition["train"]),
        val=list(partition["val"]),
        derived_from_cv={"fingerprint": cv["fingerprint"], "fold": fold},
    )
    derived["fingerprint"] = fingerprint(derived)
    return derived


def nnunet_splits(cv: dict[str, Any]) -> list[dict[str, list[str]]]:
    """nnU-Net ``splits_final.json`` content: one train/val entry per fold."""
    return [{"train": list(item["train"]), "val": list(item["val"])} for item in cv["folds"]]


def validate_cv_splits(
    manifest: dict[str, Any], splits: dict[str, Any], cv: dict[str, Any]
) -> None:
    """Reject any fold that alters fold 0, leaks groups or touches the held-out test."""
    if cv.get("schema") != SCHEMA or cv.get("schema_version") != 1:
        raise MedicalDataError("not a development cross-validation manifest")
    if cv.get("fingerprint") != fingerprint(cv):
        raise MedicalDataError("cross-validation fingerprint mismatch")
    if cv.get("manifest_fingerprint") != manifest["fingerprint"] or cv.get(
        "base_splits_fingerprint"
    ) != splits.get("fingerprint"):
        raise MedicalDataError("cross-validation manifest belongs to another manifest or split")
    partitions = cv.get("folds")
    if (
        not isinstance(partitions, list)
        or len(partitions) < 2
        or cv.get("fold_count") != len(partitions)
        or [item.get("fold") for item in partitions] != list(range(len(partitions)))
    ):
        raise MedicalDataError("cross-validation folds must be numbered 0..k-1")
    if partitions[0]["train"] != splits["train"] or partitions[0]["val"] != splits["val"]:
        raise MedicalDataError("fold 0 must be exactly the frozen train/validation partition")
    development = splits["train"] + splits["val"]
    test = set(splits["test"])
    seen: set[str] = set()
    for fold, item in enumerate(partitions):
        val = item["val"]
        if not val or len(set(val)) != len(val) or set(val) & seen:
            raise MedicalDataError(f"fold {fold} validation is empty or overlaps another fold")
        if set(val) & test or set(item["train"]) & test:
            raise MedicalDataError(f"fold {fold} contains a held-out test case")
        if item["train"] != [c for c in development if c not in set(val)]:
            raise MedicalDataError(f"fold {fold} training list is not the development complement")
        seen.update(val)
        validate_splits(manifest, fold_splits(splits, cv, fold))
    if seen != set(development):
        raise MedicalDataError("fold validation partitions must cover the development cases")
