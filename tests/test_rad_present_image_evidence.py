"""Bind GT-positive-image training statistics to the complete retained evidence."""

import copy
import gzip
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scripts.rad_present_image_evidence import load_train_positive_evidence
from scripts.run_rtis_campaign import FINAL_TRAIN_CONTRACT


def write_matrices(case):
    raw = gzip.compress(json.dumps(case.matrices).encode(), mtime=0)
    case.path.write_bytes(raw)
    case.state["collection"]["artifacts"]["final-auto-train"]["per-image-confusion.json.gz"][
        "sha256"
    ] = hashlib.sha256(raw).hexdigest()


@pytest.fixture
def train_evidence(tmp_path):
    checkpoint = tmp_path / "rtis/last.ckpt"
    path = checkpoint.parent / "diagnostics/final-auto-train/per-image-confusion.json.gz"
    path.parent.mkdir(parents=True)
    names = [f"class-{index}" for index in range(21)]
    matrices, samples = {}, []
    for index in range(255):
        matrix = np.zeros((21, 21), dtype=np.int64)
        if index == 0:
            np.fill_diagonal(matrix, 10)
        else:
            matrix[0, :2] = [5, 5]
        key = f"scene/image-{index:03}"
        matrices[key] = matrix.tolist()
        samples.append(
            {
                "key": key,
                "split": "train",
                "class_pixels": {
                    str(label): int(count)
                    for label, count in enumerate(matrix.sum(axis=1))
                    if count
                }
                | {"255": 7},
            }
        )
    confusion = np.stack(list(matrices.values())).sum(axis=0).tolist()
    job = {
        "name": "example--cityscapes_to_railsem19_to_rtis--seed-0",
        "config_sha256": "a" * 64,
        "final_checkpoint": str(checkpoint),
        "final_checkpoint_sha256": "b" * 64,
    }
    request = {"schema_version": 2, "class_names": names, "training_code_sha": "c" * 40}
    diagnostic = {
        "images": 255,
        "split": "train",
        "checkpoint_sha256": job["final_checkpoint_sha256"],
        "weights": "ema",
        "metrics": {"confusion": confusion},
        "artifacts": {"per-image-confusion.json.gz": str(path)},
    }
    state = {
        "name": job["name"],
        "config_sha256": job["config_sha256"],
        "code_sha": request["training_code_sha"],
        "evaluation_checkpoint": "final",
        "evaluation_split": "train",
        "checkpoints": {
            "final": {"path": str(checkpoint), "sha256": job["final_checkpoint_sha256"]}
        },
        "training": {"env": {"final_weights_policy": "ema"}},
        "evaluation": {
            "dataset_sizes": {"eval": 255},
            "config": {"evaluation": {"weights": "ema", "split": "train"}},
            "metrics": {"confusion": confusion},
        },
        "collection": {
            "contract": FINAL_TRAIN_CONTRACT,
            "verified": True,
            "smoke": False,
            "diagnostics": {
                "contract": FINAL_TRAIN_CONTRACT,
                "test_evaluated": False,
                "primary_checkpoint": "final",
                "standalone_variant": "final-auto-train",
                "deterministic": True,
                "standalone_confusion_exact_match": True,
                "smoke_limit": None,
                "results": {"final-auto-train": diagnostic},
            },
            "artifacts": {"final-auto-train": {"per-image-confusion.json.gz": {"path": str(path)}}},
        },
    }
    case = SimpleNamespace(
        path=path,
        matrices=matrices,
        job=job,
        state=state,
        request=request,
        names=names,
        samples=samples,
    )
    write_matrices(case)
    return case


def load(case):
    return load_train_positive_evidence(
        case.job, case.state, case.request, case.names, case.samples
    )


