#!/usr/bin/env python3
"""Evaluate published Cityscapes Swin-T Mask2Former weights with recorded protocols.

This never trains or chooses thresholds. A subset is integration evidence, not a
full Cityscapes leaderboard reproduction. COCO mask AP differs from the official
Cityscapes instance evaluator; both task reports use Segmentary preprocessing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

import torch
from huggingface_hub import model_info

from segmentary.config import ModelConfig
from segmentary.objects.checkpoint_model import model_spec
from segmentary.objects.config import ObjectConfig, ObjectDataConfig
from segmentary.objects.model_factory import build_object_model
from segmentary.objects.reports import run_report
from segmentary.objects.runner import write_json
from segmentary.utils.seed import seed_everything


def validate_initializer(initialization: dict) -> dict:
    """Permit only audited Swin transport differences; reject random active weights."""
    info = initialization["loading_info"]
    allowed_missing = {
        "model.pixel_level_module.encoder.swin.layernorm.weight",
        "model.pixel_level_module.encoder.swin.layernorm.bias",
    }
    missing = set(info.get("missing_keys", [])) - allowed_missing
    unexpected = [
        key
        for key in info.get("unexpected_keys", [])
        if not key.endswith(".relative_position_index")
    ]
    if missing or unexpected or info.get("mismatched_keys") or info.get("error_msgs"):
        raise ValueError(f"Published initializer has unaudited loading differences: {info}")
    return {
        "missing_final_norm": "SwinBackbone returns normalized per-stage reshaped_hidden_states; the final SwinModel.layernorm output is unused. Perturbation and absent-gradient regression test verifies Mask2Former path.",
        "unexpected_relative_position_index": "Swin recomputes this deterministic non-persistent buffer from window_size; checkpoint copy is unused.",
        "source": "transformers/models/swin/modeling_swin.py: SwinBackbone.forward and SwinRelativePositionBias.__init__",
    }


def benchmark(prepared: Path, output: Path, device: str, tasks: list[str], memory_fraction: float):
    if not 0 < memory_fraction <= 1:
        raise ValueError("memory_fraction must be in (0,1]")
    if str(device).startswith("cuda"):
        torch.cuda.set_per_process_memory_fraction(memory_fraction, device)
    torch.set_num_threads(2)
    manifest = json.loads((prepared / "manifest.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for task in tasks:
        seed_everything(0)
        initializer = f"facebook/mask2former-swin-tiny-cityscapes-{task}"
        revision = model_info(initializer).sha
        if not revision:
            raise ValueError("Hub did not supply a pinned revision")
        categories = json.loads((prepared / f"val/{task}.json").read_text())["categories"]
        data = {}
        for split in ("train", "val"):
            data[split] = ObjectDataConfig(
                images=manifest["splits"][split]["images"],
                annotations=str((prepared / split / f"{task}.json").resolve()),
                panoptic_masks=str((prepared / split / "panoptic").resolve())
                if task == "panoptic"
                else None,
            )
        config = ObjectConfig(
            task=cast(Literal["instance", "panoptic"], task),
            model=ModelConfig(
                arch="mask2former_swin_tiny", checkpoint=initializer, revision=revision
            ),
            train=data["train"],
            val=data["val"],
            output=str(output / task / "unused-training"),
            image_size=[512, 1024],
            device=device,
            score_threshold=0.05,
            overlap_threshold=0.8,
        )
        model = build_object_model(config.model, len(categories))
        upstream = cast(Any, model.model).config

        def normalized(name):
            return name.lower().replace("-", " ").replace("_", " ")

        expected = [normalized(c["name"]) for c in categories]
        actual = [normalized(upstream.id2label[i]) for i in range(upstream.num_labels)]
        if actual != expected:
            raise ValueError(f"Published class order differs: {actual} != {expected}")
        initialization = getattr(model, "object_initialization", None)
        if not isinstance(initialization, dict):
            raise ValueError("Initializer did not record loading provenance")
        loading_audit = validate_initializer(initialization)
        checkpoint = output / task / "published.pt"
        checkpoint.parent.mkdir()
        torch.save(
            {
                "schema": "segmentary-objects-v1",
                "task": task,
                "categories": categories,
                "architecture": model_spec(model),
                "config": asdict(config),
                "model": model.state_dict(),
                "step": 0,
                "purpose": "published pretrained evaluation, no training",
            },
            checkpoint,
        )
        del model
        write_json(
            output / task / "recipe.json",
            {
                "config": asdict(config),
                "dataset_manifest": manifest,
                "memory_fraction": memory_fraction,
                "initialization_seed": 0,
                "initialization": initialization,
                "loading_audit": loading_audit,
                "purpose": "held-out subset integration check"
                if manifest["limit_per_split"]
                else "full validation",
                "preprocessing": "fixed512x1024 resize; ImageNet normalization; native-resolution evaluation; no TTA",
            },
        )
        result = run_report(
            config,
            checkpoint,
            output / task / "report",
            reference=True,
            warmup=2,
            name=f"Mask2Former Swin-T / Cityscapes {task}",
        )
        if not (result.get("reference") or {}).get("passed", False):
            raise RuntimeError(
                f"Official evaluator parity failed; inspect {output / task / 'report'}"
            )
        results.append(
            {
                "task": task,
                "report": str(output / task / "report"),
                "reference": result.get("reference"),
            }
        )
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    write_json(output / "validation.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--tasks", nargs="+", choices=["instance", "panoptic"], default=["instance", "panoptic"]
    )
    parser.add_argument("--memory-fraction", type=float, default=0.15)
    args = parser.parse_args()
    print(
        json.dumps(
            benchmark(args.prepared, args.out, args.device, args.tasks, args.memory_fraction)
        )
    )


if __name__ == "__main__":
    main()
