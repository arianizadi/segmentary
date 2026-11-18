"""Read hash-bound per-image evidence for GT-positive-image RAD report metrics."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from scripts.rad_paper_metrics import score_images
from scripts.run_rtis_campaign import FINAL_TRAIN_CONTRACT


def load_train_positive_evidence(
    job: dict, state: dict, request: dict, names: list[str], samples: list[dict]
) -> dict:
    """Verify all 255 selected-bank train matrices and score GT-positive images.

    The completed collection binds the compressed matrix bytes by SHA-256. Each
    matrix must reproduce its audited image's GT support, and their sum must
    reproduce the independently retained full-training evaluation confusion.
    Checkpoint metadata is inspected without opening checkpoint weights.
    """
    if (
        request.get("schema_version") != 2
        or request.get("class_names") != names
        or len(names) != 21
        or len(set(names)) != 21
    ):
        raise ValueError("Train positive-image evidence requires the schema-2 21-class paper")
    collection = state.get("collection", {})
    diagnostics = collection.get("diagnostics", {})
    if (
        collection.get("contract") != FINAL_TRAIN_CONTRACT
        or collection.get("verified") is not True
        or collection.get("smoke") is not False
        or diagnostics.get("contract") != FINAL_TRAIN_CONTRACT
        or diagnostics.get("test_evaluated") is not False
        or diagnostics.get("primary_checkpoint") != "final"
        or diagnostics.get("standalone_variant") != "final-auto-train"
        or diagnostics.get("deterministic") is not True
        or diagnostics.get("standalone_confusion_exact_match") is not True
        or diagnostics.get("smoke_limit", "missing") is not None
    ):
        raise ValueError("Train positive-image evidence requires a verified complete v2 collection")

    diagnostic = diagnostics.get("results", {}).get("final-auto-train", {})
    final = state.get("checkpoints", {}).get("final", {})
    bank = state.get("training", {}).get("env", {}).get("final_weights_policy")
    evaluation = state.get("evaluation", {})
    evaluation_policy = evaluation.get("config", {}).get("evaluation", {})
    if (
        state.get("name") != job["name"]
        or state.get("code_sha") != request["training_code_sha"]
        or state.get("config_sha256") != job["config_sha256"]
        or state.get("evaluation_checkpoint") != "final"
        or state.get("evaluation_split") != "train"
        or final.get("sha256") != job["final_checkpoint_sha256"]
        or Path(final.get("path", "")).resolve() != Path(job["final_checkpoint"]).resolve()
        or diagnostic.get("checkpoint_sha256") != job["final_checkpoint_sha256"]
        or bank not in ("raw", "ema")
        or diagnostic.get("weights") != bank
        or evaluation_policy.get("weights") != bank
        or evaluation_policy.get("split") != "train"
    ):
        raise ValueError("Train positive-image evidence differs from the final endpoint or bank")
    train_samples = [sample for sample in samples if sample["split"] == "train"]
    train_keys = [sample["key"] for sample in train_samples]
    if (
        len(train_samples) != 255
        or len(set(train_keys)) != 255
        or diagnostic.get("images") != 255
        or diagnostic.get("split") != "train"
        or evaluation.get("dataset_sizes") != {"eval": 255}
    ):
        raise ValueError("Train positive-image evidence requires all 255 unique training images")

    artifact = (
        collection.get("artifacts", {})
        .get("final-auto-train", {})
        .get("per-image-confusion.json.gz", {})
    )
    artifact_path = artifact.get("path")
    expected_path = (
        Path(job["final_checkpoint"]).parent
        / "diagnostics/final-auto-train/per-image-confusion.json.gz"
    )
    if (
        not artifact_path
        or Path(artifact_path).resolve() != expected_path.resolve()
        or diagnostic.get("artifacts", {}).get("per-image-confusion.json.gz") != artifact_path
    ):
        raise ValueError("Train positive-image evidence lacks its final-auto-train artifact")
    raw = Path(artifact_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact.get("sha256"):
        raise ValueError("Train per-image confusion SHA-256 differs from its collection receipt")
    matrices = json.loads(gzip.decompress(raw))
    if not isinstance(matrices, dict) or set(matrices) != set(train_keys):
        raise ValueError("Train per-image confusion membership differs from all 255 audited images")

    checked = {}
    for sample in train_samples:
        key = sample["key"]
        matrix = np.asarray(matrices[key])
        if (
            matrix.shape != (len(names), len(names))
            or not np.issubdtype(matrix.dtype, np.integer)
            or (matrix < 0).any()
        ):
            raise ValueError(
                f"Train per-image confusion requires nonnegative integer matrices: {key}"
            )
        support = np.zeros(len(names), dtype=np.int64)
        for label, pixels in sample["class_pixels"].items():
            label = int(label)
            if label not in {*range(len(names)), 255} or type(pixels) is not int or pixels < 0:
                raise ValueError(f"Train sample audit has invalid class support: {key}")
            if label != 255:
                support[label] += pixels
        if not np.array_equal(matrix.sum(axis=1), support):
            raise ValueError(f"Train per-image GT support differs from the sample audit: {key}")
        checked[key] = matrix

    total = np.stack(list(checked.values())).sum(axis=0)
    standalone = np.asarray(evaluation.get("metrics", {}).get("confusion", []))
    if (
        standalone.shape != total.shape
        or not np.issubdtype(standalone.dtype, np.integer)
        or not np.array_equal(total, standalone)
        or diagnostic.get("metrics", {}).get("confusion") != standalone.tolist()
    ):
        raise ValueError("Train per-image confusion sum differs from the full train evaluation")
    positive = score_images(checked, names)["class_positive_images"]
    if positive["macro_scored_classes"] != len(names):
        raise ValueError(
            "Train positive-image evidence requires positive support for all 21 classes"
        )
    return {
        "images": 255,
        "weights": bank,
        "class_positive_images": positive,
        "per_image_confusions": {"path": artifact_path, "sha256": artifact["sha256"]},
    }
