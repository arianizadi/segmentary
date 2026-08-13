"""Contracts for the resumable all-model benchmark campaign."""

from __future__ import annotations

import json
import pickle
import sys
import zipfile
from itertools import pairwise
from pathlib import Path

import pytest
from scripts import run_benchmark_campaign as campaign

from segmentary.config import config_hash
from segmentary.taxonomy import load_space
from segmentary.utils.results import RunRecord, write_results

SHA = "a" * 40


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

    assert campaign.compatibility_sha256(
        legacy, runtime_device_count=8
    ) == campaign.compatibility_sha256(current)


def test_checkpoint_global_step_is_read_without_unpickling(tmp_path: Path) -> None:
    checkpoint = tmp_path / "last.ckpt"
    with zipfile.ZipFile(checkpoint, "w") as archive:
        archive.writestr("archive/data.pkl", pickle.dumps({"global_step": 24_000}))
    assert campaign._checkpoint_global_step(checkpoint) == 24_000


def test_partition_is_complete_unique_and_one_physical_gpu_per_lane() -> None:
    manifest = campaign.load_campaign_manifest()
    jobs = campaign.campaign_jobs(manifest, (0,), include_aliases=False)
    lanes = campaign.partition_jobs(jobs, (0, 2, 4, 6))
    flattened = [job for lane in lanes.values() for job in lane]
    assert len(flattened) == len(jobs) == 108
    assert len({job.id for job in flattened}) == 108
    assert max(map(len, lanes.values())) - min(map(len, lanes.values())) <= 1
    assert set(campaign.MODEL_COST_WEIGHTS) == {job.model.id for job in jobs}
    loads = [
        sum(
            campaign.MODEL_COST_WEIGHTS[job.model.id]
            * (1.5 if job.protocol.id == "cityscapes_to_railsem19" else 1.0)
            for job in lane
        )
        for lane in lanes.values()
    ]
    assert max(loads) / min(loads) < 1.02
    assert all(
        all(
            campaign.MODEL_COST_WEIGHTS[left.model.id]
            * (1.5 if left.protocol.id == "cityscapes_to_railsem19" else 1.0)
            >= campaign.MODEL_COST_WEIGHTS[right.model.id]
            * (1.5 if right.protocol.id == "cityscapes_to_railsem19" else 1.0)
            for left, right in pairwise(lane)
        )
        for lane in lanes.values()
    )


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

    assert audit["accepted_cells"] == 1
    assert audit["queued_cells"] == 107
    accepted = audit["accepted"][0]
    assert accepted["job_id"] == job["id"]
    assert accepted["checkpoint_available"] is False
    assert accepted["checkpoint"] is None
    assert "not retrained" in accepted["caveat"]


def test_generated_model_section_supports_incremental_missing_protocols() -> None:
    record = json.loads(
        (campaign.REPO_ROOT / "docs/results/model-comparison/records/segformer_b2.json").read_text()
    )
    record["protocols"] = {"cityscapes": record["protocols"]["cityscapes"]}
    record["protocols"]["cityscapes"]["caveats"] = ["checkpoint unavailable; cell is not retrained"]
    section = campaign._model_generated_section(record)
    assert "| Cityscapes | 40,000 / 40,000 | 80.51" in section
    assert "| RailSem19 | 0 / 40,000 | —" in section
    assert "checkpoint unavailable" in section


def test_lane_status_json_is_strict_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = _record(tmp_path, monkeypatch)
    lane = record["lanes"][0]
    status = campaign._lane_status(record, lane)
    path = tmp_path / "status.json"
    campaign.atomic_write_json(path, status)
    assert json.loads(path.read_text())["tmux_session"] == "segmentary-test-gpu0"


def test_preservation_merge_keeps_public_b2_record_exactly() -> None:
    path = campaign.REPO_ROOT / "docs/results/model-comparison/records/segformer_b2.json"
    before = json.loads(path.read_text())
    records = campaign._comparison_records(
        campaign.REPO_ROOT,
        campaign.load_campaign_manifest(),
        {},
        {},
    )
    assert records["segformer_b2"] == before
    assert records["segformer_b2"]["protocols"]["railsem19"]["seeds"] == [0, 1, 2]
    assert records["segformer_b2"]["protocols"]["cityscapes_to_railsem19"]["seeds"] == [
        0,
        1,
        2,
    ]


def test_public_privacy_check_rejects_server_identifiers(tmp_path: Path) -> None:
    for leaked in ("/data/private", "/scr/private", "/Users/name", "gpu_uuid"):
        with pytest.raises(campaign.CampaignError, match="private infrastructure"):
            campaign._public_privacy_check({tmp_path / "record.json": leaked})
