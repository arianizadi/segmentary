"""Whole workflow oracles: immutable evidence, split lock, pairing and native panels."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from segmentary.medical.backend import _digest
from segmentary.medical.data import fingerprint
from segmentary.medical.evaluation import evaluate_predictions
from segmentary.medical.failure_analysis import analyze
from segmentary.medical.failure_panels import canonical, render_panels, select_planes
from segmentary.medical.geometry import sha256_file


def write(path, obj):
    path.write_text(json.dumps(obj))


def volume(path, arr, affine):
    image = nib.Nifti1Image(arr, affine)
    image.header.set_xyzt_units("mm")
    nib.save(image, path)


@pytest.fixture
def experiment(tmp_path):
    affine = np.diag([1.0, 2.0, 3.0, 1.0])
    cases = []
    for i in range(4):
        label = np.zeros((12, 12, 12), np.uint8)
        label[2:10, 2:10, 2:10] = 1
        label[3:5, 3:5, 3:5] = 2
        image = tmp_path / f"ct{i}.nii.gz"
        ref = tmp_path / f"ref{i}.nii.gz"
        volume(image, np.full(label.shape, i, np.int16), affine)
        volume(ref, label, affine)
        cases.append(
            dict(
                case_id=f"c{i}",
                patient_id=f"p{i}",
                source="synthetic",
                annotation_status="labeled",
                image=str(image),
                label=str(ref),
                shape=list(label.shape),
                affine=affine.tolist(),
                spacing_mm=[1, 2, 3],
                image_sha256=sha256_file(image),
                label_sha256=sha256_file(ref),
            )
        )
    manifest = dict(
        schema_version=1,
        dataset="synthetic",
        source_root=str(tmp_path),
        audit={"passed": True},
        ontology={"background": 0, "pancreas": 1, "mass": 2},
        cases=cases,
    )
    manifest["fingerprint"] = fingerprint(manifest)
    split = dict(
        schema_version=1,
        manifest_fingerprint=manifest["fingerprint"],
        train=["c0"],
        val=["c1", "c2"],
        test=["c3"],
        grouping_status="dataset_case_unverified",
    )
    split["fingerprint"] = fingerprint(split)
    mp = tmp_path / "manifest.json"
    sp = tmp_path / "splits.json"
    write(mp, manifest)
    write(sp, split)
    models = []
    for name in ["baseline", "candidate"]:
        root = tmp_path / name
        pred = root / "predictions/val"
        pred.mkdir(parents=True)
        for c in cases[1:3]:
            array = np.asarray(nib.load(c["label"]).dataobj).copy()
            if name == "candidate" and c["case_id"] == "c2":
                array[array == 2] = 1
                array[8:10, 8:10, 8:10] = 2
            volume(pred / f"{c['case_id']}.nii.gz", array, affine)
        out = tmp_path / f"{name}-evaluation"
        evaluate_predictions(
            mp, pred, out, case_ids=split["val"], surface_tolerance_mm=2, bootstrap_samples=0
        )
        binding = {
            "manifest_sha256": sha256_file(mp),
            "splits_sha256": sha256_file(sp),
            "run_id": name,
            "config": {"seed": 0},
        }
        write(root / "binding.json", binding)
        write(
            root / "checkpoint-index.json",
            {
                "identity": _digest(binding),
                "initialization": "scratch",
                "files": {"checkpoint_best.pth": {"sha256": "a" * 64, "path": "generation.pth"}},
            },
        )
        write(
            pred / "prediction-status.json",
            {
                "identity": _digest(binding),
                "partition": "val",
                "checkpoint_sha256": "a" * 64,
                "cases": [{"case_id": c["case_id"], "status": "completed"} for c in cases[1:3]],
            },
        )
        models.append(
            {
                "id": name,
                "seed": 0,
                "prediction_dir": str(pred),
                "evaluation_report": str(out / "report.json"),
            }
        )
    # Test payloads unavailable: code must never touch them, even to hash them.
    for k in ("image", "label"):
        Path(cases[3][k]).unlink()
    return dict(manifest=str(mp), splits=str(sp), partition="val", models=models)


def test_complete_native_workflow_synchronized_review_and_no_test_access(experiment, tmp_path):
    result = analyze(
        experiment, tmp_path / "out", review_limit=2, review_random=0, slices_per_plane=2
    )
    assert all(s["complete"] for s in result["summaries"].values())
    assert len(result["cases"]) == 2
    assert all(r["models"]["baseline"]["mass_dice"] == 1 for r in result["cases"])
    failed = next(r for r in result["cases"] if r["models"]["candidate"]["mass_dice"] == 0)
    assert failed["models"]["candidate"]["missed_lesions"] == 1
    assert failed["models"]["candidate"]["false_positive_lesions"] == 1
    for row in result["cases"]:
        for plane in ("axial", "coronal", "sagittal"):
            a = row["models"]["baseline"]["panels"][plane]
            b = row["models"]["candidate"]["panels"][plane]
            assert [Path(x).name for x in a] == [Path(x).name for x in b]
    assert (tmp_path / "out/review.html").exists()
    public = json.dumps(result)
    assert str(tmp_path) not in public
    assert '"case_id"' not in public
    with pytest.raises(FileExistsError):
        analyze(experiment, tmp_path / "out")


@pytest.mark.parametrize("fault", ["prediction_hash", "reference_hash", "receipt", "primary_dice"])
def test_invalid_case_stays_visible_and_blocks_complete_status(experiment, tmp_path, fault):
    model = experiment["models"][1]
    if fault == "prediction_hash":
        Path(model["prediction_dir"], "c1.nii.gz").write_bytes(b"corrupt")
    elif fault == "reference_hash":
        m = json.loads(Path(experiment["manifest"]).read_text())
        Path(m["cases"][1]["label"]).write_bytes(b"corrupt")
    elif fault == "receipt":
        p = Path(model["prediction_dir"]) / "prediction-status.json"
        s = json.loads(p.read_text())
        s["cases"][0]["status"] = "failed"
        write(p, s)
    else:
        p = Path(model["evaluation_report"])
        s = json.loads(p.read_text())
        s["cases"][0]["metrics"]["mass"]["dice"] = 0.123
        write(p, s)
    result = analyze(experiment, tmp_path / "out", review_limit=0, review_random=0)
    assert len(result["cases"]) == 2
    assert not result["summaries"]["candidate"]["complete"]
    assert result["summaries"]["candidate"]["valid_cases"] == 1


@pytest.mark.parametrize("fault", ["test", "missing_case", "binding", "duplicate_model"])
def test_invalid_protocol_rejected_before_output(experiment, tmp_path, fault):
    spec = copy.deepcopy(experiment)
    if fault == "test":
        spec["partition"] = "test"
    elif fault == "duplicate_model":
        spec["models"][1]["id"] = "baseline"
    elif fault == "binding":
        p = Path(spec["models"][0]["prediction_dir"]).parent.parent / "binding.json"
        s = json.loads(p.read_text())
        s["manifest_sha256"] = "b" * 64
        write(p, s)
    else:
        p = Path(spec["models"][0]["evaluation_report"])
        s = json.loads(p.read_text())
        s["cases"].pop()
        write(p, s)
    with pytest.raises(ValueError):
        analyze(spec, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_panel_physical_aspect_and_canonical_flip(tmp_path):
    arr = np.zeros((10, 12, 14), np.int16)
    arr[2:4, 3:5, 4:6] = 2
    affine = np.diag([-1.0, 2.0, 3.0, 1.0])
    ras = canonical(arr, affine)
    assert np.array_equal(ras, arr[::-1])
    planes = select_planes(ras, [ras], 0)
    assert len(planes["axial"]) == 14
    # Limit rendering; expected height reflects 2 mm Y spacing vs 1 mm X.
    paths = render_panels(
        ras,
        ras,
        ras,
        np.array([1.0, 2.0, 3.0]),
        {"axial": [5], "coronal": [4], "sagittal": [3]},
        tmp_path / "panels",
    )
    from PIL import Image

    assert Image.open(paths["axial"][0]).size == (1200, 768)


def test_primary_surface_protocols_must_match(experiment, tmp_path):
    path = Path(experiment["models"][1]["evaluation_report"])
    report = json.loads(path.read_text())
    report["protocol"]["surface_tolerance_mm"] = 20
    write(path, report)
    with pytest.raises(ValueError, match="protocols differ"):
        analyze(experiment, tmp_path / "out")


def test_seed_cannot_be_relabelled(experiment, tmp_path):
    experiment["models"][0]["seed"] = 2
    with pytest.raises(ValueError, match="seed differs"):
        analyze(experiment, tmp_path / "out")


def test_perfect_model_selected_slices_remain_on_target():
    ref = np.zeros((10, 10, 10), np.uint8)
    ref[4:6, 4:6, 4:6] = 2
    planes = select_planes(ref, [ref.copy()], 2)
    assert planes == {"axial": [4, 5], "coronal": [4, 5], "sagittal": [4, 5]}


def test_native_nnunet_timestamped_prediction_directory(experiment, tmp_path):
    model = experiment["models"][0]
    old = Path(model["prediction_dir"])
    new = old.parent / "val-123456"
    old.rename(new)
    model["prediction_dir"] = str(new)
    root = new.parent.parent
    (new / "prediction-status.json").unlink()
    binding = json.loads((root / "binding.json").read_text())
    plan = {"binding_digest": _digest(binding), "runtime": {"version": "synthetic"}}
    write(root / "plan-binding.json", plan)
    identity = _digest({"binding": binding, "runtime": plan["runtime"]})
    write(
        root / "checkpoint-index.json",
        {"checkpoint_best.pth": {"identity": identity, "sha256": "a" * 64}},
    )
    write(
        new / "prediction-record.json",
        {
            "partition": "val",
            "output": str(new),
            "status": "validated",
            "cases": 2,
            "checkpoint_sha256": "a" * 64,
        },
    )
    result = analyze(experiment, tmp_path / "out", review_limit=0, review_random=0)
    assert result["summaries"]["baseline"]["complete"]


def test_predicted_roi_audit_counts_excluded_tumor_and_locks_test(experiment, tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "roi_audit", Path(__file__).parents[1] / "scripts/audit_medical_roi_coverage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mp = Path(experiment["manifest"])
    sp = Path(experiment["splits"])
    data = json.loads(mp.read_text())
    roi = {
        "schema_version": 1,
        "kind": "predicted_pancreas_native_bbox",
        "reference_labels_used": False,
        "margin_mm": 20,
        "manifest_sha256": sha256_file(mp),
        "splits_sha256": sha256_file(sp),
        "cases": {
            c["case_id"]: {
                "image_sha256": c["image_sha256"],
                "bbox_xyz": [[7, 12], [7, 12], [7, 12]],
                "empty_prediction_fallback": False,
            }
            for c in data["cases"]
        },
    }
    path = tmp_path / "roi.json"
    write(path, roi)
    result = module.audit(mp, sp, path, sha256_file(path))
    assert result["valid_cases"] == 2
    assert all(c["outside_mass_voxels"] == 8 for c in result["cases"])
    with pytest.raises(ValueError, match="Reserved test"):
        module.audit(mp, sp, path, sha256_file(path), partition="test")
    with pytest.raises(ValueError, match="identity mismatch"):
        module.audit(mp, sp, path, "b" * 64)
