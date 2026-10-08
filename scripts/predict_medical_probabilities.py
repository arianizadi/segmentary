#!/usr/bin/env python3
"""Export native-space softmax probabilities from trained nnU-Net workspaces, read-only.

Each ``--member CAMPAIGN_JSON::RUN_ID`` names one trained run. Its binding,
plan, checkpoint index and checkpoint bytes are verified against the run's own
records. The workspace is never locked or written: the checkpoint and the
trained ``plans.json`` and ``dataset.json`` are copied into the output and the
copies are verified against the bound hashes, so prediction reads only those
copies. A campaign runner that is still predicting into the same workspace is
therefore never blocked. Outputs go to a fresh ``--output`` directory:

- ``models/<run id>/`` the verified copies that prediction loads;
- ``members/<run id>/`` per-member nnU-Net exports (``.nii.gz``, ``.npz``
  probabilities, ``.pkl`` properties), for out-of-fold (OOF) analyses;
- ``ensemble/`` for two or more members: the mean of member probabilities
  (nnU-Net ``merge_files``), so a seed ensemble is a probability average,
  not nnU-Net's single-folder logit average;
- ``provenance.json``: members, checkpoints, settings, cases and file hashes.

``--partition val`` predicts the members' validation fold; every member must
have the same validation cases, and no case may be in any member's training
fold (a fold ensemble therefore needs ``unlabeled`` or external images).
Reserved test cases are refused. Label payloads are never opened. ``--mirroring``
enables nnU-Net's mirroring test-time augmentation over the checkpoint's axes.
STAR-C members predict with ``StarCPredictor`` and their run's bound
``starc_inference`` settings (two-pass case-level rendering by default).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segmentary.medical import backend as b
from segmentary.medical.data import predictable_unlabeled_cases
from segmentary.medical.recipe_plan import STARC_CLASS

# Segmentary sources inference imports, by what the run uses. A run is checked
# only against the files it loads, so a run trained before a file existed (for
# example an HRC or fine-tune run from before STAR-C) still exports.
_NETWORK_SOURCES = ("nnunet_architectures.py", "host_reference.py", "nnunet_trainers.py")
_PRETRAINED_SOURCES = ("nnunet_pretrained.py",)
_STARC_SOURCES = ("star_completion.py", "nnunet_star_trainer.py", "recipe_plan.py")


def network_sources(network_class: str, trainer: str, architecture: str) -> tuple[str, ...]:
    """The Segmentary source files a run's inference imports."""
    sources = _NETWORK_SOURCES
    if trainer == b.PRETRAINED_TRAINER:
        sources += _PRETRAINED_SOURCES
    if architecture == "starc" or network_class == STARC_CLASS or trainer in b.STARC_TRAINERS:
        sources += _STARC_SOURCES
    return sources


def _member_config(record: dict[str, Any]) -> b.NNUNetConfig:
    """A config for runtime probing only; unknown historical keys are refused."""
    fields = set(b.NNUNetConfig.__dataclass_fields__)
    unknown = set(record) - fields
    if unknown:
        raise ValueError(f"Run configuration has unknown keys: {sorted(unknown)}")
    return b.NNUNetConfig(**record)


def _probe_environment() -> dict[str, str]:
    return dict(os.environ) | {
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONNOUSERSITE": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "HF_HUB_OFFLINE": "1",
    }


