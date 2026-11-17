#!/usr/bin/env python3
"""Profile frozen final RAD checkpoints in a fresh deployment-performance process.

Test scores and predictions remain unchanged. This separate process deliberately
uses the existing deployment timing contract (nondeterministic kernels, cuDNN
benchmarking, batch-one 1024-square BF16) rather than deterministic evaluation
settings. Only already completed, explicitly authorized test jobs may be profiled.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import evaluate_rad_test as test_eval
from scripts import run_rtis_campaign as runtime

from segmentary import gpu_policy

TASK = "rad-final-deployment-profile"


def output_directory(request: dict, job_name: str) -> Path:
    return Path(request["output_root"]).parent / "deployment-performance" / job_name


def require_finished_test(request: dict, job: dict, request_sha: str) -> tuple[Path, dict]:
    path = Path(request["output_root"]) / job["name"] / "result.json"
    value = test_eval.read_json(path)
    if not (
        value.get("status") == "completed"
        and value.get("test_evaluated") is True
        and value.get("split") == "test"
        and value.get("name") == job["name"]
        and value.get("request_sha256") == request_sha
        and value.get("checkpoint_sha256") == job["final_checkpoint_sha256"]
        and value.get("images", 0) > 0
    ):
        raise test_eval.TestEvaluationError(
            "A matching completed final-checkpoint test job is required"
        )
    return path, value


def deployment_contract() -> dict:
    return {
        "backend": "pytorch",
        "precision": "bf16_autocast",
        "deterministic": False,
        "cudnn_benchmark": True,
        "batch_size": 1,
        "input_shape_nchw": [1, 3, 1024, 1024],
        "warmup_iterations": 20,
        "measured_iterations": 100,
        "timing": "per-forward CUDA events with end-event synchronization",
        "input": "zeros in normalized input space, matching existing benchmark",
        "model_only": True,
        "includes_preprocessing": False,
        "includes_data_loader": False,
        "includes_sliding_window": False,
        "includes_argmax_or_metrics": False,
        "input_resident_on_gpu": True,
        "entrypoint": "public model(image) dense-logits forward",
    }


def configure_deployment_seed(seed: int) -> None:
    import torch

    from segmentary.utils.seed import seed_everything

    # A fresh child process is expected; make the timing mode explicit even if a
    # caller reuses this function in-process. No CUDA allocation precedes seeding.
    torch.use_deterministic_algorithms(False)
    torch.backends.cudnn.deterministic = False
    seed_everything(seed, deterministic=False)


def native_pipeline_profile(model, cfg, request: dict, names: list[str], gpu_uuid: str) -> dict:
    """Time every native test image with GT checks and file I/O outside the interval."""
    import torch

    from segmentary.data.loaders import aug_from_spec
    from segmentary.data.transforms import build_eval_transform
    from segmentary.engine.inference import InferenceConfig, inference, prediction_from_inference
    from segmentary.performance import latency_summary, process_gpu_used_bytes

    samples = test_eval.validate_dataset(request, names)
    root = Path(request["dataset_root"])
    transform = build_eval_transform(aug_from_spec(cfg.aug, model), pad_to_multiple=32)
    infer_cfg = InferenceConfig(
        sliding_window=cfg.eval.sliding_window,
        window=tuple(cfg.eval.window),
        stride=tuple(cfg.eval.stride),
        scales=(1.0,),
        flip=False,
    )

    def predict(rgb, shape):
        image = transform(image=rgb)["image"].unsqueeze(0).contiguous().cuda()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            logits = inference(model, image, len(names), infer_cfg)
            pred = prediction_from_inference(logits.float(), infer_cfg)[0]
            output = pred[: shape[0], : shape[1]].cpu().numpy()
        if output.shape != shape:
            raise test_eval.TestEvaluationError(
                "Native benchmark failed to restore original image dimensions"
            )

    first_rgb, first_target = test_eval.load_test_image(root, samples[0], len(names))
    for _ in range(2):
        predict(first_rgb, first_target.shape)
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    rows = []
    for sample in samples:
        rgb, target = test_eval.load_test_image(root, sample, len(names))
        torch.cuda.synchronize()
        started = time.perf_counter()
        predict(rgb, target.shape)
        torch.cuda.synchronize()
        rows.append(
            {
                "key": sample["key"],
                "width": sample["width"],
                "height": sample["height"],
                "ms": (time.perf_counter() - started) * 1000,
            }
        )
    return {
        "contract": {
            "precision": "bf16_autocast",
            "deterministic": False,
            "batch_size": 1,
            "resolution": "native, bottom/right stride-32 padding, cropped predictions",
            "sliding_window": cfg.eval.sliding_window,
            "window": list(cfg.eval.window),
            "stride": list(cfg.eval.stride),
            "warmup_images": 2,
            "warmup_image_key": samples[0]["key"],
            "measured_images": len(samples),
            "includes": [
                "RGB preprocessing",
                "host-to-device transfer",
                "model inference and tiling",
                "argmax",
                "cropping",
                "device-to-host transfer",
            ],
            "excludes": [
                "image decoding",
                "file I/O",
                "GT checks",
                "quality metrics",
                "prediction saving",
            ],
            "timing": "synchronized per-image wall clock",
            "quality_scores_source": "separate deterministic test evaluation",
        },
        "measurements": {
            "latency": latency_summary([row["ms"] for row in rows]),
            "per_image": rows,
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "process_total_bytes": process_gpu_used_bytes(gpu_uuid),
            "process_total_kind": "post-loop process sample including context, whole-pipeline process peak unmeasured",
        },
    }


def completed_profile(directory: Path, request_sha: str, checkpoint_sha: str) -> dict | None:
    path = directory / "result.json"
    if not path.exists():
        return None
    value = test_eval.read_json(path)
    if not (
        value.get("status") == "completed"
        and value.get("task") == TASK
        and value.get("request_sha256") == request_sha
        and value.get("checkpoint_sha256") == checkpoint_sha
        and value.get("performance", {}).get("contract") == deployment_contract()
    ):
        raise test_eval.TestEvaluationError(
            "Existing profile has a different identity or timing contract"
        )
    artifact = value["artifacts"]["performance.json"]
    expected_path = (directory / "performance.json").resolve()
    if Path(artifact["path"]).resolve() != expected_path:
        raise test_eval.TestEvaluationError(
            "Completed profile artifact is outside its job directory"
        )
    test_eval.verified_path(expected_path, artifact["sha256"], "Deployment performance")
    if test_eval.read_json(expected_path) != value["performance"]:
        raise test_eval.TestEvaluationError("Inline performance differs from the hashed artifact")
    return value


def profile(request_path: Path, job_name: str, gpu: int) -> dict:
    request, job, campaign = test_eval.validate_request(request_path, job_name, gpu)
    if request["schema_version"] == 2 and request.get("benchmark_gpu") != gpu:
        raise test_eval.TestEvaluationError("Use the prespecified single benchmark GPU")
    request_sha = test_eval.digest(request_path)
    source_test, source_identity = require_finished_test(request, job, request_sha)
    source_test_sha = test_eval.digest(source_test)
    policy = gpu_policy.load(campaign)
    gpu_policy.enforce_from_env(init_cuda=False)
    directory = output_directory(request, job_name)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".profile.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        existing = completed_profile(directory, request_sha, job["final_checkpoint_sha256"])
        if existing is not None:
            return existing
        gpu_entry = gpu_policy.require_allowed(policy, gpu)
        uuid = gpu_policy.normalize_uuid(gpu_entry["uuid"])
        if any(
            gpu_policy.normalize_uuid(actual) == uuid for _, actual in gpu_policy.compute_apps()
        ):
            raise gpu_policy.GpuPolicyError(f"GPU {gpu} is no longer idle")
        import torch

        from segmentary.config import load_experiment
        from segmentary.engine.ema import ema_evaluation_safe
        from segmentary.eval import load_configured_checkpoint
        from segmentary.models.factory import build_model
        from segmentary.performance import measure_cuda_forward, process_gpu_used_bytes
        from segmentary.taxonomy import load_space
        from segmentary.utils.provenance import collect_env

        torch.set_num_threads(4)
        configure_deployment_seed(int(job["seed"]))
        placement = gpu_policy.enforce_from_env(init_cuda=True)
        cfg = load_experiment([Path(job["config"])])
        space = load_space(cfg.taxonomy_root, cfg.space)
        if list(space.names) != request["class_names"] or space.num_classes != 21:
            raise test_eval.TestEvaluationError(
                "Profile taxonomy differs from the frozen RAD request"
            )
        model = build_model(cfg.model, space.num_classes)
        use_ema = ema_evaluation_safe(model)
        if source_identity.get("weights") != ("ema" if use_ema else "raw"):
            raise test_eval.TestEvaluationError(
                "Deployment profile weights differ from final test weights"
            )
        model = (
            load_configured_checkpoint(model, cfg, Path(job["final_checkpoint"]), use_ema)
            .cuda()
            .eval()
        )
        image = torch.zeros((1, 3, 1024, 1024), dtype=torch.float32, device="cuda").contiguous()
        started_at = runtime.now()
        started = time.monotonic()
        latency, peak = measure_cuda_forward(
            model, image, warmup=20, iterations=100, expected_channels=space.num_classes
        )
        properties = torch.cuda.get_device_properties(0)
        performance = {
            "schema_version": 1,
            "status": "complete",
            "model_id": job["model"],
            "measured_at": runtime.now(),
            "benchmark_scope": "rad_final_checkpoint_deployment_model_only",
            "applies_to": [job_name],
            "source": {
                "request_sha256": request_sha,
                "campaign_git_sha": campaign.get("code_sha"),
                "config": job["config"],
                "config_sha256": job["config_sha256"],
                "checkpoint": job["final_checkpoint"],
                "checkpoint_sha256": job["final_checkpoint_sha256"],
                "checkpoint_kind": "final completed-training checkpoint",
                "checkpoint_bytes": Path(job["final_checkpoint"]).stat().st_size,
                "weights": "ema" if use_ema else "raw",
                "source_test_result": str(source_test),
                "source_test_result_sha256": source_test_sha,
                "test_scores_used_for_profiling": False,
            },
            "hardware": {
                "gpu_name": properties.name,
                "gpu_uuid": gpu_entry["uuid"],
                "physical_visibility_token": str(gpu),
                "logical_device": "cuda:0",
                "compute_capability": [properties.major, properties.minor],
                "total_memory_bytes": int(properties.total_memory),
            },
            "model": {
                "parameter_count": sum(p.numel() for p in model.parameters()),
                "trainable_parameter_count": sum(
                    p.numel() for p in model.parameters() if p.requires_grad
                ),
                "resident_parameter_bytes": sum(
                    p.numel() * p.element_size() for p in model.parameters()
                ),
            },
            "contract": deployment_contract(),
            "measurements": {
                "latency": latency,
                "peak_reserved_bytes": peak,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "memory_kind": "pytorch_cuda_allocator_peak_reserved_excluding_context",
                "process_total_bytes": process_gpu_used_bytes(gpu_entry["uuid"]),
                "process_total_kind": "nvidia-smi process memory after timed loop; includes CUDA context; not whole-pipeline peak",
                "benchmark_wall_clock_s": time.monotonic() - started,
            },
            "backend_state": {
                "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                "cudnn_deterministic": torch.backends.cudnn.deterministic,
                "cudnn_benchmark": torch.backends.cudnn.benchmark,
                "cuda_matmul_allow_tf32": torch.backends.cuda.matmul.allow_tf32,
                "cudnn_allow_tf32": torch.backends.cudnn.allow_tf32,
            },
            "started_at": started_at,
            "finished_at": runtime.now(),
            "environment": collect_env(),
        }
        if request["schema_version"] == 2:
            del image
            torch.cuda.empty_cache()
            performance["authoritative_for_paper"] = True
            performance["native_pipeline"] = native_pipeline_profile(
                model, cfg, request, list(space.names), gpu_entry["uuid"]
            )
        gpu_policy.assert_pid_on_uuid(os.getpid(), gpu_entry["uuid"])
        test_eval.verified_path(source_test, source_test_sha, "Source test result")
        artifact_path = directory / "performance.json"
        runtime.write(artifact_path, performance)
        result = {
            "schema_version": 1,
            "status": "completed",
            "task": TASK,
            "name": job_name,
            "request_sha256": request_sha,
            "checkpoint_sha256": job["final_checkpoint_sha256"],
            "source_test_result_sha256": source_test_sha,
            "gpu": placement,
            "performance": performance,
            "artifacts": {
                "performance.json": {
                    "path": str(artifact_path),
                    "sha256": test_eval.digest(artifact_path),
                }
            },
        }
        runtime.write(directory / "result.json", result)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--gpu", type=int, required=True)
    args = parser.parse_args()
    value = profile(args.request.resolve(), args.job, args.gpu)
    print(f"Completed deployment profile: {value['name']}", flush=True)


if __name__ == "__main__":
    main()
