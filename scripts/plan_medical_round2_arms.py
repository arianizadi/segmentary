#!/usr/bin/env python3
"""Freeze round-2 Task07 5-fold arms on the Wave 1 reference plan (metadata only).

``regions`` (Z2, and optionally HRC in region mode): scratch nnU-Net 2.8.1 runs
with the official ResEnc L recipe and budget (1000 x 250 updates) whose only
change is region-based labels, pancreas = {1, 2} and mass = {2} with
``regions_class_order`` [1, 2]. Predictions decode to the native label map, so
evaluation is unchanged. Arms are ``NAME=resenc``, ``NAME=hrc[:REFERENCE_MODE]``
(HRC reads region head 0 as host and head 1 as lesion) or ``NAME=starc[:aux_only]``
(STAR-C fuses its prior into region heads 0 and 1 and trains ``nnUNetTrainerStarC``
on ``--starc-targets``, bound by ``--starc-targets-sha256``); runs are
``GPU:FOLD:SEED:ARM``. Groups: ``regions_fold{f}_seed{s}_scratch_250000_steps``.

``pretrained`` (Z4 and Z4+HRC): nnFoundationCNN encoder fine-tuning in the
separate nnU-Net master environment (``--nnunet-python``). The planner probes
that interpreter and refuses to plan unless its ``pip freeze`` SHA256 and the
nnU-Net source commit equal the values passed in; it hashes the checkpoint and
binds all three into every recipe. Runs train ``nnUNetTrainerPretrainedDS``
(deep supervision on) for ``--num-epochs`` (default 300) at ``--initial-lr``
(default 1e-3), keeping Wave 1 preprocessing (copied arrays, CT normalisation).
Tensors allowed to keep their initialisation: the decoder, encoder stages
beyond the checkpoint's depth and, for HRC, ``hrc.*``. Groups are
``pretrained-nnfoundation_fold{f}_seed{s}_{steps}_steps``, so these runs are
never ranked against scratch runs. STAR-C has no trainer for this runtime and
is refused here.

Every run is pinned to one GPU in 2-9. Nothing is launched, no GPU is
allocated, and no CT payload or label is opened.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.plan_medical_seed_folds import (
    _frozen_inputs,
    _protocol,
    _publish,
    starc_targets_record,
)

from segmentary.medical.backend import (
    NNSSL_RUNTIME,
    PRETRAINED_TRAINER,
    TASK07_ONTOLOGY,
    NNUNetConfig,
)
from segmentary.medical.geometry import sha256_file
from segmentary.medical.nnunet_regions import validate_regions
from segmentary.medical.recipe_plan import (
    recipe_model_name,
    validate_hrc_options,
    validate_starc_inference,
    validate_starc_options,
)

REGIONS_PRESET = "task07_nnunet_regions_folds_v1"
PRETRAINED_PRESET = "task07_nnunet_pretrained_nnfoundation_v1"
GROUP_PREFIX = "pretrained-nnfoundation"
GPUS = tuple(str(gpu) for gpu in range(2, 10))
UPDATES_PER_EPOCH = 250
RUN = re.compile(r"^(0|[1-9][0-9]*):(0|[1-9][0-9]?):([0-9]+):([A-Za-z][A-Za-z0-9]*)$")
ARM = re.compile(r"^([A-Za-z][A-Za-z0-9]*)=(resenc|hrc|starc)(?::([a-z_]+))?$")
NNFOUNDATION = {
    "checkpoint": "/data/izadia1/models/nnfoundation-cnn/"
    "hf-8edba046f01d09771b8204b9d3e7a6c06d6e1adc/checkpoint_final.pth",
    "sha256": "ac262d3e8c226c79f9567fddc34d38e011284730ddf2294b5c6c319ce2f22bbd",
    "plan_name": "nnFoundationCNN_8edba046",
    "encoder_stages": 6,
    "python": "/data/izadia1/envs/pancreas-nnssl-20261007/bin/python",
    "runtime_freeze_sha256": "6e257d910c0348b0a564aad4bfe2372340a0c23344c1acd66d556cc693994040",
    "nnunet_commit": "47766ae39a31de6e5d3c8f3d88d6ba32ce99ef26",
}


def parse_run(text: str) -> tuple[str, int, int, str]:
    """``GPU:FOLD:SEED:ARM`` with GPU in 2-9, for example ``2:0:0:Z2``."""
    match = RUN.fullmatch(text)
    if not match:
        raise ValueError(f"Runs are GPU:FOLD:SEED:ARM, got {text!r}")
    if match.group(1) not in GPUS:
        raise ValueError(f"Round-2 runs are pinned to GPUs 2-9, got {match.group(1)}")
    return match.group(1), int(match.group(2)), int(match.group(3)), match.group(4)


def parse_arm(text: str, *, regions: bool) -> tuple[str, dict[str, Any]]:
    """``NAME=resenc``, ``NAME=hrc[:REFERENCE_MODE]`` or ``NAME=starc[:aux_only]``.

    HRC and STAR-C follow the label mode. STAR-C runs only in region mode here
    (scratch, official budget); the nnssl runtime has no STAR-C trainer.
    """
    match = ARM.fullmatch(text)
    if not match:
        raise ValueError(
            "Arms are NAME=resenc, NAME=hrc[:REFERENCE_MODE] or NAME=starc[:aux_only], "
            f"got {text!r}"
        )
    name, architecture, mode = match.groups()
    if architecture == "resenc" and mode is not None:
        raise ValueError("Only hrc and starc arms take a mode")
    options: dict[str, Any] | None = None
    starc: dict[str, Any] | None = None
    if architecture == "hrc":
        requested: dict[str, Any] = {"reference_mode": mode} if mode else {}
        if regions:
            # Region heads: 0 = pancreas {1, 2} (host), 1 = mass {2} (lesion).
            requested |= {"output_mode": "regions", "host_channels": [0], "lesion_channels": [1]}
        options = validate_hrc_options(requested)
    if architecture == "starc":
        if not regions:
            raise ValueError("STAR-C has no nnssl-runtime trainer; plan it as a region arm")
        if mode not in (None, "aux_only"):
            raise ValueError(f"Region STAR-C arms take only the aux_only mode, got {mode!r}")
        # Region heads 0 (pancreas) and 1 (mass) receive the prior; mass voxels form stars.
        starc = {"fusion_channels": [0, 1], "lesion_labels": [2]}
        if mode == "aux_only":
            starc["fusion"] = "aux_only"
        starc = validate_starc_options(starc)
    return name, {
        "architecture": architecture,
        "model": recipe_model_name({"architecture": architecture, "resenc": "L"}),
        "hrc_options": options,
        "trainer": "nnUNetTrainerStarC" if starc is not None else "nnUNetTrainer",
        "starc_options": starc,
        "starc_inference": validate_starc_inference(None) if starc is not None else None,
    }


def _arms_and_runs(
    arms: list[str], runs: list[str], *, regions: bool
) -> tuple[dict[str, dict[str, Any]], list[tuple[str, int, int, str]]]:
    declared = dict(parse_arm(text, regions=regions) for text in arms)
    if not declared or len(declared) != len(arms):
        raise ValueError("Declare at least one arm, each with a unique name")
    parsed = [parse_run(text) for text in runs]
    if not parsed or len({run[1:] for run in parsed}) != len(parsed):
        raise ValueError("Each fold/seed/arm triple must be declared exactly once")
    if any(arm not in declared for *_, arm in parsed):
        raise ValueError("A run names an undeclared arm")
    return declared, parsed


def _evaluation() -> dict[str, Any]:
    return {
        "bootstrap_samples": 1000,
        "seed": 0,
        "surface_tolerance_mm": 2.0,
        "lesion_iou_threshold": 0.1,
        "review_overlays": False,
    }


def _spec(frozen: dict[str, Any], description: str, protocol: dict, runs: list) -> dict:
    return {
        "schema_version": 1,
        "campaign_id": frozen["campaign_dir"].name,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_root": str(frozen["source_root"]),
        "source_commit": frozen["commit"],
        "python": frozen["harness"],
        "manifest": str(frozen["manifest"]),
        "splits": str(frozen["splits"]),
        "gpus": sorted({run["gpu"] for run in runs}, key=int),
        "description": description,
        "protocol": protocol,
        "runs": runs,
        "evaluation": _evaluation(),
    }


def _common_config(frozen: dict[str, Any], arm: dict[str, Any], gpu: str, fold: int, seed: int):
    targets = frozen.get("starc_targets") if arm.get("starc_options") is not None else None
    return {
        "architecture": arm["architecture"],
        "hrc_options": arm["hrc_options"],
        "starc_options": arm.get("starc_options"),
        "starc_inference": arm.get("starc_inference"),
        "starc_targets": None if targets is None else targets["path"],
        "starc_targets_manifest_sha256": None if targets is None else targets["manifest_sha256"],
        "reference_workspace": str(frozen["reference_workspace"]),
        "reference_plan_binding_sha256": frozen["reference"]["plan_binding_sha256"],
        "resenc": "L",
        "configuration": "3d_fullres",
        "dataset_id": 707,
        "dataset_name": "Pancreas",
        "workers": 4,
        "seed": seed,
        "fold": fold,
        "gpu": gpu,
        "use_mirroring": False,
        "tile_step_size": 0.5,
        "cv_splits": str(frozen["cv_splits"]),
        "cv_splits_sha256": frozen["cv_sha256"],
    }


def plan_regions(
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
    arms: list[str] | None = None,
    starc_targets: Path | None = None,
    starc_targets_sha256: str | None = None,
) -> dict:
    """Freeze Z2 region-label runs (and optional HRC or STAR-C region arms) per fold/seed."""
    declared, parsed = _arms_and_runs(arms or ["Z2=resenc"], runs, regions=True)
    frozen = _frozen_inputs(
        source_root=source_root,
        campaign_dir=campaign_dir,
        python=python,
        nnunet_python=nnunet_python,
        manifest=manifest,
        splits=splits,
        cv_splits=cv_splits,
        reference_workspace=reference_workspace,
        gpus=sorted({gpu for gpu, *_ in parsed}, key=int),
        folds=[fold for _, fold, _, _ in parsed],
    )
    label_regions, order = validate_regions(TASK07_ONTOLOGY, None, None)
    frozen["starc_targets"] = starc_targets_record(
        frozen, starc_targets, starc_targets_sha256, list(declared.values())
    )
    recipes, records = {}, []
    for gpu, fold, seed, name in parsed:
        arm = declared[name]
        identifier = f"{arm['model']}-{name}-fold{fold}-seed{seed}"
        config = NNUNetConfig(
            workspace=str(frozen["campaign_dir"] / "runs" / identifier),
            backend_python=frozen["official"],
            purpose="baseline",
            trainer=arm["trainer"],
            output_mode="regions",
            label_regions=label_regions,
            regions_class_order=order,
            **_common_config(frozen, arm, gpu, fold, seed),
        )
        recipes[identifier] = {"backend": "nnunet", **dataclasses.asdict(config)}
        records.append(
            {
                "id": identifier,
                "config": str(frozen["campaign_dir"] / "recipes" / f"{identifier}.json"),
                "model": arm["model"],
                "backend": "nnunet",
                "workspace": config.workspace,
                "gpu": gpu,
                "comparison_group": f"regions_fold{fold}_seed{seed}_scratch_250000_steps",
                "description": f"Arm {name} ({arm['architecture']}), region labels, scratch, "
                f"CV fold {fold}, seed {seed}",
            }
        )
    protocol = {
        **_protocol(frozen, REGIONS_PRESET),
        "reference_workspace": str(frozen["reference_workspace"]),
        "arms": declared,
        "starc_targets": frozen["starc_targets"],
        "regions": {"label_regions": label_regions, "regions_class_order": order},
        "region_preprocessing": "reference arrays copied unchanged; per-case class_locations "
        "recomputed for the region keys with nnU-Net's own sampler, after the label keys "
        "reproduce the reference pickle exactly",
        "evaluation_labels": "nnU-Net decodes region probabilities with regions_class_order "
        "at 0.5 to the native 0/1/2 label map; metrics are unchanged",
        "nnunet": {"expected_default_epochs": 1000, "expected_default_updates_per_epoch": 250},
        "optimizer_steps_per_run": 250000,
        "batch_size": 2,
        "early_stopping": False,
        "checkpoint_selection": "official_ema_foreground_dice",
        "primary_checkpoint": "checkpoint_final.pth",
        "secondary_checkpoint": "checkpoint_best.pth (selected on the scored fold; optimistic)",
        "inference": "native nnU-Net Gaussian logit blending, tile step 0.5, no mirroring or ensemble",
        "primary_metric": "equal-case mean native mass Dice on the run's validation fold",
        "comparison": "arms are ranked only within one fold/seed group; the label-mode control "
        "is the Wave 1 run of the same fold and seed",
        "limitations": [
            "Seeds change initialization and sampling but CUDA/augmentation remain nondeterministic",
            "Planning uses all 239 development cases; folds 1-4 validate on cases seen by the planner",
            "Dataset-case grouping is not independently verified patient identity",
        ],
    }
    spec = _spec(
        frozen,
        "Region-label (pancreas={1,2}, mass={2}) ResEnc L arms on the Wave 1 plan.",
        protocol,
        records,
    )
    _publish(frozen, recipes, records, spec)
    return spec


def _probe_environment(source_root: Path) -> dict[str, str]:
    """The backend worker's interpreter environment, without any GPU."""
    return dict(os.environ) | {
        "PYTHONPATH": str(source_root / "src"),
        "PYTHONNOUSERSITE": "1",
        "CUDA_VISIBLE_DEVICES": "",
    }


