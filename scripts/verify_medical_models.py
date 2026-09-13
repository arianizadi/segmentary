#!/usr/bin/env python3
"""Exercise every scratch CT architecture and save immutable JSON evidence.

Examples (no training campaign or checkpoint is produced):
  python scripts/verify_medical_models.py --device cpu --output /tmp/ct-matrix.json
  python scripts/verify_medical_models.py --device cuda:0 --manifest audit.json \
      --splits splits.json --case-id pancreas_001 --output /data/evidence/matrix.json

Real-data mode verifies the selected files' audited hashes and permits a fully
annotated training case only. The output contains dataset identities and derived
statistics, never CT pixels, segmentation masks, or trained weights. Smoke
capacities and patch plans are explicit and are not benchmark results.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.model_registry import build_model, catalog
from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import preprocess_case, sample_patch, training_loss


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_identity() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    medical = root / "src" / "segmentary" / "medical"
    hashes = {str(path.relative_to(root)): _sha256(path) for path in sorted(medical.rglob("*.py"))}
    hashes[str(Path(__file__).resolve().relative_to(root))] = _sha256(Path(__file__))

    def git(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    status = git("status", "--porcelain")
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": None if status is None else bool(status),
        "source_sha256": hashes,
    }


def _environment(device: torch.device, threads: int) -> dict[str, Any]:
    versions = {}
    for package in (
        "torch",
        "torchvision",
        "transformers",
        "timm",
        "segmentation-models-pytorch",
        "monai",
        "nibabel",
        "numpy",
        "scipy",
        "mamba-ssm",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    result: dict[str, Any] = {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": versions,
        "device": str(device),
        "cpu_threads": threads,
        "torch_cuda_build": torch.version.cuda,
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
    }
    if device.type == "cuda":
        properties = torch.cuda.get_device_properties(device)
        result["gpu"] = {
            "name": properties.name,
            "total_memory_bytes": properties.total_memory,
            "capability": [properties.major, properties.minor],
        }
    return result


def _data_source(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    if args.manifest is None:
        if args.splits is not None or args.case_id is not None:
            raise ValueError("--splits and --case-id require --manifest")
        rng = np.random.default_rng(args.seed)
        z, y, x = np.ogrid[-1:1:96j, -1:1:96j, -1:1:96j]
        label = np.zeros((96, 96, 96), dtype=np.uint8)
        label[(x / 0.55) ** 2 + (y / 0.3) ** 2 + (z / 0.65) ** 2 < 1] = 1
        label[(x - 0.15) ** 2 + y * y + z * z < 0.12**2] = 2
        image = np.clip(0.25 + 0.2 * label + rng.normal(0, 0.02, label.shape), 0, 1).astype(
            np.float32
        )
        return {"image": image, "label": label}, {
            "kind": "synthetic",
            "shape_zyx": list(label.shape),
            "description": "seeded synthetic volume with organ and mass masks; not clinical evidence",
        }
    if args.splits is None:
        raise ValueError(
            "Real CT verification requires --splits to prove the selected case is in train"
        )
    manifest = load_manifest(args.manifest, verify_files=False)
    splits = json.loads(Path(args.splits).read_text())
    validate_splits(manifest, splits)
    cases = {case["case_id"]: case for case in manifest["cases"]}
    case_id = args.case_id
    if case_id is None:
        case_id = min(splits["train"], key=lambda key: (int(np.prod(cases[key]["shape"])), key))
    if case_id not in splits["train"]:
        raise ValueError("Selected case must belong to the validated training partition")
    case = cases[case_id]
    if case["annotation_status"] != "labeled" or case.get("label") is None:
        raise ValueError("Selected case must be fully labeled for pancreas and mass segmentation")
    for key in ("image", "label"):
        if _sha256(Path(case[key])) != case[f"{key}_sha256"]:
            raise ValueError(f"Selected {key} no longer matches its audited hash")
    config = TorchConfig(
        workspace=str(Path(args.output).resolve().parent),
        mode="3d",
        patch_size=(32, 32, 32),
        spacing_mm=tuple(args.spacing_mm),
        hu_window=tuple(args.hu_window),
        purpose="smoke",
        augment=False,
    )
    data = preprocess_case(case, config, with_label=True)
    return data, {
        "kind": "audited_real_training_ct",
        "manifest_fingerprint": manifest["fingerprint"],
        "split_fingerprint": splits["fingerprint"],
        "partition": "train",
        "case_token": hashlib.sha256(case_id.encode()).hexdigest(),
        "image_sha256": case["image_sha256"],
        "label_sha256": case["label_sha256"],
        "grouping_status": case.get("grouping_status"),
        "shape_zyx": list(data["image"].shape),
        "spacing_mm_ras_xyz": list(config.spacing_mm),
        "hu_window": list(config.hu_window),
        "hash_scope": "Selected image and label rehashed; other cases not reread",
    }


def _verify_one(
    metadata: dict[str, Any], data: dict[str, Any], args: argparse.Namespace, device: torch.device
) -> dict[str, Any]:
    name = metadata["name"]
    dimensions = metadata.get("spatial_dims", metadata.get("dimensions"))
    if dimensions not in (2, 3):
        raise ValueError(f"{name}: missing valid spatial dimension metadata")
    patch = tuple(metadata["smoke_patch_size"])
    batch_size = metadata.get("smoke_batch_size", 2)
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError(f"{name}: invalid smoke batch size")
    options = metadata["smoke_options"] if args.profile == "smoke" else {}
    config = TorchConfig(
        workspace=str(Path(args.output).resolve().parent),
        model=name,
        mode="2.5d" if dimensions == 2 else "3d",
        context_slices=5 if dimensions == 2 else 1,
        patch_size=patch,
        spacing_mm=tuple(args.spacing_mm),
        hu_window=tuple(args.hu_window),
        batch_size=batch_size,
        seed=args.seed,
        purpose="smoke",
        epochs=1,
        steps_per_epoch=1,
        learning_rate=0.001,
        weight_decay=0.0,
        augment=False,
        foreground_probability=1.0,
        model_options=options,
        gpu=str(device.index or 0) if device.type == "cuda" else "cpu",
    )
    rng = np.random.default_rng(args.seed)
    samples = [sample_patch(data, config, rng) for _ in range(batch_size)]
    images = (
        torch.from_numpy(np.stack([sample[0] for sample in samples]))
        .to(device)
        .requires_grad_(True)
    )
    targets = torch.from_numpy(np.stack([sample[1] for sample in samples])).to(device)
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
    model = build_model(
        name, in_channels=images.shape[1], num_classes=3, patch_size=patch, model_options=options
    ).to(device)
    model.train()
    # A single SGD update proves optimizer connectivity while avoiding the
    # adaptive optimizer state and compute budget of an actual training run.
    optimizer = torch.optim.SGD(model.parameters(), lr=config.learning_rate)
    loss = training_loss(model, images, targets)
    if loss.ndim != 0 or not torch.isfinite(loss):
        raise ValueError("training loss must be a finite scalar")
    loss.backward()
    if images.grad is None or not torch.isfinite(images.grad).all() or not images.grad.abs().any():
        raise ValueError("input gradient must be finite and nonzero")
    parameters = [
        (key, parameter) for key, parameter in model.named_parameters() if parameter.requires_grad
    ]
    missing = [key for key, parameter in parameters if parameter.grad is None]
    nonfinite = [
        key
        for key, parameter in parameters
        if parameter.grad is not None and not torch.isfinite(parameter.grad).all()
    ]
    if missing or nonfinite:
        raise ValueError(
            f"parameter gradient coverage failed: missing={missing}, nonfinite={nonfinite}"
        )
    # Match the training harness's clipping policy. A tiny real CT patch can
    # produce very large but finite BatchNorm gradients (observed with PIDNet);
    # an unconstrained diagnostic SGD step can overflow subsequent activations.
    # Keep all existing finite/coverage checks, reject nonfinite aggregate norms,
    # and record the actual clipping rather than silently changing the data.
    gradient_norm_before = torch.nn.utils.clip_grad_norm_(
        model.parameters(), config.gradient_clip, error_if_nonfinite=True
    )
    gradient_norm_after = torch.linalg.vector_norm(
        torch.stack(
            [
                torch.linalg.vector_norm(parameter.grad.detach().float())
                for _, parameter in parameters
            ]
        )
    )
    changed_name, changed_parameter = next(
        (
            (key, parameter)
            for key, parameter in parameters
            if parameter.grad is not None and parameter.grad.abs().any()
        ),
        (None, None),
    )
    if changed_parameter is None:
        raise ValueError("all parameter gradients are zero")
    before = changed_parameter.detach().clone()
    optimizer.step()
    if not all(torch.isfinite(parameter).all() for _, parameter in parameters):
        raise ValueError("optimizer produced nonfinite parameters")
    delta = (changed_parameter.detach() - before).abs()
    if not delta.any():
        raise ValueError("optimizer changed no value in the selected nonzero-gradient parameter")
    model.eval()
    with torch.no_grad():
        outputs = model(images.detach())
    if outputs.shape != (batch_size, 3, *patch) or not torch.isfinite(outputs).all():
        raise ValueError(f"invalid inference logits shape/values: {tuple(outputs.shape)}")
    resolved = getattr(model, "medical_model_metadata", None)
    if resolved is None:
        resolved = getattr(model, "architecture_metadata", None)
    if resolved is None:
        resolved = {
            **metadata,
            "resolved_options": getattr(model, "resolved_model_options", options),
        }
    return {
        "model": name,
        "passed": True,
        "input_shape": list(images.shape),
        "output_shape": list(outputs.shape),
        "target_class_voxels": torch.bincount(targets.flatten(), minlength=3).cpu().tolist(),
        "loss": float(loss.detach()),
        "loss_contract": metadata.get("training_loss", metadata.get("objective")),
        "optimizer": {
            "name": "SGD",
            "learning_rate": config.learning_rate,
            "steps": 1,
            "gradient_clip_max_norm": config.gradient_clip,
        },
        "gradient_norm_before_clip": float(gradient_norm_before),
        "gradient_norm_after_clip": float(gradient_norm_after),
        "gradient_clipping_applied": bool(gradient_norm_before > config.gradient_clip),
        "changed_parameter": changed_name,
        "max_parameter_delta": float(delta.max()),
        "all_trainable_parameters_have_finite_gradients": True,
        "parameter_tensors": len(parameters),
        "parameters": sum(parameter.numel() for _, parameter in parameters),
        "requested_model_options": options,
        "resolved_model_metadata": resolved,
        "config": asdict(config),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite {output}")
    args.output = output
    if args.profile not in ("smoke", "standard"):
        raise ValueError("profile must be smoke or standard")
    if not re.fullmatch(r"cpu|cuda(?::[0-9]+)?", args.device):
        raise ValueError("--device must be cpu, cuda or cuda:N")
    if args.threads < 1 or not 0 <= args.seed < 2**32:
        raise ValueError("threads must be positive and seed a uint32")
    device = torch.device(args.device)
    if device.type == "cuda":
        if not torch.cuda.is_available() or (device.index or 0) >= torch.cuda.device_count():
            raise ValueError(f"requested CUDA device is unavailable: {device}")
        torch.cuda.set_device(device)
    entries = catalog()
    names = [entry["name"] for entry in entries]
    selected = args.models or names
    if len(selected) != len(set(selected)) or set(selected) - set(names):
        raise ValueError(
            f"Models must be distinct catalog names; unknown={sorted(set(selected) - set(names))}"
        )
    entries = [next(entry for entry in entries if entry["name"] == name) for name in selected]
    torch.set_num_threads(args.threads)
    started = time.monotonic()
    data, data_identity = _data_source(args)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "purpose": "architecture_execution_smoke",
        "quality_or_convergence_claim": False,
        "capacity_profile": args.profile,
        "patch_policy": "Use each architecture smoke patch and batch at requested capacity; not full-volume training",
        "started_at": datetime.now(UTC).isoformat(),
        "source": _source_identity(),
        "environment": _environment(device, args.threads),
        "data": data_identity,
        "catalog_size": len(names),
        "selected_models": selected,
        "seed": args.seed,
        "results": [],
    }
    for metadata in entries:
        gc.collect()
        start = time.monotonic()
        try:
            if device.type == "cuda":
                torch.cuda.empty_cache()
                torch.cuda.synchronize(device)
                torch.cuda.reset_peak_memory_stats(device)
            result = _verify_one(metadata, data, args, device)
        except Exception as exc:
            result = {
                "model": metadata["name"],
                "passed": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "model_metadata": metadata,
            }
        result["peak_cuda_allocated_bytes"] = None
        result["peak_cuda_reserved_bytes"] = None
        if device.type == "cuda":
            try:
                torch.cuda.synchronize(device)
                result["peak_cuda_allocated_bytes"] = torch.cuda.max_memory_allocated(device)
                result["peak_cuda_reserved_bytes"] = torch.cuda.max_memory_reserved(device)
                gc.collect()
                torch.cuda.empty_cache()
            except Exception as exc:
                # A poisoned CUDA context must still produce failure evidence.
                # Subsequent models each attempt their own preflight and are
                # recorded as failed if the context cannot recover.
                result["passed"] = False
                result["cuda_context_error"] = str(exc)
        result["wall_seconds"] = time.monotonic() - start
        evidence["results"].append(result)
        print(
            json.dumps({key: result[key] for key in ("model", "passed", "wall_seconds")}),
            flush=True,
        )
        gc.collect()
    evidence["passed_count"] = sum(result["passed"] for result in evidence["results"])
    evidence["failed_count"] = len(evidence["results"]) - evidence["passed_count"]
    evidence["passed"] = evidence["failed_count"] == 0
    evidence["wall_seconds"] = time.monotonic() - started
    evidence["finished_at"] = datetime.now(UTC).isoformat()
    atomic_write_json(output, evidence)
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--device", required=True, help="cpu or explicit CUDA device, e.g. cuda:0")
    parser.add_argument(
        "--models", nargs="+", help="catalog names; default is the complete current catalog"
    )
    parser.add_argument(
        "--profile",
        choices=("standard", "smoke"),
        default="smoke",
        help="standard builds default capacity on declared smoke patches; smoke reduces capacity explicitly",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--splits", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument(
        "--output", type=Path, required=True, help="new immutable JSON evidence path"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument(
        "--spacing-mm", nargs=3, type=float, default=(1.5, 1.5, 2.5), metavar=("X", "Y", "Z")
    )
    parser.add_argument(
        "--hu-window", nargs=2, type=float, default=(-100.0, 240.0), metavar=("LOW", "HIGH")
    )
    args = parser.parse_args(argv)
    try:
        evidence = run(args)
    except (ValueError, FileExistsError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(
        json.dumps(
            {
                "passed": evidence["passed"],
                "passed_count": evidence["passed_count"],
                "failed_count": evidence["failed_count"],
                "output": str(args.output),
            }
        ),
        flush=True,
    )
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
