"""Evidence integrity and real training-partition checks for the matrix verifier."""

import argparse
import importlib.util
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
import torch

from segmentary.medical.data import audit_task07, make_splits

_spec = importlib.util.spec_from_file_location(
    "medical_model_verifier", Path(__file__).parents[1] / "scripts" / "verify_medical_models.py"
)
assert _spec is not None and _spec.loader is not None
verifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verifier)


@pytest.fixture
def args(tmp_path):
    return argparse.Namespace(
        device="cpu",
        profile="smoke",
        models=["lraspp"],
        manifest=None,
        splits=None,
        case_id=None,
        output=tmp_path / "evidence.json",
        seed=0,
        threads=2,
        spacing_mm=(1.5, 1.5, 2.5),
        hu_window=(-100.0, 240.0),
    )


@pytest.fixture
def real_case(args, tmp_path):
    source = tmp_path / "Task07_Pancreas"
    for folder in ("imagesTr", "labelsTr", "imagesTs"):
        (source / folder).mkdir(parents=True)
    training = []
    affine = np.diag([1.5, 1.5, 2.5, 1.0])
    for index in range(4):
        case_id = f"case_{index:03}"
        image = np.random.default_rng(index).normal(30, 15, (16, 16, 16)).astype(np.float32)
        label = np.zeros(image.shape, dtype=np.uint8)
        label[4:12, 4:12, 4:12] = 1
        label[7:9, 7:9, 7:9] = 2
        pair = {"image": f"./imagesTr/{case_id}.nii.gz", "label": f"./labelsTr/{case_id}.nii.gz"}
        for key, array in (("image", image), ("label", label)):
            volume = nib.Nifti1Image(array, affine)
            volume.header.set_xyzt_units("mm")
            volume.set_qform(affine, code=1)
            volume.set_sform(affine, code=1)
            nib.save(volume, source / pair[key])
        training.append(pair)
    (source / "dataset.json").write_text(
        json.dumps(
            {
                "numTraining": 4,
                "numTest": 0,
                "labels": {"0": "background", "1": "pancreas", "2": "cancer"},
                "training": training,
                "test": [],
            }
        )
    )
    args.manifest = tmp_path / "audit.json"
    args.splits = tmp_path / "splits.json"
    audit_task07(source, args.manifest)
    partitions = make_splits(args.manifest, args.splits, train_fraction=0.5, val_fraction=0.25)
    args.case_id = partitions["train"][0]
    return args, partitions


def test_matrix_records_real_optimizer_update_and_refuses_overwrite(args):
    previous = torch.get_num_threads()
    try:
        evidence = verifier.run(args)
    finally:
        torch.set_num_threads(previous)
    assert evidence["passed"] and evidence["passed_count"] == 1
    result = evidence["results"][0]
    assert result["max_parameter_delta"] > 0
    assert result["input_shape"] == [2, 5, 64, 64]
    assert result["output_shape"] == [2, 3, 64, 64]
    assert result["all_trainable_parameters_have_finite_gradients"] is True
    saved = args.output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        verifier.run(args)
    assert args.output.read_bytes() == saved


def test_failed_model_is_recorded_and_remaining_matrix_continues(args, monkeypatch):
    metadata = verifier.catalog()[:2]
    args.models = [item["name"] for item in metadata]
    monkeypatch.setattr(verifier, "catalog", lambda: metadata)

    def verify_one(item, *unused):
        if item["name"] == metadata[0]["name"]:
            raise ValueError("nonfinite test loss")
        return {"model": item["name"], "passed": True}

    monkeypatch.setattr(verifier, "_verify_one", verify_one)
    previous = torch.get_num_threads()
    try:
        evidence = verifier.run(args)
    finally:
        torch.set_num_threads(previous)
    assert not evidence["passed"]
    assert evidence["failed_count"] == evidence["passed_count"] == 1
    assert evidence["results"][0]["error"] == "nonfinite test loss"
    assert evidence["results"][1]["passed"] is True
    assert json.loads(args.output.read_text())["failed_count"] == 1


def test_real_ct_requires_train_membership_and_preserves_audit_hashes(real_case):
    args, partitions = real_case
    data, identity = verifier._data_source(args)
    assert data["image"].shape == data["label"].shape == (16, 16, 16)
    assert identity["partition"] == "train"
    assert identity["kind"] == "audited_real_training_ct"
    args.case_id = partitions["val"][0]
    with pytest.raises(ValueError, match="training partition"):
        verifier._data_source(args)
    args.case_id = partitions["train"][0]
    manifest = json.loads(args.manifest.read_text())
    selected = next(case for case in manifest["cases"] if case["case_id"] == args.case_id)
    with Path(selected["image"]).open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="audited hash"):
        verifier._data_source(args)


def test_real_ct_without_split_proof_is_rejected(real_case):
    args, _ = real_case
    args.splits = None
    with pytest.raises(ValueError, match="requires --splits"):
        verifier._data_source(args)


def test_large_finite_gradients_are_clipped_before_optimizer_step(args, monkeypatch):
    original_loss = verifier.training_loss
    monkeypatch.setattr(verifier, "training_loss", lambda *values: 1e6 * original_loss(*values))
    previous = torch.get_num_threads()
    try:
        evidence = verifier.run(args)
    finally:
        torch.set_num_threads(previous)
    assert evidence["passed"]
    result = evidence["results"][0]
    assert result["gradient_norm_before_clip"] > 12
    assert result["gradient_clipping_applied"] is True
    assert result["gradient_norm_after_clip"] <= 12.00001
    # SGD without momentum/decay has delta=-lr*gradient. The global L2 bound
    # therefore bounds each parameter change, independently of the model.
    assert 0 < result["max_parameter_delta"] <= 0.001 * 12 + 1e-6
    assert result["config"]["learning_rate"] == result["optimizer"]["learning_rate"]
    assert result["config"]["epochs"] == result["config"]["steps_per_epoch"] == 1