def verify_member(
    campaign: Path, run_id: str, checkpoint: str, *, runtime: dict | None = None
) -> dict[str, Any]:
    """Verify one trained run from its own records; returns a provenance record."""
    if checkpoint not in {"checkpoint_final.pth", "checkpoint_best.pth"}:
        raise ValueError("Export checkpoint_final.pth or checkpoint_best.pth")
    spec = b._json(campaign)
    runs = [run for run in spec.get("runs", []) if run.get("id") == run_id]
    if len(runs) != 1:
        raise ValueError(f"Campaign does not declare exactly one run {run_id!r}")
    workspace = Path(b._json(Path(runs[0]["config"]))["workspace"]).resolve()
    binding = b._json(workspace / "binding.json")
    resolved = b._json(workspace / "resolved-config.json")
    if binding.get("config") != resolved:
        raise ValueError(f"{run_id}: resolved configuration differs from its binding")
    config = _member_config(resolved)
    plan_binding = b._json(workspace / "plan-binding.json")
    if plan_binding.get("binding_digest") != b._digest(binding):
        raise ValueError(f"{run_id}: plan binding does not match the prepared experiment")
    if runtime is None:
        # The recorded runtime does not depend on the GPU; probe without one.
        runtime = b._runtime(config, environment=_probe_environment())
    if plan_binding.get("runtime") != runtime:
        raise ValueError(f"{run_id}: backend environment changed since planning")
    identity = b._digest({"binding": binding, "runtime": runtime})
    item = b._json(workspace / "checkpoint-index.json").get(checkpoint, {})
    trainer = resolved.get("trainer", "nnUNetTrainer")
    plans_name = config.plans
    model_folder = (
        workspace
        / "nnUNet_results"
        / config.dataset
        / f"{trainer}__{plans_name}__{config.configuration}"
    )
    checkpoint_path = model_folder / f"fold_{config.fold}" / checkpoint
    if item.get("identity") != identity or not item.get("sha256"):
        raise ValueError(f"{run_id}: checkpoint belongs to different data, code or environment")
    b._check_hash(checkpoint_path, item["sha256"])
    if (
        checkpoint == "checkpoint_final.pth"
        and b._json(workspace / "training-result.json").get("completed") is not True
    ):
        raise ValueError(f"{run_id}: training did not complete")
    preprocessed = workspace / "nnUNet_preprocessed" / config.dataset
    for model_name, original_name in (
        ("plans.json", f"{plans_name}.json"),
        ("dataset.json", "dataset.json"),
    ):
        b._check_hash(preprocessed / original_name, plan_binding["files"][original_name])
        trained = b._json(model_folder / model_name)
        if model_name == "plans.json" and type(trained.pop("continue_training", False)) is not bool:
            raise ValueError("Invalid nnU-Net continue_training metadata")
        expected = b._json(preprocessed / original_name)
        if trained != expected or not b._same_dataset_json(trained, expected):
            raise ValueError(f"{run_id}: trained model metadata changed: {model_name}")
    plan = b._json(preprocessed / f"{plans_name}.json")
    network_class = plan["configurations"][config.configuration]["architecture"][
        "network_class_name"
    ]
    current = b._code_identity()
    # Inference imports Segmentary network and trainer code from this source.
    # It must be byte-identical to the code the run was trained with.
    needs_source = network_class.startswith("segmentary.") or trainer in b.SEGMENTARY_TRAINERS
    sources = network_sources(network_class, trainer, config.architecture) if needs_source else ()
    if any(
        binding["code"].get(name) is None or binding["code"].get(name) != current.get(name)
        for name in sources
    ):
        raise ValueError(f"{run_id}: network source differs from the trained run's source")
    # The files prediction loads, by path relative to the model folder.
    guarded = {
        "plans.json": b._sha(model_folder / "plans.json"),
        "dataset.json": b._sha(model_folder / "dataset.json"),
        f"fold_{config.fold}/{checkpoint}": item["sha256"],
    }
    return {
        "run_id": run_id,
        "campaign": str(campaign),
        "campaign_sha256": b._sha(campaign),
        "workspace": str(workspace),
        "fold": config.fold,
        "seed": config.seed,
        "architecture": config.architecture,
        "network_class": network_class,
        "trainer": trainer,
        "initialization": binding.get("initialization", "scratch"),
        "backend_runtime": config.backend_runtime,
        "output_mode": config.output_mode,
        "regions_class_order": config.regions_class_order,
        # Region heads are only comparable when they define the same regions.
        "label_regions": config.label_regions,
        # Native label values, from the run's bound ontology.
        "labels": sorted(int(value) for value in binding["ontology"].values()),
        # STAR-C predicts with its bound two-pass settings, as in the run's own validation.
        "starc_inference": config.starc_inference,
        "model_folder": str(model_folder),
        "checkpoint": checkpoint,
        "checkpoint_sha256": item["sha256"],
        "checkpoint_epoch": item.get("epoch"),
        "identity": identity,
        "network_source_bound": needs_source,
        "network_sources_checked": list(sources),
        "manifest_path": binding["manifest_path"],
        "splits_path": binding["splits_path"],
        "manifest_sha256": binding["manifest_sha256"],
        "splits_sha256": binding["splits_sha256"],
        "cv_splits": resolved.get("cv_splits"),
        "cv_splits_sha256": resolved.get("cv_splits_sha256"),
        "guarded_files": guarded,
    }


