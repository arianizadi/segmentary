"""Contracts for the resumable all-model benchmark campaign."""

from __future__ import annotations

import copy
import csv
import io
import json
import pickle
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

import pytest
import torch
import yaml
from scripts import run_benchmark_campaign as campaign

from segmentary.checkpoints import TRAINING_RESUME_KEY, TRAINING_RESUME_SCHEMA_VERSION
from segmentary.config import config_hash
from segmentary.taxonomy import load_space
from segmentary.utils.results import RunRecord, write_results

SHA = "a" * 40
NEW_SHA = "b" * 40


def _metric_payload(space_name: str) -> dict:
    space = load_space(campaign.REPO_ROOT / "taxonomy", space_name)
    names = list(space.names)
    values = {name: 0.5 for name in names}
    support = {name: 1 for name in names}
    return {
        "miou": 0.5,
        "macc": 0.5,
        "mprecision": 0.5,
        "mdice": 0.5,
        "mspecificity": 0.5,
        "pixel_accuracy": 0.5,
        "freqw_iou": 0.5,
        "per_class_iou": values,
        "per_class_acc": values,
        "per_class_precision": values,
        "per_class_recall": values,
        "per_class_dice": values,
        "per_class_specificity": values,
        "support": support,
        "boundary": {
            "macro_f1": 0.5,
            "macro_precision": 0.5,
            "macro_recall": 0.5,
        },
    }


def _record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    city = tmp_path / "cityscapes"
    rail = tmp_path / "railsem19"
    city.mkdir()
    rail.mkdir()
    manifest = campaign.load_campaign_manifest()

    def git(arguments):
        if arguments == ["config", "--get", "remote.origin.url"]:
            return "https://github.com/arianizadi/segmentary.git"
        raise AssertionError(arguments)

    monkeypatch.setattr(campaign, "_git", git)
    return campaign.build_campaign_record(
        manifest=manifest,
        campaign=tmp_path / "campaign",
        expected_sha=SHA,
        datasets={"cityscapes": str(city), "railsem19": str(rail)},
        seeds=(0,),
        gpus=(0, 1, 2, 3),
        tmux_prefix="segmentary-test",
        python=Path(sys.executable),
        hf_home=None,
        batch_size=2,
        accum=8,
        train_workers=2,
        eval_workers=1,
        deterministic=False,
        reuse_roots=(),
        allowed_reuse_shas=(),
        publisher_root=None,
        publish_remote="origin",
        publish_branch="main",
        publish_interval=30,
    )


def test_manifest_covers_every_recipe_and_alias_is_not_duplicate_gpu_work() -> None:
    manifest = campaign.load_campaign_manifest()
    assert len(manifest.models) == 37
    assert {model.config for model in manifest.models} == {
        path.relative_to(campaign.REPO_ROOT)
        for path in (campaign.REPO_ROOT / "configs/models").glob("*.yaml")
    }
    logical = campaign.campaign_jobs(manifest, (0,))
    physical = campaign.campaign_jobs(manifest, (0,), include_aliases=False)
    assert len(logical) == 111
    assert len(physical) == 108
    alias = next(model for model in manifest.models if model.id == "deeplabv3plus_r101")
    assert alias.alias_of == "smp_deeplabv3plus_resnet101"


def test_alias_and_canonical_model_configs_have_same_compatibility_signature() -> None:
    alias = campaign.load_yaml(campaign.REPO_ROOT / "configs/models/deeplabv3plus_r101.yaml")
    canonical = campaign.load_yaml(
        campaign.REPO_ROOT / "configs/models/smp_deeplabv3plus_resnet101.yaml"
    )
    assert campaign._canonical_model_config(alias["model"]) == campaign._canonical_model_config(
        canonical["model"]
    )


def test_paper_raw_protocol_overrides_quality_without_discarding_deployment_record() -> None:
    source = {"source": {"checkpoint_sha256": "checkpoint-a"}}
    deployment = {
        "evaluation": {"weights": "ema"},
        "aggregate": {"miou": {"mean": 0.7}},
        "individual": [source],
    }
    paper_raw = {
        "evaluation": {"weights": "raw"},
        "aggregate": {"miou": {"mean": 0.69}},
        "individual": [copy.deepcopy(source)],
    }
    record = {
        "protocols": {
            "cityscapes": deployment,
            "railsem19": {"evaluation": {"weights": "raw"}},
        },
        "paper_raw_protocols": {"cityscapes": paper_raw},
    }

    primary = campaign._primary_protocols(record)

    assert primary["cityscapes"] is paper_raw
    assert primary["railsem19"] is record["protocols"]["railsem19"]
    assert record["protocols"]["cityscapes"] is deployment

    paper_raw["individual"][0]["source"]["checkpoint_sha256"] = "checkpoint-b"
    assert campaign._primary_protocols(record)["cityscapes"] is deployment


def test_legacy_b2_config_normalizes_to_current_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    job = next(
        item
        for item in record["jobs"]
        if item["model"] == "segformer_b2" and item["protocol"] == "cityscapes"
    )
    _, current = campaign._resolved_config(record, job, tmp_path / "prototype")
    legacy = json.loads(json.dumps(current))
    legacy["name"] = "reference_cityscapes19"
    legacy["output_root"] = "runs"
    legacy["train"].update({"devices": "auto", "batch_size": 2, "accum": 1})
    legacy["eval"].pop("num_workers")
    legacy["eval"].pop("threshold")
    for key in (
        "activation",
        "class_weights",
        "query",
        "task",
        "terms",
    ):
        legacy["loss"].pop(key)
    for key in (
        "backbone_path",
        "batch_norm_momentum",
        "classifier_path",
        "encoder_name",
        "encoder_weights",
        "head_paths",
        "inactive_parameter_paths",
        "local_files_only",
        "native",
        "revision",
        "smp_arch",
        "subfolder",
        "trust_remote_code",
    ):
        legacy["model"].pop(key)
    for data in legacy["stages"][0]["data"]:
        data.pop("loader")
        data.pop("loader_options")
        data.pop("mapping")
    legacy["stages"][0].pop("head_group_lr_scale")

    assert campaign.compatibility_sha256(
        legacy, runtime_device_count=8
    ) == campaign.compatibility_sha256(current)


def test_checkpoint_global_step_is_read_without_unpickling(tmp_path: Path) -> None:
    checkpoint = tmp_path / "last.ckpt"
    with zipfile.ZipFile(checkpoint, "w") as archive:
        archive.writestr("archive/data.pkl", pickle.dumps({"global_step": 24_000}))
    assert campaign._checkpoint_global_step(checkpoint) == 24_000


