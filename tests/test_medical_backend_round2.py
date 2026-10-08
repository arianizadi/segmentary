"""Backend contracts for region labels (Z2) and the nnssl pretrained runtime (Z4, Z4+HRC)."""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from segmentary.medical import backend as b
from segmentary.medical import nnunet_pretrained, nnunet_reference
from test_medical_backend import prepared as prepared_backend  # noqa: F401  (fixture)
from test_medical_recipe_plan import _seven_stage_plan
from test_medical_recipe_plan import plan as official_plan  # noqa: F401  (fixture)

REGION_LABELS = {"background": 0, "pancreas": [1, 2], "mass": [2]}
FREEZE, COMMIT = "f" * 64, "c" * 40
HRC_REGIONS = {"output_mode": "regions", "host_channels": [0], "lesion_channels": [1]}


@pytest.fixture(autouse=True)
def simulated_gpu_allocation(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2")


def _external_checkpoint(tmp_path: Path) -> tuple[str, str]:
    path = tmp_path / "models" / "checkpoint_final.pth"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"pretrained encoder")
    return str(path), b._sha(path)


def _nnssl(tmp_path: Path, **changes) -> dict:
    path, digest = _external_checkpoint(tmp_path)
    return {
        "backend_runtime": b.NNSSL_RUNTIME,
        "runtime_freeze_sha256": FREEZE,
        "nnunet_commit": COMMIT,
        "pretrained_plan_name": "nnFoundationCNN_8edba046",
        "trainer": b.PRETRAINED_TRAINER,
        "purpose": "finetune",
        "num_epochs": 300,
        "initial_lr": 1e-3,
        "initialization": "pretrained",
        "init_checkpoint": path,
        "init_checkpoint_sha256": digest,
        "init_allowed_missing_prefixes": ["decoder.", "encoder.stages.6."],
        "reference_workspace": str(tmp_path / "reference"),
        "reference_plan_binding_sha256": "a" * 64,
        **changes,
    }