def _fold(member: dict[str, Any]) -> dict[str, list[str]]:
    splits = b._json(Path(member["splits_path"]))
    if member["cv_splits"] is None:
        return {"train": list(splits["train"]), "val": list(splits["val"])}
    b._check_hash(member["cv_splits"], member["cv_splits_sha256"])
    fold = b._json(Path(member["cv_splits"]))["folds"][member["fold"]]
    return {"train": list(fold["train"]), "val": list(fold["val"])}


def select_cases(members: list[dict[str, Any]], partition: str) -> list[dict[str, str]]:
    """Images to predict; never a member's training case, a test case, or a label."""
    if partition not in {"val", "unlabeled"}:
        raise ValueError("Probability export supports val or unlabeled; test access is refused")
    if len({(m["manifest_sha256"], m["splits_sha256"]) for m in members}) != 1:
        raise ValueError("Members were trained on different manifests or splits")
    for member in members:
        b._check_hash(member["manifest_path"], member["manifest_sha256"])
        b._check_hash(member["splits_path"], member["splits_sha256"])
    manifest = b._json(Path(members[0]["manifest_path"]))
    splits = b._json(Path(members[0]["splits_path"]))
    folds = [_fold(member) for member in members]
    if partition == "val":
        identifiers = folds[0]["val"]
        if any(fold["val"] != identifiers for fold in folds):
            raise ValueError("Members validate different cases; OOF export needs one fold")
    else:
        # Unlabeled scans that copy a labelled case (LiTS liver_137) are excluded.
        identifiers, _ = predictable_unlabeled_cases(manifest)
    held_out = set(splits.get("test", []))
    training = set().union(*(fold["train"] for fold in folds))
    if not identifiers or set(identifiers) & (held_out | training):
        raise ValueError("Selected cases are empty or overlap a training fold or the test set")
    lookup = {case["case_id"]: case for case in manifest["cases"]}
    cases = [
        {"case_id": key, "image": lookup[key]["image"], "image_sha256": lookup[key]["image_sha256"]}
        for key in identifiers
    ]
    for case in cases:
        b._check_hash(case["image"], case["image_sha256"])
    return cases


def copy_model(member: dict[str, Any], output: Path) -> Path:
    """Copy one member's prediction inputs out of its workspace and verify the copies.

    No lock is taken on the workspace, so a runner's own exclusive stage lock
    (predict, predict_best) never conflicts with an export. The copies, not
    the workspace, are what the predictor loads.
    """
    source = Path(member["model_folder"])
    target = output / "models" / member["run_id"] / source.name
    for relative, digest in member["guarded_files"].items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, destination)
        if b._sha(destination) != digest:
            raise ValueError(f"{member['run_id']}: {relative} changed after verification")
        destination.chmod(0o444)
    return target


def _worker(request_path: str) -> None:
    """Backend-interpreter worker: one nnU-Net predictor per member, then the ensemble."""
    import numpy as np
    import torch
    from nnunetv2.ensembling.ensemble import merge_files
    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager

    request = b._json(Path(request_path))
    if request["device"] == "cuda":
        b._require_worker_devices(request["gpu"])
        device = torch.device("cuda", 0)
    else:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
            raise ValueError("CPU export requires CUDA_VISIBLE_DEVICES to be empty")
        device = torch.device("cpu")
    torch.manual_seed(0)
    np.random.seed(0)
    output = Path(request["output"])
    images = [[case["image"]] for case in request["cases"]]
    folders = []
    for member in request["members"]:
        folder = output / "members" / member["run_id"]
        folder.mkdir(parents=True)
        predictor = b.build_predictor(
            member.get("architecture", "resenc"),
            member.get("starc_inference"),
            tile_step_size=request["tile_step_size"],
            use_gaussian=True,
            use_mirroring=request["mirroring"],
            perform_everything_on_device=device.type == "cuda",
            device=device,
            allow_tqdm=False,
        )
        torch.backends.cudnn.benchmark = False
        b.initialize_predictor(
            predictor,
            Path(member["model_folder"]),
            member["fold"],
            member["checkpoint"],
            member["trainer"],
        )
        targets = [str(folder / case["case_id"]) for case in request["cases"]]
        if request["workers"] == 1:
            predictor.predict_from_files_sequential(
                images, targets, save_probabilities=True, overwrite=False
            )
        else:
            predictor.predict_from_files(
                images,
                targets,
                save_probabilities=True,
                overwrite=False,
                num_processes_preprocessing=request["workers"],
                num_processes_segmentation_export=request["workers"],
            )
        folders.append(folder)
    if len(folders) > 1:
        ensemble = output / "ensemble"
        ensemble.mkdir()
        plans = PlansManager(b._json(folders[0] / "plans.json"))
        dataset_json = b._json(folders[0] / "dataset.json")
        for case in request["cases"]:
            merge_files(
                [str(folder / f"{case['case_id']}.npz") for folder in folders],
                str(ensemble / case["case_id"]),
                dataset_json["file_ending"],
                plans.image_reader_writer_class(),
                plans.get_label_manager(dataset_json),
                save_probabilities=True,
            )


