"""Recompute fresh conditional source scores while preserving archived evidence."""

import copy
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from scripts.rad_paper_metrics import score_images
from scripts.rad_source_positive_evidence import load_source_positive_evidence


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture(scope="module")
def native_captures():
    captures = {}
    for stage, count, classes in (("cityscapes", 500, 19), ("cityscapes_to_railsem19", 850, 21)):
        names = [f"class-{index}" for index in range(19)]
        if classes == 21:
            names.extend(["bicycle", "motorcycle"])
        first = np.zeros((classes, classes), dtype=np.int64)
        for index in range(19):
            first[index, index] = 10
        negative = np.zeros_like(first)
        negative[0, :2] = [5, 5]
        matrices = {
            f"image-{index:04}": first if index == 0 else negative for index in range(count)
        }
        total = np.stack(list(matrices.values())).sum(axis=0)
        compressed = gzip.compress(
            json.dumps({key: value.tolist() for key, value in matrices.items()}).encode(), mtime=0
        )
        captures[stage] = {
            "names": names,
            "count": count,
            "total": total.tolist(),
            "support": {name: int(total[index].sum()) for index, name in enumerate(names)},
            "raw": compressed,
            "positive": score_images(matrices, names)["class_positive_images"],
        }
    return captures


@pytest.fixture
def source_evidence(tmp_path, native_captures):
    models = [f"model-{index}" for index in range(8)]
    source_jobs, stages, payloads = [], [], []
    for model in models:
        model_stages = []
        for stage_name, dataset in (
            ("cityscapes", "cityscapes"),
            ("cityscapes_to_railsem19", "railsem19"),
        ):
            native = native_captures[stage_name]
            config_sha = hashlib.sha256((model + stage_name + "config").encode()).hexdigest()
            checkpoint_sha = hashlib.sha256(
                (model + stage_name + "checkpoint").encode()
            ).hexdigest()
            config = {
                "evaluation": {
                    "weights": "ema",
                    "deterministic": True,
                    "split": "val",
                    "data": {"name": dataset},
                }
            }
            source_jobs.append(
                {
                    "model": model,
                    "stage": stage_name,
                    "dataset": dataset,
                    "seed": 0,
                    "expected_images": native["count"],
                    "class_names": native["names"],
                    "config_sha256": config_sha,
                    "checkpoint_sha256": checkpoint_sha,
                }
            )
            model_stages.append(
                {
                    "stage": stage_name,
                    "dataset": dataset,
                    "source_seed": 0,
                    "class_names": native["names"],
                    "config": {"sha256": config_sha},
                    "checkpoint": {"sha256": checkpoint_sha},
                    "metrics": {
                        "config": config,
                        "dataset_sizes": {"eval": native["count"]},
                        "metrics": {"confusion": native["total"], "support": native["support"]},
                    },
                }
            )
            directory = tmp_path / "capture" / (model + "--" + stage_name)
            directory.mkdir(parents=True)
            matrix_path = directory / "per-image-confusion.json.gz"
            matrix_path.write_bytes(native["raw"])
            matrix_pointer = {
                "path": str(matrix_path),
                "sha256": hashlib.sha256(native["raw"]).hexdigest(),
            }
            evaluation = {
                "git_sha": "d" * 40,
                "git_dirty": False,
                "seed": 0,
                "stage": f"eval:{dataset}:val",
                "dataset_sizes": {"eval": native["count"]},
                "config": config,
                "metrics": {"confusion": native["total"], "per_image_confusions": matrix_pointer},
            }
            payloads.append(
                {
                    "model": model,
                    "stage": stage_name,
                    "class_names": native["names"],
                    "expected_images": native["count"],
                    "config_sha256": config_sha,
                    "checkpoint_sha256": checkpoint_sha,
                    "weights": "ema",
                    "evaluation_record": write_json(directory / "evaluation.json", evaluation),
                    "per_image_confusions": matrix_pointer,
                    "class_positive_images": copy.deepcopy(native["positive"]),
                    "aggregate_confusion_matches_archived": True,
                }
            )
        stages.append({"model": model, "stages": model_stages})
    spec_pointer = write_json(tmp_path / "source-request.json", {"jobs": source_jobs})
    archived = {"request_sha256": spec_pointer["sha256"], "models": stages}
    archived_pointer = write_json(tmp_path / "archive/source-stage-reports.json", archived)
    request = {
        "source_stage_reports": archived_pointer,
        "research_protocol": {
            "models": models,
            "source_stage_reports": {
                "spec": spec_pointer["path"],
                "spec_sha256": spec_pointer["sha256"],
            },
        },
    }
    report = {
        "schema_version": 1,
        "metric": "class_positive_image_miou",
        "collector_code_sha": "d" * 40,
        "source_stage_request": spec_pointer,
        "source_stage_report": archived_pointer,
        "jobs": payloads,
    }
    path = tmp_path / "capture/source-positive-metrics.json"
    write_json(path, report)
    return {"path": path, "report": report, "request": request, "archived": archived}


def load(case):
    write_json(case["path"], case["report"])
    return load_source_positive_evidence(case["path"], case["request"], case["archived"])


def rewrite_evaluation(job, evaluation):
    job["evaluation_record"] = write_json(Path(job["evaluation_record"]["path"]), evaluation)


