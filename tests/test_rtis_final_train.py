"""The opt-in final-train contract collects one fixed endpoint without validation."""

import contextlib
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from PIL import Image
from scripts import collect_rtis_statistics as collector
from scripts import profile_rtis_campaign as profiler
from scripts import run_rtis_campaign as runtime
from scripts.run_rtis_full_campaign import validate_collection

from helpers_gpu_policy import patch_live, write_campaign


def final_train_campaign():
    return {
        "collection_contract": runtime.FINAL_TRAIN_CONTRACT,
        "primary_checkpoint": "final",
        "validation_enabled": False,
    }


def final_train_config(data, output):
    return SimpleNamespace(
        stages=[SimpleNamespace(data=[SimpleNamespace(root=str(data))])],
        output_root=str(output),
        name="job",
        train=SimpleNamespace(seed=0, validation_enabled=False, early_stopping_patience=None),
        model=None,
        taxonomy_root="unused",
        space="unused",
    )


def train_dataset(root):
    (root / "audit").mkdir(parents=True)
    for kind in ("images", "masks"):
        (root / kind / "train").mkdir(parents=True)
    image = root / "images/train/train.png"
    Image.new("RGB", (5, 3), "red").save(image)
    Image.new("L", (5, 3)).save(root / "masks/train/train.png")
    sample = {
        "key": "train",
        "split": "train",
        "group": "training-scene",
        "image_extension": ".png",
        "width": 5,
        "height": 3,
        "image_sha256": runtime.digest(image),
        "mask_sha256": hashlib.sha256(bytes(15)).hexdigest(),
    }
    test = {**sample, "key": "test", "split": "test", "group": "test-scene"}
    splits = {
        "train": ["train"],
        "val": [],
        "test": ["test"],
        "groups": {"train": "training-scene", "test": "test-scene"},
    }
    runtime.write(root / "audit/samples.json", [sample, test])
    runtime.write(root / "splits.json", splits)
    runtime.write(root / "classes.json", {"classes": ["other", "mud-pumping"]})
    # Deliberately create no test directory. Adaptation must only read its metadata.
    return splits, [sample, test]


def test_final_train_runtime_uses_last_and_genuine_train_evaluation(tmp_path, monkeypatch):
    campaign = write_campaign(tmp_path, jobs=["job"], **final_train_campaign())
    data = tmp_path / "data"
    train_dataset(data)
    campaign.update(split_sha256=runtime.digest(data / "splits.json"), target_steps=4000)
    config = tmp_path / "job.yaml"
    config.write_text("config")
    job = {
        "name": "job",
        "config": str(config),
        "config_sha256": runtime.digest(config),
        "source_checkpoint": None,
        "seed": 0,
    }
    cfg = final_train_config(data, tmp_path / "future-runs")
    run = tmp_path / "future-runs/job_seed0/rtis"
    run.mkdir(parents=True)
    (run / "last.ckpt").write_text("final")
    runtime.write(
        run / "results.json",
        {"name": "job", "seed": 0, "metrics": {}, "env": {"validation_enabled": False}},
    )
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda layers: cfg)
    )
    monkeypatch.setitem(
        sys.modules,
        "segmentary.utils.resource_tracking",
        SimpleNamespace(run_recorded=lambda *a, **k: None),
    )
    monkeypatch.setattr(runtime, "learning_curve", lambda path: {"train/loss": []})
    monkeypatch.setattr(
        runtime,
        "checkpoint_info",
        lambda path: {
            "path": str(path),
            "sha256": runtime.digest(path),
            "global_step": 4000,
        },
    )
    commands = []

    def evaluate(command, **kwargs):
        commands.append(command)
        runtime.write(
            Path(command[command.index("--out") + 1]),
            {
                "metrics": {"miou": 0.5, "confusion": [[15]]},
                "config": {"evaluation": {"split": "train", "weights": "raw"}},
            },
        )

    monkeypatch.setattr(runtime.subprocess, "run", evaluate)
    runtime.run_job(tmp_path, tmp_path, job, 2, campaign)
    assert len(commands) == 1
    command = commands[0]
    assert command[command.index("--split") + 1] == "train"
    assert command[command.index("--pad-to-multiple") + 1] == "32"
    assert command[command.index("--out") + 1] == str(run / "final-train.json")
    state = runtime.read(tmp_path / "state/job.json")
    assert state["status"] == "collecting"
    assert set(state["checkpoints"]) == {"final"}
    assert state["evaluation_checkpoint"] == "final"
    assert state["evaluation_split"] == "train"
    assert state["evaluation_result"]["sha256"] == runtime.digest(run / "final-train.json")
    assert state["training"]["metrics"] == {}
    assert not list(run.glob("*val*"))
    assert not list(run.glob("best*"))


