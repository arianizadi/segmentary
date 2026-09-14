#!/usr/bin/env python3
"""Measure native training-set fit and a bounded scratch two-case memorization.

This is an in-sample engineering diagnostic, never validation or test performance.
The historical control is verified by its frozen source before its weights are read.
Only deterministically selected training image/label payloads are opened. All masks,
review images, patient keys, and checkpoints stay in the supplied server directory.
The independent fit loop uses the production sampler, objective, native export and
scorer. Its declared changes are two training cases, disabled augmentation, and a
short polynomial schedule; training-fit scores do not select clinical thresholds.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import io
import json
import math
import os
import random
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from segmentary.medical.backend import _atomic_json, _digest, _json, _lock, _sha
from segmentary.medical.data import load_manifest, validate_splits
from segmentary.medical.torch_config import TorchConfig


def select_cases(manifest: dict, splits: dict, count: int = 4) -> list[dict]:
    """Evenly spread native voxel-count ranks using audited training metadata only."""
    validate_splits(manifest, splits)
    if type(count) is not int or count < 2 or count > len(splits["train"]):
        raise ValueError("Select at least two and no more than the available training cases")
    lookup = {case["case_id"]: case for case in manifest["cases"]}
    ordered = sorted(
        [lookup[key] for key in splits["train"]],
        key=lambda case: (math.prod(case["shape"]), case["case_id"]),
    )
    selected = [ordered[index * (len(ordered) - 1) // (count - 1)] for index in range(count)]
    if any(case["annotation_status"] != "labeled" or not case.get("label") for case in selected):
        raise ValueError("Training-fit diagnostics require fully labeled training cases")
    return selected


def fit_config(original: dict, output: Path, gpu: str, steps: int, interval: int) -> TorchConfig:
    if type(steps) is not int or type(interval) is not int or steps < 1 or interval < 1:
        raise ValueError("steps and interval must be positive integers")
    if steps % interval:
        raise ValueError("steps must be divisible by the checkpoint interval")
    if gpu == "0":
        raise ValueError("GPU 0 is reserved for the ongoing nnU-Net campaign")
    return dataclasses.replace(
        TorchConfig(**original),
        workspace=str(output),
        gpu=gpu,
        backend_python=sys.executable,
        cache_root=str(output.parent / "cache"),
        augment=False,
        rotation_probability=0.0,
        intensity_scale_probability=0.0,
        epochs=steps // interval,
        steps_per_epoch=interval,
        validation_interval=1,
        purpose="overfit",
    )


def source_record() -> dict:
    from segmentary.medical.torch_backend import _code

    return {
        "medical_source_sha256": _code(),
        "diagnostic_script_sha256": _sha(Path(__file__).resolve()),
        "checkpoint_helper_sha256": _sha(REPO / "scripts" / "medical_checkpoint_diagnostic.py"),
    }


def checked_cases(cases: list[dict]) -> None:
    for case in cases:
        for role in ("image", "label"):
            if _sha(Path(case[role])) != case[f"{role}_sha256"]:
                raise ValueError(f"Selected training {role} changed from audited bytes")


def separate_output(output: Path, workspace: Path, historical_source: Path) -> None:
    for protected in (workspace.resolve(), historical_source.resolve(), REPO.resolve()):
        if output.resolve() == protected or protected in output.resolve().parents:
            raise ValueError(
                "Diagnostic output must be separate from source and historical workspace"
            )


def native_evaluate(
    model: Any,
    cases: list[dict],
    config: TorchConfig,
    manifest_path: Path,
    output: Path,
    device: Any,
    provenance: dict,
) -> dict:
    """Use the same native export and reference scorer as the clinical campaign."""
    from segmentary.medical.evaluation import evaluate_predictions
    from segmentary.medical.torch_backend import _inference_cache
    from segmentary.medical.torch_data import iter_predictions

    output.mkdir(parents=True, exist_ok=False)
    checked_cases(cases)
    model.eval()
    statuses = []
    started = time.monotonic()
    with (
        _inference_cache(config) as cache,
        contextlib.closing(
            iter_predictions(
                model,
                cases,
                config,
                device,
                output_directory=output / "predictions",
                cache=cache,
            )
        ) as results,
    ):
        for result in results:
            if result.error is not None:
                raise result.error
            statuses.append(
                {
                    "case_id": result.case["case_id"],
                    "wall_seconds": result.wall_seconds,
                    "component_seconds": result.timings,
                    "prediction_statistics": result.statistics,
                }
            )
            _atomic_json(
                output / "prediction-status.json",
                {"cases": statuses, "total_cases": len(cases), "provenance": provenance},
            )
    report = evaluate_predictions(
        manifest_path,
        output / "predictions",
        output / "evaluation",
        case_ids=[case["case_id"] for case in cases],
        pancreas_include_mass=True,
        bootstrap_samples=1000,
        seed=config.seed,
        review_overlays=True,
    )
    if report["coverage"]["status_counts"] != {"ok": len(cases)}:
        raise RuntimeError("Training-fit native evaluation contains failed cases")
    if report["coverage"]["review_failures"]:
        raise RuntimeError("Training-fit native review overlay export failed")
    if any(report["regions"][region]["dice"]["mean"] is None for region in ("mass", "pancreas")):
        raise ValueError("Diagnostic subset needs at least one positive reference for each region")
    for case in cases:
        token = hashlib.sha256(case["case_id"].encode()).hexdigest()[:20]
        orthogonal_review(
            case,
            output / "predictions" / f"{case['case_id']}.nii.gz",
            output / "orthogonal-review" / f"review-{token}.png",
        )
    summary = {
        "completed": True,
        "scope": "in_sample_training_fit_only_not_generalization",
        "cases": len(cases),
        "mean_mass_dice": report["regions"]["mass"]["dice"]["mean"],
        "mean_pancreas_dice": report["regions"]["pancreas"]["dice"]["mean"],
        "wall_seconds": time.monotonic() - started,
        "provenance": provenance,
        "interpretation": "Descriptive fit only; a small selected training subset cannot estimate generalization or establish a pipeline pass/fail threshold",
    }
    _atomic_json(output / "summary.json", summary)
    return summary


def orthogonal_review(case: dict, prediction_path: Path, output: Path) -> None:
    """Unmodified windowed CT beside annotations/prediction across five planes."""
    import nibabel as nib
    import numpy as np
    from PIL import Image, ImageDraw, ImageOps

    volumes = [
        nib.as_closest_canonical(nib.load(path))
        for path in (case["image"], case["label"], prediction_path)
    ]
    ct, truth, prediction = [np.asarray(volume.dataobj) for volume in volumes]
    target = truth == 2
    if not target.any():
        target = truth > 0
    center = (
        tuple(int(np.median(axis)) for axis in np.nonzero(target))
        if target.any()
        else tuple(size // 2 for size in ct.shape)
    )
    planes = [
        (2, max(0, center[2] - 1), "Axial: adjacent below"),
        (2, center[2], "Axial: reference center"),
        (2, min(ct.shape[2] - 1, center[2] + 1), "Axial: adjacent above"),
        (1, center[1], "Coronal: reference center"),
        (0, center[0], "Sagittal: reference center"),
    ]
    width, height = 384, 288
    montage = Image.new("RGB", (width * 3, (height + 32) * len(planes) + 48), "black")
    draw = ImageDraw.Draw(montage)
    draw.text((8, 6), "CT only | Reference labels | Model prediction", fill="white")
    draw.text(
        (8, 23),
        "Green: pancreas class 1; red: mass class 2. Label review, not a diagnosis.",
        fill="white",
    )
    spacing = volumes[0].header.get_zooms()
    for row, (axis, index, title) in enumerate(planes):
        gray = np.rot90(np.clip((np.take(ct, index, axis=axis) + 125) / 350, 0, 1))
        base = np.repeat((gray * 255).astype(np.uint8)[:, :, None], 3, axis=2)
        other = [position for position in range(3) if position != axis]
        physical_size = (
            max(1, round(base.shape[1] * spacing[other[0]])),
            max(1, round(base.shape[0] * spacing[other[1]])),
        )
        for column, mask in enumerate((None, truth, prediction)):
            rgb = base.copy()
            if mask is not None:
                plane = np.rot90(np.take(mask, index, axis=axis))
                for value, color in ((1, (0, 220, 90)), (2, (255, 60, 70))):
                    selected = plane == value
                    rgb[selected] = np.rint(rgb[selected] * 0.55 + np.asarray(color) * 0.45).astype(
                        np.uint8
                    )
            panel = Image.fromarray(rgb).resize(physical_size, Image.Resampling.BILINEAR)
            panel = ImageOps.contain(panel, (width, height), Image.Resampling.BILINEAR)
            left = column * width + (width - panel.width) // 2
            top = 48 + row * (height + 32)
            montage.paste(panel, (left, top + 24 + (height - panel.height) // 2))
            draw.text((column * width + 8, top + 4), title, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    montage.save(output)


def _load_fit_checkpoint(config: TorchConfig, identity: str, origin: dict) -> dict:
    import torch

    index = _json(config.root / "checkpoint-index.json")
    if index["identity"] != identity or index["initialization"] != "scratch":
        raise ValueError("Diagnostic checkpoint identity changed")
    item = index["files"]["checkpoint_latest.pth"]
    if Path(item["path"]).name != item["path"]:
        raise ValueError("Diagnostic checkpoint path escapes its workspace")
    data = (config.root / "checkpoints" / item["path"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise ValueError("Diagnostic checkpoint content changed")
    state = torch.load(io.BytesIO(data), map_location="cpu", weights_only=False)
    if state["identity"] != identity or state["origin"] != origin:
        raise ValueError("Diagnostic checkpoint origin changed")
    return state


def memorize(
    config: TorchConfig,
    cases: list[dict],
    manifest_path: Path,
    binding: dict,
    *,
    resume: bool = False,
) -> dict:
    """Fresh scratch fit; same production loss/optimizer and exported native scores."""
    import numpy as np
    import torch

    from segmentary.medical.model_registry import build_model
    from segmentary.medical.torch_backend import _save_checkpoint, _seed, _state_hash
    from segmentary.medical.torch_batches import BatchStream
    from segmentary.medical.torch_cache import build_cached_case, load_cached_case
    from segmentary.medical.torch_data import training_loss
    from segmentary.medical.torch_numerics import clip_grad_norm_

    config.root.mkdir(parents=True, exist_ok=True)
    identity = _digest(binding)
    _seed(config)
    device = torch.device("cpu" if config.gpu == "cpu" else "cuda:0")
    model = build_model(
        config.model,
        in_channels=config.context_slices,
        patch_size=config.patch_size,
        model_options=config.model_options,
    ).to(device)
    origin = {
        "initialization": "scratch",
        "initial_state_sha256": _state_hash(model),
        "identity": identity,
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "external_weight_loads": 0,
    }
    if resume:
        if _json(config.root / "scratch-origin.json") != origin:
            raise ValueError("Fresh diagnostic initialization differs from recorded scratch origin")
    else:
        if (config.root / "scratch-origin.json").exists():
            raise FileExistsError("Existing fit requires explicit --resume")
        _atomic_json(config.root / "scratch-origin.json", origin)
        _atomic_json(config.root / "resolved-config.json", dataclasses.asdict(config))
        _atomic_json(config.root / "diagnostic-binding.json", binding)
    groups = [
        {
            "params": [
                parameter
                for parameter in model.parameters()
                if parameter.requires_grad
                and bool(getattr(parameter, "_no_weight_decay", False)) == exempt
            ],
            "weight_decay": 0.0 if exempt else config.weight_decay,
        }
        for exempt in (False, True)
    ]
    optimizer = torch.optim.AdamW(groups, lr=config.learning_rate)
    total_steps = config.epochs * config.steps_per_epoch
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda step: max(0.0, 1 - step / total_steps) ** 0.9
    )
    scaler = torch.amp.GradScaler("cuda", enabled=config.precision == "fp16")
    rng = np.random.default_rng(config.seed)
    completed, best, summaries = 0, -1.0, []
    if resume:
        state = _load_fit_checkpoint(config, identity, origin)
        model.load_state_dict(state["model"], strict=True)
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        scaler.load_state_dict(state["scaler"])
        completed, best, summaries = state["step"], state["best"], state["summaries"]
        random.setstate(state["python_rng"])
        np.random.set_state(state["numpy_rng"])
        rng.bit_generator.state = state["sampling_rng"]
        torch.set_rng_state(state["torch_rng"])
        if device.type == "cuda":
            torch.cuda.set_rng_state_all(state["cuda_rng"])
        del state
    records = {}
    for case in cases:
        record = build_cached_case(case, config, config.cache_root or config.root / "cache")
        records[case["case_id"]] = load_cached_case(record)
    _atomic_json(config.root / "cache-membership.json", {"train_cases": list(records)})

    def save(names: list[str]) -> None:
        _save_checkpoint(
            config,
            {
                "identity": identity,
                "origin": origin,
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
                "scaler": scaler.state_dict(),
                "step": completed,
                "best": best,
                "summaries": summaries,
                "python_rng": random.getstate(),
                "numpy_rng": np.random.get_state(),
                "sampling_rng": rng.bit_generator.state,
                "torch_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state_all() if device.type == "cuda" else None,
            },
            names,
        )

    def evaluate(step: int) -> dict:
        # A partial interrupted export remains an auditable failed attempt. A new
        # attempt is written beside it; no predictions or reports are overwritten.
        base = config.root / "fit-evaluations" / f"step-{step:06d}"
        attempt = 0
        output = base / f"attempt-{attempt:03d}"
        while output.exists():
            attempt += 1
            output = base / f"attempt-{attempt:03d}"
        return native_evaluate(
            model,
            cases,
            config,
            manifest_path,
            output,
            device,
            {"diagnostic_identity": identity, "step": step, "initialization": "scratch"},
        )

    if not resume:
        summaries.append({"step": 0, **evaluate(0)})
        save(["checkpoint_latest.pth"])
    scheduled_evaluations = {min(100, total_steps), min(500, total_steps), total_steps}
    scheduled_evaluations.update(range(1000, total_steps + 1, 1000))
    started = time.monotonic()
    losses = []
    with BatchStream(config, list(records), records.__getitem__, rng, device) as batches:
        while completed < total_steps:
            model.train()
            images, labels = next(batches)
            optimizer.zero_grad(set_to_none=True)
            dtype = torch.bfloat16 if config.precision == "bf16" else torch.float16
            with torch.autocast(
                device_type=device.type, dtype=dtype, enabled=config.precision != "fp32"
            ):
                loss = training_loss(model, images, labels)
            if not torch.isfinite(loss):
                raise ValueError("Non-finite diagnostic training loss")
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            clip_grad_norm_(model.parameters(), config.gradient_clip)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            completed += 1
            losses.append(float(loss.detach()))
            if completed % config.progress_interval == 0 or completed == total_steps:
                _atomic_json(
                    config.root / "progress.json",
                    {
                        "phase": "train",
                        "step": completed,
                        "target_steps": total_steps,
                        "loss": losses[-1],
                        "learning_rate": scheduler.get_last_lr()[0],
                        "updated_at": time.time(),
                    },
                )
            names = ["checkpoint_latest.pth"]
            if completed in scheduled_evaluations:
                summary = {"step": completed, **evaluate(completed)}
                summaries.append(summary)
                if summary["mean_mass_dice"] > best:
                    best = summary["mean_mass_dice"]
                    names.append("checkpoint_best.pth")
            if completed % config.steps_per_epoch == 0 or completed in scheduled_evaluations:
                if completed == total_steps:
                    names.append("checkpoint_final.pth")
                save(names)
                _atomic_json(
                    config.root / "metrics" / f"step-{completed:06d}.json",
                    {
                        "step": completed,
                        "loss": float(np.mean(losses)),
                        "learning_rate": scheduler.get_last_lr()[0],
                        "evaluations": summaries,
                        "wall_seconds_this_invocation": time.monotonic() - started,
                    },
                )
                losses = []
    result = {
        "completed": True,
        "steps": completed,
        "early_stopping": False,
        "best_training_mass_dice": best,
        "evaluations": summaries,
        "identity": identity,
        "scope": "in_sample_memorization_only",
        "success_threshold": None,
        "interpretation": "Failure to fit within this bounded budget is evidence to investigate, not proof of a pipeline bug; fit success does not establish generalization",
    }
    _atomic_json(config.root / "training-result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--run-id", default="dynunet-control-seed0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gpu", default="7")
    parser.add_argument("--subset-cases", type=int, default=4)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--checkpoint-interval", type=int, default=100)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    from benchmark_medical_inference import check_idle
    from medical_checkpoint_diagnostic import verified_historical_checkpoint
    from segmentary.medical.torch_backend import _seed

    root = args.output.resolve()
    if args.gpu == "0":
        raise ValueError("GPU 0 is reserved for the ongoing nnU-Net campaign")
    if root.exists() and not args.resume:
        raise FileExistsError("Use a fresh diagnostic output or explicit --resume")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if args.gpu != "cpu" and inherited is not None and args.gpu not in inherited.split(","):
        raise ValueError("Diagnostic GPU exceeds inherited CUDA_VISIBLE_DEVICES")
    lock_root = Path(
        os.environ.get(
            "SEGMENTARY_MEDICAL_LOCK_DIR",
            str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
        )
    )
    with (
        verified_historical_checkpoint(args.campaign.resolve(), args.run_id) as reference,
        contextlib.ExitStack() as stack,
    ):
        separate_output(
            root, Path(reference["config"]["workspace"]), Path(reference["training_source_root"])
        )
        if args.gpu != "cpu":
            stack.enter_context(_lock(lock_root / f"gpu-{args.gpu}.lock"))
            check_idle(args.gpu)
        import torch

        from segmentary.medical.model_registry import build_model

        if torch.cuda.is_initialized():
            raise RuntimeError("CUDA initialized before diagnostic GPU binding")
        os.environ["CUDA_VISIBLE_DEVICES"] = "" if args.gpu == "cpu" else args.gpu
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        manifest_path = Path(reference["binding"]["manifest_path"])
        splits_path = Path(reference["binding"]["splits_path"])
        manifest, splits = load_manifest(manifest_path, verify_files=False), _json(splits_path)
        cases = select_cases(manifest, splits, args.subset_cases)
        memorize_cases = [cases[0], cases[len(cases) // 2]]
        checked_cases(cases)
        config = fit_config(
            reference["config"],
            root / "memorization",
            args.gpu,
            args.steps,
            args.checkpoint_interval,
        )
        source = source_record()
        binding = {
            "schema_version": 1,
            "kind": "training_fit_diagnostic",
            "config": json.loads(json.dumps(dataclasses.asdict(config))),
            "source": source,
            "reference_checkpoint_sha256": reference["checkpoint_sha256"],
            "reference_training_source_commit": reference["training_source_commit"],
            "manifest_sha256": _sha(manifest_path),
            "splits_sha256": _sha(splits_path),
            "evaluation_training_cases": [case["case_id"] for case in cases],
            "memorization_training_cases": [case["case_id"] for case in memorize_cases],
            "selection": "Evenly spread ranks by native voxel count; first and middle selected for memorization; ties ordered by case ID; no performance or held-out labels used",
            "scope": "Intentional train/evaluation overlap within training only; no validation/test payloads; no claim of independent performance",
        }
        if args.resume:
            if _json(root / "diagnostic-plan.json") != binding:
                raise ValueError("Diagnostic plan/source/data/config changed; use a fresh output")
        else:
            root.mkdir(parents=True)
            _atomic_json(root / "diagnostic-plan.json", binding)
            _atomic_json(
                root / "historical-verification.json",
                {key: value for key, value in reference.items() if key != "state"},
            )
        _seed(config)
        device = torch.device("cpu" if args.gpu == "cpu" else "cuda:0")
        baseline_path = root / "baseline-training-fit"
        if not (baseline_path / "summary.json").exists():
            if baseline_path.exists():
                raise RuntimeError(
                    "Partial baseline export exists; preserve it and use a fresh output"
                )
            model = build_model(
                config.model,
                in_channels=config.context_slices,
                patch_size=config.patch_size,
                model_options=config.model_options,
            ).to(device)
            model.load_state_dict(reference["state"]["model"], strict=True)
            baseline_config = dataclasses.replace(
                TorchConfig(**reference["config"]),
                workspace=str(baseline_path),
                gpu=args.gpu,
                cache_root=str(root / "cache"),
                backend_python=sys.executable,
            )
            native_evaluate(
                model,
                cases,
                baseline_config,
                manifest_path,
                baseline_path,
                device,
                {
                    "checkpoint_sha256": reference["checkpoint_sha256"],
                    "training_source_commit": reference["training_source_commit"],
                    "evaluation_source": source,
                    "inference_blending": "uniform",
                },
            )
            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()
        # Drop historical weights before constructing the independent random model.
        del reference["state"]
        resume_fit = args.resume and (config.root / "checkpoint-index.json").exists()
        result = memorize(config, memorize_cases, manifest_path, binding, resume=resume_fit)
        checked_cases(cases)
        if source_record() != source:
            raise ValueError("Diagnostic source changed during execution")
        summary = {
            "completed": True,
            "baseline_training_fit": _json(baseline_path / "summary.json"),
            "memorization": result,
            "scope": "Training-only fit diagnostic; not an independent accuracy comparison",
        }
    # The historical reader rechecks original artifact immutability on exit.
    # Do not mark the entire diagnostic complete until those guards succeed.
    _atomic_json(root / "summary.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