def test_latest_resume_checkpoint_selects_newest_stage_state_and_wires_cli(
    tmp_path: Path,
) -> None:
    job = {
        "experiment_name": "example",
        "seed": 0,
        "final_stage": "cityscapes",
        "evaluation_dataset": "cityscapes",
        "evaluation_mapping": "cityscapes19",
        "evaluation_split": "val",
        "evaluation_space": "cityscapes19",
        "model": "example",
        "id": "example--cityscapes--seed-0",
        "performance_owner": False,
    }
    attempt = tmp_path / "attempt-001"
    config = {
        "name": "resume-test",
        "model": {"arch": "segformer_b0"},
        "space": "cityscapes19",
        "train": {"iters": 100},
        "stages": [
            {
                "name": "cityscapes",
                "iters": None,
                "data": [{"name": "cityscapes", "root": "/unused"}],
            }
        ],
    }
    typed = campaign.from_dict(campaign.ExperimentConfig, config)
    expected_optim = asdict(
        campaign.stage_optim_config(typed.optim, typed.stages[0], typed.train.iters)
    )
    paths = campaign._attempt_paths(job, attempt, config)
    paths["config"].parent.mkdir(parents=True, exist_ok=True)
    paths["config"].write_text(yaml.safe_dump(config))
    stage_dir = paths["run_dir"] / "cityscapes"
    stage_dir.mkdir(parents=True)
    for step in (20, 40):
        torch.save(
            {
                "global_step": step,
                TRAINING_RESUME_KEY: {
                    "schema_version": TRAINING_RESUME_SCHEMA_VERSION,
                    "stage_name": "cityscapes",
                    "optim": expected_optim,
                },
            },
            stage_dir / f"step-{step:08d}.ckpt",
        )

    checkpoint, step, digest = campaign._latest_resume_checkpoint(paths, config) or (None, 0, "")
    assert checkpoint == stage_dir / "step-00000040.ckpt"
    assert step == 40
    assert digest == campaign._sha256(checkpoint)

    state = torch.load(checkpoint, weights_only=True)
    state[TRAINING_RESUME_KEY]["optim"]["backbone_lr"] *= 0.1
    torch.save(state, checkpoint)
    with pytest.raises(campaign.CampaignError, match="optimizer configuration does not match"):
        campaign._latest_resume_checkpoint(paths, config)

    record = {
        "execution": {
            "python": sys.executable,
            "deterministic": False,
            "eval_workers": 1,
        },
        "source": {"expected_git_sha": SHA},
        "datasets": {"cityscapes": "/cityscapes"},
        "jobs": [job],
    }
    train, _, _ = campaign._commands(record, job, paths, resume_checkpoint=checkpoint)
    assert train[-2:] == ["--resume-checkpoint", str(checkpoint)]


def test_partition_is_complete_unique_and_one_physical_gpu_per_lane() -> None:
    manifest = campaign.load_campaign_manifest()
    jobs = campaign.campaign_jobs(manifest, (0,), include_aliases=False)
    lanes = campaign.partition_jobs(jobs, (0, 2, 4, 6))
    flattened = [job for lane in lanes.values() for job in lane]
    assert len(flattened) == len(jobs) == 108
    assert len({job.id for job in flattened}) == 108
    assert set(campaign.MODEL_COST_WEIGHTS) == {job.model.id for job in jobs}
    loads = [sum(campaign._job_cost(job) for job in lane) for lane in lanes.values()]
    assert max(loads) / min(loads) < 1.02
    priority = {model_id: index for index, model_id in enumerate(manifest.priority_order)}
    for lane in lanes.values():
        unit_priorities = [
            priority[job.model.id] for job in lane if job.protocol.id != "cityscapes_to_railsem19"
        ]
        assert unit_priorities == sorted(unit_priorities)
    for lane in lanes.values():
        for index, job in enumerate(lane):
            if job.protocol.id != "cityscapes_to_railsem19":
                continue
            assert index > 0
            source = lane[index - 1]
            assert source.model.id == job.model.id
            assert source.seed == job.seed
            assert source.protocol.id == "cityscapes"


def test_transfer_reuses_city_checkpoint_and_only_schedules_target_iterations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    transfer = next(job for job in record["jobs"] if job["protocol"] == "cityscapes_to_railsem19")
    source = next(job for job in record["jobs"] if job["id"] == transfer["depends_on"])
    manifest = campaign.load_campaign_manifest()
    model = next(item for item in manifest.models if item.id == transfer["model"])
    assert campaign._job_cost(campaign.Job(model, manifest.protocols["cityscapes"], 0)) == (
        campaign._job_cost(campaign.Job(model, manifest.protocols["cityscapes_to_railsem19"], 0))
    )
    assert source["lane"] == transfer["lane"]
    lane = next(item for item in record["lanes"] if item["id"] == transfer["lane"])
    assert lane["job_ids"].index(transfer["id"]) == lane["job_ids"].index(source["id"]) + 1

    checkpoint = tmp_path / "city.ckpt"
    checkpoint.write_bytes(b"city")
    _, resolved = campaign._resolved_config(
        record, transfer, tmp_path / "transfer", dependency_checkpoint=checkpoint
    )
    assert campaign._iteration_plan(resolved)["total_target_iterations"] == 20_000
    assert resolved["stages"][0]["init_from"] == str(checkpoint)
    assert resolved["stages"][0]["reset_head"] is True
    assert resolved["stages"][0]["lr_scale"] == pytest.approx(0.1)
    assert resolved["stages"][0]["head_group_lr_scale"] == pytest.approx(1.0)
    assert campaign._iteration_plan(resolved)["stages"] == [
        {
            "stage": "railsem19",
            "target_iterations": 20_000,
            "learning_rate_scale": pytest.approx(0.1),
            "head_group_learning_rate_scale": pytest.approx(1.0),
        }
    ]
    assert record["execution"]["planned_optimizer_iterations"] == 3_600_000
    assert record["execution"]["avoided_duplicate_city_iterations"] == 1_440_000

    paths = campaign._attempt_paths(transfer, tmp_path / "attempt", resolved)
    assert paths["milestone_checkpoints"] == {}
    assert campaign._milestone_evaluation_commands(record, transfer, paths) == {}


def test_legacy_success_hashes_omit_empty_milestone_maps() -> None:
    hashes = {"checkpoint": "abc", "stage_results": {"cityscapes": "def"}}

    assert campaign._normalised_success_hashes(hashes) == {
        "checkpoint": "abc",
        "stage_results": {"cityscapes": "def"},
        "milestone_checkpoints": {},
        "milestone_results": {},
    }
    assert "milestone_checkpoints" not in hashes


def test_transfer_dependency_requires_unchanged_completed_city_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    transfer = next(job for job in record["jobs"] if job["protocol"] == "cityscapes_to_railsem19")
    lane = next(item for item in record["lanes"] if item["id"] == transfer["lane"])
    status = campaign._lane_status(record, lane)
    source = next(job for job in status["jobs"] if job["id"] == transfer["depends_on"])
    checkpoint = tmp_path / "city.ckpt"
    checkpoint.write_bytes(b"exact city weights")
    source.update(
        {
            "status": "succeeded",
            "attempts": [
                {
                    "paths": {"checkpoint": str(checkpoint)},
                    "sha256": {"checkpoint": campaign._sha256(checkpoint)},
                }
            ],
        }
    )

    actual, provenance = campaign._dependency_checkpoint(status, transfer)
    assert actual == checkpoint
    assert provenance == {
        "job_id": source["id"],
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": campaign._sha256(checkpoint),
        "classifier_policy": "reset incompatible target classifier only",
    }

    checkpoint.write_bytes(b"changed")
    with pytest.raises(campaign.CampaignError, match="missing or changed"):
        campaign._dependency_checkpoint(status, transfer)