@pytest.mark.parametrize(
    "validation_enabled,contract,primary",
    [
        (True, runtime.FINAL_TRAIN_CONTRACT, "final"),
        (False, "rtis-full-statistics-v1", "final"),
        (False, runtime.FINAL_TRAIN_CONTRACT, "best"),
    ],
)
def test_final_train_requires_explicit_compatible_contract(validation_enabled, contract, primary):
    cfg = SimpleNamespace(train=SimpleNamespace(validation_enabled=validation_enabled))
    with pytest.raises(RuntimeError):
        runtime.validate_training_collection(
            cfg, {"collection_contract": contract, "primary_checkpoint": primary}
        )


def test_final_train_initialization_does_not_open_test_files(tmp_path, monkeypatch):
    data = tmp_path / "data"
    train_dataset(data)
    root = tmp_path / "campaign"
    root.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text("config")
    cfg = final_train_config(data, root / "future-runs")
    plan = {
        **final_train_campaign(),
        "dataset_final_fit": {"parent_split_sha256": "parent"},
        "research_protocol": {"primary_metric": "pooled_miou"},
        "research_protocol_sha256": "protocol-hash",
        "dataset": "data",
        "split_sha256": runtime.digest(data / "splits.json"),
        "grouping_status": "provisional",
        "target_steps_per_job": 4000,
        "gpu_allowlist": [2],
        "jobs": [
            {
                "name": "job",
                "config": str(config),
                "config_sha256": runtime.digest(config),
                "source_checkpoint": None,
            }
        ],
    }
    runtime.write(root / "plan.json", plan)
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda layers: cfg)
    )
    monkeypatch.setattr(
        runtime, "git", lambda repo, *args: "code" if args[0] == "rev-parse" else ""
    )
    monkeypatch.setattr(runtime.launch_requirements, "validate_plan", lambda *a: None)
    patch_live(monkeypatch)
    runtime.initialize(root, tmp_path)
    campaign = runtime.read(root / "campaign.json")
    assert campaign["dataset_samples_verified"] == 1
    assert campaign["dataset_sizes"] == {"train": 1, "val": 0, "test": 1}
    assert campaign["validation_enabled"] is False
    assert "best" not in campaign["selection"]
    for field in ("dataset_final_fit", "research_protocol", "research_protocol_sha256"):
        assert campaign[field] == plan[field]
    assert campaign["dataset_classes_sha256"] == runtime.digest(data / "classes.json")
    runtime.verify_frozen(root, tmp_path)
    (data / "classes.json").write_text("changed")
    with pytest.raises(RuntimeError, match="dataset classes changed"):
        runtime.verify_frozen(root, tmp_path)


@pytest.mark.parametrize(
    "field", ["dataset_final_fit", "research_protocol", "research_protocol_sha256"]
)
def test_final_train_protocol_metadata_remains_bound_to_frozen_plan(tmp_path, monkeypatch, field):
    metadata = {
        **final_train_campaign(),
        "dataset_final_fit": {"parent_split_sha256": "parent"},
        "research_protocol": {"primary_metric": "pooled_miou"},
        "research_protocol_sha256": "protocol-hash",
    }
    data = tmp_path / "data"
    train_dataset(data)
    config = tmp_path / "job.yaml"
    config.write_text("config")
    campaign = write_campaign(
        tmp_path,
        jobs=["job"],
        **metadata,
        dataset_classes_sha256=runtime.digest(data / "classes.json"),
    )
    plan = {**runtime.read(tmp_path / "plan.json"), **metadata}
    plan["jobs"][0]["config"] = str(config)
    runtime.write(tmp_path / "plan.json", plan)
    campaign["plan_sha256"] = runtime.digest(tmp_path / "plan.json")
    runtime.write(tmp_path / "campaign.json", campaign)
    monkeypatch.setattr(
        runtime, "git", lambda repo, *args: "code" if args[0] == "rev-parse" else ""
    )
    monkeypatch.setattr(runtime.launch_requirements, "validate_plan", lambda *a: None)
    monkeypatch.setitem(
        sys.modules,
        "segmentary.config",
        SimpleNamespace(load_experiment=lambda *a: final_train_config(data, tmp_path / "runs")),
    )
    patch_live(monkeypatch)
    runtime.verify_frozen(tmp_path, tmp_path)
    campaign[field] = "changed"
    runtime.write(tmp_path / "campaign.json", campaign)
    with pytest.raises(RuntimeError, match=field):
        runtime.verify_frozen(tmp_path, tmp_path)


