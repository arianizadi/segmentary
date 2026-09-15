"""Import an audited nnU-Net development cache without sharing mutable files.

Only the original version-bound ResEnc preprocessing recipe is accepted. Source
training may continue while this runs: its weights/results are never opened and
copies must match the frozen cache hashes. Pickled properties are copied as
opaque bytes, never deserialized in the orchestration process.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .backend import NNUNetConfig


def _independent_copy(source: Path, destination: Path) -> None:
    """Use copy-on-write where supported, with a real-copy fallback everywhere."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "linux":
        # --reflink=auto creates an independent inode; it never hard-links the
        # active reference cache. Unsupported filesystems fall back to copying.
        try:
            result = subprocess.run(
                ["cp", "--reflink=auto", "--", str(source), str(destination)],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            result = None
        if result is not None and result.returncode == 0:
            return
    shutil.copyfile(source, destination)


def _inventory(root: Path) -> set[str]:
    if root.is_symlink() or root.parent.is_symlink():
        raise ValueError("Reference preprocessing cache must not use symlinks")
    result = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Reference preprocessing cache must not use symlinks")
        if path.is_file():
            result.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise ValueError("Reference preprocessing cache contains a special file")
    return result


def _official_plan(config: NNUNetConfig, source_binding: dict, plan: dict) -> dict:
    from .backend import NNUNET_VERSION
    from .recipe_plan import RESENC_CLASS

    original = source_binding["config"]
    for key in ("dataset_id", "dataset_name", "resenc", "configuration", "fold"):
        if original.get(key) != getattr(config, key):
            raise ValueError(f"Reference recipe {key} does not match the destination")
    if (
        original.get("nnunet_version") != NNUNET_VERSION
        or original.get("architecture", "resenc") != "resenc"
        or original.get("reference_workspace") is not None
        or original.get("purpose") != "baseline"
    ):
        raise ValueError("Reference must be an original version-bound ResEnc baseline")
    if any(
        original.get(key) is not None
        for key in ("num_epochs", "num_iterations_per_epoch", "num_val_iterations_per_epoch")
    ):
        raise ValueError("Reference must use the official baseline training budget")
    if (
        plan.get("plans_name") != config.plans
        or plan.get("dataset_name") != config.dataset
        or plan.get("experiment_planner_used") != f"nnUNetPlannerResEnc{config.resenc}"
        or plan.get("image_reader_writer") != "NibabelIO"
        or plan.get("label_manager") != "LabelManager"
    ):
        raise ValueError("Reference plan is not the requested official ResEnc recipe")
    selected = plan.get("configurations", {}).get(config.configuration)
    if not isinstance(selected, dict):
        raise ValueError("Reference does not contain the requested configuration")
    if (
        selected.get("architecture", {}).get("network_class_name") != RESENC_CLASS
        or selected.get("preprocessor_name") != "DefaultPreprocessor"
        or selected.get("normalization_schemes") != ["CTNormalization"]
    ):
        raise ValueError("Reference architecture or CT preprocessing is not official")
    data_identifier = selected.get("data_identifier")
    if (
        not isinstance(data_identifier, str)
        or not data_identifier
        or PurePosixPath(data_identifier).name != data_identifier
        or data_identifier in {".", ".."}
    ):
        raise ValueError("Unsafe reference data identifier")
    return selected


def import_reference(config: NNUNetConfig) -> dict[str, Any]:
    """Copy an exact development-only reference cache into a prepared workspace.

    The caller freezes the destination plan after any architecture-only changes.
    No checkpoint, result, source code, environment, or held-out payload is read
    or imported. A failed copy leaves the prepared destination unchanged.
    """
    from . import backend as b

    if not config.reference_workspace:
        raise ValueError("A reference_workspace is required")
    reference = Path(config.reference_workspace).resolve()
    target = config.root.resolve()
    if reference.is_relative_to(target) or target.is_relative_to(reference):
        raise ValueError("Reference and destination workspaces must be independent")
    if (
        (target / "plan-binding.json").exists()
        or _inventory(config.preprocessed) != {"splits_final.json"}
        or {path.name for path in config.preprocessed.iterdir()} != {"splits_final.json"}
    ):
        raise FileExistsError("Reference import requires a fresh prepared workspace")

    # Read the historical binding directly. Calling the current _binding on it
    # would incorrectly reject a reference produced by a different frozen source.
    source_binding_path = reference / "binding.json"
    source_record_path = reference / "plan-binding.json"
    source_binding_sha = b._sha(source_binding_path)
    source_record_sha = b._sha(source_record_path)
    if source_record_sha != config.reference_plan_binding_sha256:
        raise ValueError("Reference plan binding differs from the frozen campaign reference")
    source_binding = b._json(source_binding_path)
    record = b._json(source_record_path)
    destination = b._json(target / "binding.json")
    if (
        source_binding.get("schema_version") != 1
        or Path(source_binding.get("config", {}).get("workspace", "")).resolve() != reference
    ):
        raise ValueError("Reference workspace identity or binding schema changed")
    if record.get("binding_digest") != b._digest(source_binding):
        raise ValueError("Reference plan binding does not match its prepared data identity")
    for key in (
        "manifest_sha256",
        "splits_sha256",
        "manifest_fingerprint",
        "split_fingerprint",
        "ontology",
        "planning_scope",
        "development_cases",
        "held_out_cases",
    ):
        if source_binding.get(key) != destination.get(key):
            raise ValueError(f"Reference and destination {key} differ")
    if source_binding.get("planning_scope") != "train_and_val_only":
        raise ValueError("Reference planning must exclude the held-out test set")
    for bound in (source_binding, destination):
        b._check_hash(bound["manifest_path"], bound["manifest_sha256"])
        b._check_hash(bound["splits_path"], bound["splits_sha256"])
    runtime = record.get("runtime", {})
    if runtime.get("packages", {}).get("nnunetv2") != b.NNUNET_VERSION:
        raise ValueError("Reference runtime has an unsupported nnU-Net version")

    cache = reference / "nnUNet_preprocessed" / config.dataset
    index = record.get("files")
    if not isinstance(index, dict) or not index:
        raise ValueError("Reference has no frozen preprocessing file index")
    for relative in index:
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
            raise ValueError("Unsafe reference cache index path")
    if _inventory(cache) != set(index):
        raise ValueError("Reference preprocessing cache membership changed")
    plan_name = f"{config.plans}.json"
    for required in (plan_name, "splits_final.json", "dataset.json", "dataset_fingerprint.json"):
        if required not in index:
            raise ValueError(f"Reference cache is missing {required}")
        b._check_hash(cache / required, index[required])
    plan = b._json(cache / plan_name)
    selected = _official_plan(config, source_binding, plan)

    split = b._json(Path(destination["splits_path"]))
    expected_split = [{"train": split["train"], "val": split["val"]}]
    development = split["train"] + split["val"]
    if (
        development != source_binding["development_cases"]
        or len(set(development)) != len(development)
        or set(development) & set(source_binding["held_out_cases"])
        or split["test"] != source_binding["held_out_cases"]
        or b._json(cache / "splits_final.json") != expected_split
        or b._json(config.preprocessed / "splits_final.json") != expected_split
    ):
        raise ValueError("Reference development split or held-out exclusion changed")
    dataset = {
        "channel_names": {"0": "CT"},
        "labels": destination["ontology"],
        "numTraining": len(development),
        "file_ending": ".nii.gz",
        "overwrite_image_reader_writer": "NibabelIO",
    }
    if any(
        b._json(path) != dataset
        for path in (
            cache / "dataset.json",
            reference / "nnUNet_raw" / config.dataset / "dataset.json",
            target / "nnUNet_raw" / config.dataset / "dataset.json",
        )
    ):
        raise ValueError("Reference dataset ontology, modality, or membership changed")

    # nnU-Net 2.8.1 emits precisely these four files for each development case.
    # Reject unexpected names before reading their payloads, including weights
    # or accidentally staged held-out scans, even if someone indexed them.
    allowed = {plan_name, "splits_final.json", "dataset.json", "dataset_fingerprint.json"}
    data_id = selected["data_identifier"]
    for case in development:
        if not isinstance(case, str) or PurePosixPath(case).name != case or case in {".", ".."}:
            raise ValueError("Unsafe reference development case identifier")
        allowed.add(f"gt_segmentations/{case}.nii.gz")
        allowed.update(f"{data_id}/{case}{suffix}" for suffix in (".b2nd", "_seg.b2nd", ".pkl"))
    if set(index) != allowed:
        raise ValueError("Reference cache must contain exactly the development preprocessing files")

    total_bytes = 0
    with tempfile.TemporaryDirectory(prefix=".reference-import-", dir=target) as temporary:
        staging = Path(temporary)
        for relative, expected in sorted(index.items()):
            source = cache / relative
            b._check_hash(source, expected)
            copied = staging / relative
            _independent_copy(source, copied)
            if (
                source.stat().st_ino == copied.stat().st_ino
                and source.stat().st_dev == copied.stat().st_dev
            ):
                raise ValueError("Reference import must not share mutable file inodes")
            b._check_hash(copied, expected)
            total_bytes += copied.stat().st_size
        # Detect metadata edits during a long copy. Payloads in staging already
        # matched every immutable expected hash regardless of later source use.
        b._check_hash(source_binding_path, source_binding_sha)
        b._check_hash(source_record_path, source_record_sha)
        if _inventory(cache) != set(index):
            raise ValueError("Reference preprocessing cache membership changed during import")
        for child in sorted(staging.iterdir()):
            child.replace(config.preprocessed / child.name)

    return {
        "reference_workspace": str(reference),
        "source_binding_sha256": source_binding_sha,
        "source_plan_binding_sha256": source_record_sha,
        "source_plan_sha256": index[plan_name],
        "source_cache_index_sha256": b._digest(index),
        "source_runtime": runtime,
        "source_runtime_sha256": b._digest(runtime),
        "source_manifest_sha256": source_binding["manifest_sha256"],
        "source_splits_sha256": source_binding["splits_sha256"],
        "copy_policy": "independent_inodes_reflink_when_available_else_copy",
        "files": len(index),
        "bytes": total_bytes,
        "development_cases": len(development),
        "test_cases_excluded": len(source_binding["held_out_cases"]),
        "weights_imported": False,
        "planning_scope": source_binding["planning_scope"],
        "geometry": {
            "configuration": config.configuration,
            "data_identifier": data_id,
            "spacing": selected["spacing"],
            "patch_size": selected["patch_size"],
            "batch_size": selected["batch_size"],
            "transpose_forward": plan["transpose_forward"],
            "transpose_backward": plan["transpose_backward"],
            "normalization_schemes": selected["normalization_schemes"],
            "foreground_intensity_properties_per_channel": plan[
                "foreground_intensity_properties_per_channel"
            ],
        },
    }
