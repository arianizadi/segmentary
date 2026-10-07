"""Bound trainer, pilot budget, warm-start and HRC fields of the nnU-Net backend."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from torch import nn

from segmentary.medical import backend as b
from segmentary.medical.recipe_plan import HRC_DEFAULTS
from test_medical_backend import prepared  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def simulated_gpu_allocation(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2")


def _reference(tmp_path: Path) -> dict:
    return {
        "reference_workspace": str(tmp_path / "reference"),
        "reference_plan_binding_sha256": "a" * 64,
    }


def _checkpoint(tmp_path: Path, payload: bytes = b"weights") -> tuple[str, str]:
    path = tmp_path / "init" / "checkpoint_final.pth"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path), b._sha(path)


def _warm(tmp_path: Path, **changes) -> dict:
    path, digest = _checkpoint(tmp_path)
    return {
        "trainer": "nnUNetTrainerFinetune",
        "purpose": "pilot",
        "num_epochs": 150,
        "initialization": "warm_start",
        "init_checkpoint": path,
        "init_checkpoint_sha256": digest,
        **changes,
    }


def test_trainer_allowlist_and_trainer_specific_learning_rate(tmp_path):
    config = b.NNUNetConfig(str(tmp_path / "run"))
    assert config.trainer == "nnUNetTrainer"
    assert config.model_folder.name == "nnUNetTrainer__nnUNetResEncUNetLPlans__3d_fullres"
    tuned = b.NNUNetConfig(str(tmp_path / "run"), **_warm(tmp_path, initial_lr=1e-3))
    assert tuned.model_folder.name == "nnUNetTrainerFinetune__nnUNetResEncUNetLPlans__3d_fullres"
    b.NNUNetConfig(str(tmp_path / "run"), **_warm(tmp_path, purpose="smoke", num_epochs=1))
    for kwargs in (
        {"trainer": "nnUNetTrainerCustom"},
        {"trainer": "nnUNetTrainer_250epochs"},
        {"initial_lr": 1e-3},  # the default trainer's learning rate is part of the recipe
        {"trainer": "nnUNetTrainerFinetune", "initial_lr": True},
        {"trainer": "nnUNetTrainerFinetune", "initial_lr": 0},
        {"trainer": "nnUNetTrainerFinetune", "initial_lr": 2.0},
        # The fine-tuning recipe is never a scratch run or a baseline.
        {"trainer": "nnUNetTrainerFinetune", "purpose": "smoke"},
        {"trainer": "nnUNetTrainerFinetune", "purpose": "pilot", "num_epochs": 150},
    ):
        with pytest.raises(ValueError):
            b.NNUNetConfig(str(tmp_path / "run"), **kwargs)
    for kwargs in ({"purpose": "baseline", "num_epochs": None}, {"purpose": "overfit"}):
        with pytest.raises(ValueError, match="pilot or smoke"):
            b.NNUNetConfig(str(tmp_path / "run"), **_warm(tmp_path, **kwargs))


def test_hrc_refuses_strict_determinism(tmp_path):
    with pytest.raises(ValueError, match="deterministic"):
        b.NNUNetConfig(
            str(tmp_path / "run"), architecture="hrc", deterministic=True, **_reference(tmp_path)
        )
    b.NNUNetConfig(str(tmp_path / "run"), architecture="resenc", deterministic=True)


def test_pilot_budget_overrides_only_the_epoch_count(tmp_path):
    pilot = b.NNUNetConfig(str(tmp_path / "run"), purpose="pilot", num_epochs=150)
    assert pilot.num_epochs == 150 and pilot.num_iterations_per_epoch is None
    for kwargs in (
        {"purpose": "pilot", "num_iterations_per_epoch": 10},
        {"purpose": "pilot", "num_epochs": 150, "num_val_iterations_per_epoch": 5},
        {"purpose": "pilot", "num_epochs": 0},
        {"purpose": "baseline", "num_epochs": 150},
        {"purpose": "screening"},
    ):
        with pytest.raises(ValueError):
            b.NNUNetConfig(str(tmp_path / "run"), **kwargs)
    # Smoke and overfit keep their existing freedom.
    b.NNUNetConfig(str(tmp_path / "run"), purpose="smoke", num_iterations_per_epoch=2)


def test_warm_start_configuration_requires_a_bound_external_checkpoint(tmp_path):
    config = b.NNUNetConfig(str(tmp_path / "run"), **_warm(tmp_path))
    assert config.init_allowed_missing_prefixes == []
    round_trip = b.NNUNetConfig(**json.loads(json.dumps(dataclasses.asdict(config))))
    assert dataclasses.asdict(round_trip) == dataclasses.asdict(config)
    path, digest = _checkpoint(tmp_path)
    for kwargs in (
        {"init_checkpoint": None},
        {"init_checkpoint": "relative/checkpoint.pth"},
        {"init_checkpoint_sha256": "A" * 64},
        {"init_allowed_missing_prefixes": ["hrc"]},  # prefixes must end at a module boundary
        {"init_allowed_missing_prefixes": "hrc."},
        {"initialization": "imagenet"},
        {"init_checkpoint": str(tmp_path / "run" / "fold_0" / "checkpoint_final.pth")},
    ):
        with pytest.raises(ValueError):
            b.NNUNetConfig(str(tmp_path / "run"), **_warm(tmp_path, **kwargs))
    with pytest.raises(ValueError, match="Scratch"):
        b.NNUNetConfig(str(tmp_path / "run"), init_checkpoint=path, init_checkpoint_sha256=digest)


def test_hrc_options_are_bound_completely_and_only_for_hrc(tmp_path):
    config = b.NNUNetConfig(
        str(tmp_path / "run"),
        architecture="hrc",
        hrc_options={"reference_mode": "unmasked_lcn"},
        **_reference(tmp_path),
    )
    assert config.hrc_options == {**HRC_DEFAULTS, "reference_mode": "unmasked_lcn"}
    assert config.model == "nnunet_planned_hrc"
    default = b.NNUNetConfig(str(tmp_path / "run"), architecture="hrc", **_reference(tmp_path))
    assert default.hrc_options == HRC_DEFAULTS
    with pytest.raises(ValueError, match="hrc_options"):
        b.NNUNetConfig(str(tmp_path / "run"), hrc_options={"reference_mode": "robust"})
    with pytest.raises(ValueError, match="Unknown HRC"):
        b.NNUNetConfig(
            str(tmp_path / "run"),
            architecture="hrc",
            hrc_options={"temperature": 2},
            **_reference(tmp_path),
        )
    with pytest.raises(ValueError, match="reference"):
        b.NNUNetConfig(str(tmp_path / "run"), architecture="hrc")


def _source_checkpoint(config: b.NNUNetConfig) -> tuple[str, str]:
    """Give a prepared workspace an indexed final checkpoint, as training would."""
    path = config.fold_folder / "checkpoint_final.pth"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"source weights")
    b._atomic_json(
        config.root / "checkpoint-index.json", {"checkpoint_final.pth": {"sha256": b._sha(path)}}
    )
    return str(path), b._sha(path)


def test_preparation_binds_and_verifies_the_initial_checkpoint(prepared, tmp_path):  # noqa: F811
    config, _, _, manifest_path, splits_path = prepared
    path, digest = _source_checkpoint(config)
    warm = dataclasses.replace(
        config,
        workspace=str(tmp_path / "warm"),
        **_warm(tmp_path, init_checkpoint=path, init_checkpoint_sha256=digest),
    )
    result = b.prepare_dataset(manifest_path, splits_path, warm)
    binding = b._json(warm.root / "binding.json")
    assert binding["initialization"] == "warm_start"
    record = binding["initial_checkpoint"]
    assert record["path"] == path and record["sha256"] == digest
    assert record["allowed_missing_prefixes"] == []
    assert record["source"]["source_workspace"] == str(config.root)
    assert record["source"]["source_fold"] == config.fold
    assert result["identity"] == b._digest(binding)
    Path(path).write_bytes(b"other weights")
    tampered = dataclasses.replace(warm, workspace=str(tmp_path / "tampered"))
    with pytest.raises(ValueError, match="hash"):
        b.prepare_dataset(manifest_path, splits_path, tampered)
    assert not tampered.root.exists()


def test_warm_start_must_come_from_the_same_fold_and_cohort(prepared, tmp_path):  # noqa: F811
    config, _, _, manifest_path, splits_path = prepared
    path, digest = _source_checkpoint(config)
    external, external_digest = _checkpoint(tmp_path)

    def attempt(name: str, **changes):
        run = dataclasses.replace(
            config, workspace=str(tmp_path / name), **_warm(tmp_path, **changes)
        )
        try:
            return b.prepare_dataset(manifest_path, splits_path, run)
        finally:
            assert run.root.exists() is (name == "ok-pretrained")

    with pytest.raises(ValueError, match="Segmentary nnU-Net workspace"):
        attempt("outside", init_checkpoint=external, init_checkpoint_sha256=external_digest)
    # A pretrained checkpoint may be external, but never a Segmentary workspace's.
    attempt(
        "ok-pretrained",
        initialization="pretrained",
        init_checkpoint=external,
        init_checkpoint_sha256=external_digest,
    )
    with pytest.raises(ValueError, match="warm_start"):
        attempt(
            "relabelled",
            initialization="pretrained",
            init_checkpoint=path,
            init_checkpoint_sha256=digest,
        )
    source = b._json(config.root / "binding.json")
    # A fold-1 checkpoint trained on this fold's validation cases.
    b._atomic_json(
        config.root / "binding.json", {**source, "config": {**source["config"], "fold": 1}}
    )
    with pytest.raises(ValueError, match="same dataset, cohort, CV manifest and fold"):
        attempt("other-fold", init_checkpoint=path, init_checkpoint_sha256=digest)
    b._atomic_json(config.root / "binding.json", {**source, "splits_sha256": "0" * 64})
    with pytest.raises(ValueError, match="same dataset, cohort, CV manifest and fold"):
        attempt("other-cohort", init_checkpoint=path, init_checkpoint_sha256=digest)
    b._atomic_json(config.root / "binding.json", source)
    b._atomic_json(config.root / "checkpoint-index.json", {})
    with pytest.raises(ValueError, match="indexed"):
        attempt("unindexed", init_checkpoint=path, init_checkpoint_sha256=digest)


class _Tiny(nn.Module):
    def __init__(self, extra: bool = False, width: int = 4) -> None:
        super().__init__()
        self.encoder = nn.Conv3d(1, width, 1)
        self.decoder = nn.Conv3d(width, 3, 1)
        if extra:
            self.hrc = nn.ModuleDict({"2": nn.Conv3d(width, 2, 1)})


def _save(tmp_path: Path, state: dict, name: str = "source.pth") -> tuple[str, str]:
    path = tmp_path / "init" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"network_weights": state, "trainer_name": "nnUNetTrainer", "current_epoch": 1000},
        path,
    )
    return str(path), b._sha(path)


def test_warm_start_loads_resenc_weights_and_allows_only_listed_new_modules(tmp_path):
    torch.manual_seed(0)
    source = _Tiny()
    path, digest = _save(tmp_path, source.state_dict())
    config = b.NNUNetConfig(
        str(tmp_path / "run"),
        **_warm(
            tmp_path,
            init_checkpoint=path,
            init_checkpoint_sha256=digest,
            init_allowed_missing_prefixes=["hrc."],
        ),
    )
    target = _Tiny(extra=True)
    new_before = target.hrc["2"].weight.detach().clone()
    record = b._load_initial_weights(target, config)
    assert torch.equal(target.encoder.weight, source.encoder.weight)
    assert torch.equal(target.decoder.bias, source.decoder.bias)
    assert torch.equal(target.hrc["2"].weight, new_before)
    assert record["missing_keys"] == ["hrc.2.bias", "hrc.2.weight"]
    assert record["unexpected_keys"] == [] and record["loaded_keys"] == 4
    assert record["init_checkpoint_sha256"] == digest and record["source_epoch"] == 1000
    assert record["initial_weights_sha256"] == b._state_digest(target.state_dict())
    assert record["optimizer_state_loaded"] is False
    # Same architecture (arm A): nothing may be missing.
    exact = b.NNUNetConfig(
        str(tmp_path / "exact"),
        **_warm(tmp_path, init_checkpoint=path, init_checkpoint_sha256=digest),
    )
    assert b._load_initial_weights(_Tiny(), exact)["missing_keys"] == []
    with pytest.raises(ValueError, match="missing_outside_allowlist"):
        b._load_initial_weights(_Tiny(extra=True), exact)


def test_warm_start_refuses_hash_unexpected_keys_and_shape_changes(tmp_path):
    source = _Tiny(extra=True)
    path, digest = _save(tmp_path, source.state_dict())
    base = _warm(tmp_path, init_checkpoint=path, init_checkpoint_sha256=digest)
    with pytest.raises(ValueError, match="unexpected"):
        b._load_initial_weights(_Tiny(), b.NNUNetConfig(str(tmp_path / "a"), **base))
    narrow, narrow_digest = _save(tmp_path, _Tiny(width=2).state_dict(), "narrow.pth")
    with pytest.raises(ValueError, match="shape_mismatch"):
        b._load_initial_weights(
            _Tiny(),
            b.NNUNetConfig(
                str(tmp_path / "b"),
                **_warm(tmp_path, init_checkpoint=narrow, init_checkpoint_sha256=narrow_digest),
            ),
        )
    stale = b.NNUNetConfig(str(tmp_path / "c"), **{**base, "init_checkpoint_sha256": "0" * 64})
    with pytest.raises(ValueError, match="hash changed"):
        b._load_initial_weights(_Tiny(extra=True), stale)
    empty, empty_digest = _save(tmp_path, {}, "empty.pth")
    with pytest.raises(ValueError, match="network_weights"):
        b._load_initial_weights(
            _Tiny(),
            b.NNUNetConfig(
                str(tmp_path / "d"),
                **_warm(tmp_path, init_checkpoint=empty, init_checkpoint_sha256=empty_digest),
            ),
        )


def test_resume_requires_this_experiments_own_origin_record(tmp_path):
    scratch = b.NNUNetConfig(str(tmp_path / "scratch"))
    assert b._origin_path(scratch).name == "scratch-origin.json"
    with pytest.raises(ValueError, match="origin"):
        b._check_resume_origin(scratch, "identity")
    b._atomic_json(
        b._origin_path(scratch),
        {"initialization": "scratch", "external_weight_loads": 0, "identity": "identity"},
    )
    b._check_resume_origin(scratch, "identity")
    with pytest.raises(ValueError, match="origin"):
        b._check_resume_origin(scratch, "other identity")
    warm = b.NNUNetConfig(str(tmp_path / "warm"), **_warm(tmp_path))
    assert b._origin_path(warm).name == "initialization-origin.json"
    record = {
        "initialization": "warm_start",
        "identity": "identity",
        "init_checkpoint_sha256": warm.init_checkpoint_sha256,
    }
    b._atomic_json(b._origin_path(warm), {**record, "init_checkpoint_sha256": "0" * 64})
    with pytest.raises(ValueError, match="origin"):
        b._check_resume_origin(warm, "identity")
    b._atomic_json(b._origin_path(warm), record)
    assert b._check_resume_origin(warm, "identity") == record


def test_predictor_uses_the_official_loader_only_for_builtin_trainers(tmp_path):
    calls = []
    predictor = SimpleNamespace(
        initialize_from_trained_model_folder=lambda *args, **kwargs: calls.append((args, kwargs))
    )
    b.initialize_predictor(predictor, tmp_path, 3, "checkpoint_final.pth", "nnUNetTrainer")
    assert calls == [
        ((str(tmp_path),), {"use_folds": (3,), "checkpoint_name": "checkpoint_final.pth"})
    ]
    with pytest.raises(ValueError, match="allowlisted"):
        b.initialize_predictor(predictor, tmp_path, 3, "checkpoint_final.pth", "nnUNetTrainerX")


def test_new_modules_are_covered_by_the_code_identity():
    identity = b._code_identity()
    assert {"host_reference.py", "nnunet_trainers.py", "nnunet_architectures.py"} <= set(identity)
