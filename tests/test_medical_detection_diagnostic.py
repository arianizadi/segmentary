"""Scientific oracles for separate native mass detection diagnostic reports."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from segmentary.medical.data import fingerprint
from segmentary.medical.geometry import sha256_file

spec = importlib.util.spec_from_file_location(
    "detection_diagnostic", Path(__file__).parents[1] / "scripts/evaluate_medical_detection.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def save(path, array):
    image = nib.Nifti1Image(array, np.diag([1.0, 1.0, 2.0, 1.0]))
    image.header.set_xyzt_units("mm")
    nib.save(image, path)


@pytest.fixture
def data(tmp_path):
    workspace = tmp_path / "workspace"
    pred = workspace / "predictions" / "val"
    pred.mkdir(parents=True)
    cases, primary, statuses = [], [], []
    for i in range(5):
        key = f"case{i}"
        image = tmp_path / f"image{i}.nii.gz"
        label = tmp_path / f"label{i}.nii.gz"
        save(image, np.full((9, 9, 9), i, dtype=np.int16))
        truth = np.zeros((9, 9, 9), np.uint8)
        truth[1:8, 1:8, 1:8] = 1
        if i < 3:
            truth[2:4, 2:4, 2:4] = 2
        prediction = truth.copy()
        if i == 2:  # Positive examination, entirely wrong lesion location.
            prediction[prediction == 2] = 1
            prediction[5:7, 5:7, 5:7] = 2
        if i == 4:  # Real annotated negative with a false alert.
            prediction[5:7, 5:7, 5:7] = 2
        save(label, truth)
        destination = pred / f"{key}.nii.gz"
        save(destination, prediction)
        case = {
            "case_id": key,
            "patient_id": f"p{i}",
            "source": "synthetic",
            "annotation_status": "labeled",
            "image": str(image),
            "label": str(label),
            "shape": list(truth.shape),
            "affine": nib.load(image).affine.tolist(),
            "spacing_mm": [1, 1, 2],
            "image_sha256": sha256_file(image),
            "label_sha256": sha256_file(label),
        }
        cases.append(case)
        primary.append(
            {
                "case_id": key,
                "patient_id": f"p{i}",
                "status": "ok",
                "reference_sha256": case["label_sha256"],
                "prediction_sha256": sha256_file(destination),
            }
        )
        statuses.append(
            {
                "case_id": key,
                "status": "completed",
                "prediction_statistics": {
                    "mass_probability_max": [0.9, 0.9, 0.8, 0.2, 0.7][i],
                    "mass_score_definition": "maximum_native_class2_probability",
                    "native_voxels": truth.size,
                    "predicted_mass_voxels": int(np.count_nonzero(prediction == 2)),
                },
            }
        )
    manifest = {
        "schema_version": 1,
        "dataset": "synthetic",
        "source_root": str(tmp_path),
        "audit": {"passed": True},
        "ontology": {"background": 0, "pancreas": 1, "mass": 2},
        "cases": cases,
    }
    manifest["fingerprint"] = fingerprint(manifest)
    splits = {
        "schema_version": 1,
        "manifest_fingerprint": manifest["fingerprint"],
        "train": ["case0"],
        "val": [f"case{i}" for i in range(1, 5)],
        "test": [],
        "grouping_status": "dataset_case_unverified",
    }
    splits["fingerprint"] = fingerprint(splits)
    primary_report = {"manifest_fingerprint": manifest["fingerprint"], "cases": primary[1:]}
    paths = {
        "manifest": tmp_path / "manifest.json",
        "splits": tmp_path / "splits.json",
        "primary": tmp_path / "primary.json",
        "status": pred / "prediction-status.json",
    }
    for name, value in (
        ("manifest", manifest),
        ("splits", splits),
        ("primary", primary_report),
        ("status", {"partition": "val", "checkpoint_sha256": "a" * 64, "cases": statuses[1:]}),
    ):
        paths[name].write_text(json.dumps(value))
    binding = {
        "manifest_sha256": sha256_file(paths["manifest"]),
        "splits_sha256": sha256_file(paths["splits"]),
        "run_id": "scratch-fixture",
    }
    (workspace / "binding.json").write_text(json.dumps(binding))
    (workspace / "checkpoint-index.json").write_text(
        json.dumps(
            {
                "identity": module._digest(binding),
                "initialization": "scratch",
                "files": {
                    "checkpoint_best.pth": {"sha256": "a" * 64, "path": "generation-own.pth"}
                },
            }
        )
    )
    status = json.loads(paths["status"].read_text())
    status["identity"] = module._digest(binding)
    paths["status"].write_text(json.dumps(status))
    (pred / "case0.nii.gz").unlink()
    return {**paths, "pred": pred, "output": tmp_path / "output", "cases": cases}


def run(data, **kwargs):
    return module.evaluate_detection(
        data["manifest"], data["splits"], data["pred"], data["primary"], data["output"], **kwargs
    )


def test_patient_detection_can_succeed_when_localization_fails(data):
    result = run(data)
    assert result["cohort_complete"]
    assert result["metrics"]["patient_sensitivity"]["value"] == 1
    assert result["metrics"]["tumor_sensitivity"]["value"] == 0.5
    assert result["metrics"]["specificity"]["value"] == 0.5
    assert result["metrics"]["auc"]["value"] == 1
    assert result["metrics"]["mass_dsc"]["value"] == 0.5
    assert result["counts"]["reference_components"] == 2
    assert result["counts"]["lesion_false_positives"] == 2
    assert result["provenance"]["prediction_checkpoint_sha256"] == "a" * 64
    assert result["patient_grouping_status"] == "dataset_case_unverified"
    assert json.loads((data["output"] / "report.json").read_text()) == result
    with pytest.raises(FileExistsError):
        run(data)


@pytest.mark.parametrize(
    "fault", ["missing", "changed", "geometry", "status", "reference", "partial_label"]
)
def test_no_partial_cohort_scores(data, fault):
    path = data["pred"] / "case1.nii.gz"
    if fault == "missing":
        path.unlink()
    elif fault in ("changed", "geometry"):
        image = nib.load(path)
        values = np.asarray(image.dataobj).copy()
        values[0, 0, 0] = 2
        if fault == "changed":
            save(path, values)
        else:
            wrong = nib.Nifti1Image(values, np.eye(4))
            wrong.header.set_xyzt_units("mm")
            nib.save(wrong, path)
            primary = json.loads(data["primary"].read_text())
            primary["cases"][0]["prediction_sha256"] = sha256_file(path)
            data["primary"].write_text(json.dumps(primary))
    elif fault == "status":
        status = json.loads(data["status"].read_text())
        status["cases"][0]["status"] = "failed"
        data["status"].write_text(json.dumps(status))
    elif fault == "reference":
        Path(data["cases"][1]["label"]).write_bytes(b"corrupt reference")
    else:
        primary = json.loads(data["primary"].read_text())
        primary["cases"][0]["status"] = "unlabeled"
        data["primary"].write_text(json.dumps(primary))
    result = run(data)
    assert not result["cohort_complete"]
    assert result["counts"]["valid_cases"] == 3
    assert all(
        x["value"] is None and x["reason_code"] == "incomplete_cohort"
        for x in result["metrics"].values()
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "wrong_definition",
        "nonfinite",
        "wrong_shape",
        "wrong_mass_count",
        "invalid_object",
    ],
)
def test_auc_requires_valid_continuous_image_only_scores(data, fault):
    status = json.loads(data["status"].read_text())
    stats = status["cases"][0]["prediction_statistics"]
    if fault == "missing":
        del status["cases"][0]["prediction_statistics"]
    elif fault == "wrong_definition":
        stats["mass_score_definition"] = "reference_overlap"
    elif fault == "nonfinite":
        stats["mass_probability_max"] = float("nan")
    elif fault == "wrong_shape":
        stats["native_voxels"] = 1
    elif fault == "wrong_mass_count":
        stats["predicted_mass_voxels"] = 123
    else:
        status["cases"][0]["prediction_statistics"] = None
    data["status"].write_text(json.dumps(status))
    result = run(data)
    assert result["cohort_complete"]
    assert result["metrics"]["patient_sensitivity"]["value"] == 1
    assert result["metrics"]["auc"]["value"] is None
    assert result["metrics"]["auc"]["reason_code"] == "continuous_scores_unavailable"


def test_auc_ties_and_binary_operating_point_are_separate():
    assert module._auc([True, False], [0.8, 0.8]) == 0.5
    prediction = np.zeros((2, 2, 2), np.uint8)
    # A high score need not win an argmax; retain that continuous score unchanged.
    record = {
        "prediction_statistics": {
            "mass_probability_max": 0.49,
            "mass_score_definition": "maximum_native_class2_probability",
            "native_voxels": 8,
            "predicted_mass_voxels": 0,
        }
    }
    assert module._continuous_score(record, prediction) == 0.49


def test_positive_only_cohort_has_no_specificity_or_auc(data):
    result = run(data)
    rows = [x for x in result["cases"] if x["reference_positive"]]
    counts, metrics = module.summarize(rows, complete=True)
    assert counts["reference_negative_groups"] == 0
    assert metrics["specificity"]["reason_code"] == "no_reference_negatives"
    assert metrics["auc"]["reason_code"] == "auc_requires_both_classes"
    assert metrics["patient_sensitivity"]["value"] == 1


def test_multiple_scans_aggregate_by_group_any_positive_max_score(data):
    result = run(data)
    rows = copy.deepcopy(result["cases"])
    rows[0]["patient_id"] = rows[2]["patient_id"]  # Same patient positive + negative scan.
    counts, metrics = module.summarize(rows, complete=True)
    assert counts["patient_groups"] == 3
    assert counts["reference_positive_groups"] == 2
    assert counts["reference_negative_groups"] == 1
    assert metrics["specificity"]["value"] == 0
    assert metrics["auc"]["value"] == 1


def test_component_volume_floor_and_one_to_one_matching():
    reference = np.zeros((9, 9, 9), bool)
    reference[1:3, 1:3, 1:3] = True
    reference[5:7, 1:3, 1:3] = True
    prediction = reference.copy()
    prediction[3:5, 1:3, 1:3] = True  # Merge two reference lesions into one predicted blob.
    prediction[8, 8, 8] = True  # Two mm³ artifact removed by 10 mm³ floor.
    result = module.lesion_detection_metrics(reference, prediction, [1, 1, 2], 0.1, 26, 10)
    assert result["reference_components"] == 2
    assert result["prediction_components"] == 1
    assert result["true_positives"] == 1 and result["false_negatives"] == 1
    assert result["removed_prediction_components"] == 1


def test_cross_manifest_and_test_boundaries(data):
    with pytest.raises(ValueError, match="explicit final_test"):
        run(data, partition="test")
    primary = json.loads(data["primary"].read_text())
    primary["manifest_fingerprint"] = "different"
    data["primary"].write_text(json.dumps(primary))
    with pytest.raises(ValueError, match="another manifest"):
        run(data)
    assert not data["output"].exists()


@pytest.mark.parametrize("fault", ["run_identity", "checkpoint", "index_identity", "bound_split"])
def test_score_telemetry_cannot_be_borrowed_from_another_run(data, fault):
    workspace = data["pred"].parent.parent
    if fault in ("run_identity", "checkpoint"):
        status = json.loads(data["status"].read_text())
        status["identity" if fault == "run_identity" else "checkpoint_sha256"] = "b" * 64
        data["status"].write_text(json.dumps(status))
    elif fault == "index_identity":
        path = workspace / "checkpoint-index.json"
        index = json.loads(path.read_text())
        index["identity"] = "different"
        path.write_text(json.dumps(index))
    else:
        path = workspace / "binding.json"
        binding = json.loads(path.read_text())
        binding["splits_sha256"] = "different"
        path.write_text(json.dumps(binding))
    with pytest.raises(ValueError, match=r"different|bound checkpoint index"):
        run(data)
    assert not data["output"].exists()


def test_bound_nnunet_masks_have_detection_metrics_but_no_invented_auc(data):
    workspace = data["pred"].parent.parent
    binding = json.loads((workspace / "binding.json").read_text())
    plan = {"binding_digest": module._digest(binding), "runtime": {"version": "same"}}
    (workspace / "plan-binding.json").write_text(json.dumps(plan))
    identity = module._digest({"binding": binding, "runtime": plan["runtime"]})
    (workspace / "checkpoint-index.json").write_text(
        json.dumps({"checkpoint_best.pth": {"identity": identity, "sha256": "a" * 64}})
    )
    data["status"].unlink()
    (data["pred"] / "prediction-record.json").write_text(
        json.dumps(
            {
                "partition": "val",
                "checkpoint_sha256": "a" * 64,
                "status": "validated",
                "cases": 4,
                "output": str(data["pred"]),
            }
        )
    )
    report = run(data)
    assert report["cohort_complete"]
    assert report["metrics"]["patient_sensitivity"]["value"] == 1
    assert report["metrics"]["auc"]["reason_code"] == "continuous_scores_unavailable"
