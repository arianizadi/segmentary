"""Scientific oracles for native-volume metrics and accountable evaluation."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from segmentary.medical.data import fingerprint
from segmentary.medical.evaluation import (
    binary_segmentation_metrics,
    evaluate_predictions,
    lesion_detection_metrics,
    paired_comparison,
    patient_bootstrap,
)

nib = pytest.importorskip("nibabel")
pytest.importorskip("surface_distance")


def _volume(path: Path, data: np.ndarray, affine: np.ndarray | None = None) -> None:
    image = nib.Nifti1Image(data, np.diag([0.7, 1.2, 3.0, 1.0]) if affine is None else affine)
    image.header.set_xyzt_units("mm")
    nib.save(image, path)


@pytest.fixture
def cohort(tmp_path: Path) -> tuple[Path, Path, Path]:
    cases = []
    predictions = tmp_path / "predictions"
    predictions.mkdir()
    for index, status in enumerate(("labeled", "labeled", "organ_only", "unlabeled")):
        case_id = f"case_{index}"
        image_path, label_path = (
            tmp_path / f"image_{index}.nii.gz",
            tmp_path / f"label_{index}.nii.gz",
        )
        image = np.arange(8 * 11 * 9, dtype=np.float32).reshape(8, 11, 9)
        mask = np.zeros(image.shape, dtype=np.uint8)
        mask[1:6, 2:8, 1:7] = 1
        if status != "organ_only":
            mask[3:5, 4:6, 3:5] = 2
        _volume(image_path, image)
        if status != "unlabeled":
            _volume(label_path, mask)
        _volume(predictions / f"{case_id}.nii.gz", mask)
        cases.append(
            {
                "case_id": case_id,
                "patient_id": f"patient_{index}",
                "source": "synthetic",
                "image": str(image_path),
                "label": str(label_path) if status != "unlabeled" else None,
                "annotation_status": status,
                "shape": list(image.shape),
                "affine": nib.load(image_path).affine.tolist(),
                "spacing_mm": [0.7, 1.2, 3.0],
                "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "label_sha256": hashlib.sha256(label_path.read_bytes()).hexdigest()
                if label_path.exists()
                else None,
            }
        )
    manifest = tmp_path / "manifest.json"
    content = {
        "schema_version": 1,
        "dataset": "test",
        "source_root": str(tmp_path),
        "audit": {"passed": True},
        "ontology": {"background": 0, "pancreas": 1, "mass": 2},
        "cases": cases,
    }
    content["fingerprint"] = fingerprint(content)
    manifest.write_text(json.dumps(content))
    return manifest, predictions, tmp_path / "evaluation"


def test_positive_perfect_miss_and_empty_rules() -> None:
    reference = np.zeros((7, 11, 13), dtype=bool)
    reference[2:5, 4:8, 3:6] = True
    perfect = binary_segmentation_metrics(reference, reference.copy(), (0.7, 1.1, 3), 1)
    assert perfect["dice"] == perfect["surface_dice"] == 1
    assert perfect["hd95_mm"] == 0
    assert perfect["reference_volume_ml"] == pytest.approx(36 * 0.7 * 1.1 * 3 / 1000)
    empty = np.zeros_like(reference)
    missed = binary_segmentation_metrics(reference, empty, (0.7, 1.1, 3), 1)
    assert missed["dice"] == missed["surface_dice"] == 0
    assert missed["hd95_mm"] is None
    assert missed["hd95_status"] == "infinite_one_empty"
    false_positive = binary_segmentation_metrics(empty, reference, (1, 1, 1), 1)
    assert false_positive["dice"] == 0
    assert false_positive["empty_status"] == "reference_empty"
    both_empty = binary_segmentation_metrics(empty, empty, (1, 1, 1), 1)
    assert both_empty["dice"] is None
    assert both_empty["surface_dice"] is None
    assert both_empty["hd95_status"] == "undefined_both_empty"


def test_physical_distances_respect_anisotropic_axes_and_tolerance() -> None:
    reference = np.zeros((8, 13, 17), dtype=bool)
    reference[3, 5, 4] = True
    shifted = np.zeros_like(reference)
    shifted[3, 5, 9] = True
    isotropic = binary_segmentation_metrics(reference, shifted, (1, 1, 1), 6)
    anisotropic = binary_segmentation_metrics(reference, shifted, (1, 1, 3), 6)
    assert isotropic["hd95_mm"] == 5
    assert anisotropic["hd95_mm"] == 15
    assert isotropic["surface_dice"] == 1
    assert anisotropic["surface_dice"] == 0
    axis_permuted = binary_segmentation_metrics(
        reference.transpose(2, 0, 1), shifted.transpose(2, 0, 1), (3, 1, 1), 6
    )
    assert axis_permuted["hd95_mm"] == anisotropic["hd95_mm"]


@pytest.mark.parametrize("spacing", [(1, 1, 0), (-1, 1, 1), (1, 1), (1, 1, float("nan"))])
def test_invalid_metric_spacing_fails(spacing: tuple[float, ...]) -> None:
    mask = np.ones((3, 4, 5), dtype=bool)
    with pytest.raises(ValueError, match="spacing_mm"):
        binary_segmentation_metrics(mask, mask, spacing)


def test_patient_bootstrap_equal_patient_weight_and_determinism() -> None:
    values = {"a": [1, 1, 1, 1], "b": [0]}
    result = patient_bootstrap(values, bootstrap_samples=101, seed=7)
    assert result["mean"] == 0.5  # Not the scan-weighted mean, 0.8.
    assert result["patients"] == 2
    assert result["cases"] == 5
    assert result == patient_bootstrap(values, bootstrap_samples=101, seed=7)
    assert 0 <= result["ci"][0] <= result["ci"][1] <= 1
    assert patient_bootstrap({"a": [1]})["ci"] is None
    with pytest.raises(ValueError, match="finite"):
        patient_bootstrap({"a": [float("nan")]})


def test_complete_report_partial_labels_and_review_exports(cohort: tuple[Path, Path, Path]) -> None:
    manifest, predictions, output = cohort
    report = evaluate_predictions(
        manifest,
        predictions,
        output,
        surface_tolerance_mm=1,
        review_overlays=True,
        lesion_iou_threshold=0.1,
    )
    assert report["coverage"]["eligible_cases"] == 4
    assert report["coverage"]["status_counts"] == {"ok": 3, "unlabeled": 1}
    assert report["regions"]["mass"]["dice"]["patients"] == 2
    assert report["regions"]["mass"]["dice"]["mean"] == 1
    assert report["regions"]["pancreas"]["dice"]["patients"] == 3
    assert report["cases"][2]["metrics"]["mass"] is None
    assert report["cases"][3]["metrics"] == {}
    assert report["lesions"]["true_positives"] == 2
    assert report == json.loads((output / "report.json").read_text())
    with (output / "cases.csv").open() as stream:
        assert len(list(csv.DictReader(stream))) == 4
    reviews = list((output / "review").glob("*.png"))
    assert len(reviews) == 3
    assert all("case_" not in path.name and "patient_" not in path.name for path in reviews)
    from PIL import Image

    with Image.open(reviews[0]) as image:
        assert image.width == 1152
        assert image.height > 48


def test_missing_prediction_receives_zero_positive_dice_with_failure_coverage(
    cohort: tuple[Path, Path, Path],
) -> None:
    manifest, predictions, output = cohort
    (predictions / "case_1.nii.gz").unlink()
    report = evaluate_predictions(
        manifest, predictions, output, surface_tolerance_mm=1, lesion_iou_threshold=0.1
    )
    assert report["cases"][1]["status"] == "failed_prediction"
    assert report["cases"][1]["metrics"]["mass"]["dice"] == 0
    assert report["cases"][1]["metrics"]["mass"]["prediction_voxels"] is None
    assert report["regions"]["mass"]["dice"]["mean"] == 0.5
    assert report["regions"]["mass"]["dice"]["coverage"] == 1
    assert report["regions"]["mass"]["hd95_mm"]["coverage"] == 0.5
    assert report["coverage"]["prediction_coverage"] == 2 / 3
    assert report["lesions"]["sensitivity_including_failed_predictions"] == 0.5
    assert report["lesions"]["false_negatives"] == 1
    assert report["lesions"]["sensitivity_on_successful_cases"] == 1
    assert not report["lesions"]["false_positive_count_complete"]
    assert report["cases"][1]["lesions"]["false_positives"] is None


def test_geometry_mismatch_is_failed_case_not_automatic_resampling(
    cohort: tuple[Path, Path, Path],
) -> None:
    manifest, predictions, output = cohort
    path = predictions / "case_0.nii.gz"
    original = nib.load(path)
    affine = original.affine.copy()
    affine[0, 3] += 2
    _volume(path, np.asarray(original.dataobj), affine)
    report = evaluate_predictions(manifest, predictions, output)
    assert report["cases"][0]["status"] == "failed_prediction"
    assert "geometry mismatch" in report["cases"][0]["reason"]
    assert report["regions"]["mass"]["dice"]["mean"] == 0.5


def test_corrupt_or_changed_reference_reduces_reference_coverage(
    cohort: tuple[Path, Path, Path],
) -> None:
    manifest, predictions, output = cohort
    content = json.loads(manifest.read_text())
    Path(content["cases"][0]["label"]).write_bytes(b"corrupt")
    report = evaluate_predictions(manifest, predictions, output)
    assert report["cases"][0]["status"] == "failed_reference"
    assert report["cases"][0]["metrics"] == {}
    assert report["coverage"]["reference_coverage"] == 2 / 3
    assert report["regions"]["mass"]["reference_known_cases"] == 1


def test_pancreas_union_changes_only_declared_region(cohort: tuple[Path, Path, Path]) -> None:
    manifest, predictions, output = cohort
    path = predictions / "case_0.nii.gz"
    image = nib.load(path)
    data = np.asarray(image.dataobj).copy()
    data[data == 2] = 1
    _volume(path, data, image.affine)
    union = evaluate_predictions(manifest, predictions, output, case_ids=["case_0"])
    exclusive = evaluate_predictions(
        manifest,
        predictions,
        output / "exclusive",
        case_ids=["case_0"],
        pancreas_include_mass=False,
    )
    assert union["regions"]["pancreas"]["dice"]["mean"] == 1
    assert exclusive["regions"]["pancreas"]["dice"]["mean"] < 1
    assert union["regions"]["mass"]["dice"]["mean"] == 0


def test_paired_comparison_keeps_failures_and_rejects_changed_cohorts(
    cohort: tuple[Path, Path, Path],
) -> None:
    manifest, predictions, output = cohort
    good = evaluate_predictions(manifest, predictions, output)
    (predictions / "case_1.nii.gz").unlink()
    failed = evaluate_predictions(manifest, predictions, output / "failed")
    result = paired_comparison(good, failed)
    assert result["mean"] == -0.5
    assert result["cases"] == 2
    assert result["patients"] == 2
    assert result["eligible_cases"] == 4
    assert len(result["excluded_cases"]) == 2
    with pytest.raises(ValueError, match="One-sided undefined"):
        paired_comparison(good, failed, metric="hd95_mm")
    changed = copy.deepcopy(failed)
    changed["cases"].pop()
    with pytest.raises(ValueError, match="identical"):
        paired_comparison(good, changed)
    changed = copy.deepcopy(failed)
    changed["cases"][0]["patient_id"] = "different-patient"
    with pytest.raises(ValueError, match="grouping"):
        paired_comparison(good, changed)


def test_lesion_matching_merge_is_one_detection_and_spurious_component_is_fp() -> None:
    reference = np.zeros((20, 12, 10), dtype=bool)
    reference[2:5, 3:6, 3:6] = True
    reference[8:11, 3:6, 3:6] = True
    prediction = np.zeros_like(reference)
    prediction[2:11, 3:6, 3:6] = True  # Merges two references into one candidate.
    prediction[16:18, 8:10, 7:9] = True  # False positive candidate.
    scores = lesion_detection_metrics(reference, prediction, (1, 1, 3), 0.1)
    assert scores["true_positives"] == 1
    assert scores["false_negatives"] == 1
    assert scores["false_positives"] == 1
    assert scores["sensitivity"] == 0.5
    assert scores["false_positives_per_scan"] == 1


def test_lesion_size_filter_is_physical_and_does_not_filter_reference() -> None:
    reference = np.zeros((8, 9, 10), dtype=bool)
    reference[2, 2, 2] = True
    prediction = reference.copy()
    isotropic = lesion_detection_metrics(
        reference, prediction, (1, 1, 1), 0.1, minimum_prediction_volume_mm3=2
    )
    anisotropic = lesion_detection_metrics(
        reference, prediction, (1, 1, 3), 0.1, minimum_prediction_volume_mm3=2
    )
    assert isotropic["false_negatives"] == 1
    assert isotropic["removed_prediction_components"] == 1
    assert anisotropic["true_positives"] == 1


def test_invalid_or_duplicate_cohorts_fail_at_preflight(cohort: tuple[Path, Path, Path]) -> None:
    manifest, predictions, output = cohort
    with pytest.raises(ValueError, match="Duplicate requested"):
        evaluate_predictions(manifest, predictions, output, case_ids=["case_0", "case_0"])
    with pytest.raises(ValueError, match="unknown cases"):
        evaluate_predictions(manifest, predictions, output, case_ids=["not-in-cohort"])
    with pytest.raises(ValueError, match="tolerance"):
        evaluate_predictions(manifest, predictions, output, surface_tolerance_mm=float("nan"))


def test_manifest_tampering_and_report_overwrite_are_rejected(
    cohort: tuple[Path, Path, Path],
) -> None:
    manifest, predictions, output = cohort
    evaluate_predictions(manifest, predictions, output)
    with pytest.raises(FileExistsError, match="preserve"):
        evaluate_predictions(manifest, predictions, output)
    content = json.loads(manifest.read_text())
    content["cases"][0]["patient_id"] = "tampered"
    manifest.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="fingerprint"):
        evaluate_predictions(manifest, predictions, output / "tampered")


def test_unknown_prediction_units_and_conflicting_affines_fail(
    cohort: tuple[Path, Path, Path],
) -> None:
    manifest, predictions, output = cohort
    unknown = predictions / "case_0.nii.gz"
    original = nib.load(unknown)
    changed = nib.Nifti1Image(np.asarray(original.dataobj), original.affine)
    changed.header.set_xyzt_units("unknown")
    nib.save(changed, unknown)
    conflicting = predictions / "case_1.nii.gz"
    original = nib.load(conflicting)
    changed = nib.Nifti1Image(np.asarray(original.dataobj), original.affine)
    changed.header.set_xyzt_units("mm")
    translated = original.affine.copy()
    translated[0, 3] += 5
    changed.set_qform(translated, code=1)
    changed.set_sform(original.affine, code=1)
    nib.save(changed, conflicting)
    report = evaluate_predictions(manifest, predictions, output)
    assert report["cases"][0]["status"] == "failed_prediction"
    assert "explicitly be mm" in report["cases"][0]["reason"]
    assert report["cases"][1]["status"] == "failed_prediction"
    assert "conflicting qform/sform" in report["cases"][1]["reason"]


def test_organ_only_cannot_be_scored_as_exclusive_parenchyma(
    cohort: tuple[Path, Path, Path],
) -> None:
    manifest, predictions, output = cohort
    with pytest.raises(ValueError, match="whole-pancreas union"):
        evaluate_predictions(manifest, predictions, output, pancreas_include_mass=False)


def test_both_empty_mass_is_reported_separately_from_positive_dice(
    cohort: tuple[Path, Path, Path],
) -> None:
    manifest, predictions, output = cohort
    content = json.loads(manifest.read_text())
    label_path = Path(content["cases"][0]["label"])
    original = nib.load(label_path)
    empty_mass = np.asarray(original.dataobj).copy()
    empty_mass[empty_mass == 2] = 1
    _volume(label_path, empty_mass, original.affine)
    _volume(predictions / "case_0.nii.gz", empty_mass, original.affine)
    content["cases"][0]["label_sha256"] = hashlib.sha256(label_path.read_bytes()).hexdigest()
    content["fingerprint"] = fingerprint(content)
    manifest.write_text(json.dumps(content))
    # The other genuinely positive case fails. Empty-negative agreement must
    # not turn the mass mean into 0.5 or otherwise dilute the missed target.
    (predictions / "case_1.nii.gz").unlink()
    report = evaluate_predictions(manifest, predictions, output)
    assert report["regions"]["mass"]["dice"]["mean"] == 0
    assert report["regions"]["mass"]["dice"]["cases"] == 1
    assert report["regions"]["mass"]["both_empty_cases"] == 1
