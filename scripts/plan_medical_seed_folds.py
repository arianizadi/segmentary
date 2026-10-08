#!/usr/bin/env python3
"""Freeze ResEnc L seed/fold runs, or warm-start arm sets, on one frozen nnU-Net plan.

Scratch mode (``--run GPU:FOLD:SEED``): every run uses the original full-budget
ResEnc L 3d_fullres recipe of the verified preprocessing reference (scratch, no
mirroring, tile step 0.5) and a development CV manifest whose fold 0 is the
frozen train/validation split.

Warm-start mode (``--arm NAME=ARCHITECTURE[:MODE]`` plus
``--run GPU:FOLD:SEED:ARM``): each arm x fold run fine-tunes from the matching
fold's own ResEnc L ``checkpoint_final.pth`` (``--init-checkpoint-pattern``
with ``{fold}`` and ``{seed}``), so no fold's validation cases were seen by its
initial weights. At planning time every checkpoint must exist; its sha256 is
bound, and its source workspace must prove the same fold, seed, CV manifest,
plan and a completed scratch ResEnc L run. Runs share one comparison group per
fold and seed, tagged ``warm_start``.

Arms are ``resenc``, ``hrc[:REFERENCE_MODE]`` or ``starc[:aux_only|frozen]``.
STAR-C arms train ``nnUNetTrainerStarCFinetune`` (only ``starc.*`` may keep its
initialisation; ``frozen`` trains only ``starc.*``, the Stage-1 pilot) on the
ray targets of ``--starc-targets``, bound by ``--starc-targets-sha256``. The
targets must be ``scripts/precompute_star_targets.py`` output for the reference
workspace's own preprocessed segmentations, run with ``--forbid-cases-from``
the frozen split file; the planner checks this from the manifest and the
reference's plan-binding hashes.

Each run is pinned to one GPU. Like the strong-recipe planner, this reads
metadata only: it does not allocate GPUs, copy caches, open CT payloads or
launch work.
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
WARM_RUN = re.compile(r"^(0|[1-9][0-9]*):(0|[1-9][0-9]?):([0-9]+):([A-Za-z][A-Za-z0-9]*)$")
ARM_SPEC = re.compile(r"^([A-Za-z][A-Za-z0-9]*)=(resenc|hrc|starc)(?::([a-z_]+))?$")
STARC_MODES = {"aux_only": {"fusion": "aux_only"}, "frozen": {"freeze_backbone": True}}
WAVE1_CHECKPOINTS = (
    "/data/izadia1/projects/segmentary-runs/pancreas/task07-wave1-20261007/runs/"
    "nnunet_resenc_l-fold{fold}-seed{seed}/nnUNet_results/Dataset707_Pancreas/"
    "nnUNetTrainer__nnUNetResEncUNetLPlans__3d_fullres/fold_{fold}/checkpoint_final.pth"
)
WARM_START_PRESET = "task07_nnunet_warm_start_v1"
UPDATES_PER_EPOCH = 250


def parse_arm(text: str) -> tuple[str, int, int]:
    """``GPU:FOLD:SEED``, for example ``6:1:0``."""
    match = ARM.fullmatch(text)
    if not match:
        raise ValueError(f"Runs are GPU:FOLD:SEED, got {text!r}")
    return match.group(1), int(match.group(2)), int(match.group(3))


def parse_warm_run(text: str) -> tuple[str, int, int, str]:
    """``GPU:FOLD:SEED:ARM``, for example ``2:0:0:B``."""
    match = WARM_RUN.fullmatch(text)
    if not match:
        raise ValueError(f"Warm-start runs are GPU:FOLD:SEED:ARM, got {text!r}")
    return match.group(1), int(match.group(2)), int(match.group(3)), match.group(4)


def parse_arm_spec(text: str) -> tuple[str, dict[str, Any]]:
    """``NAME=resenc``, ``NAME=hrc[:REFERENCE_MODE]`` or ``NAME=starc[:aux_only|frozen]``."""
    from segmentary.medical.recipe_plan import (
        recipe_model_name,
        validate_hrc_options,
        validate_starc_inference,
        validate_starc_options,
    )

    match = ARM_SPEC.fullmatch(text)
    if not match:
        raise ValueError(
            "Arms are NAME=resenc, NAME=hrc[:REFERENCE_MODE] or NAME=starc[:aux_only|frozen], "
            f"got {text!r}"
        )
    name, architecture, mode = match.groups()
    if architecture == "resenc" and mode is not None:
        raise ValueError("Only hrc and starc arms take a mode")
    if architecture == "starc" and mode is not None and mode not in STARC_MODES:
        raise ValueError(f"STAR-C arm modes are {sorted(STARC_MODES)}, got {mode!r}")
    options = (
        validate_hrc_options({"reference_mode": mode} if mode else {})
        if architecture == "hrc"
        else None
    )
    starc = architecture == "starc"
    return name, {
        "architecture": architecture,
        "model": recipe_model_name({"architecture": architecture, "resenc": "L"}),
        "hrc_options": options,
        "trainer": "nnUNetTrainerStarCFinetune" if starc else "nnUNetTrainerFinetune",
        "starc_options": validate_starc_options(STARC_MODES.get(mode or "", {})) if starc else None,
        "starc_inference": validate_starc_inference(None) if starc else None,
        # Only the HRC or STAR-C modules are new; every ResEnc L key must load.
        "init_allowed_missing_prefixes": [f"{architecture}."]
        if architecture in {"hrc", "starc"}
        else [],
    }


def starc_targets_record(
    frozen: dict[str, Any], targets: Path | None, sha256: str | None, arms: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Verify STAR-C targets against the reference workspace (metadata and target hashes).

    Every case's source segmentation must be the reference's own preprocessed
    ``_seg`` file, by the hash in its frozen plan-binding record; no CT payload
    or label is opened here. The backend repeats the check on each run's copy.
    """
    from segmentary.medical.backend import verify_starc_target_manifest

    starc = [arm for arm in arms if arm["architecture"] == "starc"]
    if not starc:
        if targets is not None or sha256 is not None:
            raise ValueError("--starc-targets applies only to starc arms")
        return None
    if targets is None or not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("starc arms need --starc-targets and its --starc-targets-sha256")
    folder = targets.expanduser().resolve()
    for owner in (frozen["campaign_dir"], frozen["reference_workspace"]):
        if folder.is_relative_to(owner):
            raise ValueError("STAR-C targets must live outside the campaign and the reference")
    reference = frozen["reference_workspace"]
    index = _read(reference / "plan-binding.json")["files"]
    configuration = frozen["reference"]["configuration"]
    data_id = configuration["data_identifier"]
    split = frozen["split_record"]
    development = list(split["train"]) + list(split["val"])
    segmentations = {}
    for case in development:
        found = [
            (name, index[f"{data_id}/{name}"])
            for name in (f"{case}_seg.b2nd", f"{case}_seg.npy")
            if f"{data_id}/{name}" in index
        ]
        if len(found) != 1:
            raise ValueError(f"Reference has no unique preprocessed segmentation for {case}")
        segmentations[case] = found[0]
    records = [
        verify_starc_target_manifest(
            folder,
            sha256,
            options=arm["starc_options"],
            configuration="3d_fullres",
            plan_configuration=configuration,
            plans_sha256=frozen["reference"]["metadata_sha256"]["nnUNetResEncUNetLPlans.json"],
            splits_sha256=frozen["input_hashes"]["splits"],
            development=development,
            held_out=list(split["test"]),
            segmentations=segmentations,
        )
        for arm in starc
    ]
    frozen["watched"][folder / "manifest.json"] = sha256
    return records[0]


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def _frozen_inputs(
    *,
    source_root: Path,
    campaign_dir: Path,
    python: Path,
    nnunet_python: Path,
    manifest: Path,
    splits: Path,
    cv_splits: Path,
    reference_workspace: Path,
    gpus: list[str],
    folds: list[int],
) -> dict[str, Any]:
    """Verify source, interpreters, cohort, CV manifest and reference (metadata only)."""
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
    if any(fold >= len(cv["folds"]) for fold in folds):
        raise ValueError("A requested fold is outside the cross-validation manifest")
    reference, watched = reference_metadata(
        reference_workspace, metadata, split_record, input_hashes
    )
    watched.update(
        {manifest: input_hashes["manifest"], splits: input_hashes["splits"], cv_splits: cv_sha256}
    )
    return {
        "source_root": source_root,
        "campaign_dir": campaign_dir,
        "reference_workspace": reference_workspace,
        "manifest": manifest,
        "splits": splits,
        "cv_splits": cv_splits,
        "commit": commit,
        "harness": harness,
        "official": official,
        "input_hashes": input_hashes,
        "metadata": metadata,
        "split_record": split_record,
        "counts": counts,
        "cv": cv,
        "cv_sha256": cv_sha256,
        "reference": reference,
        "watched": watched,
    }