def test_all_sixteen_native_sources_recompute_conditional_scores(source_evidence):
    case = source_evidence
    original = copy.deepcopy(case["archived"])
    result = load(case)
    assert len(result) == 16
    assert case["archived"] == original
    for (_model, stage), payload in result.items():
        positive = payload["class_positive_images"]
        assert positive["macro_scored_classes"] == 19
        assert positive["per_class"]["class-1"]["mean_image_iou"] == 1
        assert positive["per_class"]["class-1"]["fp"] == 0
        assert payload["positive_image_evidence"]["collector_code_sha"] == "d" * 40
        if stage == "cityscapes_to_railsem19":
            for name in ("bicycle", "motorcycle"):
                assert positive["per_class"][name]["positive_images"] == 0
                assert positive["per_class"][name]["mean_image_iou"] is None


@pytest.mark.parametrize("defect", ["missing", "duplicate", "unexpected"])
def test_exact_sixteen_endpoint_set_is_required(source_evidence, defect):
    case = source_evidence
    if defect == "missing":
        case["report"]["jobs"].pop()
    elif defect == "duplicate":
        case["report"]["jobs"][-1] = case["report"]["jobs"][0]
    else:
        case["report"]["jobs"][0]["model"] = "unknown"
    with pytest.raises(ValueError, match="sixteen native endpoints"):
        load(case)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_images", 499),
        ("config_sha256", "e" * 64),
        ("checkpoint_sha256", "e" * 64),
        ("weights", "raw"),
        ("class_names", ["wrong"]),
        ("aggregate_confusion_matches_archived", False),
    ],
)
def test_native_identity_is_bound_to_the_frozen_endpoint(source_evidence, field, value):
    case = source_evidence
    case["report"]["jobs"][0][field] = value
    with pytest.raises(ValueError, match="native endpoint"):
        load(case)


@pytest.mark.parametrize(
    ("field", "value"), [("git_dirty", True), ("git_sha", "e" * 40), ("seed", 1)]
)
def test_fresh_source_capture_requires_its_clean_collector_identity(source_evidence, field, value):
    case = source_evidence
    job = case["report"]["jobs"][0]
    evaluation = json.loads(Path(job["evaluation_record"]["path"]).read_text())
    evaluation[field] = value
    rewrite_evaluation(job, evaluation)
    with pytest.raises(ValueError, match="clean native contract"):
        load(case)


@pytest.mark.parametrize("artifact", ["evaluation_record", "per_image_confusions"])
def test_fresh_artifact_bytes_must_match_their_receipt(source_evidence, artifact):
    case = source_evidence
    job = case["report"]["jobs"][0]
    path = Path(job[artifact]["path"])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA-256"):
        load(case)


@pytest.mark.parametrize("defect", ["count", "shape", "negative", "float", "sum"])
def test_native_matrices_have_complete_count_and_exact_archived_sum(source_evidence, defect):
    case = source_evidence
    job = case["report"]["jobs"][0]
    path = Path(job["per_image_confusions"]["path"])
    matrices = json.loads(gzip.decompress(path.read_bytes()))
    first = next(iter(matrices))
    if defect == "count":
        matrices.pop(first)
    elif defect == "shape":
        matrices[first] = [[1]]
    elif defect == "negative":
        matrices[first][0][0] = -1
    elif defect == "float":
        matrices[first][0][0] = 10.0
    else:
        matrices[first][0][0] += 1
    raw = gzip.compress(json.dumps(matrices).encode(), mtime=0)
    path.write_bytes(raw)
    job["per_image_confusions"]["sha256"] = hashlib.sha256(raw).hexdigest()
    evaluation = json.loads(Path(job["evaluation_record"]["path"]).read_text())
    evaluation["metrics"]["per_image_confusions"] = job["per_image_confusions"]
    rewrite_evaluation(job, evaluation)
    with pytest.raises(ValueError, match=r"native image count|keyed integer matrices|sum differs"):
        load(case)


def test_supplied_conditional_scores_must_equal_recomputed_scores(source_evidence):
    case = source_evidence
    case["report"]["jobs"][0]["class_positive_images"]["miou"] = 0
    with pytest.raises(ValueError, match="conditional scores differ"):
        load(case)


def test_archived_source_report_stays_hash_bound(source_evidence):
    case = source_evidence
    path = Path(case["request"]["source_stage_reports"]["path"])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Archived source report SHA-256"):
        load(case)


def test_caller_source_stages_must_be_the_original_archived_payload(source_evidence):
    case = source_evidence
    case["archived"]["models"][0]["stages"][0]["dataset"] = "different"
    with pytest.raises(ValueError, match="hash-bound archived source report"):
        load(case)


def test_source_request_pointer_must_match_the_frozen_specification(source_evidence):
    case = source_evidence
    case["report"]["source_stage_request"]["sha256"] = "e" * 64
    with pytest.raises(ValueError, match="different frozen source request"):
        load(case)


def test_collector_code_identity_requires_a_full_commit_sha(source_evidence):
    case = source_evidence
    case["report"]["collector_code_sha"] = "d" * 8
    with pytest.raises(ValueError, match="versioned metric and code SHA"):
        load(case)


def test_evaluation_must_bind_the_same_per_image_artifact(source_evidence):
    case = source_evidence
    job = case["report"]["jobs"][0]
    evaluation = json.loads(Path(job["evaluation_record"]["path"]).read_text())
    evaluation["metrics"]["per_image_confusions"]["sha256"] = "e" * 64
    rewrite_evaluation(job, evaluation)
    with pytest.raises(ValueError, match="clean native contract"):
        load(case)
