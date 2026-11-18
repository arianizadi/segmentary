"""Build a hash-verified, three-seed RAD paper report from completed test evidence."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import yaml
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
from scripts.rad_paper_metrics import paper_metrics, pooled_metrics, seed_summary
from scripts.rad_present_image_evidence import load_train_positive_evidence
from scripts.rad_source_positive_evidence import load_source_positive_evidence
from scripts.run_rad_test import digest, result_complete, validate_request, write
from scripts.run_rad_test_profiles import result_complete as profile_complete

from segmentary.config import config_hash
from segmentary.utils.provenance import git_sha

LIMITATIONS = [
    "Seeds measure RAD adaptation variation conditional on the frozen source training runs and these test images. Sample SD uses ddof=1. Seed labels do not establish paired data orders.",
    "The held-out test set was historically exposed. Scene blocks are visually inferred, with original recording provenance unconfirmed. Seed SD does not estimate test sampling uncertainty.",
    "All eight models follow the frozen Cityscapes-to-RailSem19-to-RAD recipe, with three fresh RAD adaptation seeds. Rankings describe the observed means.",
    "Auto weights use EMA where running-stat BatchNorm permits it and raw weights otherwise. At the recorded decay and ramp, EMA retains about 0.67 weight on its step-2000 history over the remaining 2000 updates. Running-stat BatchNorm models use raw step-4000 weights.",
    "Recipe initialization includes architecture-specific public supervision. EoMT's COCO-panoptic checkpoint and ImageNet-initialized encoders carry different upstream supervision and compute. The comparison describes complete initialization recipes.",
    "Model-only FPS measures batch-one BF16 1024-square dense-logit forwards. Native-pipeline timing includes the independently recorded full-image inference contract. Allocator peak, process memory and resident parameter bytes have separate denominators.",
    "Per-block and leave-one-block-out results are descriptive. Each block has its own class support. Four scene blocks provide limited evidence about new recordings.",
    "The 4000-step final-fit budget spans about 250 passes through the 255-image loader. The 187-image development loader had about 333 passes at the same update budget. Tail accumulation changes nominal examples per update. Example counters describe individual recorded invocations. Retained receipts provide the available earlier invocation history, with interrupted counter tails unobserved.",
]


def verified_json(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"Artifact SHA-256 changed: {path}")
    return json.loads(path.read_text())


def nullable_summary(values: dict[int, float | None]) -> dict:
    available = {
        seed: float(value)
        for seed, value in values.items()
        if value is not None and math.isfinite(value)
    }
    if len(available) == 3:
        return {**seed_summary(available), "complete_three_seeds": True}
    samples = list(available.values())
    return {
        "seeds": {str(seed): available.get(seed) for seed in values},
        "mean": float(np.mean(samples)) if samples else None,
        "sample_sd": float(np.std(samples, ddof=1)) if len(samples) > 1 else None,
        "minimum": min(samples) if samples else None,
        "maximum": max(samples) if samples else None,
        "n": len(samples),
        "complete_three_seeds": False,
        "uncertainty_scope": "available descriptive measurements; full three-seed evidence incomplete",
    }


def displayed_winner_indices(
    values: list[float | None],
    *,
    scale: float = 1,
    maximize: bool = True,
    require_complete: bool = False,
) -> set[int]:
    """Identify finite optima at the same two-decimal precision shown in the PDF."""
    displayed = {
        index: float(f"{value * scale:.2f}")
        for index, value in enumerate(values)
        if value is not None and math.isfinite(value) and math.isfinite(value * scale)
    }
    if not displayed or (require_complete and len(displayed) != len(values)):
        return set()
    best = (max if maximize else min)(displayed.values())
    return {index for index, value in displayed.items() if value == best}


def training_memory(state: dict) -> dict:
    """Keep measured allocator peaks and sampled whole-process memory distinct."""
    records = [state.get("training", {})]
    for receipt in state.get("training_invocation_receipts", []):
        records.append(verified_json(Path(receipt["path"]), receipt["sha256"]))
    peaks = [
        value
        for record in records
        for value in record.get("peak_vram_bytes", {}).values()
        if value is not None and math.isfinite(value) and value > 0
    ]
    driver = [
        attempt["sampled_peak_device_used_mib"] * 2**20
        for attempt in state.get("collection", {}).get("resources", {}).get("attempts", [])
        if attempt.get("phase") == "training"
        and attempt.get("sampled_peak_device_used_mib") is not None
    ]
    return {
        "allocator_peak_bytes": max(peaks, default=None),
        "allocator_accounting_complete": state.get("training_allocator_peak_accounting_complete"),
        "missing_allocator_attempts": state.get("missing_training_allocator_peak_attempts"),
        "sampled_driver_peak_bytes": max(driver, default=None),
        "receipts": state.get("training_invocation_receipts", []),
    }


def public_origin_evidence(run: dict, source_stages: dict) -> dict | None:
    origins = [
        origin
        for origin in (run["training"].get("env", {}).get("model_origins") or [])
        if any(origin.get(field) for field in ("hf_name_or_path", "hf_commit", "timm_pretrained"))
    ]
    if origins:
        return {
            "basis": "runtime_model_origins",
            "runtime_model_origins_recorded": True,
            "model_origins": origins,
        }
    model = run["training"].get("config", {}).get("model", {})
    encoder, weights = model.get("encoder_name"), model.get("encoder_weights")
    if model.get("arch") != "smp" or not encoder or not weights:
        return None
    expected = f"smp-hub/{encoder}.{weights}"
    for source in source_stages["models"]:
        if source["model"] != run["model"]:
            continue
        for stage in source["stages"]:
            public = stage.get("public_pretraining", {})
            revision = public.get("smp_registry_pinned_revision")
            if (
                stage["stage"] == "cityscapes"
                and public.get("public_checkpoint") == expected
                and isinstance(revision, str)
                and re.fullmatch(r"[0-9a-fA-F]{40}", revision)
            ):
                return {
                    "basis": "source_public_pretraining_and_encoder_recipe",
                    "runtime_model_origins_recorded": False,
                    "revision_evidence": "Evidence is the recorded SMP package-registry pin. RAD runtime observation of the loaded public revision is unavailable.",
                    "encoder_name": encoder,
                    "encoder_weights": weights,
                    "public_pretraining": public,
                }
    return None


def training_timing(training: dict, resources: dict) -> dict:
    return {
        "latest_invocation_run_record_wall_seconds": training.get("wall_clock_s"),
        "recorded_training_process_wall_seconds_all_attempts": resources.get(
            "phase_wall_seconds_including_failed_attempts", {}
        ).get("training"),
        "recorded_training_process_seconds_is_lower_bound": resources.get(
            "phase_wall_seconds_are_lower_bounds", {}
        ).get("training"),
        "training_process_accounting_complete": resources.get("phase_accounting_complete", {}).get(
            "training"
        ),
        "scope": "RunRecord duration describes the latest completed invocation; training-process duration includes the recorded wall time of all attempts",
    }


def resource_summary(
    values: dict[int, float | None], lower_bound_seeds: list[int], measurement_scope: str
) -> dict:
    result = nullable_summary(values)
    result.update(
        measurement_scope=measurement_scope,
        lower_bound_seeds=sorted(lower_bound_seeds),
        mean_and_range_are_lower_bounds=bool(lower_bound_seeds),
    )
    if lower_bound_seeds:
        result["observed_sample_sd"] = result["sample_sd"]
        result["sample_sd"] = None
    return result


def recorded_training_hours(runs: dict[int, dict]) -> dict:
    durations = {}
    lower_bound_seeds = []
    for seed, run in runs.items():
        timing = training_timing(run["training"], run["training_resources"])
        seconds = timing["recorded_training_process_wall_seconds_all_attempts"]
        durations[seed] = seconds / 3600 if seconds is not None else None
        if timing["recorded_training_process_seconds_is_lower_bound"]:
            lower_bound_seeds.append(seed)
    return resource_summary(
        durations, lower_bound_seeds, "recorded training-process wall time across all attempts"
    )


def recorded_training_allocator_peaks(runs: dict[int, dict]) -> dict:
    values = {seed: run["training_memory"]["allocator_peak_bytes"] for seed, run in runs.items()}
    lower_bound_seeds = [
        seed
        for seed, run in runs.items()
        if run["training_memory"]["allocator_accounting_complete"] is not True
    ]
    return resource_summary(
        values,
        lower_bound_seeds,
        "maximum observed allocator peak across retained training invocation records",
    )


def class_split_support(samples: list[dict], names: list[str]) -> dict:
    """Count label support on both sides from the hashed, mask-derived sample audit."""
    totals = {}
    classes = {name: {} for name in names}
    for split in ("train", "test"):
        selected = [sample for sample in samples if sample["split"] == split]
        pixels = np.zeros(len(names), dtype=np.int64)
        positives = np.zeros(len(names), dtype=np.int64)
        for sample in selected:
            counts = np.zeros(len(names), dtype=np.int64)
            if "class_pixels" not in sample:
                raise ValueError("Class support requires mask-derived audited class_pixels")
            for label, count in sample["class_pixels"].items():
                label = int(label)
                if type(count) is not int or count < 0 or label not in {*range(len(names)), 255}:
                    raise ValueError("Audited class support contains invalid labels or counts")
                if label != 255:
                    counts[label] += count
            pixels += counts
            positives += counts > 0
        missing = [name for name, count in zip(names, positives, strict=True) if count == 0]
        if missing:
            raise ValueError(f"Every class requires positive {split} support; missing {missing}")
        valid_pixels = int(pixels.sum())
        totals[split] = {"images": len(selected), "valid_pixels": valid_pixels}
        for index, name in enumerate(names):
            classes[name][split] = {
                "positive_images": int(positives[index]),
                "positive_image_fraction": int(positives[index]) / len(selected),
                "pixels": int(pixels[index]),
                "valid_pixel_fraction": int(pixels[index]) / valid_pixels,
            }
    return {"totals": totals, "classes": classes}


def full_train_evaluation(
    job: dict, state: dict, request: dict, names: list[str], split_support: dict, test_result: dict
) -> dict:
    """Read the complete selected-bank final-train record and verify its endpoint."""
    artifact = state.get("evaluation_result", {})
    expected_path = Path(job["final_checkpoint"]).parent / "final-train.json"
    if not artifact.get("path") or Path(artifact["path"]).resolve() != expected_path.resolve():
        raise ValueError("Train evaluation must identify its genuine final-train.json")
    record = verified_json(expected_path, artifact.get("sha256", ""))

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    if canonical(record) != canonical(state.get("evaluation")):
        raise ValueError("Train evaluation file differs from its inline completed-state record")
    final = state.get("checkpoints", {}).get("final", {})
    if (
        state.get("evaluation_checkpoint") != "final"
        or state.get("evaluation_split") != "train"
        or final.get("sha256") != job["final_checkpoint_sha256"]
        or Path(final.get("path", "")).resolve() != Path(job["final_checkpoint"]).resolve()
        or record.get("name") != job["name"]
        or type(record.get("seed")) is not int
        or record["seed"] != job["seed"]
        or record.get("git_sha") != request["training_code_sha"]
        or record.get("git_dirty") is not False
        or record.get("dataset_sizes") != {"eval": 255}
        or split_support["totals"]["train"]["images"] != 255
    ):
        raise ValueError(
            "Train evaluation lacks the complete matching final endpoint and 255-image scope"
        )
    if digest(Path(job["config"])) != job["config_sha256"]:
        raise ValueError("Train evaluation job configuration SHA-256 changed")
    original = yaml.safe_load(Path(job["config"]).read_text())
    cfg = record.get("config", {})
    base = {key: value for key, value in cfg.items() if key != "evaluation"}
    if (
        canonical(base) != canonical(original)
        or canonical(base) != canonical(state.get("training", {}).get("config"))
        or record.get("config_hash") != config_hash(cfg)
    ):
        raise ValueError(
            "Train evaluation configuration differs from its frozen training configuration"
        )
    data = original["stages"][0]["data"][0]
    evaluation = cfg.get("evaluation", {})
    bank = state.get("training", {}).get("env", {}).get("final_weights_policy")
    profile_source = state.get("performance", {}).get("source", {})
    diagnostic = (
        state.get("collection", {})
        .get("diagnostics", {})
        .get("results", {})
        .get("final-auto-train", {})
    )
    if (
        bank not in ("raw", "ema")
        or evaluation.get("weights") != bank
        or test_result.get("weights") != bank
        or profile_source.get("weights") != bank
        or diagnostic.get("weights") != bank
        or profile_source.get("checkpoint_sha256") != job["final_checkpoint_sha256"]
        or profile_source.get("config_sha256") != job["config_sha256"]
        or profile_source.get("result_sha256") != artifact["sha256"]
        or diagnostic.get("checkpoint_sha256") != job["final_checkpoint_sha256"]
    ):
        raise ValueError(
            "Train evaluation checkpoint/configuration or selected weight bank differs"
        )
    native = cfg.get("eval", {})
    if (
        record.get("stage") != f"eval:{data['name']}:train"
        or evaluation.get("split") != "train"
        or canonical(evaluation.get("data")) != canonical(data)
        or data.get("limit") is not None
        or Path(data["root"]).resolve() != Path(request["dataset_root"]).resolve()
        or evaluation.get("deterministic") is not True
        or evaluation.get("padding")
        != {
            "multiple": 32,
            "position": "bottom_right",
            "target_fill": 255,
            "padded_pixels_scored": False,
        }
        or evaluation.get("tta") != {"enabled": False, "scales": [1.0], "flip": False}
        or evaluation.get("prediction")
        != {"task": "multiclass", "activation": "softmax", "threshold": None}
        or native.get("batch_size") != 1
        or native.get("sliding_window") is not True
        or native.get("window") != [1024, 1024]
        or native.get("stride") != [768, 768]
        or test_result.get("deterministic") is not True
        or test_result.get("precision") != "bf16_autocast"
        or test_result.get("padding") != {"multiple": 32, "prediction_cropped_to_original": True}
        or test_result.get("inference")
        != {
            "sliding_window": True,
            "window": [1024, 1024],
            "stride": [768, 768],
            "scales": [1.0],
            "flip": False,
        }
    ):
        raise ValueError(
            "Train/test quality evaluation native deterministic padding/inference policies differ"
        )
    metrics = record.get("metrics", {})
    matrix = np.asarray(metrics.get("confusion", []))
    if (
        matrix.shape != (len(names), len(names))
        or not np.issubdtype(matrix.dtype, np.integer)
        or (matrix < 0).any()
    ):
        raise ValueError("Train evaluation requires a complete integer confusion matrix")
    support = {name: split_support["classes"][name]["train"]["pixels"] for name in names}
    if metrics.get("support") != support or not np.array_equal(
        matrix.sum(axis=1), list(support.values())
    ):
        raise ValueError("Train confusion support differs from all 255 audited training masks")
    recomputed = pooled_metrics(matrix, names)
    score = metrics.get("miou")
    if (
        type(score) not in (int, float)
        or not math.isfinite(score)
        or not math.isclose(score, recomputed["miou"], rel_tol=1e-12, abs_tol=1e-12)
    ):
        raise ValueError("Train pooled mIoU differs from its complete confusion matrix")
    return {
        "source": artifact,
        "record": record,
        "images": 255,
        "weights": bank,
        "pixel_pooled": recomputed,
    }


def aggregate(runs: list[dict], names: list[str]) -> list[dict]:
    groups = {}
    for run in runs:
        key = run["model"], run["protocol"]
        if run["seed"] in groups.setdefault(key, {}):
            raise ValueError("Duplicate model/recipe/seed result")
        groups[key][run["seed"]] = run
    result = []
    for (model, protocol), seeds in groups.items():
        if sorted(seeds) != [0, 1, 2]:
            raise ValueError(f"Incomplete three-seed recipe: {model}/{protocol}")

        def summary(getter, current=seeds):
            return nullable_summary({seed: getter(run) for seed, run in current.items()})

        classes = {}
        for name in names:
            support = [
                run["metrics"]["pixel_pooled"]["per_class"][name]["pixels"]
                for run in seeds.values()
            ]
            positive = [
                run["metrics"]["class_positive_images"]["per_class"][name]["positive_images"]
                for run in seeds.values()
            ]
            if (
                len(set(support)) != 1
                or len(set(positive)) != 1
                or min(support) <= 0
                or min(positive) <= 0
            ):
                raise ValueError(
                    f"All 21 classes require matching nonzero ground-truth support: {name}"
                )
            classes[name] = {
                "pixels": support[0],
                "positive_images": positive[0],
                **{
                    metric: summary(
                        lambda run, field=metric, label=name: run["metrics"]["pixel_pooled"][
                            "per_class"
                        ][label][field]
                    )
                    for metric in ("iou", "precision", "recall", "dice")
                },
                "negative_image_false_alarm_rate": summary(
                    lambda run, label=name: run["metrics"]["negative_images"][label][
                        "image_false_alarm_rate_any_pixel"
                    ]
                ),
                "positive_image_iou": summary(
                    lambda run, label=name: run["metrics"]["class_positive_images"]["per_class"][
                        label
                    ]["mean_image_iou"]
                ),
                **{
                    f"positive_image_{metric}": summary(
                        lambda run, field=metric, label=name: run["metrics"][
                            "class_positive_images"
                        ]["per_class"][label][field]
                    )
                    for metric in ("precision", "recall", "dice")
                },
                "negative_image_false_alarm_rate_area": summary(
                    lambda run, label=name: run["metrics"]["negative_images"][label][
                        "image_false_alarm_rate_0_1_percent_area"
                    ]
                ),
            }
        result.append(
            {
                "model": model,
                "protocol": protocol,
                "pixel_pooled_miou": summary(lambda run: run["metrics"]["pixel_pooled"]["miou"]),
                "class_positive_image_miou": summary(
                    lambda run: run["metrics"]["class_positive_images"]["miou"]
                ),
                "train_pixel_pooled_miou": summary(lambda run: run["train_pixel_pooled_miou"]),
                "train_test_miou_gap": summary(lambda run: run["train_test_miou_gap"]),
                "train_class_positive_image_miou": summary(
                    lambda run: run["train_class_positive_image_miou"]
                ),
                "conditional_train_test_miou_gap": summary(
                    lambda run: run["conditional_train_test_miou_gap"]
                ),
                "model_only_fps": summary(
                    lambda run: run["performance"]["measurements"]["latency"]["fps"]
                ),
                "native_pipeline_fps": summary(
                    lambda run: run["performance"]["native_pipeline"]["measurements"]["latency"][
                        "fps"
                    ]
                ),
                "allocator_peak_bytes": summary(
                    lambda run: run["performance"]["measurements"]["peak_reserved_bytes"]
                ),
                "process_total_bytes": summary(
                    lambda run: run["performance"]["measurements"]["process_total_bytes"]
                ),
                "native_allocator_peak_bytes": summary(
                    lambda run: run["performance"]["native_pipeline"]["measurements"][
                        "peak_reserved_bytes"
                    ]
                ),
                "parameter_count": summary(
                    lambda run: run["performance"]["model"]["parameter_count"]
                ),
                "resident_parameter_bytes": summary(
                    lambda run: run["performance"]["model"]["resident_parameter_bytes"]
                ),
                "training_peak_bytes": recorded_training_allocator_peaks(seeds),
                "sampled_training_driver_peak_bytes": summary(
                    lambda run: run["training_memory"]["sampled_driver_peak_bytes"]
                ),
                "training_allocator_peak_accounting_complete": all(
                    run["training_memory"]["allocator_accounting_complete"] is True
                    for run in seeds.values()
                ),
                "training_hours": recorded_training_hours(seeds),
                "training_hours_is_lower_bound": any(
                    run["training_resources"]
                    .get("phase_wall_seconds_are_lower_bounds", {})
                    .get("training", False)
                    for run in seeds.values()
                ),
                "per_class": classes,
            }
        )
    return result


def load_source_stage_report(request: dict) -> dict:
    from scripts.evaluate_rad_source_stages import load_verified_report

    pointer = request["research_protocol"]["source_stage_reports"]
    spec_path = Path(pointer["spec"])
    spec = verified_json(spec_path, pointer["spec_sha256"])
    artifact = request["source_stage_reports"]
    expected_path = Path(spec["output_root"]) / "source-stage-reports.json"
    if Path(artifact["path"]).resolve() != expected_path.resolve():
        raise ValueError("Source-stage report path differs from its frozen request")
    recorded = verified_json(expected_path, artifact["sha256"])
    if recorded != load_verified_report(spec_path, REPO):
        raise ValueError("Source-stage report differs from its verified native-stage artifacts")
    if {value["model"] for value in recorded["models"]} != set(
        request["research_protocol"]["models"]
    ):
        raise ValueError("Source-stage report lacks the complete prespecified model set")
    for model in recorded["models"]:
        if [stage["stage"] for stage in model["stages"]] != [
            "cityscapes",
            "cityscapes_to_railsem19",
        ]:
            raise ValueError("Each model requires both verified native source stages")
    return recorded


def load_report(request_path: Path, source_positive_path: Path | None = None) -> dict:
    request, policy, request_sha = validate_request(request_path)
    if request["schema_version"] != 2:
        raise ValueError("The paper report requires a complete-run-set schema-2 request")
    protocol = request["research_protocol"]
    if protocol["primary_metric"] != "pixel_pooled_miou" or protocol["qualitative_seed"] != 0:
        raise ValueError(
            "The archived protocol requires pooled primary mIoU and qualitative seed 0"
        )
    source_stages = load_source_stage_report(request)
    if source_positive_path is None:
        source_positive_path = (
            Path(request["source_stage_reports"]["path"]).parent.parent
            / "source-positive-images/source-positive-metrics.json"
        )
    source_positive = load_source_positive_evidence(source_positive_path, request, source_stages)
    for model in source_stages["models"]:
        for stage in model["stages"]:
            stage.update(source_positive[(model["model"], stage["stage"])])
    root = Path(request["dataset_root"])
    samples = verified_json(root / "audit/samples.json", request["samples_sha256"])
    classes = sorted(
        verified_json(root / "classes.json", request["classes_sha256"])["classes"],
        key=lambda value: value["id"],
    )
    names = request["class_names"]
    if [value["name"] for value in classes] != names:
        raise ValueError("Report palette differs from the frozen class order")
    splits = verified_json(root / "splits.json", request["split_sha256"])
    if len({sample["key"] for sample in samples}) != len(samples):
        raise ValueError("Sample audit contains duplicate image keys")
    for split in ("train", "val", "test"):
        if {sample["key"] for sample in samples if sample["split"] == split} != set(splits[split]):
            raise ValueError("Sample audit membership differs from the frozen split")
    split_support = class_split_support(samples, names)
    test_samples = {sample["key"]: sample for sample in samples if sample["split"] == "test"}
    if len(test_samples) != 59:
        raise ValueError("The confirmed paper report requires exactly 59 held-out test images")
    if not set(protocol["qualitative_keys"]) <= set(test_samples):
        raise ValueError("Qualitative keys differ from frozen test membership")
    output = Path(request["output_root"])
    deployment = output.parent / "deployment-performance"
    expected_gpu = next(
        entry["uuid"] for entry in policy["allowed"] if entry["index"] == request["benchmark_gpu"]
    )
    runs = []
    for job in request["jobs"]:
        if not result_complete(output, job, request_sha, names):
            raise ValueError(f"Incomplete test result: {job['name']}")
        if not profile_complete(deployment, job, request_sha, names):
            raise ValueError(f"Incomplete deployment profile: {job['name']}")
        directory = output / job["name"]
        source = json.loads((directory / "result.json").read_text())
        if any(
            source.get(field) != job[field]
            for field in ("name", "model", "protocol", "seed", "config_sha256")
        ):
            raise ValueError("Test result identity differs from the prespecified run")
        profile = json.loads((deployment / job["name"] / "result.json").read_text())
        performance = profile["performance"]
        if performance["source"]["source_test_result_sha256"] != digest(directory / "result.json"):
            raise ValueError("Deployment profile is bound to a different test result")
        if performance["hardware"]["gpu_uuid"] != expected_gpu:
            raise ValueError("Deployment profiles must use the frozen common benchmark GPU")
        native = performance.get("native_pipeline", {})
        latency = native.get("measurements", {}).get("latency", {})
        timings = native.get("per_image", native.get("measurements", {}).get("per_image", []))
        if {row["key"] for row in timings} != set(test_samples) or len(timings) != len(
            test_samples
        ):
            raise ValueError("Native-pipeline timing lacks complete test-image coverage")
        if not math.isfinite(latency.get("fps", 0)) or latency.get("fps", 0) <= 0:
            raise ValueError("Native-pipeline timing requires positive finite FPS")
        artifact = source["artifacts"].get("paper-metrics.json")
        if not artifact:
            raise ValueError("Missing recomputable paper-metrics.json artifact")
        metrics = verified_json(Path(artifact["path"]), artifact["sha256"])
        confusion_artifact = source["artifacts"]["per-image-confusion.json.gz"]
        matrices = json.loads(gzip.decompress(Path(confusion_artifact["path"]).read_bytes()))
        if set(matrices) != set(test_samples):
            raise ValueError("Per-image confusion evidence differs from the complete test set")
        matrices = {key: np.asarray(value, dtype=np.int64) for key, value in matrices.items()}
        expected = paper_metrics(
            matrices, names, {key: sample["group"] for key, sample in test_samples.items()}
        )
        if metrics != expected:
            raise ValueError("Paper metrics differ from the per-image confusion evidence")
        state = json.loads(Path(job["state_path"]).read_text())
        train_evaluation = full_train_evaluation(job, state, request, names, split_support, source)
        train_evaluation.update(load_train_positive_evidence(job, state, request, names, samples))
        train_miou = train_evaluation["pixel_pooled"]["miou"]
        train_positive_miou = train_evaluation["class_positive_images"]["miou"]
        runs.append(
            {
                **{
                    key: job[key]
                    for key in (
                        "name",
                        "model",
                        "protocol",
                        "seed",
                        "config_sha256",
                        "final_checkpoint_sha256",
                        "state_sha256",
                    )
                },
                "weights": source["weights"],
                "source_checkpoint": job.get("source_checkpoint"),
                "training": json.loads(Path(job["state_path"]).read_text()).get("training", {}),
                "training_memory": training_memory(state),
                "training_resources": json.loads(Path(job["state_path"]).read_text())
                .get("collection", {})
                .get("resources", {}),
                "metrics": metrics,
                "train_evaluation": train_evaluation,
                "train_pixel_pooled_miou": train_miou,
                "train_test_miou_gap": train_miou - metrics["pixel_pooled"]["miou"],
                "train_class_positive_image_miou": train_positive_miou,
                "conditional_train_test_miou_gap": (
                    train_positive_miou - metrics["class_positive_images"]["miou"]
                ),
                "performance": performance,
                "provenance": {
                    "test_result": str(directory / "result.json"),
                    "test_result_sha256": digest(directory / "result.json"),
                    "deployment_result": str(deployment / job["name"] / "result.json"),
                    "deployment_result_sha256": digest(deployment / job["name"] / "result.json"),
                    "paper_metrics": artifact,
                    "source_state": job["state_path"],
                },
            }
        )
    aggregates = aggregate(runs, names)
    if any(entry["class_positive_image_miou"]["n"] != 3 for entry in aggregates):
        raise ValueError("Ranking requires three finite primary quality scores per model")
    headline = sorted(
        [row for row in aggregates if row["protocol"] == protocol["headline_protocol"]],
        key=lambda row: (-row["class_positive_image_miou"]["mean"], row["model"]),
    )
    if {row["model"] for row in headline} != set(protocol["models"]):
        raise ValueError("Headline recipe lacks all prespecified models")
    coverage = {
        name: {key: headline[0]["per_class"][name][key] for key in ("pixels", "positive_images")}
        for name in names
    }
    if any(
        {name: {key: row["per_class"][name][key] for key in coverage[name]} for name in names}
        != coverage
        for row in aggregates
    ):
        raise ValueError("Test class support differs across models or initialization recipes")
    if any(
        coverage[name]
        != {
            field: split_support["classes"][name]["test"][field]
            for field in ("positive_images", "pixels")
        }
        for name in names
    ):
        raise ValueError("Test class support differs between sample audit and confusion evidence")
    missing = []
    for run in runs:
        run["public_origin_evidence"] = public_origin_evidence(run, source_stages)
        run["training_timing"] = training_timing(run["training"], run["training_resources"])
        if run["public_origin_evidence"] is None:
            missing.append(
                run["name"] + " public checkpoint origins and revisions must be collected"
            )
        if not run["training"].get("config", {}).get("optim"):
            missing.append(run["name"] + " optimizer recipe must be collected")
    for entry in aggregates:
        for field in ("training_peak_bytes", "training_hours"):
            if entry[field]["mean"] is None:
                missing.append(
                    entry["model"] + "/" + entry["protocol"] + " " + field + " must be collected"
                )
    report_code_sha, report_code_dirty = git_sha(REPO)
    return {
        "schema_version": 1,
        "report_code_sha": report_code_sha,
        "report_code_dirty": report_code_dirty,
        "request": str(request_path.resolve()),
        "request_sha256": request_sha,
        "training_plan_sha256": request["training_plan_sha256"],
        "training_campaign_sha256": request["training_campaign_sha256"],
        "training_code_sha": request["training_code_sha"],
        "split_sha256": request["split_sha256"],
        "samples_sha256": request["samples_sha256"],
        "research_protocol": protocol,
        "report_metric_policy": {
            "primary_metric": "class_positive_image_miou",
            "secondary_metric": "pixel_pooled_miou",
            "recorded_on": "2026-11-17",
            "reason": "author_requested_reporting_correction_and_dual_metric_comparison",
            "class_positive_image_miou": (
                "For each class, compute whole-valid-image IoU on each image with GT pixels "
                "of that class, average those image IoUs, then average supported class scores."
            ),
            "pixel_pooled_miou": (
                "Pool all image confusion matrices, compute each class IoU from pooled "
                "TP/FP/FN, then average class scores with a nonempty union. The native "
                "source evaluator uses its archived active-class mask."
            ),
            "ranking": "descending three-RAD-seed mean class_positive_image_miou",
            "source_positive_evaluations": {
                "path": str(source_positive_path.resolve()),
                "sha256": digest(source_positive_path),
            },
            "archived_primary_metric": protocol["primary_metric"],
            "scope": "reporting correction after the first report; archived training protocol retained",
        },
        "class_names": names,
        "class_coverage": coverage,
        "class_split_support": split_support["classes"],
        "split_totals": split_support["totals"],
        "test_images": len(test_samples),
        "runs": runs,
        "aggregates": aggregates,
        "headline_order": [row["model"] for row in headline],
        "limitations": LIMITATIONS,
        "missing_provenance": missing,
        "source_stage_reports": source_stages,
        "qualitative": {
            "seed": protocol["qualitative_seed"],
            "keys": protocol["qualitative_keys"],
            "selection": "prespecified from ground truth before final-fit training",
        },
    }


def write_csv(path: Path, report: dict) -> None:
    def add_summary(row, prefix, statistics):
        for statistic in ("mean", "sample_sd", "minimum", "maximum", "n", "complete_three_seeds"):
            row[f"{prefix}:{statistic}"] = statistics.get(statistic)
        for seed, value in statistics["seeds"].items():
            row[f"{prefix}:seed_{seed}"] = value

    ranks = {model: index for index, model in enumerate(report["headline_order"], start=1)}
    sources = {
        model["model"]: model["stages"] for model in report["source_stage_reports"]["models"]
    }
    rows = []
    for entry in sorted(report["aggregates"], key=lambda row: ranks[row["model"]]):
        row = {
            "model": entry["model"],
            "protocol": entry["protocol"],
            "seeds": "0,1,2",
            "primary_metric": report["report_metric_policy"]["primary_metric"],
            "class_positive_rank": ranks[entry["model"]],
        }
        for stage in sources[entry["model"]]:
            prefix = f"source:{stage['stage']}"
            row[f"{prefix}:pixel_pooled_miou"] = stage["metrics"]["metrics"]["miou"]
            row[f"{prefix}:class_positive_image_miou"] = stage["class_positive_images"]["miou"]
            row[f"{prefix}:class_positive_scored_classes"] = stage["class_positive_images"][
                "macro_scored_classes"
            ]
        for metric in (
            "pixel_pooled_miou",
            "class_positive_image_miou",
            "train_pixel_pooled_miou",
            "train_test_miou_gap",
            "train_class_positive_image_miou",
            "conditional_train_test_miou_gap",
            "model_only_fps",
            "native_pipeline_fps",
            "allocator_peak_bytes",
            "process_total_bytes",
            "resident_parameter_bytes",
            "parameter_count",
            "training_hours",
            "training_peak_bytes",
            "sampled_training_driver_peak_bytes",
        ):
            add_summary(row, metric, entry[metric])
        for name, metrics in entry["per_class"].items():
            row[f"positive_images:{name}"] = metrics["positive_images"]
            row[f"pixels:{name}"] = metrics["pixels"]
            for metric in (
                "iou",
                "positive_image_iou",
                "positive_image_precision",
                "positive_image_recall",
                "positive_image_dice",
                "precision",
                "recall",
                "dice",
                "negative_image_false_alarm_rate",
                "negative_image_false_alarm_rate_area",
            ):
                add_summary(row, f"{metric}:{name}", metrics[metric])
        runs = [
            run
            for run in report["runs"]
            if (run["model"], run["protocol"]) == (entry["model"], entry["protocol"])
        ]
        row["weight_bank"] = "/".join(sorted({run["weights"] for run in runs}))
        row["training_hours_is_lower_bound"] = entry["training_hours_is_lower_bound"]
        for field in ("training_hours", "training_peak_bytes"):
            row[f"{field}:measurement_scope"] = entry[field]["measurement_scope"]
            row[f"{field}:observed_sample_sd"] = entry[field].get("observed_sample_sd")
            for seed in range(3):
                row[f"{field}:seed_{seed}_is_lower_bound"] = (
                    seed in entry[field]["lower_bound_seeds"]
                )
        row["training_allocator_peak_accounting_complete"] = entry[
            "training_allocator_peak_accounting_complete"
        ]
        for scope in ("per_block", "leave_one_block_out"):
            for block in runs[0]["metrics"][scope]:
                for field, label in (
                    ("pixel_pooled", "pixel_pooled_miou"),
                    ("class_positive_images", "class_positive_image_miou"),
                ):
                    statistics = nullable_summary(
                        {run["seed"]: run["metrics"][scope][block][field]["miou"] for run in runs}
                    )
                    add_summary(row, f"{scope}:{block}:{label}", statistics)
        rows.append(row)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def semantic_panel(
    request: dict, job: dict, key: str, classes: list[dict], sample: dict
) -> io.BytesIO:
    root = Path(request["dataset_root"])
    source = root / "images/test" / (key + sample["image_extension"])
    if digest(source) != sample["image_sha256"]:
        raise ValueError("Qualitative RGB image differs from the frozen sample audit")
    rgb = np.asarray(Image.open(source).convert("RGB"))
    target = np.asarray(Image.open(root / "masks/test" / (key + ".png")))
    if hashlib.sha256(target.tobytes()).hexdigest() != sample["mask_sha256"]:
        raise ValueError("Qualitative ground truth differs from the frozen sample audit")
    directory = Path(request["output_root"]) / job["name"]
    prediction_path = directory / "predictions" / (key + ".png")
    with (directory / "per-image.csv").open() as stream:
        rows = {row["key"]: row for row in csv.DictReader(stream)}
    if digest(prediction_path) != rows[key]["prediction_sha256"]:
        raise ValueError("Qualitative prediction differs from its inference artifact")
    prediction = np.asarray(Image.open(prediction_path))
    palette = np.asarray([value["color"] for value in classes], dtype=np.uint8)
    if target.shape != prediction.shape or rgb.shape[:2] != target.shape:
        raise ValueError("Qualitative image/mask/prediction dimensions differ")
    images = [Image.fromarray(rgb)]
    for mask in (target, prediction):
        if set(np.unique(mask)) - set(range(21)) - {255}:
            raise ValueError("Qualitative labels fall outside the 21-class taxonomy")
        overlay = rgb.copy()
        valid = mask != 255
        overlay[valid] = (0.48 * rgb[valid] + 0.52 * palette[mask[valid]]).astype(np.uint8)
        images.append(Image.fromarray(overlay))
    panel = Image.new("RGB", (1500, 300), "white")
    for column, image in enumerate(images):
        rendered = ImageOps.contain(image, (490, 280))
        panel.paste(
            rendered,
            (column * 500 + (500 - rendered.width) // 2, 10 + (280 - rendered.height) // 2),
        )
    stream = io.BytesIO()
    panel.save(stream, format="PNG")
    stream.seek(0)
    return stream


def pdf_compact_provenance(value):
    """Condense display-only provenance while retaining the raw report evidence."""
    if isinstance(value, dict):
        compacted = {}
        for key, item in value.items():
            compact = pdf_compact_provenance(item)
            if compact not in (None, "", [], {}):
                compacted[key] = compact
        return compacted
    if isinstance(value, list):
        return [pdf_compact_provenance(item) for item in value]
    return value


def pdf_origin_summary(evidence: dict | None) -> dict | None:
    """Show each observed origin once, with the count of modules recording it."""
    if not evidence:
        return evidence
    summary = {key: value for key, value in evidence.items() if key != "model_origins"}
    if "public_pretraining" in summary:
        summary["public_pretraining"] = {
            key: value
            for key, value in summary["public_pretraining"].items()
            if key.startswith("public_") or key in ("identity", "smp_registry_pinned_revision")
        }
    origins = evidence.get("model_origins")
    if origins is not None:
        grouped = {}
        for origin in origins:
            identity = pdf_compact_provenance(
                {key: value for key, value in origin.items() if key != "module"}
            )
            key = json.dumps(identity, sort_keys=True)
            grouped.setdefault(key, {**identity, "module_count": 0})["module_count"] += 1
        summary["recorded_module_count"] = len(origins)
        summary["unique_origins"] = list(grouped.values())
    return pdf_compact_provenance(summary)


def pdf_model_recipe(model: dict) -> dict:
    summary = pdf_compact_provenance(model)
    if summary.get("tuning") != "lora":
        summary = {key: value for key, value in summary.items() if not key.startswith("lora_")}
    return summary


def build_pdf(path: Path, report: dict) -> None:
    from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Image as PdfImage
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    width = A4[0] - 72
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="PaperTitle",
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#142D46"),
            spaceAfter=12,
        )
    )
    styles.add(ParagraphStyle(name="PaperBody", fontSize=8.5, leading=11.5, spaceAfter=7))
    styles.add(ParagraphStyle(name="PaperSmall", fontSize=6.8, leading=8.8, spaceAfter=5))
    styles.add(ParagraphStyle(name="PaperCell", fontSize=6.5, leading=8))
    styles.add(ParagraphStyle(name="GuideBody", fontSize=10, leading=14, spaceAfter=9))
    styles.add(
        ParagraphStyle(
            name="GuideHeading",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            spaceBefore=8,
            spaceAfter=5,
            textColor=colors.HexColor("#142D46"),
        )
    )
    story = []

    def paragraph(value, style="PaperBody", help_key=None, target=None):
        markup = escape(str(value)).replace("\n", "<br/>")
        if target:
            markup = f'<link href="#{escape(target)}" color="#007F83">{markup}</link>'
        if help_key:
            markup += f' <link href="#help-{escape(help_key)}" color="#007F83">?</link>'
        return Paragraph(markup, styles[style])

    def table(rows, fractions=None, winners=(), cell_padding=3):
        rendered = [
            [
                value if isinstance(value, Paragraph) else paragraph(value, "PaperCell")
                for value in row
            ]
            for row in rows
        ]
        widths = (
            [width * fraction for fraction in fractions]
            if fractions
            else [width / len(rows[0])] * len(rows[0])
        )
        item = Table(rendered, colWidths=widths, repeatRows=1, spaceAfter=8)
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBE5ED")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F8")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), cell_padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), cell_padding),
        ]
        for column, row in winners:
            commands.extend(
                [
                    ("BACKGROUND", (column, row), (column, row), colors.HexColor("#D6F2DF")),
                    ("BOX", (column, row), (column, row), 0.6, colors.HexColor("#27904B")),
                ]
            )
        item.setStyle(TableStyle(commands))
        story.append(item)

    def title(value, anchor=None):
        markup = escape(str(value)).replace("\n", "<br/>")
        if anchor:
            markup = f'<a name="{escape(anchor)}"/>' + markup
        story.append(Paragraph(markup, styles["PaperTitle"]))

    def guide_section(key, heading, explanation):
        story.append(
            Paragraph(f'<a name="help-{escape(key)}"/>' + escape(heading), styles["GuideHeading"])
        )
        story.append(paragraph(explanation, "GuideBody"))

    def reading_guide():
        story.append(PageBreak())
        title("How to read the scores")
        story.append(
            paragraph(
                "Click a blue ? beside a table label to return to the matching explanation.",
                "GuideBody",
            )
        )
        guide_section(
            "iou",
            "IoU measures overlap",
            "Intersection over Union (IoU) asks how much the predicted class overlaps its ground truth. Divide correctly predicted class pixels (TP) by TP + false-positive pixels (FP) + missed class pixels (FN). A perfect overlap scores 100%.",
        )
        guide_section(
            "positive",
            "Class-positive IoU gives each selected image equal weight",
            "For each class, select images containing ground-truth pixels of that class. Compute IoU separately in each selected image, then average those IoUs. Images shows how many images were selected. A model can make false alarms in other images, which the negative-image table measures separately.",
        )
        guide_section(
            "pooled",
            "Pooled IoU combines pixels across the full split",
            "Add TP, FP and FN across every image, then divide the combined TP by the combined union. Larger class regions contribute more pixels, and false alarms in class-absent images enter the combined FP count.",
        )
        story.append(
            paragraph(
                "Example for one class\nImage A contains the class. TP 50, FP 25 and FN 25 give IoU 50%.\nImage B contains the class. TP 8, FP 1 and FN 1 give IoU 80%.\nImage C has no ground-truth pixels of the class and contributes 20 false-positive pixels.\nClass-positive IoU is (50% + 80%) / 2 = 65%.\nPooled IoU is 58 / (58 + 46 + 26) = 44.62%.",
                "GuideBody",
            )
        )
        guide_section(
            "miou",
            "mIoU averages the class scores",
            "Compute each class's IoU using the named method, then average the class scores. RAD uses all 21 supported classes. Both methods appear side by side. The report ranks models by class-positive mIoU, and their pooled-mIoU ordering can differ.",
        )
        guide_section(
            "seeds",
            "Mean and SD describe three RAD training repeats",
            "Seeds 0, 1 and 2 repeat RAD adaptation from the same source checkpoint. Mean is their average. Sample SD describes their spread. Scores 60%, 63% and 66% have mean 63% and SD 3 percentage points. Train-test gaps subtract each seed's test score from its train score before summarizing the three gaps.",
        )
        story.append(PageBreak())
        title("Data, stages and resources")
        guide_section(
            "data",
            "Training data and source stages",
            "The final RAD fit uses 255 training images, including the former validation images. Evaluation uses 59 test images. Models follow Cityscapes -> RailSem19 -> RAD. Source-stage tables use each source dataset's own validation images and labels. Their score levels describe different datasets. GT pixels counts labeled class pixels, and Images counts class-positive images.",
        )
        guide_section(
            "precision",
            "Precision, recall and Dice use the selected images",
            "For each class, these tables sum confusion counts over its ground-truth-positive images. Precision asks how many predicted class pixels are correct. Recall asks how many ground-truth class pixels were found. Dice divides twice the overlap by the total predicted and ground-truth class pixels.",
        )
        guide_section(
            "speed",
            "FPS measures processing speed",
            "Higher frames per second (FPS) means faster processing. Model-only FPS measures batch-one BF16 forwards on a 1024-by-1024 input. Native-pipeline FPS measures the full recorded image workload, including preprocessing, CPU/GPU transfers and inference. Their work differs, so read the named measurement. Speed variation includes timing noise.",
        )
        guide_section(
            "memory",
            "GPU memory has several scopes",
            "Reserved allocator memory includes PyTorch's cached GPU blocks. Allocated memory counts live tensors within those blocks. The reported allocator peaks use reserved memory. Process memory also includes the CUDA context and other process allocations. Sampled training-driver memory describes whole-device usage observed during training. GiB means 2^30 bytes.",
        )
        guide_section(
            "size",
            "Model size and checkpoints",
            "Parameters M counts millions of learned numbers. Weights MiB measures resident parameter bytes, with 1 MiB = 2^20 bytes. A checkpoint can also store optimizer and training state, so its file size has a broader scope. SHA256 fingerprints identify the exact recorded artifacts.",
        )
        guide_section(
            "green",
            "Green boxes, N/A and zero",
            "Green boxes mark the best comparable displayed value, including displayed ties. Higher scores and FPS win. Lower false alarms, memory and model size win. Source comparisons match dataset and stage. Block comparisons match scored class sets. N/A means the denominator or measurement is unavailable. Zero is a defined result, and 0.00 can include a small value rounded to two decimals. A recorded lower bound begins with >=, and its full-run SD can be Unknown.",
        )

    def rad_title(model, section, anchor=None):
        title(model.replace("_", " ") + "\n" + section, anchor)
        story.append(
            paragraph(
                f"RAD class-positive-image mIoU rank {headline_indices[model] + 1} of {len(headline)} | three-seed held-out test mean",
                "PaperSmall",
            )
        )

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#586979"))
        canvas.drawString(
            36, 22, "RAD semantic segmentation | request " + report["request_sha256"][:12]
        )
        canvas.drawRightString(A4[0] - 36, 22, str(canvas.getPageNumber()))
        canvas.restoreState()

    def metric(value, scale=100, lower_bound=False):
        if value is None:
            return "N/A"
        return (">= " if lower_bound else "") + f"{scale * value:.2f}"

    def speed_plot(field, label, quality_field, quality_label):
        drawing = Drawing(width, 220)
        left, bottom, plot_width, plot_height = 43, 31, width - 56, 165
        points = [
            (rank, entry[field], entry[quality_field])
            for rank, entry in enumerate(headline, 1)
            if entry[field]["mean"] is not None
        ]
        if not points:
            drawing.add(String(left, 100, "Timing measurements unavailable", fontSize=8))
            return drawing
        x_max = max(values["mean"] + (values["sample_sd"] or 0) for _, values, _ in points) * 1.12
        y_min = max(
            0,
            math.floor(
                min(100 * (values["mean"] - (values["sample_sd"] or 0)) for _, _, values in points)
                / 5
            )
            * 5
            - 2,
        )
        y_max = min(
            100,
            math.ceil(
                max(100 * (values["mean"] + (values["sample_sd"] or 0)) for _, _, values in points)
                / 5
            )
            * 5
            + 2,
        )
        y_max = max(y_max, y_min + 1)
        x_scale = plot_width / x_max
        y_scale = plot_height / (y_max - y_min)
        for tick in range(5):
            x = left + tick * plot_width / 4
            y = bottom + tick * plot_height / 4
            drawing.add(
                Line(
                    x,
                    bottom,
                    x,
                    bottom + plot_height,
                    strokeColor=colors.HexColor("#E4EAF0"),
                    strokeWidth=0.4,
                )
            )
            drawing.add(
                Line(
                    left,
                    y,
                    left + plot_width,
                    y,
                    strokeColor=colors.HexColor("#E4EAF0"),
                    strokeWidth=0.4,
                )
            )
            drawing.add(
                String(
                    x,
                    bottom - 12,
                    f"{tick * x_max / 4:.1f}" if x_max < 10 else f"{tick * x_max / 4:.0f}",
                    textAnchor="middle",
                    fontSize=6.5,
                )
            )
            drawing.add(
                String(
                    left - 7,
                    y - 2,
                    f"{y_min + tick * (y_max - y_min) / 4:.0f}",
                    textAnchor="end",
                    fontSize=6.5,
                )
            )
        drawing.add(
            Line(left, bottom, left + plot_width, bottom, strokeColor=colors.HexColor("#586979"))
        )
        drawing.add(
            Line(left, bottom, left, bottom + plot_height, strokeColor=colors.HexColor("#586979"))
        )
        drawing.add(String(left, bottom + plot_height + 11, quality_label, fontSize=8))
        drawing.add(String(left + plot_width / 2, 4, label, textAnchor="middle", fontSize=8))
        used = []
        for rank, speed, quality in points:
            x = left + speed["mean"] * x_scale
            y = bottom + (quality["mean"] * 100 - y_min) * y_scale
            x_error = (speed["sample_sd"] or 0) * x_scale
            y_error = (quality["sample_sd"] or 0) * 100 * y_scale
            color = colors.HexColor("#007F83")
            drawing.add(Line(x - x_error, y, x + x_error, y, strokeColor=color, strokeWidth=0.7))
            drawing.add(
                Line(
                    x,
                    max(bottom, y - y_error),
                    x,
                    min(bottom + plot_height, y + y_error),
                    strokeColor=color,
                    strokeWidth=0.7,
                )
            )
            drawing.add(Circle(x, y, 3, fillColor=color, strokeColor=None))
            for attempt in range(20):
                text_x = min(left + plot_width - 8, max(left + 5, x + 8 + (attempt % 4) * 10))
                text_y = min(bottom + plot_height - 8, max(bottom + 6, y + 5 + (attempt // 4) * 11))
                if all(
                    abs(text_x - prior_x) > 9 or abs(text_y - prior_y) > 9
                    for prior_x, prior_y in used
                ):
                    break
            used.append((text_x, text_y))
            drawing.add(Line(x, y, text_x - 2, text_y, strokeColor=color, strokeWidth=0.35))
            drawing.add(
                String(
                    text_x,
                    text_y,
                    str(rank),
                    fontName="Helvetica-Bold",
                    fontSize=7,
                    fillColor=color,
                )
            )
        return drawing

    def class_mean_winners(entry, fields):
        winners = []
        current = headline_indices[entry["model"]]
        for row, name in enumerate(report["class_names"], 1):
            for column, field, maximize in fields:
                summaries = [candidate["per_class"][name][field] for candidate in headline]
                values = [
                    summary["mean"] if summary["complete_three_seeds"] else None
                    for summary in summaries
                ]
                if current in displayed_winner_indices(values, scale=100, maximize=maximize):
                    winners.append((column, row))
        return winners

    def class_table(entries):
        if len(entries) != 1:
            raise ValueError("The confirmed paper tables require the single common recipe")
        entry = entries[0]
        rows = [
            [
                "Class",
                paragraph("Images", "PaperCell", "data"),
                "GT pixels",
                paragraph("Class-positive IoU mean (%)", "PaperCell", "positive"),
                "SD",
                paragraph("Pooled IoU mean (%)", "PaperCell", "pooled"),
                "SD",
            ]
        ]
        for name in report["class_names"]:
            values = entry["per_class"][name]
            rows.append(
                [
                    name,
                    values["positive_images"],
                    f"{values['pixels']:,}",
                    metric(values["positive_image_iou"]["mean"]),
                    metric(values["positive_image_iou"]["sample_sd"]),
                    metric(values["iou"]["mean"]),
                    metric(values["iou"]["sample_sd"]),
                ]
            )
        winners = class_mean_winners(entry, [(3, "positive_image_iou", True), (5, "iou", True)])
        table(rows, [0.29, 0.08, 0.16, 0.16, 0.075, 0.16, 0.075], winners)

    def resource_mean_winners(entry, fields):
        maximize_fields = {"model_only_fps", "native_pipeline_fps"}
        minimize_fields = {
            "training_peak_bytes",
            "training_hours",
            "parameter_count",
            "resident_parameter_bytes",
            "allocator_peak_bytes",
            "process_total_bytes",
            "native_allocator_peak_bytes",
        }
        winners = []
        current = headline_indices[entry["model"]]
        for row, (_, field, scale) in enumerate(fields, 1):
            if field not in maximize_fields | minimize_fields:
                continue
            if field == "training_hours" and not training_hours_complete:
                continue
            if field == "training_peak_bytes" and not all(
                candidate["training_allocator_peak_accounting_complete"] for candidate in headline
            ):
                continue
            values = [
                candidate[field]["mean"] if candidate[field]["complete_three_seeds"] else None
                for candidate in headline
            ]
            if current in displayed_winner_indices(
                values,
                scale=scale,
                maximize=field in maximize_fields,
                require_complete=True,
            ):
                winners.append((1, row))
        return winners

    def block_mean_winners(model, field, blocks, measurement_field, class_field, column):
        winners = []
        current = headline_indices[model]
        for row, block in enumerate(blocks, 1):
            scored_class_sets = set()
            values = []
            for entry in headline:
                measurements = {
                    run["seed"]: run["metrics"][field][block][measurement_field]
                    for run in headline_runs[entry["model"]]
                }
                for measurement in measurements.values():
                    scored_class_sets.add(
                        tuple(
                            name
                            for name in report["class_names"]
                            if measurement["per_class"][name][class_field] is not None
                        )
                    )
                statistics = nullable_summary(
                    {seed: measurement["miou"] for seed, measurement in measurements.items()}
                )
                values.append(statistics["mean"] if statistics["complete_three_seeds"] else None)
            if len(scored_class_sets) == 1 and current in displayed_winner_indices(
                values, scale=100
            ):
                winners.append((column, row))
        return winners

    def legend(classes):
        cells = []
        for value in classes:
            swatch = Drawing(9, 9)
            swatch.add(
                Rect(
                    0,
                    0,
                    9,
                    9,
                    fillColor=colors.Color(*[channel / 255 for channel in value["color"]]),
                    strokeColor=None,
                )
            )
            cells.append(
                Table(
                    [[swatch, paragraph(value["name"], "PaperCell")]],
                    colWidths=[13, width / 3 - 17],
                )
            )
        rows = [cells[index : index + 3] for index in range(0, len(cells), 3)]
        item = Table(rows, colWidths=[width / 3] * 3)
        item.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(item)

    def native_source_cohort(stage):
        cohort = []
        for source in report["source_stage_reports"]["models"]:
            for candidate in source["stages"]:
                same_native_stage = all(
                    candidate[field] == stage[field]
                    for field in ("stage", "dataset", "split", "taxonomy", "class_names")
                )
                same_support = (
                    candidate["metrics"]["metrics"]["support"]
                    == stage["metrics"]["metrics"]["support"]
                )
                if same_native_stage and same_support:
                    cohort.append((source["model"], candidate))
        return cohort

    def source_stage_pages(model):
        source_model = next(
            value for value in report["source_stage_reports"]["models"] if value["model"] == model
        )
        for stage in source_model["stages"]:
            story.append(PageBreak())
            title(model.replace("_", " ") + "\n" + stage["stage"].replace("_", " "))
            record = stage["metrics"]
            metrics = record["metrics"]
            positive = stage["class_positive_images"]
            performance = stage["performance"]
            training = stage["training"]
            duration = training.get("wall_clock_s")
            story.append(
                paragraph(
                    f"Dataset {stage['dataset']} | split {stage['split']} | label space {stage['taxonomy']} | original source seed {stage['source_seed']} | fresh auto-weight evaluation",
                    "PaperSmall",
                )
            )
            bank = (
                record.get("config", {})
                .get("evaluation", {})
                .get("weights", performance.get("source", {}).get("weights", "unrecorded"))
            )
            cohort = native_source_cohort(stage)
            current = next(index for index, (name, _) in enumerate(cohort) if name == model)
            summary_winners = []
            source_summary_values = [
                (0, [value["class_positive_images"]["miou"] for _, value in cohort], 100, True),
                (1, [value["metrics"]["metrics"]["miou"] for _, value in cohort], 100, True),
                (
                    4,
                    [value["performance"]["model"]["parameter_count"] for _, value in cohort],
                    1 / 1e6,
                    False,
                ),
                (
                    5,
                    [
                        value["performance"]["model"]["resident_parameter_bytes"]
                        for _, value in cohort
                    ],
                    1 / 2**20,
                    False,
                ),
            ]
            for column, values, scale, maximize in source_summary_values:
                if current in displayed_winner_indices(
                    values, scale=scale, maximize=maximize, require_complete=True
                ):
                    summary_winners.append((column, 1))
            story.append(
                paragraph(
                    "Evaluation weight bank "
                    + bank
                    + ". Source-stage model-only FPS is contextual and non-authoritative, measured on the recorded source-evaluation GPU while other jobs may run concurrently.",
                    "PaperSmall",
                )
            )
            table(
                [
                    [
                        paragraph("Class-positive mIoU (%)", "PaperCell", "positive"),
                        paragraph("Pooled mIoU (%)", "PaperCell", "pooled"),
                        paragraph("Model-only FPS", "PaperCell", "speed"),
                        "Latest source wall hours",
                        paragraph("Parameters M", "PaperCell", "size"),
                        paragraph("Weights MiB", "PaperCell", "size"),
                    ],
                    [
                        metric(positive["miou"]),
                        metric(metrics["miou"]),
                        metric(performance["measurements"]["latency"]["fps"], 1),
                        metric(duration / 3600 if duration is not None else None, 1),
                        metric(performance["model"]["parameter_count"], 1 / 1e6),
                        metric(performance["model"]["resident_parameter_bytes"], 1 / 2**20),
                    ],
                ],
                winners=summary_winners,
            )
            rows = [
                [
                    "Class",
                    "Images",
                    "GT pixels",
                    paragraph("Class-positive IoU (%)", "PaperCell", "positive"),
                    paragraph("Pooled IoU (%)", "PaperCell", "pooled"),
                    paragraph("Precision (%)", "PaperCell", "precision"),
                    "Recall (%)",
                    "Dice (%)",
                ]
            ]
            class_winners = []
            class_fields = (
                "precision",
                "recall",
                "dice",
            )
            for row, name in enumerate(stage["class_names"], 1):
                rows.append(
                    [
                        name,
                        positive["per_class"][name]["positive_images"],
                        f"{metrics['support'][name]:,}",
                        metric(positive["per_class"][name]["mean_image_iou"]),
                        metric(metrics["per_class_iou"][name]),
                        *[
                            metric(positive["per_class"][name][field])
                            if positive["per_class"][name]["positive_images"] > 0
                            else "N/A"
                            for field in class_fields
                        ],
                    ]
                )
                for column, field in enumerate(class_fields, 5):
                    values = [
                        value["class_positive_images"]["per_class"][name][field]
                        if value["class_positive_images"]["per_class"][name]["positive_images"] > 0
                        else None
                        for _, value in cohort
                    ]
                    if current in displayed_winner_indices(values, scale=100):
                        class_winners.append((column, row))
                for column, values in (
                    (
                        3,
                        [
                            value["class_positive_images"]["per_class"][name]["mean_image_iou"]
                            for _, value in cohort
                        ],
                    ),
                    (
                        4,
                        [value["metrics"]["metrics"]["per_class_iou"][name] for _, value in cohort],
                    ),
                ):
                    if current in displayed_winner_indices(values, scale=100):
                        class_winners.append((column, row))
            table(rows, [0.24, 0.07, 0.14, 0.11, 0.11, 0.11, 0.11, 0.11], class_winners)
            story.append(
                paragraph(
                    "Class-positive IoU averages selected GT-positive image IoUs. Pooled IoU combines all validation counts. Precision, recall and Dice use selected-image counts. Source validation datasets and label spaces differ. Wall hours include validation in the latest invocation. Earlier source invocation history is unknown. Source runs are shared across all three RAD seeds.",
                    "PaperSmall",
                )
            )
            cfg = training.get("config", {})
            public = {
                key: value
                for key, value in (stage.get("public_pretraining") or {}).items()
                if key != "model" and (key != "base_optimizer" or value != cfg.get("optim"))
            }
            provenance = {
                "public_pretraining": public,
                "optimizer": cfg.get("optim"),
                "effective_stage_optimizer": training.get("env", {}).get("stage_optimizer"),
                "model": pdf_model_recipe(cfg.get("model", {})),
            }
            story.append(
                paragraph(
                    "Public supervision and training recipe\n"
                    + json.dumps(pdf_compact_provenance(provenance), sort_keys=True),
                    "PaperSmall",
                )
            )
            artifacts = [["Artifact", "SHA256 - full artifact paths in rad-paper.json"]]
            for label in (
                "checkpoint",
                "config",
                "evaluation_receipt",
                "performance_receipt",
                "training_receipt",
            ):
                artifacts.append([label.replace("_", " "), stage[label]["sha256"]])
            for label, field in (
                ("GT-positive evaluation", "evaluation_record"),
                ("GT-positive confusions", "per_image_confusions"),
            ):
                artifacts.append([label, stage["positive_image_evidence"][field]["sha256"]])
            table(artifacts, [0.23, 0.77], cell_padding=1.5)
            if duration is None or not stage.get("public_pretraining"):
                story.append(
                    paragraph(
                        "Missing source duration or public-pretraining provenance must be collected. Public pretraining compute remains unavailable unless its published source explicitly records it.",
                        "PaperSmall",
                    )
                )

    protocol = report["research_protocol"]
    aggregates = report["aggregates"]
    headline = [
        next(
            row
            for row in aggregates
            if row["model"] == model and row["protocol"] == protocol["headline_protocol"]
        )
        for model in report["headline_order"]
    ]
    headline_indices = {entry["model"]: index for index, entry in enumerate(headline)}
    headline_runs = {
        entry["model"]: [
            run
            for run in report["runs"]
            if run["model"] == entry["model"] and run["protocol"] == entry["protocol"]
        ]
        for entry in headline
    }
    training_hours_complete = all(
        run["training_timing"]["training_process_accounting_complete"] is True
        and not run["training_timing"]["recorded_training_process_seconds_is_lower_bound"]
        for run in report["runs"]
        if run["protocol"] == protocol["headline_protocol"]
    )
    request = json.loads(Path(report["request"]).read_text())
    root = Path(request["dataset_root"])
    classes = sorted(
        json.loads((root / "classes.json").read_text())["classes"], key=lambda value: value["id"]
    )
    samples = {
        sample["key"]: sample for sample in json.loads((root / "audit/samples.json").read_text())
    }
    title("RAD semantic segmentation\nThree-seed final-checkpoint study")
    story.append(
        paragraph(
            f"{len(report['runs'])} completed RAD runs | {len(headline)} models | 21 classes | {report['test_images']} test images"
        )
    )
    story.append(
        paragraph(
            "Class-positive IoU averages image IoUs over images containing ground-truth pixels of the class. Pooled IoU combines confusion counts across all images. Each mIoU averages its 21 RAD class scores. Models are ranked by class-positive mIoU. Mean and sample SD summarize RAD adaptation seeds 0, 1 and 2.",
            help_key="miou",
        )
    )
    story.append(
        paragraph(
            "User-requested dual-metric reporting correction recorded "
            + report["report_metric_policy"]["recorded_on"]
            + ". The archived research protocol retains the original study record.",
            "PaperSmall",
        )
    )
    story.append(paragraph("Common recipe " + protocol["headline_protocol"]))
    rows = [
        [
            "Rank",
            "Model",
            paragraph("Class-positive mIoU mean (%)", "PaperCell", "positive"),
            "SD",
            paragraph("Pooled mIoU mean (%)", "PaperCell", "pooled"),
            "SD",
            paragraph("Model FPS mean", "PaperCell", "speed"),
            paragraph("Native FPS mean", "PaperCell", "speed"),
        ]
    ]
    for index, entry in enumerate(headline, 1):
        rows.append(
            [
                index,
                paragraph(entry["model"], "PaperCell", target="model-" + entry["model"]),
                metric(entry["class_positive_image_miou"]["mean"]),
                metric(entry["class_positive_image_miou"]["sample_sd"]),
                metric(entry["pixel_pooled_miou"]["mean"]),
                metric(entry["pixel_pooled_miou"]["sample_sd"]),
                metric(entry["model_only_fps"]["mean"], 1),
                metric(entry["native_pipeline_fps"]["mean"], 1),
            ]
        )
    winners = []
    for column, summaries, scale in (
        (2, [entry["class_positive_image_miou"] for entry in headline], 100),
        (4, [entry["pixel_pooled_miou"] for entry in headline], 100),
        (6, [entry["model_only_fps"] for entry in headline], 1),
        (7, [entry["native_pipeline_fps"] for entry in headline], 1),
    ):
        values = [
            summary["mean"] if summary["complete_three_seeds"] else None for summary in summaries
        ]
        winners.extend(
            (column, index + 1)
            for index in displayed_winner_indices(values, scale=scale, require_complete=True)
        )
    table(rows, [0.05, 0.26, 0.14, 0.06, 0.14, 0.06, 0.145, 0.145], winners)
    story.append(
        paragraph(
            "Green boxes mark the best comparable displayed values, including ties. Higher quality and FPS win. Lower defined false alarms, memory, parameter counts and weight sizes win. RAD comparisons use the common recipe, source quality and size comparisons use matching native stages, and block comparisons use identical scored-class sets. Resource comparisons require complete cohort evidence. Seed boxes compare that model's test quality and speed. Qualitative figures use fixed images and seed 0 for every model.",
            "PaperSmall",
            "green",
        )
    )
    for limitation in report["limitations"]:
        story.append(paragraph(limitation, "PaperSmall"))
    if report["missing_provenance"]:
        story.append(paragraph("Evidence requiring collection", "Heading2"))
        for missing in sorted(set(report["missing_provenance"]))[:8]:
            story.append(paragraph(missing, "PaperSmall"))
        story.append(
            paragraph(
                "The complete missing-evidence list is retained in rad-paper.json.", "PaperSmall"
            )
        )
    reading_guide()
    story.append(PageBreak())
    title("Complete study summary")
    table(
        [["Split", "Images", "Valid ground-truth pixels"]]
        + [
            [
                split.capitalize(),
                report["split_totals"][split]["images"],
                f"{report['split_totals'][split]['valid_pixels']:,}",
            ]
            for split in ("train", "test")
        ],
        [0.3, 0.2, 0.5],
    )
    table(
        [["Class", "Positive train images", "Train pixels", "Positive test images", "Test pixels"]]
        + [
            [
                name,
                f"{report['class_split_support'][name]['train']['positive_images']}\n{100 * report['class_split_support'][name]['train']['positive_image_fraction']:.2f}%",
                f"{report['class_split_support'][name]['train']['pixels']:,}\n{100 * report['class_split_support'][name]['train']['valid_pixel_fraction']:.4f}%",
                f"{report['class_split_support'][name]['test']['positive_images']}\n{100 * report['class_split_support'][name]['test']['positive_image_fraction']:.2f}%",
                f"{report['class_split_support'][name]['test']['pixels']:,}\n{100 * report['class_split_support'][name]['test']['valid_pixel_fraction']:.4f}%",
            ]
            for name in report["class_names"]
        ],
        [0.3, 0.175, 0.175, 0.175, 0.175],
    )
    story.append(
        paragraph(
            "Image percentages divide class-positive images by all images in the named split. Pixel percentages divide ground-truth class pixels by valid labeled pixels in that split. Void pixels are excluded from pixel denominators. One image can contain several classes.",
            "PaperSmall",
        )
    )
    mud = report["class_split_support"]["mud-pumping"]
    story.append(
        paragraph(
            f"Mud-pumping training support is {mud['train']['positive_images']} positive images and {mud['train']['pixels']:,} pixels ({100 * mud['train']['valid_pixel_fraction']:.4f}% of valid training pixels). Test support is {mud['test']['positive_images']} positive images and {mud['test']['pixels']:,} pixels ({100 * mud['test']['valid_pixel_fraction']:.4f}% of valid test pixels).",
            "PaperSmall",
        )
    )
    for quality_field, quality_label in (
        ("class_positive_image_miou", "Class-positive mIoU (%)"),
        ("pixel_pooled_miou", "Pooled mIoU (%)"),
    ):
        story.append(PageBreak())
        title("Speed and segmentation accuracy\n" + quality_label)
        story.append(
            speed_plot(
                "model_only_fps",
                "Mean model-only FPS - batch one, 1024 square",
                quality_field,
                quality_label,
            )
        )
        story.append(
            speed_plot(
                "native_pipeline_fps",
                "Mean native-pipeline FPS - full recorded image workload",
                quality_field,
                quality_label,
            )
        )
        table(
            [["Plot label", "Model", "RAD weight bank"]]
            + [
                [
                    rank,
                    entry["model"],
                    "/".join(
                        sorted(
                            {
                                run["weights"]
                                for run in report["runs"]
                                if run["model"] == entry["model"]
                            }
                        )
                    ),
                ]
                for rank, entry in enumerate(headline, 1)
            ],
            [0.12, 0.68, 0.2],
        )
        story.append(
            paragraph(
                "Plot numbers follow the class-positive rank on the cover. Both plots use the common-GPU final-checkpoint deployment pass. Vertical bars show RAD adaptation sample SD. Horizontal bars include timing noise across the three checkpoint profiles. Native timings cover the recorded preprocessing and inference workload.",
                "PaperSmall",
                "speed",
            )
        )
    for model in report["headline_order"]:
        entries = [entry for entry in aggregates if entry["model"] == model]
        source_stage_pages(model)
        story.append(PageBreak())
        rad_title(model, "RAD IoU comparison", anchor="model-" + model)
        story.append(
            paragraph(
                "Class-positive IoU averages image IoUs over GT-positive images. Pooled IoU combines counts across all test images. Images lists the GT-positive count. All 21 RAD classes have test support.",
                "PaperSmall",
            )
        )
        class_table(entries)
        story.append(paragraph("Deployment and RAD training resources", "Heading2"))
        for entry in entries:
            banks = sorted({run["weights"] for run in report["runs"] if run["model"] == model})
            story.append(paragraph("Final-checkpoint weight bank " + "/".join(banks), "PaperSmall"))
            rows = [["Measurement", "Mean", "SD", "Seeds", "Minimum", "Maximum"]]
            fields = [
                ("Train class-positive mIoU (%)", "train_class_positive_image_miou", 100),
                ("Train-test class-positive mIoU gap (pp)", "conditional_train_test_miou_gap", 100),
                ("Train pooled mIoU (%)", "train_pixel_pooled_miou", 100),
                ("Train-test pooled mIoU gap (pp)", "train_test_miou_gap", 100),
                ("Model-only FPS", "model_only_fps", 1),
                ("Native-pipeline FPS", "native_pipeline_fps", 1),
                ("Observed train allocator peak GiB", "training_peak_bytes", 1 / 2**30),
                ("Sampled train driver peak GiB", "sampled_training_driver_peak_bytes", 1 / 2**30),
                ("Recorded RAD training hours", "training_hours", 1),
                ("Parameters M", "parameter_count", 1 / 1e6),
                ("Weights MiB", "resident_parameter_bytes", 1 / 2**20),
                ("Inference allocator peak GiB", "allocator_peak_bytes", 1 / 2**30),
                ("Inference process GiB", "process_total_bytes", 1 / 2**30),
                ("Native allocator peak GiB", "native_allocator_peak_bytes", 1 / 2**30),
            ]
            resource_help = {
                "train_class_positive_image_miou": "positive",
                "conditional_train_test_miou_gap": "seeds",
                "train_pixel_pooled_miou": "pooled",
                "train_test_miou_gap": "seeds",
                "model_only_fps": "speed",
                "native_pipeline_fps": "speed",
                "training_peak_bytes": "memory",
                "sampled_training_driver_peak_bytes": "memory",
                "training_hours": "seeds",
                "parameter_count": "size",
                "resident_parameter_bytes": "size",
                "allocator_peak_bytes": "memory",
                "process_total_bytes": "memory",
                "native_allocator_peak_bytes": "memory",
            }
            for label, field, scale in fields:
                values = entry[field]
                lower = (field == "training_hours" and entry["training_hours_is_lower_bound"]) or (
                    field == "training_peak_bytes"
                    and not entry["training_allocator_peak_accounting_complete"]
                )
                rows.append(
                    [
                        paragraph(label, "PaperCell", resource_help[field]),
                        metric(values["mean"], scale, lower),
                        "Unknown" if lower else metric(values["sample_sd"], scale),
                        values["n"],
                        metric(values.get("minimum"), scale, lower),
                        metric(values.get("maximum"), scale, lower),
                    ]
                )
            winners = resource_mean_winners(entry, fields)
            table(rows, [0.34, 0.14, 0.14, 0.1, 0.14, 0.14], winners)
        story.append(
            paragraph(
                "Recorded training hours include failed attempts. Missing tails and missing allocator observations produce lower bounds with unknown full-run SD. Allocator peaks take the maximum across retained invocation receipts. Driver memory is sampled separately and includes context. Available measurement counts accompany incomplete resource summaries.",
                "PaperSmall",
            )
        )
        story.append(
            paragraph(
                "Train evaluation covers all 255 images at the test checkpoint and weight bank. Both named IoU methods follow their definitions within each split. Each train-test gap combines fitting and train/test distribution differences. Its SD uses the three individual seed gaps.",
                "PaperSmall",
            )
        )
        story.append(PageBreak())
        rad_title(model, "Class-positive precision, recall and Dice")
        story.append(
            paragraph(
                "For each class, precision, recall and Dice use confusion counts summed only over test images containing ground-truth pixels of that class.",
                "PaperSmall",
            )
        )
        common = next(
            entry for entry in entries if entry["protocol"] == protocol["headline_protocol"]
        )
        rows = [
            [
                "Class",
                paragraph("Precision mean (%)", "PaperCell", "precision"),
                "SD",
                "Recall mean (%)",
                "SD",
                "Dice mean (%)",
                "SD",
            ]
        ]
        for name in report["class_names"]:
            values = common["per_class"][name]
            rows.append(
                [
                    name,
                    *[
                        metric(values[field][statistic])
                        for field in (
                            "positive_image_precision",
                            "positive_image_recall",
                            "positive_image_dice",
                        )
                        for statistic in ("mean", "sample_sd")
                    ],
                ]
            )
        winners = class_mean_winners(
            common,
            [
                (1, "positive_image_precision", True),
                (3, "positive_image_recall", True),
                (5, "positive_image_dice", True),
            ],
        )
        table(rows, [0.28, 0.14, 0.1, 0.14, 0.1, 0.14, 0.1], winners)
        model_runs = [run for run in report["runs"] if run["model"] == model]
        observations = [
            {
                "seed": run["seed"],
                "protocol": run["protocol"],
                **run["training"]["env"]["training_observations"],
            }
            for run in model_runs
            if run["training"].get("env", {}).get("training_observations")
        ]
        if observations:
            story.append(
                paragraph(
                    "Latest-invocation training observations\n"
                    + json.dumps(observations, sort_keys=True),
                    "PaperSmall",
                )
            )
            story.append(
                paragraph(
                    "These counters describe the latest completed RunRecord invocation. Available earlier invocation counters remain in the hash-verified training invocation receipts referenced in the JSON. Interrupted invocation counter tails can be unrecorded.",
                    "PaperSmall",
                )
            )
        for run in model_runs:
            if run["seed"]:
                continue
            training = run["training"]
            cfg = training.get("config", {})
            source = run.get("source_checkpoint") or {}
            initialization = {
                key: {
                    field: "source_checkpoint"
                    if field == "checkpoint" and value == source.get("checkpoint")
                    else value
                    for field, value in item.items()
                }
                for key, item in (training.get("env", {}).get("initialization") or {}).items()
            }
            if initialization.get("invocation_start") == initialization.get(
                "source_stage_initializer"
            ):
                initialization = {
                    "source_and_invocation_start": initialization.get("source_stage_initializer")
                }
            summary = {
                "recipe": run["protocol"],
                "public_model": pdf_model_recipe(cfg.get("model", {})),
                "public_origin_evidence": pdf_origin_summary(run["public_origin_evidence"]),
                "optimizer": cfg.get("optim"),
                "effective_stage_optimizer": training.get("env", {}).get("stage_optimizer"),
                "stage_learning_rates": [
                    {key: stage.get(key) for key in ("lr_scale", "head_group_lr_scale", "iters")}
                    for stage in cfg.get("stages", [])
                ],
                "training_timing": run["training_timing"],
                "source_checkpoint": {key: source.get(key) for key in ("name", "recorded_sha256")},
                "initialization": initialization,
            }
            story.append(
                paragraph(
                    "Initialization and optimizer provenance\n"
                    + json.dumps(pdf_compact_provenance(summary), sort_keys=True),
                    "PaperSmall",
                )
            )
        story.append(PageBreak())
        rad_title(model, "Negative-image false alarms")
        rows = [
            [
                "Class",
                paragraph("Any-pixel mean (%)", "PaperCell", "green"),
                "SD",
                "0.1% area mean (%)",
                "SD",
            ]
        ]
        for name in report["class_names"]:
            values = common["per_class"][name]
            rows.append(
                [
                    name,
                    *[
                        metric(values[field][statistic])
                        for field in (
                            "negative_image_false_alarm_rate",
                            "negative_image_false_alarm_rate_area",
                        )
                        for statistic in ("mean", "sample_sd")
                    ],
                ]
            )
        winners = class_mean_winners(
            common,
            [
                (1, "negative_image_false_alarm_rate", False),
                (3, "negative_image_false_alarm_rate_area", False),
            ],
        )
        table(rows, [0.36, 0.2, 0.12, 0.2, 0.12], winners)
        story.append(
            paragraph(
                "False-alarm denominators contain images with zero ground-truth pixels of the named class. The fixed rules count any predicted pixel, or predicted area at least 0.1 percent of valid pixels. N/A identifies an unavailable denominator. Exact support counts remain in the JSON.",
                "PaperSmall",
            )
        )
        story.append(paragraph("Individual RAD replicates and observed range", "Heading2"))
        rows = [
            [
                paragraph("Measurement", "PaperCell", "seeds"),
                "Seed 0",
                "Seed 1",
                "Seed 2",
                "Minimum",
                "Maximum",
                "Mean",
                "SD",
            ]
        ]
        replicate_fields = [
            ("Train class-positive mIoU (%)", common["train_class_positive_image_miou"], 100),
            ("Test class-positive mIoU (%)", common["class_positive_image_miou"], 100),
            ("Train-test class-positive gap (pp)", common["conditional_train_test_miou_gap"], 100),
            ("Train pooled mIoU (%)", common["train_pixel_pooled_miou"], 100),
            ("Test pooled mIoU (%)", common["pixel_pooled_miou"], 100),
            ("Train-test pooled gap (pp)", common["train_test_miou_gap"], 100),
            (
                "Mud class-positive IoU (%)",
                common["per_class"]["mud-pumping"]["positive_image_iou"],
                100,
            ),
            ("Mud pooled IoU (%)", common["per_class"]["mud-pumping"]["iou"], 100),
            ("Model-only FPS", common["model_only_fps"], 1),
            ("Native-pipeline FPS", common["native_pipeline_fps"], 1),
            ("Recorded training hours", common["training_hours"], 1),
        ]
        seed_winners = []
        seed_objectives = {
            "Test class-positive mIoU (%)",
            "Mud class-positive IoU (%)",
            "Test pooled mIoU (%)",
            "Mud pooled IoU (%)",
            "Model-only FPS",
            "Native-pipeline FPS",
        }
        for row, (label, values, scale) in enumerate(replicate_fields, 1):
            lower = values.get("mean_and_range_are_lower_bounds", False)
            rows.append(
                [
                    label,
                    *[
                        metric(
                            values["seeds"].get(str(seed)),
                            scale,
                            seed in values.get("lower_bound_seeds", []),
                        )
                        for seed in range(3)
                    ],
                    metric(values.get("minimum"), scale, lower),
                    metric(values.get("maximum"), scale, lower),
                    metric(values["mean"], scale, lower),
                    "Unknown"
                    if label == "Recorded training hours"
                    and common["training_hours_is_lower_bound"]
                    else metric(values["sample_sd"], scale),
                ]
            )
            if label in seed_objectives:
                candidates = [values["seeds"].get(str(seed)) for seed in range(3)]
                seed_winners.extend(
                    (seed + 1, row) for seed in displayed_winner_indices(candidates, scale=scale)
                )
        table(rows, [0.3] + [0.1] * 7, seed_winners)
        story.append(
            paragraph(
                "FPS variation across adaptation seeds includes timing noise. Resource summaries with fewer available measurements remain descriptive and retain their observed count in the resource table. Unknown recovery tails do not trigger a scientific rerun.",
                "PaperSmall",
            )
        )
        common_runs = [
            run for run in model_runs if run["protocol"] == protocol["headline_protocol"]
        ]
        story.append(PageBreak())
        rad_title(model, "Scene-block sensitivity")
        for field, heading in (
            ("per_block", "Per-block test scores"),
            ("leave_one_block_out", "Leave-one-block-out sensitivity"),
        ):
            story.append(paragraph(heading, "Heading2"))
            rows = [
                [
                    "Block",
                    "Scored images",
                    "GT-positive classes",
                    "Pooled classes by seed",
                    paragraph("Class-positive mIoU mean (%)", "PaperCell", "positive"),
                    "SD",
                    paragraph("Pooled mIoU mean (%)", "PaperCell", "pooled"),
                    "SD",
                ]
            ]
            blocks = common_runs[0]["metrics"][field]
            for block in blocks:
                statistics = seed_summary(
                    {
                        run["seed"]: run["metrics"][field][block]["class_positive_images"]["miou"]
                        for run in common_runs
                    }
                )
                pooled_statistics = seed_summary(
                    {
                        run["seed"]: run["metrics"][field][block]["pixel_pooled"]["miou"]
                        for run in common_runs
                    }
                )
                first = common_runs[0]["metrics"][field][block]
                rows.append(
                    [
                        block,
                        first["images"],
                        first["class_positive_images"]["macro_scored_classes"],
                        "/".join(
                            str(
                                run["metrics"][field][block]["pixel_pooled"]["macro_scored_classes"]
                            )
                            for run in sorted(common_runs, key=lambda value: value["seed"])
                        ),
                        metric(statistics["mean"]),
                        metric(statistics["sample_sd"]),
                        metric(pooled_statistics["mean"]),
                        metric(pooled_statistics["sample_sd"]),
                    ]
                )
            winners = block_mean_winners(
                model, field, blocks, "class_positive_images", "mean_image_iou", 4
            )
            winners.extend(block_mean_winners(model, field, blocks, "pixel_pooled", "iou", 6))
            table(rows, [0.29, 0.08, 0.09, 0.14, 0.14, 0.06, 0.14, 0.06], winners)
        story.append(
            paragraph(
                "Class-positive mIoU averages GT-supported class means within the scored subset. Pooled mIoU uses classes with GT or predicted pixels, so its class count can differ by seed. Green comparisons require matching class sets for the named metric. Leave-one-block-out rows exclude the named block. Four inferred scene blocks provide descriptive sensitivity, with recording independence unconfirmed. Full class statistics remain in the JSON.",
                "PaperSmall",
            )
        )
        job = next(
            job
            for job in request["jobs"]
            if job["model"] == model
            and job["protocol"] == protocol["headline_protocol"]
            and job["seed"] == 0
        )
        keys = protocol["qualitative_keys"]
        for start in range(0, len(keys), 4):
            story.append(PageBreak())
            rad_title(model, "Full semantic overlays")
            story.append(
                paragraph(
                    "Prespecified common recipe | fixed seed 0 | complete model predictions | GT void transparent and ignored in scores",
                    "PaperSmall",
                )
            )
            table([["Original RGB", "Ground truth - all classes", "Prediction - all classes"]])
            for key in keys[start : start + 4]:
                story.append(paragraph(key, "PaperSmall"))
                panel = semantic_panel(request, job, key, classes, samples[key])
                story.append(PdfImage(panel, width=width, height=width * 300 / 1500))
                story.append(Spacer(1, 3))
            legend(classes)
    story.append(PageBreak())
    title("Exact provenance")
    for field in (
        "request",
        "request_sha256",
        "training_plan_sha256",
        "training_campaign_sha256",
        "training_code_sha",
        "report_code_sha",
        "report_code_dirty",
        "split_sha256",
        "samples_sha256",
    ):
        story.append(paragraph(field.replace("_", " ") + "\n" + str(report[field]), "PaperSmall"))
    story.append(
        paragraph(
            "Every RAD run binds its configuration and final checkpoint. Full state hashes, raw timing samples, optimizer recipes, source records, per-block statistics and individual-seed metrics remain in rad-paper.json and the hashed artifacts it references.",
            "PaperSmall",
        )
    )
    for run in report["runs"]:
        story.append(
            KeepTogether(
                [
                    paragraph(
                        run["name"]
                        + "\nconfig "
                        + run["config_sha256"]
                        + "\nfinal "
                        + run["final_checkpoint_sha256"],
                        "PaperSmall",
                    )
                ]
            )
        )
    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=35,
        bottomMargin=35,
        title="RAD semantic segmentation - three-seed paper study",
    ).build(story, onFirstPage=footer, onLaterPages=footer)


def build(request_path: Path, out: Path, source_positive_path: Path | None = None) -> dict:
    report = load_report(request_path, source_positive_path)
    out.mkdir(parents=True, exist_ok=True)
    write(out / "rad-paper.json", report)
    write_csv(out / "rad-paper.csv", report)
    build_pdf(out / "rad-paper.pdf", report)
    return {
        "status": "completed",
        "files": [str(out / name) for name in ("rad-paper.json", "rad-paper.csv", "rad-paper.pdf")],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-positive-evaluations", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.request.resolve(), args.out.resolve(), args.source_positive_evaluations),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