def _protocol(frozen: dict[str, Any], preset: str) -> dict[str, Any]:
    cv, split_record, metadata = frozen["cv"], frozen["split_record"], frozen["metadata"]
    return {
        "preset": preset,
        "manifest_sha256": frozen["input_hashes"]["manifest"],
        "splits_sha256": frozen["input_hashes"]["splits"],
        "cv_splits": str(frozen["cv_splits"]),
        "cv_splits_sha256": frozen["cv_sha256"],
        "cv_fingerprint": cv["fingerprint"],
        "manifest_fingerprint": metadata["fingerprint"],
        "splits_fingerprint": split_record["fingerprint"],
        "partition_counts": frozen["counts"],
        "fold_validation_counts": [len(item["val"]) for item in cv["folds"]],
        "grouping_status": metadata.get("grouping_status", "unspecified"),
        "reference": frozen["reference"],
    }


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
    arms = [parse_arm(text) for text in runs]
    if not arms or len({(fold, seed) for _, fold, seed in arms}) != len(arms):
        raise ValueError("Each fold/seed pair must be declared exactly once")
    gpus = sorted({gpu for gpu, _, _ in arms}, key=int)
    frozen = _frozen_inputs(
        source_root=source_root,
        campaign_dir=campaign_dir,
        python=python,
        nnunet_python=nnunet_python,
        manifest=manifest,
        splits=splits,
        cv_splits=cv_splits,
        reference_workspace=reference_workspace,
        gpus=gpus,
        folds=[fold for _, fold, _ in arms],
    )
    campaign_dir, reference_workspace = frozen["campaign_dir"], frozen["reference_workspace"]
    cv_splits, cv_sha256, reference = frozen["cv_splits"], frozen["cv_sha256"], frozen["reference"]
    recipes, run_records = {}, []
    for gpu, fold, seed in arms:
        identifier = f"{MODEL}-fold{fold}-seed{seed}"
        config = NNUNetConfig(
            workspace=str(campaign_dir / "runs" / identifier),
            backend_python=frozen["official"],
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
        "source_root": str(frozen["source_root"]),
        "source_commit": frozen["commit"],
        "python": frozen["harness"],
        "manifest": str(frozen["manifest"]),
        "splits": str(frozen["splits"]),
        "gpus": gpus,
        "description": "ResEnc L seeds on fold 0 and development CV folds under one frozen nnU-Net plan.",
        "protocol": {
            **_protocol(frozen, "task07_nnunet_seed_folds_v1"),
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
    _publish(frozen, recipes, run_records, spec)
    return spec


def _publish(
    frozen: dict[str, Any],
    recipes: dict[str, dict[str, Any]],
    run_records: list[dict[str, Any]],
    spec: dict[str, Any],
) -> None:
    """Write recipes and spec to staging, validate with the pinned runner, then publish."""
    campaign_dir, source_root = frozen["campaign_dir"], frozen["source_root"]
    commit, watched = frozen["commit"], frozen["watched"]
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


def _source_run(path: Path, *, fold: int, seed: int, frozen: dict[str, Any]) -> dict[str, Any]:
    """Prove an initial checkpoint is this fold's own completed scratch ResEnc L run."""
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError(f"Initial checkpoint does not exist as a regular file: {path}")
    if path.parent.name != f"fold_{fold}" or path.name != "checkpoint_final.pth":
        raise ValueError(f"Initial checkpoint must be fold_{fold}/checkpoint_final.pth: {path}")
    digest = sha256_file(path)
    workspace = path.parents[4]
    binding_path = workspace / "binding.json"
    binding, index = _read(binding_path), _read(workspace / "checkpoint-index.json")
    training = _read(workspace / "training-result.json")
    plan_binding = _read(workspace / "plan-binding.json")
    config = binding.get("config", {})
    plan_name = "nnUNetResEncUNetLPlans.json"
    if (
        Path(config.get("workspace", "")).resolve() != workspace.resolve()
        or config.get("fold") != fold
        or config.get("seed") != seed
        or config.get("architecture", "resenc") != "resenc"
        or config.get("resenc") != "L"
        or config.get("purpose") != "baseline"
        or config.get("trainer", "nnUNetTrainer") != "nnUNetTrainer"
        or binding.get("initialization", "scratch") != "scratch"
        or config.get("cv_splits_sha256") != frozen["cv_sha256"]
        or binding.get("manifest_sha256") != frozen["input_hashes"]["manifest"]
        or binding.get("splits_sha256") != frozen["input_hashes"]["splits"]
    ):
        raise ValueError(f"Initial checkpoint is not fold {fold} seed {seed} scratch ResEnc L")
    if index.get("checkpoint_final.pth", {}).get("sha256") != digest:
        raise ValueError(f"Initial checkpoint differs from its run's checkpoint index: {path}")
    if training.get("completed") is not True:
        raise ValueError(f"Initial checkpoint's training run did not complete: {workspace}")
    # A run imported from a reference re-serialises the plan (transfer_plan, then
    # sorted-key JSON), so its bytes differ even when the plan is identical:
    # compare the reference binding and the parsed plan, never the plan bytes.
    source_plan_path = workspace / "nnUNet_preprocessed" / "Dataset707_Pancreas" / plan_name
    reference_plan_path = (
        frozen["reference_workspace"] / "nnUNet_preprocessed" / "Dataset707_Pancreas" / plan_name
    )
    if sha256_file(source_plan_path) != plan_binding.get("files", {}).get(plan_name):
        raise ValueError(f"Initial checkpoint's plan changed after planning: {source_plan_path}")
    source_reference = config.get("reference_plan_binding_sha256")
    if (
        source_reference is not None
        and source_reference != frozen["reference"]["plan_binding_sha256"]
    ) or _read(source_plan_path) != _read(reference_plan_path):
        raise ValueError("Initial checkpoint was trained on a different nnU-Net plan")
    frozen["watched"][path] = digest
    frozen["watched"][binding_path] = sha256_file(binding_path)
    frozen["watched"][source_plan_path] = plan_binding["files"][plan_name]
    return {
        "path": str(path),
        "sha256": digest,
        "source_workspace": str(workspace),
        "source_binding_sha256": frozen["watched"][binding_path],
        "source_epochs": training.get("epochs"),
    }


def plan_warm_start(
    *,
    source_root: Path,
    campaign_dir: Path,
    python: Path,
    nnunet_python: Path,
    manifest: Path,
    splits: Path,
    cv_splits: Path,
    reference_workspace: Path,
    arms: list[str],
    runs: list[str],
    init_checkpoint_pattern: str = WAVE1_CHECKPOINTS,
    num_epochs: int = 150,
    initial_lr: float = 1e-3,
    starc_targets: Path | None = None,
    starc_targets_sha256: str | None = None,
) -> dict:
    """Freeze warm-start arm x fold runs, each from its own fold's checkpoint."""
    declared = dict(parse_arm_spec(text) for text in arms)
    if len(declared) != len(arms):
        raise ValueError("Arm names must be unique")
    parsed = [parse_warm_run(text) for text in runs]
    if not parsed or len({run[1:] for run in parsed}) != len(parsed):
        raise ValueError("Each fold/seed/arm triple must be declared exactly once")
    if any(arm not in declared for *_, arm in parsed):
        raise ValueError("A run names an undeclared arm")
    if type(num_epochs) is not int or num_epochs < 1:
        raise ValueError("num_epochs must be a positive integer")
    if "{fold}" not in init_checkpoint_pattern:
        raise ValueError("The checkpoint pattern must contain {fold}")
    gpus = sorted({gpu for gpu, *_ in parsed}, key=int)
    frozen = _frozen_inputs(
        source_root=source_root,
        campaign_dir=campaign_dir,
        python=python,
        nnunet_python=nnunet_python,
        manifest=manifest,
        splits=splits,
        cv_splits=cv_splits,
        reference_workspace=reference_workspace,
        gpus=gpus,
        folds=[fold for _, fold, _, _ in parsed],
    )
    campaign_dir = frozen["campaign_dir"]
    targets = starc_targets_record(
        frozen, starc_targets, starc_targets_sha256, list(declared.values())
    )
    checkpoints = {}
    for fold, seed in sorted({(fold, seed) for _, fold, seed, _ in parsed}):
        path = Path(init_checkpoint_pattern.format(fold=fold, seed=seed))
        if path.resolve().is_relative_to(campaign_dir):
            raise ValueError("Initial checkpoints must come from outside the new campaign")
        checkpoints[f"fold{fold}-seed{seed}"] = _source_run(
            path, fold=fold, seed=seed, frozen=frozen
        )
    steps = num_epochs * UPDATES_PER_EPOCH
    trainers = sorted({arm["trainer"] for arm in declared.values()})
    recipes, run_records = {}, []
    for gpu, fold, seed, arm in parsed:
        spec_arm = declared[arm]
        identifier = f"{spec_arm['model']}-{arm}-fold{fold}-seed{seed}"
        bound = checkpoints[f"fold{fold}-seed{seed}"]
        config = NNUNetConfig(
            workspace=str(campaign_dir / "runs" / identifier),
            backend_python=frozen["official"],
            architecture=spec_arm["architecture"],
            hrc_options=spec_arm["hrc_options"],
            reference_workspace=str(frozen["reference_workspace"]),
            reference_plan_binding_sha256=frozen["reference"]["plan_binding_sha256"],
            resenc="L",
            configuration="3d_fullres",
            dataset_id=707,
            dataset_name="Pancreas",
            workers=4,
            seed=seed,
            fold=fold,
            gpu=gpu,
            purpose="pilot",
            num_epochs=num_epochs,
            trainer=spec_arm["trainer"],
            initial_lr=initial_lr,
            initialization="warm_start",
            init_checkpoint=bound["path"],
            init_checkpoint_sha256=bound["sha256"],
            init_allowed_missing_prefixes=spec_arm["init_allowed_missing_prefixes"],
            starc_options=spec_arm["starc_options"],
            starc_targets=None if spec_arm["starc_options"] is None else targets["path"],
            starc_targets_manifest_sha256=None
            if spec_arm["starc_options"] is None
            else targets["manifest_sha256"],
            starc_inference=spec_arm["starc_inference"],
            use_mirroring=False,
            tile_step_size=0.5,
            cv_splits=str(frozen["cv_splits"]),
            cv_splits_sha256=frozen["cv_sha256"],
        )
        recipes[identifier] = {"backend": "nnunet", **dataclasses.asdict(config)}
        run_records.append(
            {
                "id": identifier,
                "config": str(campaign_dir / "recipes" / f"{identifier}.json"),
                "model": spec_arm["model"],
                "backend": "nnunet",
                "workspace": config.workspace,
                "gpu": gpu,
                "comparison_group": f"warm_start_fold{fold}_seed{seed}_{steps}_steps",
                "description": f"Arm {arm} ({spec_arm['architecture']}), warm start from "
                f"fold {fold} seed {seed} ResEnc L, {steps} updates",
            }
        )
    spec = {
        "schema_version": 1,
        "campaign_id": campaign_dir.name,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_root": str(frozen["source_root"]),
        "source_commit": frozen["commit"],
        "python": frozen["harness"],
        "manifest": str(frozen["manifest"]),
        "splits": str(frozen["splits"]),
        "gpus": gpus,
        "description": "Warm-start arm x fold pilot from each fold's own ResEnc L checkpoint.",
        "protocol": {
            **_protocol(frozen, WARM_START_PRESET),
            "arms": declared,
            "initial_checkpoints": checkpoints,
            "starc_targets": targets,
            "pilot": {
                # One trainer name, or the sorted set when STAR-C arms are declared.
                "trainer": trainers[0] if len(trainers) == 1 else trainers,
                "num_epochs": num_epochs,
                "updates_per_epoch": UPDATES_PER_EPOCH,
                "optimizer_steps": steps,
                "initial_lr": float(initial_lr),
                "optimizer_state": "fresh SGD; epoch counter and poly schedule restart at 0",
            },
            "batch_size": 2,
            "early_stopping": False,
            "checkpoint_selection": "official_ema_foreground_dice",
            "primary_checkpoint": "checkpoint_final.pth",
            "secondary_checkpoint": "checkpoint_best.pth (selected on the scored fold; optimistic)",
            "inference": "native nnU-Net Gaussian logit blending, tile step 0.5, no mirroring or ensemble",
            "primary_metric": "equal-case mean native mass Dice on the run's validation fold",
            "comparison": "arms are compared only within one fold/seed warm_start group; "
            "warm-start results are never ranked against scratch runs",
            "limitations": [
                "A warm-start pilot screens; it does not predict from-scratch results",
                "The initial checkpoint already trained 250,000 updates on the same training fold",
                "Planning uses all 239 development cases; folds 1-4 validate on cases seen by the planner",
                "Dataset-case grouping is not independently verified patient identity",
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
    _publish(frozen, recipes, run_records, spec)
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
        "--run",
        dest="runs",
        action="append",
        required=True,
        help="GPU:FOLD:SEED (scratch) or GPU:FOLD:SEED:ARM (warm start), repeatable",
    )
    parser.add_argument(
        "--arm",
        dest="arms",
        action="append",
        help="Warm-start arm NAME=resenc|hrc[:REFERENCE_MODE]|starc[:aux_only|frozen], "
        "repeatable; selects warm-start mode",
    )
    parser.add_argument("--init-checkpoint-pattern", default=WAVE1_CHECKPOINTS)
    parser.add_argument("--num-epochs", type=int, default=150)
    parser.add_argument("--initial-lr", type=float, default=1e-3)
    parser.add_argument("--starc-targets", type=Path, help="STAR-C ray-target folder")
    parser.add_argument("--starc-targets-sha256", help="sha256 of its manifest.json")
    args = parser.parse_args()
    values = vars(args)
    warm = {
        key: values.pop(key)
        for key in (
            "init_checkpoint_pattern",
            "num_epochs",
            "initial_lr",
            "starc_targets",
            "starc_targets_sha256",
        )
    }
    arms = values.pop("arms")
    spec = plan_warm_start(**values, arms=arms, **warm) if arms else plan_campaign(**values)
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