def test_full_train_positive_iou_excludes_negative_image_false_positives(train_evidence):
    case = train_evidence
    result = load(case)
    positive = result["class_positive_images"]
    assert result["images"] == 255
    assert result["weights"] == "ema"
    assert positive["macro_scored_classes"] == 21
    assert positive["per_class"]["class-1"]["positive_images"] == 1
    assert positive["per_class"]["class-1"]["mean_image_iou"] == 1
    assert positive["per_class"]["class-1"]["precision"] == 1
    assert positive["per_class"]["class-1"]["recall"] == 1
    assert positive["per_class"]["class-1"]["dice"] == 1
    assert positive["per_class"]["class-1"]["fp"] == 0
    class_zero = (1 + 254 * 0.5) / 255
    assert positive["per_class"]["class-0"]["mean_image_iou"] == pytest.approx(class_zero)
    assert positive["miou"] == pytest.approx((class_zero + 20) / 21)
    assert (
        result["per_image_confusions"]
        == case.state["collection"]["artifacts"]["final-auto-train"]["per-image-confusion.json.gz"]
    )
    assert not (case.path.parents[2] / "last.ckpt").exists()


def test_changed_matrix_bytes_require_the_bound_collection_sha(train_evidence):
    case = train_evidence
    case.matrices[case.samples[0]["key"]][0][0] += 1
    case.path.write_bytes(gzip.compress(json.dumps(case.matrices).encode(), mtime=0))
    with pytest.raises(ValueError, match="SHA-256"):
        load(case)


@pytest.mark.parametrize("defect", ["shape", "negative", "float", "membership", "support"])
def test_matrices_must_match_each_native_audited_image(train_evidence, defect):
    case = train_evidence
    key = case.samples[0]["key"]
    if defect == "shape":
        case.matrices[key] = [[1]]
    elif defect == "negative":
        case.matrices[key][0][0] = -1
    elif defect == "float":
        case.matrices[key][0][0] = 10.0
    elif defect == "membership":
        case.matrices["unknown-image"] = case.matrices.pop(key)
    else:
        case.matrices[key][0][0] += 1
    write_matrices(case)
    with pytest.raises(ValueError, match=r"matrices|membership|GT support"):
        load(case)


def test_sum_must_reproduce_the_retained_full_training_confusion(train_evidence):
    case = train_evidence
    confusion = copy.deepcopy(case.state["evaluation"]["metrics"]["confusion"])
    confusion[0][0] += 1
    case.state["evaluation"]["metrics"]["confusion"] = confusion
    with pytest.raises(ValueError, match="sum differs"):
        load(case)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("collection", "verified"), False, "verified complete v2"),
        (("collection", "contract"), "legacy", "verified complete v2"),
        (("collection", "smoke"), True, "verified complete v2"),
        (("collection", "diagnostics", "smoke_limit"), 2, "verified complete v2"),
        (("collection", "diagnostics", "deterministic"), False, "verified complete v2"),
        (
            ("collection", "diagnostics", "standalone_confusion_exact_match"),
            False,
            "verified complete v2",
        ),
        (("training", "env", "final_weights_policy"), "raw", "endpoint or bank"),
        (("checkpoints", "final", "sha256"), "d" * 64, "endpoint or bank"),
        (("config_sha256",), "d" * 64, "endpoint or bank"),
        (("evaluation", "config", "evaluation", "weights"), "raw", "endpoint or bank"),
        (("evaluation", "dataset_sizes", "eval"), 254, "255 unique"),
        (("collection", "diagnostics", "results", "final-auto-train", "images"), 2, "255 unique"),
        (
            ("collection", "diagnostics", "results", "final-auto-train", "weights"),
            "raw",
            "endpoint or bank",
        ),
        (
            ("collection", "diagnostics", "results", "final-auto-train", "checkpoint_sha256"),
            "d" * 64,
            "endpoint or bank",
        ),
    ],
)
def test_collection_and_endpoint_metadata_are_required(train_evidence, path, value, message):
    case = train_evidence
    target = case.state
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match=message):
        load(case)


def test_training_sample_membership_is_unique_and_complete(train_evidence):
    case = train_evidence
    case.samples[-1] = case.samples[0]
    with pytest.raises(ValueError, match="255 unique"):
        load(case)
