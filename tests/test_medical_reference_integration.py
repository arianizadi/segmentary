"""Backend-stage contracts for frozen recipe transfer and upstream metadata."""

from __future__ import annotations

import copy
import dataclasses

import pytest

from segmentary.medical import backend as b
from segmentary.medical import nnunet_reference
from test_medical_backend import fake_checkpoint, fake_plan
from test_medical_backend import prepared as prepared_backend  # noqa: F401
from test_medical_recipe_plan import plan as official_plan  # noqa: F401


@pytest.fixture
def transfer(prepared_backend, official_plan, monkeypatch, tmp_path):  # noqa: F811
    original, _, _, manifest, splits = prepared_backend
    config = dataclasses.replace(
        original,
        workspace=str(tmp_path / "transfer"),
        architecture="plainconv",
        reference_workspace=original.workspace,
        reference_plan_binding_sha256="a" * 64,
    )
    b.prepare_dataset(manifest, splits, config)
    plan = copy.deepcopy(official_plan)
    imported = {"source_plan_sha256": b._digest(plan), "weights_imported": False}
    calls = []

    def import_reference(received):
        assert received == config
        assert {path.name for path in config.preprocessed.iterdir()} == {"splits_final.json"}
        b._atomic_json(config.preprocessed / f"{config.plans}.json", plan)
        raw = config.root / "nnUNet_raw" / config.dataset
        (config.preprocessed / "dataset.json").write_bytes((raw / "dataset.json").read_bytes())
        cache = config.preprocessed / "nnUNetPlans_3d_fullres"
        cache.mkdir()
        (cache / "train_a.b2nd").write_bytes(b"immutable imported preprocessing")
        calls.append("import")
        return imported

    def no_external_plan(*_args, **_kwargs):
        pytest.fail("Reference transfer must not invoke a fresh planner or worker")

    monkeypatch.setattr(nnunet_reference, "import_reference", import_reference)
    monkeypatch.setattr(b, "_run", no_external_plan)
    return config, plan, imported, calls


def test_import_freezes_adapted_plan_and_records_reference_without_training(transfer):
    config, original_plan, imported, calls = transfer
    result = b.plan_and_preprocess(config)
    assert calls == ["import"]
    assert result["stage"] == {"action": "import_reference", "status": "completed"}
    adapted = b._json(config.preprocessed / f"{config.plans}.json")
    architecture = adapted["configurations"]["3d_fullres"]["architecture"]
    assert architecture["network_class_name"].endswith(".PlainConvUNet")
    adapted["configurations"]["3d_fullres"]["architecture"] = original_plan["configurations"][
        "3d_fullres"
    ]["architecture"]
    assert adapted == original_plan
    record = b._plan_binding(config)
    assert result["plan_sha256"] == record["files"][f"{config.plans}.json"]
    assert record["binding_digest"] == b._digest(b._binding(config))
    assert record["runtime"] == b._runtime(config)
    receipt = b._json(config.root / "recipe-transfer.json")
    assert receipt["reference"] == imported
    assert receipt["architecture"] == "plainconv"
    assert receipt["changes"]["nonarchitecture_plan_fields_unchanged"] is True
    assert not (config.root / "scratch-origin.json").exists()
    assert b.train(config, dry_run=True)["resume"] is False


def test_transfer_dry_run_does_not_import_or_mutate(transfer):
    config, _, _, calls = transfer
    assert b.plan_and_preprocess(config, dry_run=True)["dry_run"] is True
    assert not calls
    assert {path.name for path in config.preprocessed.iterdir()} == {"splits_final.json"}


@pytest.mark.parametrize("change", ["plan", "cache", "architecture", "reference_pin"])
def test_transfer_train_and_resume_reject_mutated_identity(transfer, change):
    config, _, _, _ = transfer
    b.plan_and_preprocess(config)
    fake_checkpoint(config)
    assert b.train(config, resume=True, dry_run=True)["resume"] is True
    if change == "plan":
        path = config.preprocessed / f"{config.plans}.json"
        plan = b._json(path)
        plan["configurations"]["3d_fullres"]["spacing"] = [1, 1, 1]
        b._atomic_json(path, plan)
    elif change == "cache":
        (config.preprocessed / "nnUNetPlans_3d_fullres" / "train_a.b2nd").write_bytes(b"changed")
    elif change == "architecture":
        config = dataclasses.replace(config, architecture="resenc")
    else:
        config = dataclasses.replace(config, reference_plan_binding_sha256="b" * 64)
    with pytest.raises(ValueError):
        b.train(config, resume=True, dry_run=True)


@pytest.mark.parametrize("continue_training", [False, True])
def test_predict_accepts_upstream_boolean_runtime_plan_flag(
    prepared_backend,  # noqa: F811
    continue_training,
):
    config = prepared_backend[0]
    fake_plan(config)
    fake_checkpoint(config)
    path = config.model_folder / "plans.json"
    plan = b._json(path)
    plan["continue_training"] = continue_training
    b._atomic_json(path, plan)
    assert b.predict(config, dry_run=True)["cases"] == 1


@pytest.mark.parametrize("change", ["bad_runtime_type", "extra_runtime_key", "geometry"])
def test_predict_still_rejects_other_model_plan_changes(
    prepared_backend,  # noqa: F811
    change,
):
    config = prepared_backend[0]
    fake_plan(config)
    fake_checkpoint(config)
    path = config.model_folder / "plans.json"
    plan = b._json(path)
    plan["continue_training"] = False
    if change == "bad_runtime_type":
        plan["continue_training"] = "false"
    elif change == "extra_runtime_key":
        plan["another_runtime_setting"] = True
    else:
        plan["configurations"]["3d_fullres"]["spacing"] = [1, 1, 1]
    b._atomic_json(path, plan)
    with pytest.raises(ValueError):
        b.predict(config, dry_run=True)