def plan_pretrained(
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
    arms: list[str] | None = None,
    init_checkpoint: Path = Path(str(NNFOUNDATION["checkpoint"])),
    init_checkpoint_sha256: str = str(NNFOUNDATION["sha256"]),
    runtime_freeze_sha256: str = str(NNFOUNDATION["runtime_freeze_sha256"]),
    nnunet_commit: str = str(NNFOUNDATION["nnunet_commit"]),
    pretrained_plan_name: str = str(NNFOUNDATION["plan_name"]),
    pretrained_encoder_stages: int = int(NNFOUNDATION["encoder_stages"]),
    num_epochs: int = 300,
    initial_lr: float = 1e-3,
) -> dict:
    """Freeze nnFoundation fine-tune arms (ResEnc L and HRC) in the nnssl runtime."""
    from segmentary.medical.nnunet_pretrained import runtime_identity

    declared, parsed = _arms_and_runs(arms or ["Z4=resenc", "Z4HRC=hrc"], runs, regions=False)
    if type(num_epochs) is not int or num_epochs < 1:
        raise ValueError("num_epochs must be a positive integer")
    if type(pretrained_encoder_stages) is not int or pretrained_encoder_stages < 1:
        raise ValueError("pretrained_encoder_stages must be a positive integer")
    frozen = _frozen_inputs(
        source_root=source_root,
        campaign_dir=campaign_dir,
        python=python,
        nnunet_python=nnunet_python,
        manifest=manifest,
        splits=splits,
        cv_splits=cv_splits,
        reference_workspace=reference_workspace,
        gpus=sorted({gpu for gpu, *_ in parsed}, key=int),
        folds=[fold for _, fold, _, _ in parsed],
    )
    checkpoint = init_checkpoint.expanduser().resolve()
    if not checkpoint.is_file() or sha256_file(checkpoint) != init_checkpoint_sha256:
        raise ValueError(
            f"Pretrained checkpoint is missing or differs from its SHA256: {checkpoint}"
        )
    if checkpoint.is_relative_to(frozen["campaign_dir"]):
        raise ValueError("The pretrained checkpoint must live outside the campaign")
    identity = runtime_identity(frozen["official"], _probe_environment(frozen["source_root"]))
    if identity["pip_freeze_sha256"] != runtime_freeze_sha256:
        raise ValueError("The nnssl interpreter's pip freeze differs from the expected SHA256")
    if identity["nnunetv2_commit"] != nnunet_commit:
        raise ValueError("The nnssl interpreter's nnU-Net source differs from the expected commit")
    frozen["watched"][checkpoint] = init_checkpoint_sha256
    n_stages = frozen["reference"]["configuration"]["architecture"]["arch_kwargs"]["n_stages"]
    random = ["decoder."] + [
        f"encoder.stages.{stage}." for stage in range(pretrained_encoder_stages, n_stages)
    ]
    for arm in declared.values():
        extra = ["hrc."] if arm["architecture"] == "hrc" else []
        arm["init_allowed_missing_prefixes"] = sorted(random + extra)
        arm["trainer"] = PRETRAINED_TRAINER
    steps = num_epochs * UPDATES_PER_EPOCH
    recipes, records = {}, []
    for gpu, fold, seed, name in parsed:
        arm = declared[name]
        identifier = f"{arm['model']}-{name}-fold{fold}-seed{seed}"
        config = NNUNetConfig(
            workspace=str(frozen["campaign_dir"] / "runs" / identifier),
            backend_python=frozen["official"],
            backend_runtime=NNSSL_RUNTIME,
            runtime_freeze_sha256=runtime_freeze_sha256,
            nnunet_commit=nnunet_commit,
            pretrained_plan_name=pretrained_plan_name,
            purpose="finetune",
            num_epochs=num_epochs,
            trainer=PRETRAINED_TRAINER,
            initial_lr=initial_lr,
            initialization="pretrained",
            init_checkpoint=str(checkpoint),
            init_checkpoint_sha256=init_checkpoint_sha256,
            init_allowed_missing_prefixes=arm["init_allowed_missing_prefixes"],
            **_common_config(frozen, arm, gpu, fold, seed),
        )
        recipes[identifier] = {"backend": "nnunet", **dataclasses.asdict(config)}
        records.append(
            {
                "id": identifier,
                "config": str(frozen["campaign_dir"] / "recipes" / f"{identifier}.json"),
                "model": arm["model"],
                "backend": "nnunet",
                "workspace": config.workspace,
                "gpu": gpu,
                "comparison_group": f"{GROUP_PREFIX}_fold{fold}_seed{seed}_{steps}_steps",
                "description": f"Arm {name} ({arm['architecture']}), nnFoundationCNN encoder "
                f"fine-tune, CV fold {fold}, seed {seed}, {steps} updates",
            }
        )
    protocol = {
        **_protocol(frozen, PRETRAINED_PRESET),
        "reference_workspace": str(frozen["reference_workspace"]),
        "arms": declared,
        "comparison_group_prefix": GROUP_PREFIX,
        "pretrained": {
            "checkpoint": str(checkpoint),
            "sha256": init_checkpoint_sha256,
            "plan_name": pretrained_plan_name,
            "encoder_stages": pretrained_encoder_stages,
            "backend_python": frozen["official"],
            "runtime_freeze_sha256": runtime_freeze_sha256,
            "nnunet_commit": nnunet_commit,
            "runtime_sources": identity["sources"],
            "runtime_packages": identity["packages"],
        },
        "finetune": {
            "trainer": PRETRAINED_TRAINER,
            "num_epochs": num_epochs,
            "updates_per_epoch": UPDATES_PER_EPOCH,
            "optimizer_steps": steps,
            "initial_lr": float(initial_lr),
            "warmup_epochs": max(1, round(num_epochs * 50 / 1000)),
            "deep_supervision": True,
            "optimizer": "SGD Nesterov momentum 0.99, weight decay 3e-5; linear whole-network "
            "warm-up, then poly (nnU-Net master PretrainedTrainer)",
            "torch_compile": False,
        },
        "preprocessing": "Wave 1 reference arrays copied; nnUNetv2_extract_sampling_locations on "
        "the copy; nnUNetv2_plan_like_dynamic on the frozen ResEnc L plan (spacing, patch, "
        "CTNormalization unchanged)",
        "batch_size": 2,
        "early_stopping": False,
        "checkpoint_selection": "official_ema_foreground_dice",
        "primary_checkpoint": "checkpoint_final.pth",
        "secondary_checkpoint": "checkpoint_best.pth (selected on the scored fold; optimistic)",
        "inference": "native nnU-Net Gaussian logit blending, tile step 0.5, no mirroring or ensemble",
        "primary_metric": "equal-case mean native mass Dice on the run's validation fold",
        "comparison": "arms are ranked only within one pretrained-nnfoundation fold/seed group, "
        "never against scratch runs or across nnU-Net environments",
        "limitations": [
            "The nnFoundation corpus is partly private and cannot be audited for Task07 overlap",
            "CT normalisation, not the paper's z-score; 300 epochs, not the paper's 1000",
            "Encoder stages beyond the checkpoint's depth and the decoder start at initialisation",
            "Planning uses all 239 development cases; folds 1-4 validate on cases seen by the planner",
        ],
    }
    spec = _spec(
        frozen,
        "nnFoundationCNN encoder fine-tuning of ResEnc L and HRC on the Wave 1 plan.",
        protocol,
        records,
    )
    _publish(frozen, recipes, records, spec)
    return spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("regions", "pretrained"):
        sub = commands.add_parser(command)
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
            sub.add_argument(f"--{name}", type=Path, required=True)
        sub.add_argument("--run", dest="runs", action="append", required=True)
        sub.add_argument("--arm", dest="arms", action="append")
        if command == "regions":
            sub.add_argument("--starc-targets", type=Path, help="STAR-C ray-target folder")
            sub.add_argument("--starc-targets-sha256", help="sha256 of its manifest.json")
        if command == "pretrained":
            sub.add_argument("--init-checkpoint", type=Path, default=NNFOUNDATION["checkpoint"])
            sub.add_argument("--init-checkpoint-sha256", default=NNFOUNDATION["sha256"])
            sub.add_argument(
                "--runtime-freeze-sha256", default=NNFOUNDATION["runtime_freeze_sha256"]
            )
            sub.add_argument("--nnunet-commit", default=NNFOUNDATION["nnunet_commit"])
            sub.add_argument("--pretrained-plan-name", default=NNFOUNDATION["plan_name"])
            sub.add_argument(
                "--pretrained-encoder-stages", type=int, default=NNFOUNDATION["encoder_stages"]
            )
            sub.add_argument("--num-epochs", type=int, default=300)
            sub.add_argument("--initial-lr", type=float, default=1e-3)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    spec = plan_regions(**args) if command == "regions" else plan_pretrained(**args)
    print(
        json.dumps(
            {
                "campaign": str(args["campaign_dir"] / "campaign.json"),
                "source_commit": spec["source_commit"],
                "runs": {run["id"]: run["gpu"] for run in spec["runs"]},
                "status": "planned; nothing launched",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