def export(
    members: list[dict[str, Any]],
    *,
    partition: str,
    output: Path,
    device: str,
    gpu: str | None,
    mirroring: bool,
    tile_step_size: float,
    workers: int,
    backend_python: str,
) -> dict[str, Any]:
    """Run the worker in the backend interpreter and validate every output file."""
    output = output.expanduser().resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Use a fresh output directory")
    for member in members:
        if output.is_relative_to(Path(member["workspace"])):
            raise ValueError("Output must be outside every trained workspace")
    if len({member["run_id"] for member in members}) != len(members):
        raise ValueError("Each member may appear once")
    modes = {
        json.dumps(
            [
                m.get("output_mode", "labels"),
                m.get("regions_class_order"),
                m.get("label_regions"),
                m.get("labels"),
            ]
        )
        for m in members
    }
    if len(modes) != 1:
        # Softmax class and sigmoid region probabilities must never be averaged together,
        # nor sigmoid channels that define different regions.
        raise ValueError("Members must share one output mode, region set, region order and labels")
    if device not in {"cuda", "cpu"} or (device == "cuda") != (gpu is not None):
        raise ValueError("Use --device cpu, or --device cuda with one --gpu")
    if gpu is not None:
        b._refuse_forbidden_gpu(gpu)
        inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
        if inherited is not None and gpu not in inherited.split(","):
            raise ValueError("Requested GPU exceeds inherited CUDA_VISIBLE_DEVICES")
    if type(workers) is not int or workers < 1 or not 0 < tile_step_size <= 1:
        raise ValueError("workers must be positive and tile_step_size in (0, 1]")
    cases = select_cases(members, partition)
    # Native-space checks use the manifest's own label set and geometry policy (KiTS23
    # declares no spatial units and has label 3), exactly as backend.predict does.
    manifest = b._json(Path(members[0]["manifest_path"]))
    native_labels = tuple(members[0].get("labels") or (0, 1, 2))
    unknown_units_as_mm = bool(
        (manifest.get("geometry_policy") or {}).get("unknown_spatial_units_as_mm", False)
    )
    started = time.time()
    with contextlib.ExitStack() as stack:
        if gpu is not None:
            lock_root = Path(
                os.environ.get(
                    "SEGMENTARY_MEDICAL_LOCK_DIR",
                    str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
                )
            )
            stack.enter_context(b._lock(lock_root / f"gpu-{gpu}.lock"))
        output.mkdir(parents=True)
        copies = {member["run_id"]: str(copy_model(member, output)) for member in members}
        request = {
            "members": [
                {
                    k: v
                    for k, v in (member | {"model_folder": copies[member["run_id"]]}).items()
                    if k != "guarded_files"
                }
                for member in members
            ],
            "cases": [{k: v for k, v in case.items() if k != "image_sha256"} for case in cases],
            "output": str(output),
            "device": device,
            "gpu": gpu,
            "mirroring": mirroring,
            "tile_step_size": tile_step_size,
            "workers": workers,
        }
        b._atomic_json(output / "request.json", request)
        unused = output / ".nnunet-unused"
        environment = dict(os.environ) | {
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONUNBUFFERED": "1",
            "CUDA_VISIBLE_DEVICES": gpu if gpu is not None else "",
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "nnUNet_compile": "false",
            "nnUNet_raw": str(unused),
            "nnUNet_preprocessed": str(unused),
            "nnUNet_results": str(unused),
            "nnUNet_n_proc_DA": str(workers),
            "OMP_NUM_THREADS": str(workers),
            "HF_HUB_OFFLINE": "1",
        }
        with (output / "worker.log").open("wb") as log:
            completed = subprocess.run(
                [
                    backend_python,
                    str(Path(__file__).resolve()),
                    "_worker",
                    str(output / "request.json"),
                ],
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if completed.returncode:
            raise RuntimeError(f"Probability worker failed; see {output / 'worker.log'}")
        for member in members:
            for relative, digest in member["guarded_files"].items():
                if b._sha(Path(copies[member["run_id"]]) / relative) != digest:
                    raise ValueError(f"A copied model file changed during export: {relative}")
    folders = [output / "members" / member["run_id"] for member in members]
    if len(members) > 1:
        folders.append(output / "ensemble")
    files: dict[str, str] = {}
    for folder in folders:
        for case in cases:
            for suffix in (".nii.gz", ".npz", ".pkl"):
                path = folder / f"{case['case_id']}{suffix}"
                if suffix == ".nii.gz":
                    b._finalize_native_prediction(
                        case["image"],
                        path,
                        labels=native_labels,
                        unknown_units_as_mm=unknown_units_as_mm,
                    )
                files[str(path.relative_to(output))] = b._sha(path)
    provenance = {
        "action": "export_probabilities",
        "partition": partition,
        "members": [
            {k: v for k, v in m.items() if k != "guarded_files"}
            | {"model_copy": copies[m["run_id"]], "model_copy_sha256": m["guarded_files"]}
            for m in members
        ],
        "ensemble": "mean of member native-space probabilities (nnU-Net merge_files)"
        if len(members) > 1
        else None,
        "probabilities": "nnU-Net export: logits resampled to native shape, then softmax/sigmoid; "
        "npz arrays are channel-first in the image reader's axis order",
        "probability_channels": f"softmax over label values {list(native_labels)}"
        if members[0].get("output_mode", "labels") == "labels"
        else "sigmoid per region in dataset.json region order; labels are "
        f"decoded with regions_class_order {members[0].get('regions_class_order')} at 0.5",
        "cases": [case["case_id"] for case in cases],
        "settings": {
            "device": device,
            "gpu": gpu,
            "mirroring": mirroring,
            "tile_step_size": tile_step_size,
            "gaussian_blending": True,
            "workers": workers,
        },
        "labels_opened": False,
        "test_partition_accessed": False,
        "workspaces_written": False,
        "workspaces_locked": False,
        "source_code_identity": b._code_identity(),
        "started_at": started,
        "finished_at": time.time(),
        "files": files,
    }
    b._atomic_json(output / "provenance.json", provenance)
    return provenance


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "_worker":
        _worker(argv[1])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", action="append", required=True, help="CAMPAIGN_JSON::RUN_ID")
    parser.add_argument("--checkpoint", default="checkpoint_final.pth")
    parser.add_argument("--partition", default="val", choices=["val", "unlabeled"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--gpu")
    parser.add_argument("--mirroring", action="store_true")
    parser.add_argument("--tile-step-size", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    status = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True)
    if status.strip():
        raise ValueError("Probability export requires a clean committed source checkout")
    members = []
    for text in args.member:
        campaign, separator, run_id = text.partition("::")
        if not separator:
            raise ValueError("Members are CAMPAIGN_JSON::RUN_ID")
        members.append(verify_member(Path(campaign).resolve(), run_id, args.checkpoint))
    pythons = {
        b._json(Path(m["workspace"]) / "resolved-config.json")["backend_python"] for m in members
    }
    if len(pythons) != 1:
        raise ValueError("Members must share one backend interpreter")
    provenance = export(
        members,
        partition=args.partition,
        output=args.output,
        device=args.device,
        gpu=args.gpu,
        mirroring=args.mirroring,
        tile_step_size=args.tile_step_size,
        workers=args.workers,
        backend_python=pythons.pop(),
    )
    print(json.dumps({"output": str(args.output), "cases": len(provenance["cases"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
