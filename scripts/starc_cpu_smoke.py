#!/usr/bin/env python3
"""End-to-end STAR-C check on CPU: synthetic data, offline targets, training steps, two-pass inference.

Builds a small synthetic nnU-Net 2.8.1 dataset (pancreas-like host with one
or two masses per case, some cut by the patch edge) inside a fresh
``--workdir``, transfers the given ResEnc plan to STAR-C (optionally with
narrow widths and a reduced patch), precomputes the full-volume targets with
``precompute_star_targets.py``, trains ``nnUNetTrainerStarC`` for ``--steps``
updates with nnU-Net's own pipeline (synchronous augmentation, frame
recording, star losses, teacher forcing), then runs ``StarCPredictor`` on a
validation case in two-pass and in-tile modes. Writes one JSON record.

No real image, label, workspace or checkpoint is opened; ``--plan`` is read
only for its architecture and plan fields. Run in the nnU-Net backend
interpreter with ``CUDA_VISIBLE_DEVICES=""``; it always uses the CPU.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

DATASET = "Dataset998_StarSmoke"
NARROW = {"features_per_stage": [8, 16, 16, 16, 16, 16, 16], "n_blocks_per_stage": [1] * 7}


def _ellipsoid(shape, centre, axes_mm, spacing) -> np.ndarray:
    grids = np.meshgrid(
        *[np.arange(n) * s for n, s in zip(shape, spacing, strict=True)], indexing="ij"
    )
    total = sum(
        ((g - c * s) / a) ** 2 for g, c, s, a in zip(grids, centre, spacing, axes_mm, strict=True)
    )
    return total <= 1


def make_dataset(base: Path, plan: dict, cases: int, seed: int) -> tuple[list[str], dict]:
    from nnunetv2.training.dataloading.nnunet_dataset import nnUNetDatasetBlosc2

    configuration = plan["configurations"]["3d_fullres"]
    spacing = configuration["spacing"]
    patch = configuration["patch_size"]
    shape = tuple(int(p * 1.5) for p in patch)
    data_folder = base / configuration["data_identifier"]
    data_folder.mkdir(parents=True)
    rng = np.random.default_rng(seed)
    names = []
    for index in range(cases):
        name = f"star_{index:03d}"
        segmentation = np.zeros(shape, np.int8)
        middle = np.asarray(shape) / 2
        segmentation[_ellipsoid(shape, middle, (shape[0] * 1.0, 30.0, 45.0), spacing)] = 1
        for _ in range(1 + index % 2):
            centre = middle + rng.uniform(-0.25, 0.25, 3) * np.asarray(shape)
            segmentation[_ellipsoid(shape, centre, rng.uniform(5, 10, 3), spacing)] = 2
        image = rng.normal(0, 0.3, shape).astype(np.float32)
        image[segmentation == 1] += 1.0
        image[segmentation == 2] += 0.6
        locations = {}
        for label in (1, 2):
            points = np.argwhere(segmentation == label)
            points = points[rng.permutation(len(points))[:2000]]
            # nnU-Net stores (channel, z, y, x) rows per foreground label.
            locations[label] = np.c_[np.zeros(len(points), int), points]
        properties = {
            "spacing": list(spacing),
            "shape_before_cropping": shape,
            "bbox_used_for_cropping": [[0, n] for n in shape],
            "shape_after_cropping_and_before_resampling": shape,
            "class_locations": locations,
        }
        nnUNetDatasetBlosc2.save_case(
            image[None],
            segmentation[None],
            properties,
            str(data_folder / name),
            chunks=(1, *shape),
            blocks=(1, *shape),
        )
        names.append(name)
    dataset_json = {
        "channel_names": {"0": "CT"},
        "labels": {"background": 0, "pancreas": 1, "mass": 2},
        "numTraining": cases,
        "file_ending": ".nii.gz",
    }
    (base / "dataset.json").write_text(json.dumps(dataset_json))
    (base / "dataset_fingerprint.json").write_text("{}")
    val = names[-1:]
    (base / "splits_final.json").write_text(json.dumps([{"train": names[:-1], "val": val}]))
    return names, dataset_json


def build_plan(source: dict, patch: list[int], narrow: bool) -> dict:
    from segmentary.medical.star_completion import transfer_starc_plan

    plan = copy.deepcopy(source)
    plan["dataset_name"] = DATASET
    plan["configurations"] = {"3d_fullres": plan["configurations"]["3d_fullres"]}
    configuration = plan["configurations"]["3d_fullres"]
    configuration["patch_size"] = list(patch)
    configuration["batch_size"] = 2
    configuration["median_image_size_in_voxels"] = [float(int(p * 1.5)) for p in patch]
    if narrow:
        configuration["architecture"]["arch_kwargs"].update(copy.deepcopy(NARROW))
    transferred, _ = transfer_starc_plan(plan, {"max_instances": 4})
    return transferred


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", type=Path, required=True, help="ResEnc nnU-Net plans JSON")
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--patch", type=int, nargs=3, default=[16, 128, 128])
    parser.add_argument("--narrow", action="store_true")
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--cases", type=int, default=4)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        # Torch and nnU-Net are imported below; with any GPU visible, refuse.
        parser.error('Run with CUDA_VISIBLE_DEVICES="" (the smoke is CPU-only)')
    workdir = args.workdir.resolve()
    if workdir.exists() or args.output.exists():
        parser.error("--workdir and --output must not exist")
    for name in ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"):
        (workdir / name).mkdir(parents=True)
        os.environ[name] = str(workdir / name)
    os.environ["nnUNet_n_proc_DA"] = "0"  # noqa: SIM112 - upstream variable name
    os.environ["nnUNet_compile"] = "false"  # noqa: SIM112 - upstream variable name

    import torch

    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager

    import precompute_star_targets
    from segmentary.medical.nnunet_star_trainer import StarCPredictor, nnUNetTrainerStarC
    from segmentary.medical.star_completion import sha256_file

    record: dict[str, Any] = {"plan": str(args.plan.resolve()), "patch": args.patch}
    plan = build_plan(json.loads(args.plan.read_text()), args.patch, args.narrow)
    base = workdir / "nnUNet_preprocessed" / DATASET
    names, dataset_json = make_dataset(base, plan, args.cases, args.seed)
    plans_file = base / f"{plan['plans_name']}.json"
    plans_file.write_text(json.dumps(plan, indent=1))
    configuration = plan["configurations"]["3d_fullres"]
    # Outside nnUNet_preprocessed, as precompute_star_targets.py requires.
    targets = workdir / "starc-targets"
    started = time.monotonic()
    precompute_star_targets.main(
        [
            "--preprocessed",
            str(base / configuration["data_identifier"]),
            "--plans",
            str(plans_file),
            "--output",
            str(targets),
            "--workers",
            "2",
        ]
    )
    record["precompute_seconds"] = round(time.monotonic() - started, 2)
    manifest_sha = sha256_file(targets / "manifest.json")

    trainer = nnUNetTrainerStarC(
        plans={**copy.deepcopy(plan), "continue_training": False},
        configuration="3d_fullres",
        fold=0,
        dataset_json=dataset_json,
        device=torch.device("cpu"),
    )
    trainer.configure_star({"ray_samples": 32}, targets_dir=targets, manifest_sha256=manifest_sha)
    trainer.num_epochs = 1
    trainer.num_iterations_per_epoch = args.steps
    trainer.num_val_iterations_per_epoch = 1
    started = time.monotonic()
    trainer.run_training()
    record["train_seconds"] = round(time.monotonic() - started, 2)
    record["train_steps"] = args.steps
    log = Path(trainer.log_file).read_text()
    record["star_log"] = [line for line in log.splitlines() if "STAR-C" in line]
    record["checkpoint_final"] = (Path(trainer.output_folder) / "checkpoint_final.pth").is_file()
    losses = [
        line.split("train_loss")[-1].strip() for line in log.splitlines() if "train_loss" in line
    ]
    record["train_loss"] = float(losses[-1]) if losses else float("nan")

    network = trainer.network
    trainer.set_deep_supervision_enabled(False)
    network.eval()
    starc = network.starc
    with torch.no_grad():
        # A flat heatmap above threshold makes every tile propose: this exercises
        # tile detection, case-level NMS and case-level rendering after 2 steps.
        starc.centre_head[-1].bias.fill_(2.0)
        starc.fusion_weight.fill_(1.0)
    import blosc2

    case = names[-1]
    data = np.asarray(
        blosc2.open(urlpath=str(base / configuration["data_identifier"] / f"{case}.b2nd"))[:]
    )
    results = {}
    for two_pass in (True, False):
        predictor = StarCPredictor(
            tile_step_size=0.5,
            use_gaussian=True,
            use_mirroring=True,
            perform_everything_on_device=False,
            device=torch.device("cpu"),
            allow_tqdm=False,
            star_two_pass=two_pass,
        )
        predictor.manual_initialization(
            network,
            PlansManager(plan),
            PlansManager(plan).get_configuration("3d_fullres"),
            None,
            dataset_json,
            "nnUNetTrainerStarC",
            trainer.inference_allowed_mirroring_axes,
        )
        started = time.monotonic()
        logits = predictor.predict_sliding_window_return_logits(torch.from_numpy(data))
        results[two_pass] = logits.float()
        record["two_pass" if two_pass else "in_tile"] = {
            "seconds": round(time.monotonic() - started, 2),
            "shape": list(logits.shape),
            "finite": bool(torch.isfinite(logits.float()).all()),
            "case_detections": len(predictor.star_case_detections),
        }
    record["two_pass_differs_from_in_tile"] = not torch.equal(results[True], results[False])
    record["ok"] = bool(
        record["checkpoint_final"]
        and record["star_log"]
        and np.isfinite(record["train_loss"])
        and record["two_pass"]["finite"]
        and record["in_tile"]["finite"]
        and 0 < record["two_pass"]["case_detections"] <= 32
        and record["two_pass_differs_from_in_tile"]
    )
    args.output.write_text(json.dumps(record, indent=1))
    print(json.dumps(record))
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
