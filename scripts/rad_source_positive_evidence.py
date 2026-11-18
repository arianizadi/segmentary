"""Verify GT-positive-image source statistics against frozen native evaluations."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from scripts.rad_paper_metrics import score_images


def _read_verified_json(pointer: dict, label: str, *, compressed: bool = False) -> dict:
    path = Path(pointer["path"])
    expected_suffix = ".json.gz" if compressed else ".json"
    if not path.name.endswith(expected_suffix):
        raise ValueError(f"{label} requires its JSON evidence file")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer.get("sha256"):
        raise ValueError(f"{label} SHA-256 differs from its recorded artifact")
    return json.loads(gzip.decompress(raw) if compressed else raw)


def load_source_positive_evidence(
    path: Path, request: dict, source_stages: dict
) -> dict[tuple[str, str], dict]:
    """Recompute all sixteen conditional source scores from hash-bound matrices.

    The original source report and request remain unchanged. Fresh evidence must
    use their checkpoint/configuration identities, selected bank, native count,
    taxonomy and exact aggregate confusion. Only JSON and gzip JSON are read.
    """
    report = json.loads(path.read_text())
    code_sha = report.get("collector_code_sha")
    if (
        report.get("schema_version") != 1
        or report.get("metric") != "class_positive_image_miou"
        or not isinstance(code_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", code_sha) is None
    ):
        raise ValueError(
            "Source positive-image evidence requires its versioned metric and code SHA"
        )
    archived_pointer = request["source_stage_reports"]
    if report.get("source_stage_report") != archived_pointer:
        raise ValueError("Source positive-image evidence binds a different archived source report")
    archived = _read_verified_json(archived_pointer, "Archived source report")
    if archived != source_stages:
        raise ValueError("Source stages differ from the hash-bound archived source report")
    spec = request["research_protocol"]["source_stage_reports"]
    spec_pointer = {"path": spec["spec"], "sha256": spec["spec_sha256"]}
    if report.get("source_stage_request") != spec_pointer:
        raise ValueError("Source positive-image evidence binds a different frozen source request")
    source_request = _read_verified_json(spec_pointer, "Frozen source request")
    if archived.get("request_sha256") != spec_pointer["sha256"]:
        raise ValueError("Archived source report differs from its frozen request SHA-256")
    models = request["research_protocol"]["models"]
    if len(models) != 8 or len(set(models)) != 8:
        raise ValueError("Source positive-image evidence requires eight distinct models")
    expected = {
        (model, stage) for model in models for stage in ("cityscapes", "cityscapes_to_railsem19")
    }
    original_stages = {
        (model["model"], stage["stage"]): stage
        for model in archived["models"]
        for stage in model["stages"]
    }
    source_jobs = {(job["model"], job["stage"]): job for job in source_request["jobs"]}
    jobs = report.get("jobs", [])
    keys = [(job["model"], job["stage"]) for job in jobs]
    if (
        len(original_stages) != 16
        or sum(len(model["stages"]) for model in archived["models"]) != 16
        or set(original_stages) != expected
        or len(source_request["jobs"]) != 16
        or set(source_jobs) != expected
        or len(jobs) != 16
        or len(set(keys)) != 16
        or set(keys) != expected
    ):
        raise ValueError(
            "Source positive-image evidence requires the exact sixteen native endpoints"
        )

    result = {}
    for job in jobs:
        key = (job["model"], job["stage"])
        stage, source_job = original_stages[key], source_jobs[key]
        original = stage["metrics"]
        city = job["stage"] == "cityscapes"
        count, classes = (500, 19) if city else (850, 21)
        names = stage["class_names"]
        bank = original["config"]["evaluation"]["weights"]
        if (
            job.get("class_names") != names
            or source_job["class_names"] != names
            or len(names) != len(set(names))
            or len(names) != classes
            or job.get("expected_images") != count
            or source_job["expected_images"] != count
            or source_job["dataset"] != stage["dataset"]
            or source_job["seed"] != stage["source_seed"]
            or stage["source_seed"] != 0
            or original.get("dataset_sizes") != {"eval": count}
            or job.get("config_sha256") != stage["config"]["sha256"]
            or job["config_sha256"] != source_job["config_sha256"]
            or job.get("checkpoint_sha256") != stage["checkpoint"]["sha256"]
            or job["checkpoint_sha256"] != source_job["checkpoint_sha256"]
            or bank not in ("raw", "ema")
            or job.get("weights") != bank
            or job.get("aggregate_confusion_matches_archived") is not True
        ):
            raise ValueError(
                f"Source positive-image identity differs from the native endpoint: {key}"
            )
        evaluation = _read_verified_json(job["evaluation_record"], "Fresh source evaluation")
        if (
            evaluation.get("git_sha") != code_sha
            or evaluation.get("git_dirty") is not False
            or evaluation.get("seed") != 0
            or evaluation.get("stage") != f"eval:{stage['dataset']}:val"
            or evaluation.get("dataset_sizes") != {"eval": count}
            or evaluation.get("config") != original["config"]
            or evaluation["config"]["evaluation"].get("deterministic") is not True
            or evaluation["metrics"].get("per_image_confusions") != job["per_image_confusions"]
        ):
            raise ValueError(
                f"Fresh source evaluation differs from its clean native contract: {key}"
            )
        matrices = _read_verified_json(
            job["per_image_confusions"], "Source per-image confusion", compressed=True
        )
        if not isinstance(matrices, dict) or len(matrices) != count:
            raise ValueError(
                f"Source per-image confusion lacks its complete native image count: {key}"
            )
        checked = {}
        for image_key, values in matrices.items():
            matrix = np.asarray(values)
            if (
                not isinstance(image_key, str)
                or not image_key
                or matrix.shape != (classes, classes)
                or not np.issubdtype(matrix.dtype, np.integer)
                or (matrix < 0).any()
            ):
                raise ValueError(
                    f"Source per-image confusion requires keyed integer matrices: {key}"
                )
            checked[image_key] = matrix
        total = np.stack(list(checked.values())).sum(axis=0)
        if (
            not np.array_equal(total, original["metrics"]["confusion"])
            or not np.array_equal(total, evaluation["metrics"].get("confusion"))
            or original["metrics"]["support"]
            != {name: int(total[index].sum()) for index, name in enumerate(names)}
        ):
            raise ValueError(
                f"Source per-image confusion sum differs from its archived evaluation: {key}"
            )
        positive = score_images(checked, names)["class_positive_images"]
        supported = {
            name for name, values in positive["per_class"].items() if values["positive_images"] > 0
        }
        unsupported = set(names) - supported
        if (
            positive["macro_scored_classes"] != 19
            or unsupported != (set() if city else {"bicycle", "motorcycle"})
            or positive != job.get("class_positive_images")
        ):
            raise ValueError(
                f"Source conditional scores differ from their recomputed native evidence: {key}"
            )
        result[key] = {
            "class_positive_images": positive,
            "positive_image_evidence": {
                "evaluation_record": job["evaluation_record"],
                "per_image_confusions": job["per_image_confusions"],
                "collector_code_sha": code_sha,
            },
        }
    return result