def test_public_transfer_provenance_keeps_hash_but_redacts_server_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    transfer = next(job for job in record["jobs"] if job["protocol"] == "cityscapes_to_railsem19")
    _, resolved = campaign._resolved_config(record, transfer, tmp_path / "transfer")
    resolved["evaluation"] = {"weights": "ema"}
    attempt = {
        "kind": "reused",
        "iteration_plan": campaign._iteration_plan(resolved),
        "checkpoint_available": False,
        "checkpoint_step": None,
        "dependency": {
            "job_id": transfer["depends_on"],
            "checkpoint": "/data/private/city.ckpt",
            "checkpoint_sha256": "a" * 64,
            "classifier_policy": "reset incompatible target classifier only",
        },
    }

    protocol = campaign._new_protocol(
        transfer,
        {"config": resolved, "dataset_sizes": {"eval": 850}},
        attempt,
    )

    serialized = json.dumps(protocol)
    assert "/data/" not in serialized
    assert protocol["source_checkpoint"] == {
        "job_id": transfer["depends_on"],
        "checkpoint_sha256": "a" * 64,
        "classifier_policy": "reset incompatible target classifier only",
    }
    assert protocol["training"] == (
        "reused matching 40,000-step Cityscapes checkpoint; 20,000 RailSem19 steps"
    )
    assert protocol["evaluation"]["weights"] == "ema"

    raw_resolved = copy.deepcopy(resolved)
    raw_resolved["evaluation"]["weights"] = "raw"
    raw_protocol = campaign._new_protocol(
        transfer,
        {"config": raw_resolved, "dataset_sizes": {"eval": 850}},
        attempt,
    )
    assert raw_protocol["evaluation"]["weights"] == "raw"

    legacy_plan = copy.deepcopy(attempt["iteration_plan"])
    for stage in legacy_plan["stages"]:
        stage.pop("head_group_learning_rate_scale")
    legacy_attempt = {**attempt, "iteration_plan": legacy_plan}
    legacy_protocol = campaign._new_protocol(
        transfer,
        {"config": resolved, "dataset_sizes": {"eval": 850}},
        legacy_attempt,
    )
    assert legacy_protocol["training"] == protocol["training"]
    assert legacy_protocol["iteration_progress"] == protocol["iteration_progress"]


@pytest.mark.parametrize("model_id", ["eomt_large", "eomt_dinov3_large"])
@pytest.mark.parametrize("protocol_id", ["cityscapes", "railsem19", "cityscapes_to_railsem19"])
def test_eomt_campaign_cells_use_fixed_native_query_objective(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
    protocol_id: str,
) -> None:
    record = _record(tmp_path, monkeypatch)
    job = next(
        item
        for item in record["jobs"]
        if item["model"] == model_id and item["protocol"] == protocol_id
    )
    _, resolved = campaign._resolved_config(record, job, tmp_path / "prototype")
    loss = resolved["loss"]
    assert loss["query"]["kind"] == "hungarian_query"
    assert loss["query"]["matching_num_points"] == 8192
    assert loss["terms"] == []
    assert loss["aux"] == "none"
    assert loss["aux_weight"] == 0.0
    assert loss["ce_weight"] == 1.0
    assert loss["label_smoothing"] == 0.0
    assert loss["class_weights"] is None
    assert resolved["train"]["batch_size"] == 2
    assert resolved["train"]["accum"] == 8


@pytest.mark.parametrize("protocol_id", ["cityscapes", "railsem19", "cityscapes_to_railsem19"])
def test_beit_campaign_uses_native_crop_and_fast_equivalent_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, protocol_id: str
) -> None:
    record = _record(tmp_path, monkeypatch)
    job = next(
        item
        for item in record["jobs"]
        if item["model"] == "hf_auto_beit_base_ade" and item["protocol"] == protocol_id
    )

    _, resolved = campaign._resolved_config(record, job, tmp_path / "prototype")

    assert resolved["aug"]["crop"] == [640, 640]
    assert resolved["train"]["batch_size"] == 4
    assert resolved["train"]["accum"] == 4
    assert resolved["train"]["batch_size"] * resolved["train"]["accum"] == 16
    assert resolved["eval"]["window"] == [1024, 1024]


def test_model_runtime_override_cannot_change_effective_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    job = next(item for item in record["jobs"] if item["model"] == "hf_auto_beit_base_ade")
    original_load_yaml = campaign.load_yaml

    def load_yaml(path: Path) -> dict:
        if path.name == "bad-runtime.yaml":
            return {"train": {"batch_size": 3, "accum": 4}}
        return original_load_yaml(path)

    monkeypatch.setattr(campaign, "load_yaml", load_yaml)
    job["campaign_config"] = "bad-runtime.yaml"

    with pytest.raises(campaign.CampaignError, match="changed effective batch to 12"):
        campaign._resolved_config(record, job, tmp_path / "prototype")


def test_default_cli_uses_batch_two_and_accumulation_eight() -> None:
    args = campaign.build_parser().parse_args(
        [
            "launch",
            "--campaign",
            "/runs/campaign",
            "--expected-sha",
            SHA,
            "--cityscapes-root",
            "/datasets/cityscapes",
            "--railsem19-root",
            "/datasets/railsem19",
            "--gpus",
            "0",
        ]
    )
    assert args.batch_size == 2
    assert args.accum == 8


def test_exactly_one_rail_performance_owner_per_physical_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    owners = [job for job in record["jobs"] if job["performance_owner"]]
    assert len(owners) == 36
    assert {job["protocol"] for job in owners} == {"railsem19"}
    assert {job["seed"] for job in owners} == {0}
    assert all(not job.get("alias_of") for job in owners)
    monkeypatch.setattr(campaign, "_expected_final_step", lambda *_args: 40_000)
    monkeypatch.setattr(campaign, "load_yaml", lambda *_args: {})
    for job in record["jobs"]:
        paths = {
            "config": Path("/resolved.yaml"),
            "checkpoint": Path("/last.ckpt"),
            "common_results": Path("/results.json"),
            "performance": Path("/performance.json"),
            "run_dir": Path("/run"),
        }
        benchmark = campaign._commands(record, job, paths)[2]
        assert bool(benchmark) is bool(job["performance_owner"])
        if benchmark:
            assert "--auto-weights" in benchmark
            assert "--ema" not in benchmark


def test_stage_iters_none_uses_train_default() -> None:
    config = {
        "train": {"iters": 40_000},
        "stages": [
            {"name": "cityscapes", "iters": None},
            {"name": "railsem19", "iters": 20_000},
        ],
    }
    assert campaign._iteration_plan(config)["total_target_iterations"] == 60_000
    assert campaign._expected_final_step(config, "cityscapes") == 40_000
    assert campaign._expected_final_step(config, "railsem19") == 20_000


def test_iteration_plan_preserves_legacy_inherited_head_group_scale() -> None:
    config = {
        "train": {"iters": 40_000},
        "stages": [{"name": "railsem19", "iters": 20_000, "lr_scale": 0.1}],
    }

    assert campaign._iteration_plan(config)["stages"] == [
        {
            "stage": "railsem19",
            "target_iterations": 20_000,
            "learning_rate_scale": pytest.approx(0.1),
            "head_group_learning_rate_scale": pytest.approx(0.1),
        }
    ]


def test_worker_refuses_to_run_outside_tmux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    with pytest.raises(campaign.CampaignError, match="inside a named tmux session"):
        campaign.run_worker(tmp_path, "gpu0")


