"""The recorded source bank and retained invocation receipts match loaded state."""

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from scripts import run_rtis_campaign as runtime

from helpers_gpu_policy import write_campaign
from segmentary import curriculum
from segmentary.engine.ema import EMA_CHECKPOINT_KEY, EmaConfig, ModelEma
from test_curriculum import (
    _tiny_model,
)
from test_curriculum import (
    test_no_validation_stage_and_recovery_preserve_final_training_state as exercise_stage,
)
from test_rtis_final_train import final_train_campaign, final_train_config, train_dataset


@pytest.mark.parametrize("reset_head", [False, True])
@pytest.mark.parametrize("batchnorm", [False, True])
@pytest.mark.parametrize("ema_present", [False, True])
def test_source_bank_provenance_matches_actual_loaded_parameters(
    tmp_path, reset_head, batchnorm, ema_present
):
    raw, shadow, target = [_tiny_model(seed) for seed in (1, 2, 3)]
    for model in (raw, shadow, target):
        if batchnorm:
            model.model.backbone.norm = torch.nn.BatchNorm2d(4)
    with torch.no_grad():
        for parameter in raw.parameters():
            parameter.fill_(1)
        for parameter in shadow.parameters():
            parameter.fill_(7)
    state = {
        "global_step": 40000,
        "state_dict": {"model." + name: tensor for name, tensor in raw.state_dict().items()},
    }
    if ema_present:
        state[EMA_CHECKPOINT_KEY] = ModelEma(shadow, EmaConfig()).state_dict()
    checkpoint = tmp_path / "source.ckpt"
    torch.save(state, checkpoint)
    metadata = {}
    assert (
        curriculum.load_backbone_weights(target, checkpoint, reset_head, provenance=metadata)
        is None
    )
    uses_ema = ema_present and not batchnorm
    assert target.model.backbone.stem.weight.eq(7 if uses_ema else 1).all()
    assert metadata == {
        "kind": "source_checkpoint",
        "checkpoint": str(checkpoint.resolve()),
        "checkpoint_bytes": checkpoint.stat().st_size,
        "checkpoint_global_step": 40000,
        "weights": "ema" if uses_ema else "raw",
        "model_state_key": EMA_CHECKPOINT_KEY if uses_ema else "state_dict",
        "optimizer_state": "fresh",
        "reset_head": reset_head,
    }


def test_real_no_validation_resume_records_optimizer_start_separately(tmp_path, monkeypatch):
    exercise_stage(tmp_path, monkeypatch)
    record = json.loads((tmp_path / "stage/results.json").read_text())
    initialization = record["env"]["initialization"]
    assert initialization["source_stage_initializer"]["kind"] == "public_recipe"
    assert initialization["source_stage_initializer"]["weights"] == "recipe_pretrained"
    actual_start = initialization["invocation_start"]
    assert actual_start["kind"] == "full_state_resume"
    assert actual_start["weights"] == "raw"
    assert actual_start["optimizer_state"] == "restored"
    assert actual_start["ema_shadow_restored"] is True
    assert actual_start["checkpoint_global_step"] == 2
    assert record["env"]["training_observations"]["optimizer_steps_this_invocation"] == 2
    assert record["env"]["stage_optimizer"]["warmup_iters"] == 0


def test_invocation_receipts_retain_original_bytes_peaks_and_deduplicate(tmp_path):
    job = {"name": "job", "seed": 1}
    run = tmp_path / "run"
    run.mkdir()
    source = run / "results.json"
    prior = b'{"name":"job","seed":1,"peak_vram_bytes":{"cuda:0":100}}\n'
    source.write_bytes(prior)
    first = runtime.archive_training_receipts(tmp_path, job, run)
    source.write_text(json.dumps({"name": "job", "seed": 1, "peak_vram_bytes": {"cuda:0": 10}}))
    retained = runtime.archive_training_receipts(tmp_path, job, run)
    assert len(retained) == 2
    assert runtime.archive_training_receipts(tmp_path, job, run) == retained
    assert Path(first[0]["path"]).read_bytes() == prior
    assert first[0]["sha256"] == hashlib.sha256(prior).hexdigest()
    assert (
        max(
            json.loads(Path(item["path"]).read_text())["peak_vram_bytes"]["cuda:0"]
            for item in retained
        )
        == 100
    )
    Path(first[0]["path"]).write_text("changed")
    with pytest.raises(RuntimeError, match="receipt changed"):
        runtime.archive_training_receipts(tmp_path, job, run)


def test_different_invocation_identity_is_rejected_before_archival(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    runtime.write(run / "results.json", {"name": "other-job", "seed": 1})
    with pytest.raises(RuntimeError, match="different run identity"):
        runtime.archive_training_receipts(tmp_path, {"name": "job", "seed": 1}, run)
    assert not (tmp_path / "attempts").exists()


def test_runtime_archives_prior_receipt_before_resume_overwrites_it(tmp_path, monkeypatch):
    campaign = write_campaign(tmp_path, jobs=["job"], **final_train_campaign())
    data = tmp_path / "data"
    train_dataset(data)
    campaign.update(split_sha256=runtime.digest(data / "splits.json"), target_steps=4000)
    config = tmp_path / "job.yaml"
    config.write_text("config")
    job = {
        "name": "job",
        "seed": 0,
        "config": str(config),
        "config_sha256": runtime.digest(config),
        "source_checkpoint": None,
    }
    cfg = final_train_config(data, tmp_path / "future-runs")
    run = tmp_path / "future-runs/job_seed0/rtis"
    run.mkdir(parents=True)
    (run / "last.ckpt").write_text("checkpoint")
    prior = {
        "name": "job",
        "seed": 0,
        "metrics": {},
        "env": {"validation_enabled": False},
        "peak_vram_bytes": {"cuda:0": 100},
    }
    runtime.write(run / "results.json", prior)
    runtime.write(
        tmp_path / "attempts/job/0000-training.json", {"phase": "training", "status": "interrupted"}
    )
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda *a: cfg)
    )
    monkeypatch.setattr(
        runtime,
        "checkpoint_info",
        lambda path: {"path": str(path), "sha256": runtime.digest(path), "global_step": 4000},
    )
    monkeypatch.setattr(runtime, "learning_curve", lambda *a: {})

    def train(*args, **kwargs):
        archived = list((tmp_path / "attempts/job/training-receipts").glob("*.json"))
        assert len(archived) == 1
        assert runtime.read(archived[0])["peak_vram_bytes"]["cuda:0"] == 100
        runtime.write(run / "results.json", {**prior, "peak_vram_bytes": {"cuda:0": 10}})
        runtime.write(
            tmp_path / "attempts/job/0001-training.json",
            {"phase": "training", "status": "completed"},
        )

    monkeypatch.setitem(
        sys.modules, "segmentary.utils.resource_tracking", SimpleNamespace(run_recorded=train)
    )

    def evaluate(command, **kwargs):
        runtime.write(
            Path(command[command.index("--out") + 1]),
            {"metrics": {"miou": 1}, "config": {"evaluation": {"split": "train"}}},
        )

    monkeypatch.setattr(runtime.subprocess, "run", evaluate)
    runtime.run_job(tmp_path, tmp_path, job, 2, campaign)
    state = runtime.read(tmp_path / "state/job.json")
    assert len(state["training_invocation_receipts"]) == 2
    assert state["training_allocator_peak_accounting_complete"] is False
    assert state["missing_training_allocator_peak_attempts"] == [
        str(tmp_path / "attempts/job/0000-training.json")
    ]
