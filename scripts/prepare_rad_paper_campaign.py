"""Prepare explicit RAD paper choices as CPU-only YAML and frozen queue metadata.

This helper writes a new preparation directory. The existing campaign planner
and prioritizer are separate steps. No campaign, worker or GPU is initialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_rad_allclasses import digest, read, write
from scripts.prioritize_rad_plan import validate_seed_priority

REPO = Path(__file__).resolve().parents[1]
ACCURACY = [
    "eomt_large",
    "eomt_dinov3_large",
    "segformer_b5",
    "native_convnext_tiny_channelmapper_dpt",
]
FAST = [
    "smp_fpn_resnet50",
    "smp_deeplabv3plus_resnet101",
    "smp_pan_resnext50",
    "native_mobilenetv3_large_lraspp",
]
PRIMARY = [*ACCURACY, FAST[0]]
ARM_ORDER = [
    "cityscapes_to_railsem19_to_rtis",
    "railsem19_to_rtis",
    "cityscapes_to_rtis",
    "rtis_only",
]
SOURCE_PROTOCOLS = ["cityscapes_to_railsem19", "railsem19", "cityscapes", None]
MATRICES = {"staged24": 24, "focused60": 60, "nested69": 69, "full96": 96}


def qualitative_keys(
    samples: list[dict], splits: dict, class_names: list[str], maximum: int
) -> list[str]:
    """Deterministic greedy set cover using GT class/group metadata only."""
    if type(maximum) is not int or maximum < 1:
        raise ValueError("Qualitative maximum must be a positive integer")
    test = set(splits["test"])
    rows = {row["key"]: row for row in samples if row["key"] in test}
    if not test or set(rows) != test:
        raise ValueError("Every test key needs a ground-truth audit record")
    groups = splits["groups"]
    mud = class_names.index("mud-pumping")
    wanted = {("class", str(index)) for index in range(len(class_names))}
    wanted.update(("group", groups[key]) for key in test)
    wanted.add(("mud-negative", "yes"))
    coverage = {}
    for key in sorted(test):
        row = rows[key]
        if row.get("group") != groups[key]:
            raise ValueError("Qualitative group metadata disagrees with the split")
        pixels = {int(index): int(value) for index, value in row["class_pixels"].items()}
        present = {
            ("class", str(index))
            for index, value in pixels.items()
            if value > 0 and 0 <= index < len(class_names)
        }
        present.add(("group", groups[key]))
        if pixels.get(mud, 0) == 0:
            present.add(("mud-negative", "yes"))
        coverage[key] = present
    selected = []
    while wanted and coverage and len(selected) < maximum:
        # sorted keys make equal-coverage choices stable across input order.
        key = max(coverage, key=lambda item: len(coverage[item] & wanted))
        gained = coverage.pop(key) & wanted
        if not gained:
            break
        selected.append(key)
        wanted -= gained
    if wanted:
        raise ValueError(
            f"GT class/group/mud-negative coverage does not fit the qualitative maximum {maximum}"
        )
    return selected


def prepare(
    *,
    matrix: str,
    split_policy: str,
    dataset_root: Path,
    source_checkpoints: Path,
    development_scores: Path,
    out: Path,
    qualitative_max_images: int = 6,
    source_stage_spec: Path | None = None,
) -> dict:
    if matrix not in MATRICES or split_policy not in ("finalfit", "development"):
        raise ValueError("Explicit supported matrix and split policy are required")
    if matrix == "staged24" and split_policy != "finalfit":
        raise ValueError("The confirmed staged24 protocol requires finalfit")
    dataset_root = dataset_root.resolve(strict=True)
    source_checkpoints = source_checkpoints.resolve(strict=True)
    development_scores = development_scores.resolve(strict=True)
    out = out.absolute()
    staging = out.with_name(out.name + ".preparing")
    if os.path.lexists(out) or os.path.lexists(staging):
        raise FileExistsError("Refusing to overwrite preparation or staging directory")
    splits = read(dataset_root / "splits.json")
    sizes = {split: len(splits[split]) for split in ("train", "val", "test")}
    expected = (
        {"train": 255, "val": 0, "test": 59}
        if split_policy == "finalfit"
        else {"train": 187, "val": 68, "test": 59}
    )
    if sizes != expected:
        raise ValueError("Dataset split sizes disagree with the explicit split policy")
    if split_policy == "finalfit":
        from scripts.plan_rtis_campaign import final_fit_dataset

        final_fit_dataset(
            {
                "validation_enabled": False,
                "primary_checkpoint": "final",
                "collection_contract": "rtis-final-train-statistics-v2",
            },
            dataset_root,
        )
    samples_path = dataset_root / "audit/samples.json"
    samples = read(samples_path)
    classes = sorted(read(dataset_root / "classes.json")["classes"], key=lambda row: row["id"])
    names = [row["name"] for row in classes]
    if [row["id"] for row in classes] != list(range(21)) or len(set(names)) != 21:
        raise ValueError("The paper dataset requires the unchanged 21-class taxonomy")
    selected_keys = qualitative_keys(samples, splits, names, qualitative_max_images)
    evidence = read(development_scores)
    if evidence.get("class_order") != names:
        raise ValueError("Development score taxonomy differs from the paper dataset")
    models = list(PRIMARY if matrix == "focused60" else ACCURACY + FAST)
    scores = {}
    for row in evidence["jobs"]:
        if row.get("status") == "completed" and row.get("seed") == 0 and row.get("model") in models:
            value = row.get("positive_image_miou")
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError("Development ordering needs finite conditional mIoU in [0,1]")
            key = row["model"], row["protocol"]
            if (
                key in scores
                or row.get("positive_image_class_count") != 21
                or row.get("validation_images") != 68
            ):
                raise ValueError(
                    "Development ordering needs unique 21-class, 68-image final results"
                )
            scores[key] = value
    arm_orders = {}
    preset_models = []
    for model in models:
        available = {arm: scores[(model, arm)] for arm in ARM_ORDER if (model, arm) in scores}
        if len(available) != 4:
            if model not in FAST[2:]:
                raise ValueError(
                    f"All four development initialization scores are required for {model}"
                )
            preset_models.append(model)
            arm_orders[model] = list(ARM_ORDER)
        else:
            arm_orders[model] = sorted(ARM_ORDER, key=lambda arm: -available[arm])
    models.sort(
        key=lambda model: (
            -max((scores[(model, arm)] for arm in ARM_ORDER if (model, arm) in scores), default=-1)
        )
    )
    if matrix == "staged24":
        allowed_arms = {model: ARM_ORDER[:1] for model in models}
    else:
        allowed_arms = {
            model: list(ARM_ORDER) if matrix == "full96" or model in PRIMARY else ARM_ORDER[:1]
            for model in models
        }
    priority_jobs = []
    for seed in (0, 1, 2):
        for model in models:
            for arm in arm_orders[model]:
                if arm in allowed_arms[model]:
                    priority_jobs.append(
                        {
                            "priority": len(priority_jobs) + 1,
                            "model": model,
                            "protocol": arm,
                            "seed": seed,
                            "development_positive_image_miou": scores.get((model, arm)),
                        }
                    )
    priority = {
        "schema_version": 2,
        "models": models,
        "seeds": [0, 1, 2],
        "jobs": priority_jobs,
        "source_scores_sha256": digest(development_scores),
        "source_git_sha": evidence["campaign_code_sha"],
        "ranking_metric": "final-checkpoint 21-class positive-image development mIoU",
        "rule": "Seed-major, models descending by best development score, initializations descending within model; missing PAN/LRASPP scores use explicit CityRail,Rail,City,recipe preset",
    }
    if matrix == "staged24":
        priority["rule"] = (
            "Seed-major, models descending by their best development score, followed by PAN/LRASPP while complete development scores are unavailable; every run uses the fixed Cityscapes-to-RailSem19 chain"
        )
    validate_seed_priority(priority)
    if len(priority_jobs) != MATRICES[matrix]:
        raise ValueError("Prepared matrix has an unexpected job count")
    protocol = {
        "schema_version": 1,
        "matrix": matrix,
        "split_policy": split_policy,
        "models": models,
        "accuracy_models": ACCURACY,
        "fast_models": [model for model in FAST if model in models],
        "primary_models": models if matrix == "staged24" else PRIMARY,
        "model_protocols": allowed_arms,
        "headline_protocol": ARM_ORDER[0],
        "initialization_ablation_protocols": [] if matrix == "staged24" else ARM_ORDER,
        "source_stage_reporting": [
            {
                "checkpoint_stage": "cityscapes",
                "evaluation_dataset": "Cityscapes",
                "split": "native validation",
                "source_training_seed": 0,
            },
            {
                "checkpoint_stage": "cityscapes_to_railsem19",
                "evaluation_dataset": "RailSem19",
                "split": "native validation",
                "source_training_seed": 0,
            },
            {
                "checkpoint_stage": "cityscapes_to_railsem19_to_rtis",
                "evaluation_dataset": "RAD",
                "split": "fixed59 test",
                "rad_adaptation_seeds": [0, 1, 2],
            },
        ],
        "stage_comparison_scope": "Each stage uses its own native dataset and label space; stage metrics describe distinct benchmarks",
        "rad_adaptation_seeds": [0, 1, 2],
        "source_training_seeds": [0],
        "source_checkpoint_manifest": {
            "path": str(source_checkpoints),
            "sha256": digest(source_checkpoints),
        },
        "development_evidence": {
            "path": str(development_scores),
            "sha256": digest(development_scores),
        },
        "preset_initialization_order_models": [] if matrix == "staged24" else preset_models,
        "models_without_complete_development_scores": preset_models,
        "primary_metric": "pixel-pooled 21-class mIoU, seed mean on the prespecified Cityscapes-to-RailSem19-to-RAD headline arm",
        "secondary_metrics": [
            "class-positive-image mIoU",
            "per-class pooled IoU, precision, recall and Dice",
            "mud pooled and class-positive-image IoU",
            "negative-image false alarms",
            "per-block class scores and support",
            "leave-one-block-out sensitivity",
        ],
        "seed_summary": "three values, mean, sample SD with ddof=1, minimum and maximum; no paired-seed inference",
        "qualitative_keys": selected_keys,
        "qualitative_seed": 0,
        "qualitative_selection": {
            "rule": "deterministic greedy GT class/group coverage plus mud-negative image, lexicographic ties",
            "maximum_images": qualitative_max_images,
            "samples_sha256": digest(samples_path),
            "split_sha256": digest(dataset_root / "splits.json"),
            "uses_predictions": False,
        },
        "training": {
            "steps": 4000,
            "batch_size": 2,
            "accumulation": 8,
            "effective_batch_size": 16,
            "precision": "bf16-mixed",
            "checkpoint": "final",
            "weights": "auto",
            "early_stopping": False,
        },
        "failure_rule": {
            "infrastructure": {
                "maximum_attempts": 3,
                "resume_same_seed": True,
                "resume_same_config": True,
            },
            "non_finite_loss": "stop_and_report",
            "test_scores_used_for_retry": False,
        },
        "resume_random_state_scope": "global Python, NumPy, Torch CPU and CUDA RNG only; worker and dataloader order is not an exact replay",
        "limitations": [
            "The test split has historical exposure",
            "Scene groups are inferred and recording independence remains unconfirmed",
            "RAD seed variation is conditional on fixed source seed-0 checkpoints and does not estimate source-training variation",
            "Seeds are labels across architectures and initialization recipes, without paired data orders",
            "Public pretraining corpora and source recipes differ; transfer backbone LR is 0.1x and recipe LR is 1x, so contrasts are system-level initialization recipes",
            "The EoMT public recipe includes COCO-panoptic pretraining; public pretraining exposure differs across model families",
            "Class-positive-image scores omit false alarms on class-negative images",
            "GT qualitative selection is fixed before inference",
            "Three-seed SD does not quantify test sampling uncertainty",
        ],
    }
    dataset_name = "rad_2026_11_paper_" + split_policy
    dataset = {
        "name": dataset_name,
        "space": "paul-test-rtis",
        "taxonomy_root": str(REPO / "taxonomy"),
        "train": {"precision": "bf16-mixed"},
        "stages": [
            {
                "name": "rtis",
                "data": [
                    {
                        "name": dataset_name,
                        "root": str(dataset_root),
                        "loader": "folder",
                        "mapping": "paul-test-rtis",
                        "train_split": "train",
                        "val_split": "val",
                        "split_file": "splits.json",
                        "loader_options": {"require_groups": True},
                    }
                ],
                "init_from": "pretrained",
            }
        ],
    }
    if source_stage_spec is not None:
        source_stage_spec = source_stage_spec.resolve(strict=True)
        protocol["source_stage_reports"] = {
            "spec": str(source_stage_spec),
            "spec_sha256": digest(source_stage_spec),
        }
    manifest = {
        "name": dataset_name,
        "dataset": dataset_name,
        "dataset_config": str(out / "dataset.yaml"),
        "model_catalog": str(REPO / "configs/campaigns/all_models_cityscapes_railsem19.yaml"),
        "models": models,
        "model_protocols": allowed_arms,
        "seeds": [0, 1, 2],
        "target_steps": 4000,
        "batch_size": 2,
        "accumulation": 8,
        "validation_interval": 250,
        "checkpoint_interval": 500,
        "num_workers": 2,
        "primary_checkpoint": "final",
        "validation_enabled": split_policy == "development",
        "publisher": False,
        "collection_contract": "rtis-final-train-statistics-v2"
        if split_policy == "finalfit"
        else "rtis-full-statistics-v1",
        "selection_metric": "val/miou",
        "launch_requirements": {
            "expected_gpu_allowlist": list(range(10)),
            "require_queue_priority": True,
            "shared_gpu_lock_and_idle": True,
            "require_non_rad_sources": True,
        },
        "protocols": {
            arm: {"source_protocol": source}
            for arm, source in zip(ARM_ORDER, SOURCE_PROTOCOLS, strict=True)
            if matrix != "staged24" or arm == ARM_ORDER[0]
        },
        "research_protocol": protocol,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    try:
        for filename, value in (("manifest.yaml", manifest), ("dataset.yaml", dataset)):
            (staging / filename).write_text(yaml.safe_dump(value, sort_keys=False))
        write(staging / "training-priority.json", priority)
        write(staging / "research-protocol.json", protocol)
        if os.path.lexists(out):
            raise FileExistsError("Preparation target appeared during writing")
        os.rename(staging, out)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return {
        "directory": str(out),
        "matrix": matrix,
        "split_policy": split_policy,
        "jobs": len(priority_jobs),
        "research_protocol_sha256": hashlib.sha256(
            json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "campaign_initialized": False,
        "gpu_jobs_started": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, choices=MATRICES)
    parser.add_argument("--split-policy", required=True, choices=("finalfit", "development"))
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--source-checkpoints", type=Path, required=True)
    parser.add_argument("--development-scores", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--qualitative-max-images", type=int, default=6)
    parser.add_argument(
        "--source-stage-spec", type=Path, help="frozen native source-stage evaluation request"
    )
    args = parser.parse_args()
    print(json.dumps(prepare(**vars(args)), indent=2))


if __name__ == "__main__":
    main()