def test_reused_performance_failure_retries_same_attempt_without_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    lane = record["lanes"][0]
    source = next(job for job in record["jobs"] if job["lane"] == lane["id"])
    source["performance_owner"] = True
    lane["job_ids"] = [source["id"]]
    record["lanes"] = [lane]
    root = Path(record["campaign"])
    root.mkdir(parents=True)
    campaign.atomic_write_json(root / "campaign.json", record)
    status = campaign._lane_status(record, lane)
    job = status["jobs"][0]
    job.update(
        {
            "status": "reused",
            "attempts": [
                {
                    "number": 0,
                    "kind": "reused",
                    "status": "reused",
                    "paths": {},
                    "failure": None,
                }
            ],
        }
    )
    campaign.atomic_write_json(campaign._status_path(root, lane["id"]), status)
    monkeypatch.setenv("TMUX", "/tmp/tmux")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", str(lane["gpu"]))
    monkeypatch.setattr(campaign, "check_source_provenance", lambda _sha: SHA)
    monkeypatch.setattr(campaign, "validate_reused", lambda *_args: {})
    calls = {"count": 0}

    def backfill(*_args):
        calls["count"] += 1
        if calls["count"] == 1:
            raise campaign.CampaignError("benchmark failed once")

    monkeypatch.setattr(campaign, "_run_reused_performance", backfill)
    monkeypatch.setattr(
        campaign, "run_logged", lambda *_args: pytest.fail("training/eval must not run")
    )

    assert campaign.run_worker(root, lane["id"]) == 1
    assert campaign.run_worker(root, lane["id"]) == 0
    final = json.loads(campaign._status_path(root, lane["id"]).read_text())
    assert len(final["jobs"][0]["attempts"]) == 1
    assert final["jobs"][0]["attempts"][0]["number"] == 0
    assert final["jobs"][0]["status"] == "reused"


def test_interrupted_training_resumes_same_attempt_from_latest_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    lane = record["lanes"][0]
    source = next(job for job in record["jobs"] if job["lane"] == lane["id"])
    lane["job_ids"] = [source["id"]]
    record["lanes"] = [lane]
    root = Path(record["campaign"])
    root.mkdir(parents=True)
    campaign.atomic_write_json(root / "campaign.json", record)
    status = campaign._lane_status(record, lane)
    job = status["jobs"][0]
    attempt_dir = root / "jobs" / job["id"] / "attempt-001"
    _, config = campaign._resolved_config(record, job, attempt_dir)
    paths = campaign._attempt_paths(job, attempt_dir, config)
    paths["config"].parent.mkdir(parents=True)
    paths["config"].write_text(yaml.safe_dump(config))
    checkpoint = paths["run_dir"] / job["final_stage"] / "step-00004000.ckpt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"resume checkpoint")
    train, evaluate, benchmark = campaign._commands(record, job, paths)
    attempt = campaign._attempt_record(
        1,
        paths,
        train,
        evaluate,
        benchmark,
        campaign._job_environment(record, job, lane),
    )
    attempt["status"] = job["status"] = "training"
    job["attempts"] = [attempt]
    campaign.atomic_write_json(campaign._status_path(root, lane["id"]), status)

    monkeypatch.setenv("TMUX", "/tmp/tmux")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", str(lane["gpu"]))
    monkeypatch.setattr(campaign, "check_source_provenance", lambda _sha: SHA)
    digest = "d" * 64
    monkeypatch.setattr(
        campaign,
        "_latest_resume_checkpoint",
        lambda *_args: (checkpoint, 4_000, digest),
    )
    commands: list[list[str]] = []

    def fail_after_capture(command, *_args):
        commands.append(list(command))
        return 1

    monkeypatch.setattr(campaign, "run_logged", fail_after_capture)

    assert campaign.run_worker(root, lane["id"]) == 1
    final = json.loads(campaign._status_path(root, lane["id"]).read_text())
    final_job = final["jobs"][0]
    assert len(final_job["attempts"]) == 1
    assert commands[0][-2:] == ["--resume-checkpoint", str(checkpoint)]
    expected_commands = campaign._commands(record, source, paths, resume_checkpoint=checkpoint)
    assert final_job["attempts"][0]["train_command"] == expected_commands[0]
    assert final_job["attempts"][0]["eval_command"] == expected_commands[1]
    assert final_job["attempts"][0]["performance_command"] == expected_commands[2]
    assert final_job["attempts"][0]["resume"] == {
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": digest,
        "global_step": 4_000,
        "resumed_at": final_job["attempts"][0]["resumes"][0]["resumed_at"],
    }