def test_final_train_dataset_preflight_keeps_test_unopened(tmp_path, monkeypatch):
    train_dataset(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text("config")
    job = {"config": str(config), "config_sha256": runtime.digest(config)}
    campaign = {
        **final_train_campaign(),
        "split_sha256": runtime.digest(tmp_path / "splits.json"),
        "dataset_audit_sha256": runtime.digest(tmp_path / "audit/samples.json"),
        "dataset_sizes": {"train": 1, "val": 0, "test": 1},
    }
    monkeypatch.setattr(collector, "load_space", lambda *a: SimpleNamespace(num_classes=2))
    splits, samples = collector.validate_dataset(
        tmp_path, job, final_train_config(tmp_path, tmp_path / "runs"), campaign
    )
    assert splits["val"] == []
    assert len(samples) == 2


def test_final_train_collector_requires_both_train_variants():
    results = {key: {"images": 255} for key in ("final-auto-train", "final-alternate-train")}
    splits = {"train": list(range(255)), "val": [], "test": ["held-out"]}
    collector.validate_split_coverage(results, splits, runtime.FINAL_TRAIN_CONTRACT)
    with pytest.raises(RuntimeError, match="variants"):
        collector.validate_split_coverage(results, splits)
    results["final-auto-train"]["images"] -= 1
    with pytest.raises(RuntimeError, match="expected 255"):
        collector.validate_split_coverage(results, splits, runtime.FINAL_TRAIN_CONTRACT)


def test_final_train_collector_main_uses_only_final_train(tmp_path, monkeypatch):
    campaign = final_train_campaign()
    checkpoint = {"path": str(tmp_path / "last.ckpt"), "sha256": "final"}
    runtime.write(tmp_path / "campaign.json", campaign)
    runtime.write(tmp_path / "plan.json", {"jobs": [{"name": "job", "config": "unused"}]})
    runtime.write(
        tmp_path / "state/job.json",
        {
            "checkpoints": {"final": checkpoint},
            "evaluation": {"metrics": {"confusion": [[1]]}},
        },
    )
    cfg = final_train_config(tmp_path, tmp_path / "runs")
    monkeypatch.setattr(sys, "argv", ["collector", "--campaign", str(tmp_path), "--job", "job"])
    monkeypatch.setattr(collector, "load_experiment", lambda *a: cfg)
    monkeypatch.setattr(
        collector, "load_space", lambda *a: SimpleNamespace(names=["class"], num_classes=1)
    )
    monkeypatch.setattr(collector, "validate_dataset", lambda *a: ({"train": ["a"], "val": []}, []))
    monkeypatch.setattr(collector.runtime, "digest", lambda *a: "final")
    monkeypatch.setattr(collector, "seed_everything", lambda *a, **k: None)
    monkeypatch.setattr(collector.gpu_policy, "enforce_from_env", lambda **k: None)
    monkeypatch.setattr(collector, "ema_evaluation_safe", lambda *a: True)

    class Model:
        def cuda(self):
            return self

        def eval(self):
            return self

    monkeypatch.setattr(collector, "build_model", lambda *a: Model())
    monkeypatch.setattr(collector, "load_configured_checkpoint", lambda model, *a: model)
    calls = []

    def collect(model, cfg, samples, split, *args):
        calls.append(split)
        return {"images": 1, "metrics": {"confusion": [[1]]}}

    monkeypatch.setattr(collector, "collect", collect)
    collector.main()
    summary = runtime.read(tmp_path / "diagnostics/summary.json")
    assert calls == ["train", "train"]
    assert summary["contract"] == runtime.FINAL_TRAIN_CONTRACT
    assert summary["standalone_variant"] == "final-auto-train"
    assert set(summary["results"]) == {"final-auto-train", "final-alternate-train"}
    assert summary["standalone_confusion_exact_match"] is True
    assert summary["test_evaluated"] is False


def test_train_diagnostics_pad_narrow_frames_and_crop_predictions(tmp_path, monkeypatch):
    _, samples = train_dataset(tmp_path)
    cfg = final_train_config(tmp_path, tmp_path / "runs")
    cfg.aug = SimpleNamespace(
        crop=(32, 32),
        scale_min=1.0,
        scale_max=1.0,
        hflip_p=0.0,
        color_jitter_p=0.0,
        brightness=0.0,
        contrast=0.0,
        saturation=0.0,
        hue=0.0,
    )
    cfg.eval = SimpleNamespace(sliding_window=True, window=(32, 32), stride=(32, 32))
    monkeypatch.setattr(torch.Tensor, "cuda", lambda self: self)
    monkeypatch.setattr(collector.torch, "autocast", lambda *a, **k: contextlib.nullcontext())
    sizes = []

    def inference(model, image, *args):
        sizes.append(tuple(image.shape[-2:]))
        return torch.zeros((1, 2, *image.shape[-2:]))

    monkeypatch.setattr(collector, "inference", inference)
    result = collector.collect(
        object(), cfg, samples, "train", tmp_path / "diagnostics", ["other", "mud-pumping"]
    )
    assert sizes == [(32, 32)]
    assert np.asarray(result["metrics"]["confusion"]).sum() == 15
    with Image.open(tmp_path / "diagnostics/predictions/train.png") as prediction:
        assert prediction.size == (5, 3)


def test_final_train_profile_binds_genuine_train_record(tmp_path, monkeypatch):
    from segmentary import performance

    runtime.write(tmp_path / "campaign.json", {**final_train_campaign(), "code_sha": "code"})
    runtime.write(
        tmp_path / "plan.json",
        {"jobs": [{"name": "job", "config": "config.yaml", "model": "model", "seed": 0}]},
    )
    path = tmp_path / "last.ckpt"
    path.write_text("final")
    result_path = tmp_path / "final-train.json"
    runtime.write(result_path, {"config": {"evaluation": {"split": "train", "weights": "raw"}}})
    state = {
        "checkpoints": {
            "final": {"path": str(path), "sha256": runtime.digest(path), "global_step": 4000}
        },
        "evaluation_split": "train",
        "evaluation_result": {"path": str(result_path), "sha256": runtime.digest(result_path)},
        "evaluation": {
            "git_sha": "eval-code",
            "stage": "rtis",
            "config": {"evaluation": {"split": "train"}},
        },
    }
    runtime.write(tmp_path / "state/job.json", state)
    monkeypatch.setattr(profiler.gpu_policy, "enforce_from_env", lambda **k: None)
    seen = []

    def benchmark(args):
        seen.append(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("pending")
        return {"source": {"checkpoint_sha256": runtime.digest(args.ckpt)}}

    monkeypatch.setattr(performance, "run_benchmark", benchmark)
    profiler.measure(tmp_path, "job")
    assert seen[0].result == result_path
    assert runtime.read(tmp_path / "performance/job.json")["evaluation_split"] == "train"
    result_path.write_text("changed")
    with pytest.raises(RuntimeError, match="genuine final-train"):
        profiler.measure(tmp_path, "job")


def test_final_train_collection_validates_its_own_complete_evidence():
    state = {
        "checkpoints": {"final": {"sha256": "final"}},
        "evaluation_split": "train",
        "evaluation_checkpoint": "final",
        "evaluation_result": {"sha256": "train-result"},
        "evaluation": {"config": {"evaluation": {"split": "train"}}},
    }
    diagnostics = {
        "contract": runtime.FINAL_TRAIN_CONTRACT,
        "test_evaluated": False,
        "standalone_confusion_exact_match": True,
        "standalone_variant": "final-auto-train",
        "results": {
            variant: {"checkpoint_sha256": "final"}
            for variant in ("final-auto-train", "final-alternate-train")
        },
    }
    performance = {
        "status": "complete",
        "source": {"checkpoint_sha256": "final", "result_sha256": "train-result"},
        "model": {"parameter_count": 1},
        "measurements": {"latency": {"fps": 1}, "peak_reserved_bytes": 1},
    }
    attempts = [
        {"phase": phase, "status": "completed", "wall_clock_s": 1}
        for phase in ("training", "diagnostics", "performance")
    ]
    kwargs = {"primary_checkpoint": "final", "collection_contract": runtime.FINAL_TRAIN_CONTRACT}
    validate_collection(state, diagnostics, performance, attempts, **kwargs)
    with pytest.raises(RuntimeError, match="Missing train"):
        validate_collection(state, diagnostics, performance, attempts, primary_checkpoint="final")
    state["checkpoints"]["best"] = {"sha256": "best"}
    with pytest.raises(RuntimeError, match="exactly one final"):
        validate_collection(state, diagnostics, performance, attempts, **kwargs)


def test_final_train_full_worker_completes_and_retains_only_final(tmp_path, monkeypatch):
    from scripts import run_rtis_full_campaign as full

    campaign = write_campaign(tmp_path, jobs=["job"], **final_train_campaign())
    config = tmp_path / "job.yaml"
    config.write_text("config")
    job = {"name": "job", "config": str(config)}
    run = tmp_path / "future-runs/job_seed0/rtis"
    run.mkdir(parents=True)
    checkpoint = run / "last.ckpt"
    checkpoint.write_text("final")
    (run / "step-00000500.ckpt").write_text("periodic")
    state = {
        "name": "job",
        "status": "collecting",
        "checkpoints": {"final": {"path": str(checkpoint), "sha256": runtime.digest(checkpoint)}},
        "evaluation_checkpoint": "final",
        "evaluation_split": "train",
        "evaluation_result": {"sha256": "train-result"},
        "evaluation": {"config": {"evaluation": {"split": "train"}}},
    }
    runtime.write(tmp_path / "state/job.json", state)
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(collector, "validate_dataset", lambda *a: None)
    monkeypatch.setattr(runtime, "run_job", lambda *a: None)
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda *a: None)
    )

    def attempt(phase):
        runtime.write(
            tmp_path / "attempts/job" / f"{phase}.json",
            {
                "phase": phase,
                "status": "completed",
                "wall_clock_s": 1,
                "started_at": runtime.now(),
                "telemetry": [],
            },
        )

    attempt("training")

    def recorded(command, **kwargs):
        phase = kwargs["phase"]
        attempt(phase)
        if phase == "diagnostics":
            artifact = run / "diagnostics/per-image.csv"
            artifact.parent.mkdir()
            artifact.write_text("images\n1\n")
            runtime.write(
                run / "diagnostics/summary.json",
                {
                    "contract": runtime.FINAL_TRAIN_CONTRACT,
                    "test_evaluated": False,
                    "primary_checkpoint": "final",
                    "standalone_variant": "final-auto-train",
                    "standalone_confusion_exact_match": True,
                    "results": {
                        variant: {
                            "checkpoint_sha256": runtime.digest(checkpoint),
                            "artifacts": {"per-image.csv": str(artifact)},
                        }
                        for variant in ("final-auto-train", "final-alternate-train")
                    },
                },
            )
        else:
            runtime.write(
                tmp_path / "performance/job.json",
                {
                    "status": "complete",
                    "source": {
                        "checkpoint_sha256": runtime.digest(checkpoint),
                        "result_sha256": "train-result",
                    },
                    "model": {"parameter_count": 1},
                    "measurements": {"latency": {"fps": 1}, "peak_reserved_bytes": 1},
                },
            )

    monkeypatch.setattr(full, "run_recorded", recorded)
    full.run_job(tmp_path, tmp_path, job, 2, campaign)
    completed = runtime.read(tmp_path / "state/job.json")
    assert completed["status"] == "completed"
    assert completed["collection"]["contract"] == runtime.FINAL_TRAIN_CONTRACT
    assert completed["collection"]["resources"]["whole_run_accounting_complete"] is True
    assert {path.name for path in run.glob("*.ckpt")} == {"last.ckpt"}