def test_region_mode_binds_the_lossless_task07_decode(tmp_path):
    config = b.NNUNetConfig(str(tmp_path / "run"), output_mode="regions")
    assert config.label_regions == [["pancreas", [1, 2]], ["mass", [2]]]
    assert config.regions_class_order == [1, 2]
    round_trip = b.NNUNetConfig(**json.loads(json.dumps(dataclasses.asdict(config))))
    assert dataclasses.asdict(round_trip) == dataclasses.asdict(config)
    assert b._dataset_json(config, b.TASK07_ONTOLOGY, 3)["labels"] == REGION_LABELS
    assert b._dataset_json(config, b.TASK07_ONTOLOGY, 3)["regions_class_order"] == [1, 2]
    labels = b.NNUNetConfig(str(tmp_path / "run"))
    assert b._dataset_json(labels, b.TASK07_ONTOLOGY, 3)["labels"] == b.TASK07_ONTOLOGY
    for kwargs, message in (
        ({"output_mode": "softmax"}, "labels or regions"),
        ({"label_regions": {"pancreas": [1, 2]}}, "require output_mode=regions"),
        ({"regions_class_order": [1, 2]}, "require output_mode=regions"),
        ({"output_mode": "regions", "regions_class_order": [2, 1]}, "reproduce label"),
        ({"output_mode": "regions", "label_regions": [["mass", [3]]]}, "regions_class_order"),
        (
            {"output_mode": "regions", "label_regions": [["mass", [2]], ["pancreas", [1, 2]]]},
            "reproduce label 1",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            b.NNUNetConfig(str(tmp_path / "run"), **kwargs)


def test_hrc_output_mode_must_match_the_label_mode(tmp_path):
    reference = {
        "reference_workspace": str(tmp_path / "ref"),
        "reference_plan_binding_sha256": "a" * 64,
    }
    b.NNUNetConfig(
        str(tmp_path / "run"),
        architecture="hrc",
        output_mode="regions",
        hrc_options=HRC_REGIONS,
        **reference,
    )
    with pytest.raises(ValueError, match="HRC output_mode must be regions"):
        b.NNUNetConfig(
            str(tmp_path / "run"), architecture="hrc", output_mode="regions", **reference
        )
    with pytest.raises(ValueError, match="HRC output_mode must be softmax"):
        b.NNUNetConfig(
            str(tmp_path / "run"), architecture="hrc", hrc_options=HRC_REGIONS, **reference
        )


def test_nnssl_runtime_is_bound_to_its_freeze_commit_and_pretrained_trainer(tmp_path):
    config = b.NNUNetConfig(str(tmp_path / "run"), **_nnssl(tmp_path))
    assert config.plans == "ptPlans_dynamic__nnFoundationCNN_8edba046"
    assert config.reference_plans == "nnUNetResEncUNetLPlans"
    assert config.model_folder.name == (
        "nnUNetTrainerPretrainedDS__ptPlans_dynamic__nnFoundationCNN_8edba046__3d_fullres"
    )
    b.NNUNetConfig(str(tmp_path / "run"), **_nnssl(tmp_path, purpose="smoke", num_epochs=1))
    hrc = b.NNUNetConfig(
        str(tmp_path / "run"),
        **_nnssl(tmp_path, architecture="hrc", init_allowed_missing_prefixes=["decoder.", "hrc."]),
    )
    assert hrc.hrc_options is not None and hrc.hrc_options["output_mode"] == "softmax"
    for changes, message in (
        ({"runtime_freeze_sha256": None}, "pip-freeze"),
        ({"runtime_freeze_sha256": "F" * 64}, "pip-freeze"),
        ({"nnunet_commit": "c" * 7}, "nnunet_commit"),
        ({"pretrained_plan_name": "../x"}, "pretrained_plan_name"),
        (
            {"trainer": "nnUNetTrainerFinetune", "purpose": "pilot"},
            "runs nnUNetTrainerPretrainedDS",
        ),
        (
            {"reference_workspace": None, "reference_plan_binding_sha256": None},
            "reference workspace",
        ),
        ({"output_mode": "regions"}, "2.8.1 runtime only"),
        ({"purpose": "baseline", "num_epochs": None}, "finetune or smoke"),
        ({"purpose": "pilot"}, "finetune or smoke"),
        ({"num_iterations_per_epoch": 10}, "num_epochs only"),
        ({"initialization": "warm_start"}, "pretrained finetune"),
        ({"backend_runtime": "nnunet-3"}, "backend_runtime"),
    ):
        with pytest.raises(ValueError, match=message):
            b.NNUNetConfig(str(tmp_path / "run"), **_nnssl(tmp_path, **changes))
    official = {k: v for k, v in _nnssl(tmp_path).items() if k != "backend_runtime"}
    with pytest.raises(ValueError, match="bind the nnssl runtime"):
        b.NNUNetConfig(str(tmp_path / "run"), **official)
    for key in ("runtime_freeze_sha256", "nnunet_commit", "pretrained_plan_name"):
        official.pop(key)
    with pytest.raises(ValueError, match="only in the nnssl runtime"):
        b.NNUNetConfig(str(tmp_path / "run"), **official)
    with pytest.raises(ValueError, match="finetune is the"):
        b.NNUNetConfig(str(tmp_path / "run"), purpose="finetune")


def test_runtime_probe_binds_pip_freeze_and_nnunet_commit(tmp_path, monkeypatch):
    config = b.NNUNetConfig(
        str(tmp_path / "run"), **_nnssl(tmp_path, backend_python="/env/bin/python", gpu="2")
    )
    probe = {"python": "3.11", "executable": "/env/bin/python", "packages": {"nnunetv2": "2.8.1"}}
    monkeypatch.setattr(
        b.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(probe), stderr=""),
    )
    identity = {
        "pip_freeze_sha256": FREEZE,
        "nnunetv2_commit": COMMIT,
        "packages": {},
        "sources": {},
    }
    seen = []

    def runtime_identity(python, environment):
        seen.append((python, environment["PYTHONPATH"], environment["CUDA_VISIBLE_DEVICES"]))
        return dict(identity)

    monkeypatch.setattr(nnunet_pretrained, "runtime_identity", runtime_identity)
    runtime = b._runtime(config)
    assert runtime["nnssl"] == identity and runtime["packages"] == {"nnunetv2": "2.8.1"}
    assert seen[0][0] == "/env/bin/python" and seen[0][2] == "2"
    identity["pip_freeze_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="pip freeze"):
        b._runtime(config)
    identity.update(pip_freeze_sha256=FREEZE, nnunetv2_commit="0" * 40)
    with pytest.raises(RuntimeError, match="bound commit"):
        b._runtime(config)
    # The official runtime is probed exactly as before: no freeze or source probe.
    monkeypatch.setattr(nnunet_pretrained, "runtime_identity", lambda *a: pytest.fail("probed"))
    assert "nnssl" not in b._runtime(b.NNUNetConfig(str(tmp_path / "plain"), gpu="2"))


def test_scheduler_state_is_restored_only_into_the_same_scheduler_class():
    class Poly:
        def __init__(self):
            self.loaded = None

        def load_state_dict(self, state):
            self.loaded = state

    scheduler = Poly()
    b._restore_scheduler(scheduler, {"scheduler": {"max_steps": 285}, "scheduler_class": "Poly"})
    assert scheduler.loaded == {"max_steps": 285}
    scheduler = Poly()
    b._restore_scheduler(scheduler, {"scheduler": {"max_steps": 15}, "scheduler_class": "Lin_incr"})
    assert scheduler.loaded is None
    b._restore_scheduler(scheduler, {"scheduler": {"ctr": 3}})  # sidecars written before the guard
    assert scheduler.loaded == {"ctr": 3}


def test_pretrained_trainer_resolves_from_its_own_module(monkeypatch):
    sentinel = type("nnUNetTrainerPretrainedDS", (), {})
    # setitem on the module namespace: getattr would define the real (nnU-Net master) class.
    monkeypatch.setitem(vars(nnunet_pretrained), "nnUNetTrainerPretrainedDS", sentinel)
    assert b._trainer_class(b.PRETRAINED_TRAINER) is sentinel


# ---- planning from the frozen reference ---------------------------------------------------


def _reference(original: b.NNUNetConfig, plan: dict) -> tuple[str, dict]:
    """Give the prepared fixture workspace a frozen reference cache and plan binding."""
    cache = original.preprocessed
    data_id = plan["configurations"]["3d_fullres"]["data_identifier"]
    files = {
        "nnUNetResEncUNetLPlans.json": json.dumps(plan),
        "dataset.json": (
            original.root / "nnUNet_raw" / original.dataset / "dataset.json"
        ).read_text(),
        "dataset_fingerprint.json": "{}",
    }
    for case in ("train_a", "val_b"):
        files[f"{data_id}/{case}.b2nd"] = f"{case} image array"
        files[f"{data_id}/{case}_seg.b2nd"] = f"{case} segmentation array"
        files[f"{data_id}/{case}.pkl"] = f"{case} label-mode class_locations"
        files[f"gt_segmentations/{case}.nii.gz"] = f"{case} ground truth"
    for relative, text in files.items():
        (cache / relative).parent.mkdir(parents=True, exist_ok=True)
        (cache / relative).write_text(text)
    index = {str(p.relative_to(cache)): b._sha(p) for p in sorted(cache.rglob("*")) if p.is_file()}
    b._atomic_json(original.root / "plan-binding.json", {"files": index})
    return b._sha(original.root / "plan-binding.json"), index


@pytest.fixture
def frozen(prepared_backend, official_plan, monkeypatch, tmp_path):  # noqa: F811
    original, _, _, manifest, splits = prepared_backend
    plan = _seven_stage_plan(copy.deepcopy(official_plan))
    plan["configurations"]["3d_fullres"]["data_identifier"] = "nnUNetPlans_3d_fullres"
    plan["plans_name"] = "nnUNetResEncUNetLPlans"
    sha, index = _reference(original, plan)

    def make(name: str, **changes):
        config = dataclasses.replace(
            original,
            workspace=str(tmp_path / name),
            reference_workspace=original.workspace,
            reference_plan_binding_sha256=sha,
            deterministic=False,
            **changes,
        )
        b.prepare_dataset(manifest, splits, config)
        return config

    def import_reference(config):
        for relative in index:
            if relative != "splits_final.json":
                target = config.preprocessed / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((original.preprocessed / relative).read_bytes())
        return {"weights_imported": False}

    monkeypatch.setattr(nnunet_reference, "import_reference", import_reference)
    return SimpleNamespace(make=make, plan=plan, index=index, monkeypatch=monkeypatch)


def _region_worker(monkeypatch, *, cases: int = 2, tamper=None):
    calls = []

    def run(config, action, payload, *, gpu=False):
        assert (action, payload, gpu) == ("plan", {"adapt_reference": True}, False)
        data = config.preprocessed / "nnUNetPlans_3d_fullres"
        for case in ("train_a", "val_b"):
            (data / f"{case}.pkl").write_text(f"{case} region-mode class_locations")
        if tamper:
            tamper(config)
        b._atomic_json(
            config.root / "reference-adaptation-worker.json",
            {"regions": {"label_mode_reference_reproduced": cases, "region_keys": [[1, 2], [2]]}},
        )
        calls.append(config.workspace)
        return {"action": "plan", "status": "completed"}

    monkeypatch.setattr(b, "_run", run)
    return calls


def test_region_run_keeps_reference_arrays_and_rewrites_only_sampling_keys(frozen):
    config = frozen.make("regions", output_mode="regions")
    raw = b._json(config.root / "nnUNet_raw" / config.dataset / "dataset.json")
    assert raw["labels"] == REGION_LABELS and raw["regions_class_order"] == [1, 2]
    # nnU-Net's region heads follow this order; it must survive every record we write.
    assert list(raw["labels"]) == ["background", "pancreas", "mass"]
    calls = _region_worker(frozen.monkeypatch)
    result = b.plan_and_preprocess(config)
    assert calls == [config.workspace] and result["stage"]["action"] == "plan"
    assert b._json(config.preprocessed / "dataset.json") == raw
    assert list(b._json(config.preprocessed / "dataset.json")["labels"]) == list(raw["labels"])
    record = b._json(config.root / "reference-adaptation.json")
    assert record["arrays_and_ground_truth_equal_reference"] is True
    assert b._json(config.root / "recipe-transfer.json")["output_mode"] == "regions"
    binding = b._plan_binding(config)
    for relative, digest in frozen.index.items():
        if relative.endswith((".b2nd", ".nii.gz")):
            assert binding["files"][relative] == digest
        elif relative.endswith(".pkl"):
            assert binding["files"][relative] != digest
    # The raw region dataset.json, including its label order, is part of the bound identity.
    path = config.root / "nnUNet_raw" / config.dataset / "dataset.json"
    path.write_text(json.dumps(raw, sort_keys=True))
    with pytest.raises(ValueError, match="ontology"):
        b._binding(config)
    path.write_text(json.dumps({**raw, "regions_class_order": [2, 1]}))
    with pytest.raises(ValueError, match="ontology"):
        b._binding(config)


@pytest.mark.parametrize(
    "tamper, cases, message",
    [
        (
            lambda c: (c.preprocessed / "nnUNetPlans_3d_fullres/train_a.b2nd").write_text("x"),
            2,
            "hash changed",
        ),
        (
            lambda c: (c.preprocessed / "gt_segmentations/val_b.nii.gz").write_text("x"),
            2,
            "hash changed",
        ),
        (
            lambda c: (c.preprocessed / "nnUNetPlans_3d_fullres/extra.npy").write_text("x"),
            2,
            "membership",
        ),
        (None, 1, "every case"),
    ],
)
def test_region_adaptation_fails_closed(frozen, tamper, cases, message):
    config = frozen.make("regions", output_mode="regions")
    _region_worker(frozen.monkeypatch, cases=cases, tamper=tamper)
    with pytest.raises(ValueError, match=message):
        b.plan_and_preprocess(config)
    assert not (config.root / "plan-binding.json").exists()


def test_hrc_region_arm_reads_pancreas_as_host_and_mass_as_lesion(frozen):
    config = frozen.make(
        "hrc-regions", output_mode="regions", architecture="hrc", hrc_options=HRC_REGIONS
    )
    _region_worker(frozen.monkeypatch)
    b.plan_and_preprocess(config)
    receipt = b._json(config.root / "recipe-transfer.json")
    assert receipt["changes"]["hrc_outputs"] == {
        "output_mode": "regions",
        "host": ["pancreas"],
        "lesion": ["mass"],
    }


def _nnssl_worker(monkeypatch, *, plan_change=None, checkpoint=None, store=True):
    def run(config, action, payload, *, gpu=False):
        assert (action, payload) == ("plan", {"adapt_reference": True})
        frozen = b._json(config.preprocessed / f"{config.reference_plans}.json")
        pretrained = {
            **frozen,
            "configurations": {"3d_fullres": copy.deepcopy(frozen["configurations"]["3d_fullres"])},
            "plans_name": config.plans,
            "pretrain_info": {
                "checkpoint_path": checkpoint or config.init_checkpoint,
                "key_to_encoder": "encoder.stages",
                "citations": ["long"],
            },
        }
        if plan_change:
            plan_change(pretrained)
        b._atomic_json(config.preprocessed / f"{config.plans}.json", pretrained)
        if store:
            sampling = config.preprocessed / "nnUNetPlans_3d_fullres" / "fg_sampling"
            sampling.mkdir()
            for name in ("indptr.npy", "meta.json"):
                (sampling / name).write_text(name)
        b._atomic_json(config.root / "reference-adaptation-worker.json", {"nnssl": {}})
        return {"action": "plan", "status": "completed"}

    monkeypatch.setattr(b, "_run", run)


@pytest.mark.parametrize("architecture", ["resenc", "hrc"])
def test_nnssl_run_copies_arrays_and_binds_the_plan_like_dynamic_plan(
    frozen, tmp_path, architecture
):
    extra = ["hrc."] if architecture == "hrc" else []
    settings = _nnssl(
        tmp_path,
        architecture=architecture,
        init_allowed_missing_prefixes=["decoder.", "encoder.stages.6.", *extra],
    )
    settings.pop("reference_workspace")
    settings.pop("reference_plan_binding_sha256")
    config = frozen.make(f"nnssl-{architecture}", **settings)
    assert b._json(config.root / "binding.json")["initial_checkpoint"]["sha256"] == (
        config.init_checkpoint_sha256
    )
    _nnssl_worker(frozen.monkeypatch)
    result = b.plan_and_preprocess(config)
    assert result["plan_sha256"] == b._plan_binding(config)["files"][f"{config.plans}.json"]
    record = b._json(config.root / "reference-adaptation.json")
    assert record["pretrain_info"] == {
        "checkpoint_path": config.init_checkpoint,
        "key_to_encoder": "encoder.stages",
    }
    assert record["sampling_store_files"] == 2
    network = b._json(config.preprocessed / f"{config.plans}.json")["configurations"]["3d_fullres"]
    assert network["architecture"]["network_class_name"].endswith(
        "HRCResEncUNet" if architecture == "hrc" else "ResidualEncoderUNet"
    )
    assert b.train(config, dry_run=True)["trainer"] == b.PRETRAINED_TRAINER


@pytest.mark.parametrize(
    "worker, message",
    [
        (
            {
                "plan_change": lambda p: p["configurations"]["3d_fullres"].update(
                    patch_size=[1, 2, 3]
                )
            },
            "plan_like_dynamic",
        ),
        ({"plan_change": lambda p: p.update(transpose_forward=[2, 1, 0])}, "plan_like_dynamic"),
        ({"checkpoint": "/elsewhere/checkpoint_final.pth"}, "plan_like_dynamic"),
        ({"store": False}, "sampling store"),
    ],
)
def test_nnssl_adaptation_fails_closed(frozen, tmp_path, worker, message):
    settings = _nnssl(tmp_path)
    settings.pop("reference_workspace")
    settings.pop("reference_plan_binding_sha256")
    config = frozen.make("nnssl", **settings)
    _nnssl_worker(frozen.monkeypatch, **worker)
    with pytest.raises(ValueError, match=message):
        b.plan_and_preprocess(config)
    assert not (config.root / "plan-binding.json").exists()


def test_label_mode_official_runtime_never_starts_an_adaptation_worker(frozen):
    config = frozen.make("labels")
    frozen.monkeypatch.setattr(b, "_run", lambda *a, **k: pytest.fail("worker started"))
    assert b.plan_and_preprocess(config)["stage"]["action"] == "import_reference"
    assert not (config.root / "reference-adaptation.json").exists()