def test_source_migration_requires_stopped_sessions_and_preserves_resume_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    lane = record["lanes"][0]
    source = next(job for job in record["jobs"] if job["lane"] == lane["id"])
    lane["job_ids"] = [source["id"]]
    record["lanes"] = [lane]
    root = Path(record["campaign"])
    root.mkdir(parents=True)
    campaign.atomic_write_json(root / "campaign.json", record)
    status = campaign._lane_status(record, lane)
    job = status["jobs"][0]
    attempt_dir = root / "jobs" / job["id"] / "attempt-001"
    _, config = campaign._resolved_config(record, job, attempt_dir)
    paths = campaign._attempt_paths(job, attempt_dir, config)
    paths["config"].parent.mkdir(parents=True)
    paths["config"].write_text(yaml.safe_dump(config))
    checkpoint = paths["run_dir"] / job["final_stage"] / "step-00004000.ckpt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"full resume state")
    train, evaluate, benchmark = campaign._commands(record, job, paths)
    attempt = campaign._attempt_record(
        1,
        paths,
        train,
        evaluate,
        benchmark,
        campaign._job_environment(record, job, lane),
    )
    attempt["status"] = job["status"] = "training"
    job["attempts"] = [attempt]
    campaign.atomic_write_json(campaign._status_path(root, lane["id"]), status)

    monkeypatch.setenv("TMUX", "/tmp/tmux")
    monkeypatch.setattr(campaign, "check_source_provenance", lambda sha: sha)
    monkeypatch.setattr(
        campaign.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(
        campaign,
        "_latest_resume_checkpoint",
        lambda *_args: (checkpoint, 4_000, "d" * 64),
    )
    monkeypatch.setattr(campaign, "_tmux_exists", lambda _session: True)
    with pytest.raises(campaign.CampaignError, match="stop every managed tmux"):
        campaign.migrate_campaign_source(
            root,
            from_sha=SHA,
            to_sha=NEW_SHA,
            reason="training-safe classifier handoff fix",
        )
    assert json.loads((root / "campaign.json").read_text())["source"]["expected_git_sha"] == SHA

    monkeypatch.setattr(campaign, "_tmux_exists", lambda _session: False)
    migration = campaign.migrate_campaign_source(
        root,
        from_sha=SHA,
        to_sha=NEW_SHA,
        reason="training-safe classifier handoff fix",
    )

    assert migration["resume_checkpoints"] == [
        {
            "lane": lane["id"],
            "job_id": job["id"],
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": "d" * 64,
            "global_step": 4_000,
        }
    ]
    migrated_record = json.loads((root / "campaign.json").read_text())
    migrated_status = json.loads(campaign._status_path(root, lane["id"]).read_text())
    assert migrated_record["source"]["expected_git_sha"] == NEW_SHA
    assert migrated_record["reuse_policy"]["allowed_git_shas"] == [SHA, NEW_SHA]
    assert migrated_record["source_migrations"][-1] == migration
    assert migrated_status["expected_git_sha"] == NEW_SHA
    assert migrated_status["source_migrations"][-1] == migration


def test_dry_run_prints_named_tmux_sessions_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    record = _record(tmp_path, monkeypatch)
    assert campaign.launch_campaign(record, dry_run=True) == 0
    shown = capsys.readouterr().out
    assert "108 jobs" in shown
    assert "segmentary-test-gpu0" in shown
    assert "CUDA_VISIBLE_DEVICES=0" in shown
    assert not Path(record["campaign"]).exists()


def test_prepare_only_persists_without_starting_tmux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    record["reuse"] = {
        "accepted": [],
        "accepted_cells": 0,
        "queued_cells": record["physical_job_count"],
    }
    calls = []
    monkeypatch.setattr(campaign.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    assert campaign.launch_campaign(record, dry_run=False, prepare_only=True) == 0
    root = Path(record["campaign"])
    assert (root / "campaign.json").is_file()
    assert len(list(root.glob("lane_*_status.json"))) == len(record["lanes"])
    assert not calls


def test_publisher_does_not_create_empty_public_results_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    publisher_root = tmp_path / "publisher"
    publisher_root.mkdir()
    record["publisher"] = {
        "worktree": str(publisher_root),
        "remote": "origin",
        "branch": "main",
    }
    monkeypatch.setattr(campaign, "_git_status_porcelain", lambda _root: "")
    monkeypatch.setattr(campaign, "_run_checked", lambda *args, **kwargs: SHA)
    monkeypatch.setattr(
        campaign.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(
        campaign,
        "report_campaign",
        lambda *args, **kwargs: pytest.fail("zero-cell snapshot must not render"),
    )

    assert campaign._publish_snapshot(record, tmp_path / "campaign", 0) is None


def test_prepared_campaign_rejects_option_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    changed = json.loads(json.dumps(record))
    changed["execution"]["gpus"] = [9]
    with pytest.raises(campaign.CampaignError, match="launch options differ"):
        campaign.validate_prepared_request(record, changed)


def test_reporting_complete_result_without_checkpoint_is_reused_and_not_queued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    job = next(
        item
        for item in record["jobs"]
        if item["model"] == "segformer_b2" and item["protocol"] == "railsem19"
    )
    _, resolved = campaign._resolved_config(record, job, tmp_path / "prototype")
    reuse_root = tmp_path / "prior"
    result_path = reuse_root / "segformer_b2" / "railsem19" / "results.json"
    write_results(
        result_path,
        RunRecord(
            name="rs_only",
            stage="railsem19",
            config_hash=config_hash(resolved),
            git_sha=SHA,
            git_dirty=False,
            seed=0,
            finished_at="2026-08-13T00:00:00+00:00",
            wall_clock_s=1.0,
            metrics=_metric_payload("rail_union"),
            config=resolved,
            env={"gpu_count": 1},
        ),
    )
    record["reuse_policy"]["roots"] = [str(reuse_root)]

    audit = campaign.scan_reusable_cells(record)

    assert audit["accepted_cells"] == 1
    assert audit["queued_cells"] == 107
    accepted = audit["accepted"][0]
    assert accepted["job_id"] == job["id"]
    assert accepted["checkpoint_available"] is False
    assert accepted["checkpoint"] is None
    assert "not retrained" in accepted["caveat"]


def test_reused_evaluation_preserves_matching_training_resource_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    job = next(
        item
        for item in record["jobs"]
        if item["model"] == "segformer_b2" and item["protocol"] == "cityscapes"
    )
    _, resolved = campaign._resolved_config(record, job, tmp_path / "prototype")
    reuse_root = tmp_path / "prior"
    run_root = reuse_root / "jobs" / job["id"]
    checkpoint = run_root / "train" / job["experiment_name"] / "cityscapes" / "last.ckpt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(checkpoint, "w") as archive:
        archive.writestr("archive/data.pkl", pickle.dumps({"global_step": 40_000}))
    training_result = checkpoint.parent / "results.json"
    write_results(
        training_result,
        RunRecord(
            name=job["experiment_name"],
            stage="cityscapes",
            config_hash=config_hash(resolved),
            git_sha=SHA,
            git_dirty=False,
            seed=0,
            finished_at="2026-08-13T00:00:00+00:00",
            wall_clock_s=123.0,
            metrics=_metric_payload("cityscapes19"),
            config=resolved,
            env={"gpu_count": 1},
            peak_vram_bytes={"cuda:0": 987_654_321},
        ),
    )
    evaluation_result = run_root / "evaluation" / "cityscapes" / "results.json"
    write_results(
        evaluation_result,
        RunRecord(
            name=job["experiment_name"],
            stage="eval:cityscapes:val",
            config_hash=config_hash(resolved),
            git_sha=SHA,
            git_dirty=False,
            seed=0,
            finished_at="2026-08-13T00:01:00+00:00",
            wall_clock_s=5.0,
            metrics=_metric_payload("cityscapes19"),
            config=resolved,
            dataset_sizes={"eval": 500},
            env={"gpu_count": 1},
            notes=f"checkpoint={checkpoint} ema=True tta=False",
        ),
    )
    record["reuse_policy"]["roots"] = [str(reuse_root)]

    audit = campaign.scan_reusable_cells(record)
    accepted = next(item for item in audit["accepted"] if item["job_id"] == job["id"])
    assert accepted["source_result"] == str(evaluation_result)
    assert accepted["training_source_result"] == str(training_result)
    assert accepted["training_result_sha256"] == campaign._sha256(training_result)

    record["reuse"] = audit
    campaign._materialize_reused_results(record, Path(record["campaign"]))
    lane = next(item for item in record["lanes"] if job["id"] in item["job_ids"])
    reused = next(
        item for item in campaign._lane_status(record, lane)["jobs"] if item["id"] == job["id"]
    )
    attempt = reused["attempts"][0]
    result = campaign.validate_reused(record, job, attempt)
    individual = campaign._normalised_individual(job, result, attempt)
    assert individual["source"]["training_stages"] == [
        {
            "stage": "cityscapes",
            "wall_clock_s": 123.0,
            "gpu_count": 1,
            "gpu_hours": pytest.approx(123.0 / 3600),
            "peak_vram_bytes_per_device": 987_654_321,
            "result_sha256": campaign._sha256(training_result),
        }
    ]


def test_reporting_only_city_source_stays_queued_when_transfer_needs_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    job = next(
        item
        for item in record["jobs"]
        if item["model"] == "segformer_b2" and item["protocol"] == "cityscapes"
    )
    _, resolved = campaign._resolved_config(record, job, tmp_path / "prototype")
    reuse_root = tmp_path / "prior"
    result_path = reuse_root / "segformer_b2" / "cityscapes" / "results.json"
    write_results(
        result_path,
        RunRecord(
            name="reference_cityscapes19",
            stage="cityscapes",
            config_hash=config_hash(resolved),
            git_sha=SHA,
            git_dirty=False,
            seed=0,
            finished_at="2026-08-13T00:00:00+00:00",
            wall_clock_s=1.0,
            metrics=_metric_payload("cityscapes19"),
            config=resolved,
            env={"gpu_count": 1},
        ),
    )
    record["reuse_policy"]["roots"] = [str(reuse_root)]

    audit = campaign.scan_reusable_cells(record)

    assert audit["accepted_cells"] == 0
    assert audit["queued_cells"] == 108
    assert audit["counts"]["dependency_source_without_checkpoint"] == 1
    assert "source training remains queued" in audit["rejected_examples"][-1]["reason"]


def test_resumed_training_segment_is_not_aggregated_as_whole_run_cost() -> None:
    partial_stage = {
        "stage": "railsem19",
        "wall_clock_s": 120.0,
        "gpu_count": 1,
        "gpu_hours": 120.0 / 3600,
        "peak_vram_bytes_per_device": 123,
        "result_sha256": "result",
        "timing_scope": "post_resume_segment_only",
        "resume_checkpoint_steps": [32_000],
    }
    evidence = campaign._protocol_resource_evidence(
        [
            {
                "source": {
                    "checkpoint_size_bytes": 456,
                    "training_stages": [partial_stage],
                    "full_validation_pipeline": None,
                }
            }
        ],
        parameter_count=789,
    )

    training = evidence["training"]
    assert training["wall_clock_s_mean"] is None
    assert training["gpu_hours_mean"] is None
    assert training["peak_vram_bytes_per_device"] is None
    assert training["total_timing_status"] == "not_retained_due_to_resume"
    assert training["post_resume_segments"][0]["stages"] == [partial_stage]
    assert "post_resume_segment_only" not in training


def test_reuse_scan_accepts_exact_20k_transfer_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path, monkeypatch)
    job = next(
        item
        for item in record["jobs"]
        if item["model"] == "segformer_b2" and item["protocol"] == "cityscapes_to_railsem19"
    )
    _, resolved = campaign._resolved_config(record, job, tmp_path / "prototype")
    reuse_root = tmp_path / "prior"
    stage_root = reuse_root / "jobs" / job["id"] / "railsem19"
    final_checkpoint = stage_root / "last.ckpt"
    final_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(final_checkpoint, "w") as archive:
        archive.writestr("archive/data.pkl", pickle.dumps({"global_step": 20_000}))

    evaluation_root = reuse_root / "jobs" / job["id"] / "evaluation"
    final_result = evaluation_root / "railsem19" / "results.json"
    write_results(
        final_result,
        RunRecord(
            name=job["experiment_name"],
            stage="eval:railsem19:val",
            config_hash=config_hash(resolved),
            git_sha=SHA,
            git_dirty=False,
            seed=0,
            finished_at="2026-08-15T00:00:00+00:00",
            wall_clock_s=1.0,
            metrics=_metric_payload("rail_union"),
            config=resolved,
            env={"gpu_count": 1},
            notes=f"checkpoint={final_checkpoint} ema=True tta=False",
        ),
    )
    record["reuse_policy"]["roots"] = [str(reuse_root)]

    audit = campaign.scan_reusable_cells(record)

    accepted = next(item for item in audit["accepted"] if item["job_id"] == job["id"])
    assert accepted["checkpoint"] == str(final_checkpoint)
    assert accepted["checkpoint_step"] == 20_000
    assert accepted["milestones"] == {}

    final_result.unlink()
    missing = campaign.scan_reusable_cells(record)
    assert all(item["job_id"] != job["id"] for item in missing["accepted"])


def test_lane_status_json_is_strict_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = _record(tmp_path, monkeypatch)
    lane = record["lanes"][0]
    status = campaign._lane_status(record, lane)
    path = tmp_path / "status.json"
    campaign.atomic_write_json(path, status)
    assert json.loads(path.read_text())["tmux_session"] == "segmentary-test-gpu0"


def test_worker_tmux_pane_is_live_and_also_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(tmp_path, monkeypatch)
    lane = record["lanes"][0]
    shell = campaign._tmux_shell_command(tmp_path / "campaign", lane, record["execution"])
    assert shell.startswith("set -o pipefail; ")
    assert " 2>&1 | tee -a " in shell
    assert "lane_gpu0.console.log" in shell
    assert ">>" not in shell


def test_comparison_records_start_empty_without_completed_cells(tmp_path: Path) -> None:
    records = campaign._comparison_records(
        tmp_path,
        campaign.load_campaign_manifest(),
        {},
        {},
    )
    assert records == {}


def test_existing_obsolete_transfer_evidence_is_removed(tmp_path: Path) -> None:
    existing = {
        "schema_version": 2,
        "model_id": "segformer_b2",
        "model_config": "configs/models/segformer_b2.yaml",
        "protocols": {"cityscapes_to_railsem19": {"obsolete": True}},
        "historical_protocols": {"old_transfer": {"obsolete": True}},
        "model_profile": {},
    }
    destination = tmp_path / "docs/results/model-comparison/records/segformer_b2.json"
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(existing), encoding="utf-8")

    records = campaign._comparison_records(
        tmp_path,
        campaign.load_campaign_manifest(),
        {},
        {},
    )

    migrated = records["segformer_b2"]
    assert "cityscapes_to_railsem19" not in migrated["protocols"]
    assert "historical_protocols" not in migrated


def test_trusted_weight_source_correction_is_narrow_and_provenance_identical() -> None:
    source = {
        "result_sha256": "old-result",
        "git_sha": "a" * 40,
        "checkpoint_sha256": "checkpoint",
        "checkpoint_step": 40_000,
    }
    candidate_source = {**source, "result_sha256": "new-result"}
    protocol = {"evaluation": {"weights": "EMA"}}
    existing = {"source": source}
    candidate = {"source": candidate_source}
    result = {"config": {"evaluation": {"weights": "raw"}}}
    attempt = {
        "kind": "reused",
        "record_kind": "evaluation",
        "caveat": "Standalone raw-weight validation evidence is retained.",
    }

    assert campaign._is_trusted_weight_source_correction(
        protocol, existing, candidate, result, attempt
    )

    mutations = [
        ({"evaluation": {"weights": "raw"}}, existing, candidate, result, attempt),
        (protocol, existing, candidate, {"config": {"evaluation": {"weights": "ema"}}}, attempt),
        (protocol, existing, candidate, result, {**attempt, "caveat": "ordinary reuse"}),
        (
            protocol,
            existing,
            {"source": {**candidate_source, "checkpoint_sha256": "different"}},
            result,
            attempt,
        ),
    ]
    for arguments in mutations:
        assert not campaign._is_trusted_weight_source_correction(*arguments)


def test_trusted_bn_recalibration_requires_explicit_zero_parameter_provenance() -> None:
    existing_source = {
        "result_sha256": "old-result",
        "git_sha": "a" * 40,
        "checkpoint_sha256": "old-checkpoint",
        "checkpoint_step": 40_000,
    }
    candidate_source = {
        **existing_source,
        "result_sha256": "new-result",
        "checkpoint_sha256": "new-checkpoint",
    }
    existing = {"metrics": {"miou": 0.31}, "source": existing_source}
    candidate = {"metrics": {"miou": 0.67}, "source": candidate_source}
    result = {"config": {"evaluation": {"weights": "raw"}}}
    correction = {
        "kind": "batchnorm_running_statistics_recalibration",
        "parameters_changed": 0,
        "bn_modules": 55,
        "recalibration_batches": 371,
        "recalibration_images": 2968,
        "source_checkpoint_sha256": "old-checkpoint",
        "corrected_checkpoint_sha256": "new-checkpoint",
        "source_result_sha256": "old-result",
        "corrected_result_sha256": "new-result",
        "old_miou": 0.31,
        "corrected_miou": 0.67,
    }
    attempt = {
        "evaluation_correction": correction,
        "sha256": {
            "checkpoint": "new-checkpoint",
            "common_results": "new-result",
        },
    }

    assert campaign._is_trusted_bn_recalibration_correction(existing, candidate, result, attempt)

    mutations = [
        {**correction, "parameters_changed": 1},
        {**correction, "recalibration_images": 0},
        {**correction, "source_checkpoint_sha256": "wrong"},
        {**correction, "corrected_checkpoint_sha256": "wrong"},
        {**correction, "source_result_sha256": "wrong"},
        {**correction, "corrected_result_sha256": "wrong"},
        {**correction, "corrected_miou": 0.66},
    ]
    for changed in mutations:
        assert not campaign._is_trusted_bn_recalibration_correction(
            existing,
            candidate,
            result,
            {**attempt, "evaluation_correction": changed},
        )
    assert not campaign._is_trusted_bn_recalibration_correction(
        existing,
        candidate,
        {"config": {"evaluation": {"weights": "ema"}}},
        attempt,
    )


def test_training_specifications_match_resolved_campaign_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(tmp_path, monkeypatch)
    manifest = campaign.load_campaign_manifest()

    specifications = campaign._model_training_specifications(manifest, record)

    default = specifications["segformer_b2"]
    assert default == {
        **default,
        "gpu_count": 1,
        "crop_height": 1024,
        "crop_width": 1024,
        "batch_size_per_gpu": 2,
        "gradient_accumulation": 8,
        "effective_batch_size": 16,
        "precision": "bf16-mixed",
        "optimizer": "AdamW",
        "backbone_lr": pytest.approx(6e-5),
        "fresh_component_lr": pytest.approx(6e-4),
        "head_lr_multiplier": pytest.approx(10.0),
        "weight_decay": pytest.approx(0.05),
        "llrd": pytest.approx(1.0),
        "warmup_iterations": 1_500,
        "warmup_ratio": pytest.approx(1e-6),
        "poly_power": pytest.approx(0.9),
        "gradient_clip": pytest.approx(1.0),
        "ema_decay": pytest.approx(0.9998),
        "validation_interval": 4_000,
        "checkpoint_interval": 4_000,
        "objective": "dense_semantic",
    }

    beit = specifications["hf_auto_beit_base_ade"]
    assert (beit["crop_height"], beit["crop_width"]) == (640, 640)
    assert beit["batch_size_per_gpu"] == 4
    assert beit["gradient_accumulation"] == 4
    assert beit["effective_batch_size"] == 16
    assert beit["backbone_lr"] == pytest.approx(2e-5)
    assert beit["llrd"] == pytest.approx(0.8)

    eomt = specifications["eomt_dinov3_large"]
    assert eomt["batch_size_per_gpu"] == 2
    assert eomt["gradient_accumulation"] == 8
    assert eomt["effective_batch_size"] == 16
    assert eomt["backbone_lr"] == pytest.approx(1e-5)
    assert eomt["llrd"] == pytest.approx(0.75)
    assert eomt["objective"] == "hungarian_query"

    assert specifications["deeplabv3plus_r101"] == specifications["smp_deeplabv3plus_resnet101"]


def test_training_specifications_are_rendered_in_readme_and_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(tmp_path, monkeypatch)
    manifest = campaign.load_campaign_manifest()
    monkeypatch.setattr(campaign, "_model_execution_states", lambda _record: {})

    status = campaign._comparison_status(manifest, {}, record)
    readme = campaign._central_readme(manifest, status, {}, SHA)
    rows = list(csv.DictReader(io.StringIO(campaign._comparison_csv(status, {}))))

    assert "## Training specification" in readme
    assert "batch/GPU" in readme
    assert "effective batch" in readme
    assert "CPU data-loader workers per job" in readme
    assert "raw for running-stat BatchNorm; EMA otherwise" in readme
    assert "| model | weights | parameters" in readme
    assert "Quality evaluation: EMA" not in readme
    assert "Primary quality evaluation: raw checkpoint weights for every protocol" in readme
    assert "paper-primary raw checkpoint weights for every model" in readme
    assert "automatic recorded weights" not in readme
    assert "[`RAW_VS_EMA.md`](RAW_VS_EMA.md)" in readme
    assert "FPS can remain pending while Cityscapes mIoU is already available" in readme
    assert "City → Rail mIoU (Rail20 / total60)" in readme
    assert "Rail40" not in readme
    assert "historical" not in readme.lower()
    assert "corrected" not in readme.lower()
    assert "±" not in readme
    assert "## RailSem19 accuracy-speed leaderboard" in readme
    leaderboard = readme.split("## RailSem19 accuracy-speed leaderboard", maxsplit=1)[1]
    assert "| rank | model | status | quality gate | recommendation score |" in leaderboard
    assert leaderboard.count("| — | [") == status["scope"]["model_recipes"]
    assert "| pending |" in leaderboard

    by_model = {row["model"]: row for row in rows}
    beit = by_model["hf_auto_beit_base_ade"]
    assert beit["training_crop_height"] == "640"
    assert beit["training_batch_size_per_gpu"] == "4"
    assert beit["training_gradient_accumulation"] == "4"
    assert beit["training_effective_batch_size"] == "16"
    assert beit["training_backbone_lr"] == "2e-05"
    assert beit["training_objective"] == "dense_semantic"
    assert (
        beit["cityscapes_to_railsem19_training_cost_scope"]
        == "Rail20 adaptation; City40 warm-start provenance not retained"
    )
    assert beit["cityscapes_to_railsem19_cumulative_iterations"] == ""

    eomt = by_model["eomt_dinov3_large"]
    assert eomt["training_batch_size_per_gpu"] == "2"
    assert eomt["training_gradient_accumulation"] == "8"
    assert eomt["training_effective_batch_size"] == "16"
    assert eomt["training_objective"] == "hungarian_query"


def test_rail_accuracy_speed_leaderboard_is_accuracy_gated_and_includes_aliases() -> None:
    manifest = campaign.load_campaign_manifest()

    def record(miou: float, fps: float) -> dict[str, object]:
        return {
            "protocols": {
                "railsem19": {"aggregate": {"miou": {"mean": miou}}},
            },
            "model_profile": {
                "standardized_inference": {
                    "status": "complete",
                    "fps": fps,
                    "latency_ms": {"p50": 10.0},
                    "provenance": {"weights": "ema"},
                }
            },
        }

    records = {
        "eomt_dinov3_large": record(0.80, 20.0),
        "eomt_large": record(0.70, 100.0),
        "smp_deeplabv3plus_resnet101": record(0.60, 200.0),
        "smp_pspnet_mobilenet_v2": record(0.40, 1_000.0),
        "deeplabv3plus_r101": record(0.99, 999.0),
        "hf_auto_beit_base_ade": {
            "protocols": {"railsem19": {"aggregate": {"miou": {"mean": 0.95}}}},
            "model_profile": {"standardized_inference": {"status": "pending"}},
        },
    }

    rows = campaign._rail_accuracy_speed_leaderboard(manifest, records)

    assert [row["model"] for row in rows[:4]] == [
        "eomt_dinov3_large",
        "eomt_large",
        "smp_deeplabv3plus_resnet101",
        "deeplabv3plus_r101",
    ]
    assert len(rows) == len(manifest.models)
    assert all(row["status"] == "complete" for row in rows[:4])
    assert all(
        rows[index]["recommendation_score"] >= rows[index + 1]["recommendation_score"]
        for index in range(3)
    )
    bad_but_fast = next(row for row in rows if row["model"] == "smp_pspnet_mobilenet_v2")
    assert bad_but_fast["quality_gate"] == "below 60% mIoU"
    assert "recommendation_score" not in bad_but_fast
    assert bad_but_fast["speed_rank"] == 1
    assert rows.index(bad_but_fast) > 3
    assert all(
        row["status"] == "pending"
        for row in rows
        if row["model"]
        not in {
            "eomt_dinov3_large",
            "eomt_large",
            "smp_deeplabv3plus_resnet101",
            "deeplabv3plus_r101",
            "smp_pspnet_mobilenet_v2",
        }
    )
    alias = next(row for row in rows if row["model"] == "deeplabv3plus_r101")
    assert alias["alias_of"] == "smp_deeplabv3plus_resnet101"
    assert alias["miou"] == pytest.approx(0.60)
    assert alias["fps"] == pytest.approx(200.0)
    assert alias["accuracy_rank"] == next(
        row["accuracy_rank"] for row in rows if row["model"] == "smp_deeplabv3plus_resnet101"
    )


def test_transfer_reporting_accepts_only_verified_20k_final() -> None:
    aggregate = {key: {"mean": 0.5} for key, _ in campaign.RECORD_METRICS}
    aggregate["miou"] = {"mean": 0.66}
    aggregate["boundary_macro_f1"] = {"mean": 0.72}
    aggregate["per_class_iou"] = {}
    progress_20k = {
        "target_iterations": 20_000,
        "current_iterations": 20_000,
        "stages": [],
        "final_verification": {
            "result_verified": True,
            "result_total_iterations": 20_000,
            "result_final_stage_iteration": 20_000,
            "checkpoint_available": True,
            "checkpoint_verified": True,
            "checkpoint_global_step": 20_000,
        },
    }
    transfer_20k = {
        "aggregate": aggregate,
        "iteration_progress": progress_20k,
        "milestones": {},
        "seed_count": 1,
        "seeds": [0],
        "resource_evidence": {
            "training": {
                "wall_clock_s_mean": 3_600,
                "gpu_hours_mean": 1.0,
                "peak_vram_bytes_per_device": 1_073_741_824,
            },
            "full_validation_pipeline": {"images_per_s_mean": 2.0},
        },
        "evaluation": {"weights": "ema"},
        "individual": [{"source": {"git_sha": SHA}}],
    }
    record = {
        "model_id": "probe",
        "model_config": "configs/models/probe.yaml",
        "protocols": {"cityscapes_to_railsem19": transfer_20k},
        "model_profile": {},
    }

    assert campaign._transfer_final(record)["aggregate"]["miou"]["mean"] == pytest.approx(0.66)

    empty = {
        protocol: campaign._empty_progress(protocol) for protocol in campaign.REQUIRED_PROTOCOLS
    }
    row = {
        "priority": 1,
        "model": "probe",
        "status": "running",
        "iteration_progress": empty,
        "standardized_inference": {"status": "pending"},
        "training_specification": {},
    }
    csv_row = next(
        csv.DictReader(io.StringIO(campaign._comparison_csv({"models": [row]}, {"probe": record})))
    )
    assert csv_row["cityscapes_to_railsem19_miou_mean"] == "0.66"
    assert csv_row["cityscapes_to_railsem19_iterations_target"] == "20000"

    generated = campaign._model_generated_section(record)
    assert "| Cityscapes → RailSem19 | 20,000 / 20,000 | 66.00 |" in generated
    assert "historical" not in generated.lower()
    assert "corrected" not in generated.lower()
    assert "40,000 / 40,000 | 66.00" not in generated

    complete_shape_only = copy.deepcopy(record)
    complete_shape_only["protocols"].update({"cityscapes": {}, "railsem19": {}})
    assert campaign._model_record_status(complete_shape_only) == "complete"

    for field, value in (
        ("current_iterations", 19_999),
        ("target_iterations", 40_000),
    ):
        invalid = copy.deepcopy(record)
        invalid["protocols"]["cityscapes_to_railsem19"]["iteration_progress"][field] = value
        assert campaign._transfer_final(invalid) == {}
    invalid = copy.deepcopy(record)
    invalid["protocols"]["cityscapes_to_railsem19"]["iteration_progress"]["final_verification"][
        "result_verified"
    ] = False
    assert campaign._transfer_final(invalid) == {}


def test_public_weight_source_rejects_legacy_unverified_ema_label() -> None:
    assert campaign._recorded_evaluation_weights({"evaluation": {"weights": "raw"}}) == "raw"
    assert campaign._recorded_evaluation_weights({"evaluation": {"weights": "ema"}}) == "ema"
    assert campaign._recorded_evaluation_weights({"evaluation": {"weights": "EMA"}}) is None
    assert campaign._recorded_evaluation_weights({"evaluation": {}}) is None


def test_legacy_confusion_derivation_uses_taxonomy_order() -> None:
    space = load_space(campaign.REPO_ROOT / "taxonomy", "rail_union")
    canonical_names = list(space.names)
    assert canonical_names != sorted(canonical_names)

    metrics = _metric_payload("rail_union")
    metrics.pop("mprecision")
    metrics.pop("mdice")
    metrics.pop("mspecificity")
    metrics["per_class_iou"] = {
        name: None if name in {"bicycle", "motorcycle"} else 0.5 for name in sorted(canonical_names)
    }
    size = len(canonical_names)
    metrics["confusion"] = [
        [10 + row if row == column else (row + column) % 3 for column in range(size)]
        for row in range(size)
    ]

    canonical = campaign._complete_metrics(metrics, canonical_names)
    alphabetic = campaign._complete_metrics(metrics, sorted(canonical_names))
    assert canonical["mprecision"] != alphabetic["mprecision"]
    assert canonical["mdice"] != alphabetic["mdice"]
    assert canonical["mspecificity"] != alphabetic["mspecificity"]


def test_public_privacy_check_rejects_server_identifiers(tmp_path: Path) -> None:
    for leaked in ("/data/private", "/scr/private", "/Users/name", "gpu_uuid"):
        with pytest.raises(campaign.CampaignError, match="private infrastructure"):
            campaign._public_privacy_check({tmp_path / "record.json": leaked})


def test_git_status_porcelain_preserves_first_status_column(tmp_path: Path) -> None:
    subprocess = campaign.subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    readme = tmp_path / "docs/catalog/models/example/README.md"
    readme.parent.mkdir(parents=True)
    readme.write_text("before\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=tmp_path, check=True)
    readme.write_text("after\n")

    changed = campaign._git_status_porcelain(tmp_path)
    assert changed == " M docs/catalog/models/example/README.md"
    assert changed.splitlines()[0][3:] == "docs/catalog/models/example/README.md"
