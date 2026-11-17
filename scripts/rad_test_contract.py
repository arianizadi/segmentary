"""Frozen complete-run-set contract for the focused RAD paper evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def evaluation_mode(request: dict) -> tuple[str, bool]:
    """Keep an explicitly authorized train-only rehearsal outside held-out results."""
    rehearsal = request.get("rehearsal", False)
    if type(rehearsal) is not bool:
        raise ValueError("rehearsal must be a boolean")
    if rehearsal:
        keys = request.get("image_keys")
        if (
            request.get("schema_version") != 1
            or request.get("rehearsal_authorized") is not True
            or request.get("test_evaluation_authorized") is not False
            or request.get("evaluation_split") != "train"
            or not isinstance(keys, list)
            or not keys
            or any(
                not isinstance(key, str) or Path(key).is_absolute() or ".." in Path(key).parts
                for key in keys
            )
            or len(set(keys)) != len(keys)
        ):
            raise ValueError(
                "Explicit schema-1 train-only rehearsal authorization and image keys are required"
            )
        return "train", False
    if (
        request.get("test_evaluation_authorized") is not True
        or request.get("evaluation_split", "test") != "test"
    ):
        raise ValueError("Explicit held-out test evaluation authorization is required")
    return "test", True


def read_verified(path: str, expected: str, label: str) -> dict:
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"{label} SHA-256 differs from the frozen test request")
    return json.loads(raw)


def validate_v2(request: dict[str, Any], campaign: dict[str, Any]) -> set[int]:
    """Require all prespecified model/recipe/seed endpoints before any test inference."""
    plan = read_verified(request["training_plan"], request["training_plan_sha256"], "Training plan")
    training = read_verified(
        request["training_campaign"], request["training_campaign_sha256"], "Training campaign"
    )
    if training.get("code_sha") != request.get("training_code_sha"):
        raise ValueError("Training code identity differs from the request")
    if training.get("plan_sha256") != request["training_plan_sha256"]:
        raise ValueError("Training campaign does not bind this training plan")
    for field in (
        "research_protocol",
        "research_protocol_sha256",
        "split_sha256",
        "dataset_final_fit",
    ):
        if training.get(field) != plan.get(field):
            raise ValueError(f"Training campaign differs from the planned {field}")
    protocol = request.get("research_protocol")
    if not protocol or protocol != plan.get("research_protocol"):
        raise ValueError("The research protocol must equal the prespecified training plan")
    protocol_sha = hashlib.sha256(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if protocol_sha != plan.get("research_protocol_sha256"):
        raise ValueError("Research protocol hash differs from the training plan")
    if protocol.get("primary_metric") not in ("pixel_pooled_miou", "class_positive_image_miou"):
        raise ValueError("Prespecify the primary mIoU definition")
    if protocol.get("seeds") != [0, 1, 2] or protocol.get("qualitative_seed") not in [0, 1, 2]:
        raise ValueError(
            "The paper protocol requires seeds 0, 1 and 2 and a fixed qualitative seed"
        )
    planned = {job["name"]: job for job in plan["jobs"]}
    jobs = request["jobs"]
    if len(planned) != len(plan["jobs"]) or len({job["name"] for job in jobs}) != len(jobs):
        raise ValueError("Duplicate planned or requested runs")
    if {job["name"] for job in jobs} != set(planned):
        raise ValueError("Test request must cover the complete prespecified run set")
    headline_arm = protocol.get("headline_protocol")
    models = set(protocol.get("models", []))
    headline = {(job["model"], job["seed"]) for job in jobs if job["protocol"] == headline_arm}
    if headline != {(model, seed) for model in models for seed in [0, 1, 2]}:
        raise ValueError("Every model must have all three seeds of the common headline recipe")
    for job in jobs:
        expected = planned[job["name"]]
        for field in ("model", "protocol", "seed", "config", "config_sha256"):
            if job.get(field) != expected.get(field):
                raise ValueError(
                    f"Requested run differs from the training plan: {job['name']} {field}"
                )
        state = read_verified(job["state_path"], job["state_sha256"], "Completed training state")
        endpoint = state.get("checkpoints", {}).get("final", {})
        if (
            state.get("status") != "completed"
            or state.get("collection", {}).get("verified") is not True
            or state.get("collection", {}).get("contract") != plan.get("collection_contract")
            or state.get("name") != job["name"]
            or state.get("config_sha256") != job["config_sha256"]
            or state.get("code_sha") != training["code_sha"]
            or state.get("final_step") != plan["target_steps_per_job"]
            or endpoint.get("global_step") != plan["target_steps_per_job"]
            or endpoint.get("sha256") != job["final_checkpoint_sha256"]
            or Path(endpoint.get("path", "")).resolve() != Path(job["final_checkpoint"]).resolve()
        ):
            raise ValueError(f"Run lacks its completed fixed-budget final endpoint: {job['name']}")
    authorized = set(training.get("launch_requirements", {}).get("expected_gpu_allowlist", []))
    if not authorized or not authorized <= set(range(10)):
        raise ValueError("Training campaign must freeze its explicit GPU authorization")
    if campaign.get("authorized_gpu_indices") != sorted(authorized):
        raise ValueError("Test campaign GPU authorization differs from the training campaign")
    if request.get("split_sha256") != plan.get("split_sha256"):
        raise ValueError("Test dataset split differs from the training plan")
    return authorized


def verify_evaluation_code(campaign: dict, repo: Path) -> None:
    from segmentary.utils.provenance import git_sha

    current, dirty = git_sha(repo)
    if dirty or current != campaign.get("code_sha"):
        raise ValueError("Test evaluation requires clean HEAD at the frozen evaluation code SHA")
