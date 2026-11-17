#!/usr/bin/env python3
"""Explicit, frozen-checkpoint RAD held-out-test evaluation.

This is deliberately separate from the validation-only campaign collectors. It never
trains, chooses a checkpoint, changes the historical campaign, or chooses an
initialization using test results. Standardized final-checkpoint profiling is
recorded separately from full-image test inference.
The request must explicitly authorize test evaluation and be byte-hashed in a new
campaign.json carrying its own frozen GPU policy. The caller assigns one idle GPU
using gpu_policy.child_env before launching this one-job process.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime
from scripts.rad_test_contract import evaluation_mode

from segmentary import gpu_policy
from segmentary.engine.present_image import present_image_metrics


class TestEvaluationError(ValueError):
    """The explicitly authorized, frozen test evaluation cannot be verified."""


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def digest(path: str | Path) -> str:
    return runtime.digest(path)


def verified_path(path: str | Path, expected: str, label: str) -> Path:
    value = Path(path)
    if not expected or digest(value) != expected:
        raise TestEvaluationError(f"{label} SHA-256 changed: {value}")
    return value


def validate_request(request_path: Path, job_name: str, gpu: int) -> tuple[dict, dict, dict]:
    request = read_json(request_path)
    if request.get("schema_version") not in (1, 2):
        raise TestEvaluationError(
            "A version-1 or version-2 request explicitly authorizing test evaluation is required"
        )
    try:
        evaluation_mode(request)
    except ValueError as error:
        raise TestEvaluationError(
            f"A request explicitly authorizing evaluation is required: {error}"
        ) from error
    campaign_path = Path(request["campaign_json"])
    campaign = read_json(campaign_path)
    if campaign.get("request_sha256") != digest(request_path):
        raise TestEvaluationError("Request differs from the byte-hash frozen in campaign.json")
    if request["schema_version"] == 2:
        from scripts.rad_test_contract import validate_v2, verify_evaluation_code

        authorized = validate_v2(request, campaign)
        verify_evaluation_code(campaign, Path(__file__).resolve().parents[1])
        if not set(gpu_policy.allowed_indices(gpu_policy.load(campaign))) <= authorized:
            raise TestEvaluationError("Frozen test GPU policy exceeds the campaign authorization")
    elif request.get("rehearsal"):
        from scripts.rad_test_contract import verify_evaluation_code

        verify_evaluation_code(campaign, Path(__file__).resolve().parents[1])
    policy = gpu_policy.load(campaign)
    if request["schema_version"] == 1 and not set(gpu_policy.allowed_indices(policy)) <= {
        0,
        1,
        2,
        3,
        7,
        8,
        9,
    }:
        raise TestEvaluationError("Legacy test policy exceeds the authorized GPU allowlist")
    if campaign.get("gpu_policy_sha256") != gpu_policy.policy_sha256(policy):
        raise gpu_policy.GpuPolicyError("Frozen GPU policy SHA-256 changed")
    gpu_policy.require_allowed(policy, gpu)
    if Path(os.environ.get(gpu_policy.POLICY_ENV, "")).resolve() != campaign_path.resolve():
        raise gpu_policy.GpuPolicyError("Child must use this test campaign's SEGMENTARY_GPU_POLICY")
    gpu_policy.assert_env(policy, gpu)
    jobs = request.get("jobs", [])
    names = [j["name"] for j in jobs]
    if len(names) != len(set(names)):
        raise TestEvaluationError("Request has duplicate job names")
    matched = [j for j in jobs if j["name"] == job_name]
    if len(matched) != 1 or Path(job_name).name != job_name or job_name in {".", ".."}:
        raise TestEvaluationError(f"Request must identify exactly one safe job: {job_name}")
    job = matched[0]
    verified_path(job["config"], job["config_sha256"], "Configuration")
    verified_path(job["final_checkpoint"], job["final_checkpoint_sha256"], "Final checkpoint")
    state = read_json(job["state_path"])
    source = state.get("checkpoints", {}).get("final", {})
    if source.get("sha256") != job["final_checkpoint_sha256"]:
        raise TestEvaluationError("Request checkpoint differs from source state's final checkpoint")
    if Path(source.get("path", "")).resolve() != Path(job["final_checkpoint"]).resolve():
        raise TestEvaluationError("Request path differs from source state's final checkpoint")
    if state.get("status") != "completed":
        raise TestEvaluationError("Source training job is not completed")
    if "state_sha256" in job:
        verified_path(job["state_path"], job["state_sha256"], "Source state")
    if request.get("rehearsal") and (
        not job.get("state_sha256")
        or state.get("code_sha") != campaign.get("code_sha")
        or state.get("collection", {}).get("verified") is not True
    ):
        raise TestEvaluationError("Rehearsal requires verified same-code smoke endpoints")
    return request, job, campaign


def audited_pixels(sample: dict, n: int) -> np.ndarray:
    expected = np.zeros(n, dtype=np.int64)
    for key, count in sample["class_pixels"].items():
        index = int(key)
        if 0 <= index < n:
            expected[index] = int(count)
        elif index != 255 and int(count):
            raise TestEvaluationError(f"Invalid audited class {index}")
    return expected


def validate_dataset(request: dict, names: list[str]) -> list[dict]:
    root = Path(request["dataset_root"])
    verified_path(root / "splits.json", request["split_sha256"], "Dataset split")
    verified_path(root / "audit/samples.json", request["samples_sha256"], "Dataset sample audit")
    splits = read_json(root / "splits.json")
    samples = read_json(root / "audit/samples.json")
    if len(names) != 21 or request.get("class_names") != names or names.index("mud-pumping") != 13:
        raise TestEvaluationError("Expected exact ordered 21-class RAD taxonomy (mud-pumping = 13)")
    seen: set[str] = set()
    by_split = {}
    image_splits: dict[str, str] = {}
    for split in ("train", "val", "test"):
        selected = [s for s in samples if s["split"] == split]
        keys = [s["key"] for s in selected]
        if len(set(keys)) != len(keys) or set(keys) != set(splits[split]):
            raise TestEvaluationError(f"{split}: split keys do not match the audited images")
        if seen.intersection(keys):
            raise TestEvaluationError("Image keys overlap across splits")
        seen.update(keys)
        for sample in selected:
            prior = image_splits.setdefault(sample["image_sha256"], split)
            if prior != split:
                raise TestEvaluationError("Identical image bytes overlap train/validation/test")
            if Path(sample["key"]).is_absolute() or ".." in Path(sample["key"]).parts:
                raise TestEvaluationError("Unsafe sample key")
        by_split[split] = selected
    if sum(map(len, by_split.values())) != len(samples):
        raise TestEvaluationError("Unknown splits in sample audit")
    split = "train" if request.get("rehearsal") else "test"
    selected = sorted(by_split[split], key=lambda s: s["key"])
    if request.get("rehearsal"):
        wanted = set(request["image_keys"])
        if not wanted <= set(splits["train"]):
            raise TestEvaluationError("Rehearsal image keys must belong to training")
        selected = [sample for sample in selected if sample["key"] in wanted]
    if not selected:
        raise TestEvaluationError("Test split is empty")
    support = sum((audited_pixels(s, len(names)) > 0 for s in selected), np.zeros(len(names), int))
    if (support == 0).any():
        missing = [names[i] for i in np.flatnonzero(support == 0)]
        raise TestEvaluationError(f"Test must contain all 21 classes; absent: {missing}")
    return selected


def load_test_image(root: Path, sample: dict, n: int) -> tuple[np.ndarray, np.ndarray]:
    key = sample["key"]
    split = sample.get("split", "test")
    if split not in ("train", "test"):
        raise TestEvaluationError("Expected a scored training rehearsal or test sample")
    image_path = root / "images" / split / (key + sample["image_extension"])
    target_path = root / "masks" / split / (key + ".png")
    verified_path(image_path, sample["image_sha256"], "Test image")
    with Image.open(target_path) as decoded:
        if decoded.mode != "L" or decoded.size != (sample["width"], sample["height"]):
            raise TestEvaluationError(f"Mask dimensions or encoding changed: {key}")
        target = np.asarray(decoded).copy()
    if hashlib.sha256(target.tobytes()).hexdigest() != sample["mask_sha256"]:
        raise TestEvaluationError(f"Decoded test mask changed: {key}")
    values, counts = np.unique(target, return_counts=True)
    if any(int(value) not in set(range(n)) | {255} for value in values):
        raise TestEvaluationError(f"Invalid test class IDs: {key}")
    actual = np.zeros(n, np.int64)
    for value, count in zip(values, counts, strict=True):
        if value < n:
            actual[value] = count
    if not np.array_equal(actual, audited_pixels(sample, n)):
        raise TestEvaluationError(f"Test mask does not match audited class_pixels: {key}")
    with Image.open(image_path) as image:
        rgb = np.asarray(image.convert("RGB")).copy()
    if rgb.shape[:2] != target.shape:
        raise TestEvaluationError(f"Image and mask dimensions disagree: {key}")
    return rgb, target


def cropped_prediction(prediction: np.ndarray, target_shape: tuple[int, ...], n: int) -> np.ndarray:
    if (
        prediction.ndim != 2
        or prediction.shape[0] < target_shape[0]
        or prediction.shape[1] < target_shape[1]
    ):
        raise TestEvaluationError("Prediction cannot be cropped back to the original full image")
    pred = prediction[: target_shape[0], : target_shape[1]]
    if not np.issubdtype(pred.dtype, np.integer) or (pred < 0).any() or (pred >= n).any():
        raise TestEvaluationError("Prediction contains invalid class IDs")
    return pred.astype(np.uint8)


def confusion(target: np.ndarray, pred: np.ndarray, n: int) -> np.ndarray:
    if pred.shape != target.shape:
        raise TestEvaluationError("Prediction shape differs from original test mask")
    valid = target != 255
    return np.bincount(
        target[valid].astype(np.int64) * n + pred[valid].astype(np.int64), minlength=n * n
    ).reshape(n, n)


def summarize(matrices: dict[str, np.ndarray], names: list[str], samples: list[dict]) -> dict:
    if set(matrices) != {s["key"] for s in samples}:
        raise TestEvaluationError("Per-image confusion does not cover exactly the test split")
    n = len(names)
    for sample in samples:
        matrix = matrices[sample["key"]]
        if matrix.shape != (n, n) or not np.array_equal(matrix.sum(1), audited_pixels(sample, n)):
            raise TestEvaluationError(
                f"Confusion rows differ from audited class_pixels: {sample['key']}"
            )
    score = present_image_metrics(matrices.values(), n)
    if score.miou_classes != n:
        raise TestEvaluationError("All 21 classes must have positive test support")
    return {
        "images": score.images,
        "miou_present_images": score.miou,
        "miou_present_images_classes": score.miou_classes,
        "per_class": {
            name: {
                "positive_images": s.images,
                "iou": s.iou,
                "precision": s.precision,
                "recall": s.recall,
                "tp": s.tp,
                "fp": s.fp,
                "fn": s.fn,
            }
            for name, s in zip(names, score.classes, strict=True)
        },
    }


def completed_result(
    directory: Path, request_sha: str, checkpoint_sha: str, *, rehearsal=False
) -> dict | None:
    path = directory / "result.json"
    if not path.exists():
        return None
    value = read_json(path)
    if not (
        value.get("status") == "completed"
        and value.get("request_sha256") == request_sha
        and value.get("checkpoint_sha256") == checkpoint_sha
        and value.get("split") == ("train" if rehearsal else "test")
        and value.get("test_evaluated") is (not rehearsal)
        and bool(value.get("rehearsal")) == rehearsal
    ):
        raise TestEvaluationError("Existing completed result belongs to a different evaluation")
    for artifact in value["artifacts"].values():
        verified_path(artifact["path"], artifact["sha256"], "Completed artifact")
    with (directory / "per-image.csv").open() as stream:
        for row in csv.DictReader(stream):
            verified_path(
                directory / "predictions" / (row["key"] + ".png"),
                row["prediction_sha256"],
                "Completed prediction",
            )
    return value


def evaluate(request_path: Path, job_name: str, gpu: int) -> dict:
    request, job, campaign = validate_request(request_path, job_name, gpu)
    split, held_out = evaluation_mode(request)
    rehearsal = not held_out
    policy = gpu_policy.load(campaign)
    # Verify physical placement before importing the model implementation or touching CUDA.
    gpu_policy.enforce_from_env(init_cuda=False)
    from segmentary.config import load_experiment
    from segmentary.taxonomy import load_space

    cfg = load_experiment([Path(job["config"])])
    names = list(load_space(cfg.taxonomy_root, cfg.space).names)
    if Path(cfg.stages[0].data[0].root).resolve() != Path(request["dataset_root"]).resolve():
        raise TestEvaluationError("Frozen model configuration uses a different dataset")
    samples = validate_dataset(request, names)
    directory = Path(request["output_root"]) / job_name
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".evaluate.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        done = completed_result(
            directory, digest(request_path), job["final_checkpoint_sha256"], rehearsal=rehearsal
        )
        if done is not None:
            return done
        # Fail before CUDA initialization if another process uses the assigned GPU.
        assigned_uuid = gpu_policy.normalize_uuid(gpu_policy.require_allowed(policy, gpu)["uuid"])
        if any(
            gpu_policy.normalize_uuid(uuid) == assigned_uuid
            for _, uuid in gpu_policy.compute_apps()
        ):
            raise gpu_policy.GpuPolicyError(f"GPU {gpu} is no longer idle")
        import torch

        from segmentary.data.loaders import aug_from_spec
        from segmentary.data.transforms import build_eval_transform
        from segmentary.engine.ema import ema_evaluation_safe
        from segmentary.engine.inference import (
            InferenceConfig,
            inference,
            prediction_from_inference,
        )
        from segmentary.engine.metrics import ConfusionMatrix
        from segmentary.eval import load_configured_checkpoint
        from segmentary.models.factory import build_model
        from segmentary.performance import measure_cuda_forward, process_gpu_used_bytes
        from segmentary.utils.provenance import collect_env
        from segmentary.utils.seed import seed_everything

        torch.set_num_threads(4)
        seed_everything(int(job["seed"]), deterministic=True)
        placement = gpu_policy.enforce_from_env(init_cuda=True)
        started_at = runtime.now()
        started = time.monotonic()
        model = build_model(cfg.model, len(names))
        use_ema = ema_evaluation_safe(model)
        if request["schema_version"] == 2 or rehearsal:
            recorded_bank = (
                read_json(job["state_path"])
                .get("training", {})
                .get("env", {})
                .get("final_weights_policy")
            )
            if recorded_bank != ("ema" if use_ema else "raw"):
                raise TestEvaluationError(
                    "Evaluation bank differs from the recorded final training policy"
                )
        model = (
            load_configured_checkpoint(model, cfg, Path(job["final_checkpoint"]), use_ema)
            .cuda()
            .eval()
        )
        performance = None
        if request["schema_version"] == 1 and not rehearsal:
            # Same model-only normalized-space zero input as the existing benchmark.
            # Measure before full-resolution evaluation changes the CUDA allocator cache.
            image = torch.zeros((1, 3, 1024, 1024), dtype=torch.float32, device="cuda").contiguous()
            profile_started = time.monotonic()
            latency, peak = measure_cuda_forward(
                model, image, warmup=20, iterations=100, expected_channels=len(names)
            )
            gpu_entry = gpu_policy.require_allowed(policy, gpu)
            properties = torch.cuda.get_device_properties(0)
            performance = {
                "schema_version": 1,
                "status": "complete",
                "model_id": job["model"],
                "benchmark_scope": "rad_final_checkpoint_model_only",
                "measured_at": runtime.now(),
                "source": {
                    "checkpoint_sha256": job["final_checkpoint_sha256"],
                    "config_sha256": job["config_sha256"],
                    "weights": "ema" if use_ema else "raw",
                },
                "hardware": {
                    "gpu_name": properties.name,
                    "gpu_uuid": gpu_entry["uuid"],
                    "physical_visibility_token": str(gpu),
                    "logical_device": "cuda:0",
                },
                "model": {
                    "parameter_count": sum(p.numel() for p in model.parameters()),
                    "resident_parameter_bytes": sum(
                        p.numel() * p.element_size() for p in model.parameters()
                    ),
                },
                "contract": {
                    "precision": "bf16_autocast",
                    "deterministic": True,
                    "batch_size": 1,
                    "input_shape_nchw": [1, 3, 1024, 1024],
                    "warmup_iterations": 20,
                    "measured_iterations": 100,
                    "model_only": True,
                    "input": "zeros in normalized input space, matching existing benchmark",
                    "includes_preprocessing": False,
                    "includes_data_loader": False,
                    "includes_sliding_window": False,
                },
                "measurements": {
                    "latency": latency,
                    "peak_reserved_bytes": peak,
                    "process_total_bytes": process_gpu_used_bytes(gpu_entry["uuid"]),
                    "memory_kind": "pytorch_cuda_allocator_peak_reserved_excluding_context",
                    "benchmark_wall_clock_s": time.monotonic() - profile_started,
                },
            }
            runtime.write(directory / "performance.json", performance)
            del image
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        transform = build_eval_transform(aug_from_spec(cfg.aug, model), pad_to_multiple=32)
        infer_cfg = InferenceConfig(
            sliding_window=cfg.eval.sliding_window,
            window=tuple(cfg.eval.window),
            stride=tuple(cfg.eval.stride),
            scales=(1.0,),
            flip=False,
        )
        matrices: dict[str, np.ndarray] = {}
        rows = []
        data_root = Path(request["dataset_root"])
        for index, sample in enumerate(samples, 1):
            rgb, target = load_test_image(data_root, sample, len(names))
            item = transform(image=rgb, mask=target)
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                logits = inference(
                    model, item["image"].unsqueeze(0).contiguous().cuda(), len(names), infer_cfg
                )
                if not torch.isfinite(logits).all():
                    raise TestEvaluationError(f"Nonfinite inference logits: {sample['key']}")
                raw_pred = prediction_from_inference(logits.float(), infer_cfg)[0].cpu().numpy()
            pred = cropped_prediction(raw_pred, target.shape, len(names))
            matrix = confusion(target, pred, len(names))
            matrices[sample["key"]] = matrix
            path = directory / "predictions" / (sample["key"] + ".png")
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(pred).save(path)
            single = present_image_metrics([matrix], len(names))
            rows.append(
                {
                    "key": sample["key"],
                    "split": split,
                    "group": sample["group"],
                    "image_sha256": sample["image_sha256"],
                    "mask_decoded_sha256": sample["mask_sha256"],
                    "prediction_sha256": digest(path),
                    **{f"iou:{name}": s.iou for name, s in zip(names, single.classes, strict=True)},
                }
            )
            print(f"{job_name}: {split} {index}/{len(samples)} {sample['key']}", flush=True)
        present = summarize(matrices, names, samples)
        total = sum(matrices.values(), np.zeros((len(names), len(names)), np.int64))
        pixel = ConfusionMatrix(len(names), 255, device="cpu")
        pixel.mat.copy_(torch.from_numpy(total))
        pixel_metrics = {**pixel.compute().as_dict(names), "confusion": total.tolist()}
        runtime.write(
            directory / "metrics.json", {"present_image": present, "pixel_pooled": pixel_metrics}
        )
        with (directory / "per-image.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        (directory / "per-image-confusion.json.gz").write_bytes(
            gzip.compress(
                json.dumps(
                    {key: value.tolist() for key, value in matrices.items()}, separators=(",", ":")
                ).encode(),
                mtime=0,
            )
        )
        coverage = {
            name: {
                "positive_images": present["per_class"][name]["positive_images"],
                "pixels": int(total[c].sum()),
            }
            for c, name in enumerate(names)
        }
        runtime.write(directory / "coverage.json", coverage)
        from scripts.rad_paper_metrics import paper_metrics

        runtime.write(
            directory / "paper-metrics.json",
            paper_metrics(matrices, names, {sample["key"]: sample["group"] for sample in samples}),
        )
        selection = {
            "validation_miou": job.get("validation_miou"),
            "selected_by_validation": job.get("selected_by_validation"),
            "checkpoint": "final",
            "test_used_for_selection": False,
        }
        if request["schema_version"] == 2:
            selection = {
                "method": "all_prespecified_initialization_recipes_and_seeds",
                "primary_metric": request["research_protocol"]["primary_metric"],
                "headline_protocol": request["research_protocol"]["headline_protocol"],
                "checkpoint": "final",
                "test_used_for_selection": False,
            }
        result = {
            "schema_version": request["schema_version"],
            "status": "completed",
            "test_evaluated": held_out,
            "rehearsal": rehearsal,
            "split": split,
            "name": job_name,
            "model": job["model"],
            "protocol": job["protocol"],
            "seed": job["seed"],
            "request_sha256": digest(request_path),
            "evaluation_code_sha": campaign.get("code_sha"),
            "source_state_path": job["state_path"],
            "checkpoint_sha256": job["final_checkpoint_sha256"],
            "config_sha256": job["config_sha256"],
            "split_sha256": request["split_sha256"],
            "samples_sha256": request["samples_sha256"],
            "images": len(samples),
            "weights": "ema" if use_ema else "raw",
            "deterministic": True,
            "precision": "bf16_autocast",
            "padding": {"multiple": 32, "prediction_cropped_to_original": True},
            "inference": {
                "sliding_window": cfg.eval.sliding_window,
                "window": list(cfg.eval.window),
                "stride": list(cfg.eval.stride),
                "scales": [1.0],
                "flip": False,
            },
            "selection": selection,
            "gpu": placement,
            "started_at": started_at,
            "finished_at": runtime.now(),
            "wall_seconds": time.monotonic() - started,
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            "present_image": present,
            "pixel_pooled": pixel_metrics,
            "performance": performance,
            "performance_authority": "separate frozen deployment-performance record"
            if performance is None
            else "legacy inline deterministic profile",
            "environment": collect_env(),
            "artifacts": {
                name: {"path": str(directory / name), "sha256": digest(directory / name)}
                for name in [
                    "metrics.json",
                    "per-image.csv",
                    "per-image-confusion.json.gz",
                    "coverage.json",
                    "paper-metrics.json",
                    *(["performance.json"] if performance is not None else []),
                ]
            },
        }
        runtime.write(directory / "summary.json", result)
        runtime.write(directory / "result.json", result)  # completion marker is written last
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--gpu", type=int, required=True)
    args = parser.parse_args()
    value = evaluate(args.request.resolve(), args.job, args.gpu)
    print(
        json.dumps({"status": value["status"], "name": value["name"], "images": value["images"]}),
        flush=True,
    )


if __name__ == "__main__":
    main()
