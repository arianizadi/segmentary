"""Opt-in RAD launch gates fail closed before GPU access; all hardware is mocked."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from scripts import plan_rtis_campaign as planner
from scripts import run_rtis_campaign as runtime

from helpers_gpu_policy import make_policy, patch_live, pinned_env, uuid_of, write_campaign
from segmentary import gpu_policy
from segmentary import launch_requirements as guards

ALLOWED = [0, 1, 2, 3, 7, 8, 9]


def test_absent_opt_in_preserves_legacy_plan_behavior():
    assert guards.requirements_from_spec({}) is None
    assert guards.validate_plan({"gpu_allowlist": [4], "jobs": []}) is None


@pytest.mark.parametrize(
    "requirements",
    [
        {},
        {"unknown_guard": True},
        {"require_queue_priority": "true"},
        {"expected_gpu_allowlist": [0, 0]},
        {"expected_gpu_allowlist": [1, 0]},
        {"expected_gpu_allowlist": [True]},
        {"shared_gpu_lock_and_idle": 1},
    ],
)
def test_rejects_malformed_opt_in(requirements):
    with pytest.raises(ValueError):
        guards.requirements_from_spec({"launch_requirements": requirements})


def prioritized_plan(tmp_path):
    job = {
        "name": "model--rtis_only--seed-0",
        "model": "model",
        "protocol": "rtis_only",
        "queue_priority": 1,
    }
    source = {"source_csv_sha256": "c" * 64, "jobs": [{"model": "model", "protocol": "rtis_only"}]}
    path = tmp_path / "priority.json"
    path.write_text(json.dumps(source))
    return {
        "gpu_allowlist": ALLOWED,
        "launch_requirements": {
            "expected_gpu_allowlist": ALLOWED,
            "require_queue_priority": True,
            "shared_gpu_lock_and_idle": True,
        },
        "queue_priority_provenance": {
            "source_priority_file": str(path),
            "source_priority_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_csv_sha256": source["source_csv_sha256"],
            "jobs": 1,
            "models": ["model"],
        },
        "jobs": [job],
    }


def test_queue_guard_requires_actual_order_and_source_hash(tmp_path):
    plan = prioritized_plan(tmp_path)
    assert guards.validate_plan(plan)["require_queue_priority"] is True
    plan["jobs"][0]["queue_priority"] = 2
    with pytest.raises(ValueError, match="consecutive queue_priority"):
        guards.validate_plan(plan)
    plan["jobs"][0]["queue_priority"] = 1
    Path(plan["queue_priority_provenance"]["source_priority_file"]).write_text("changed")
    with pytest.raises(ValueError, match="source SHA-256 changed"):
        guards.validate_plan(plan)


def init_fixture(tmp_path, monkeypatch):
    plan = prioritized_plan(tmp_path)
    root = tmp_path / "campaign"
    root.mkdir()
    data = tmp_path / "data"
    (data / "audit").mkdir(parents=True)
    runtime.write(data / "audit/samples.json", [])
    runtime.write(
        data / "splits.json",
        {"train": ["a"], "val": ["b"], "test": ["c"], "_grouping_status": "provisional"},
    )
    cfg = tmp_path / "config.yaml"
    cfg.write_text("frozen")
    plan.update(
        dataset="new-rad",
        split_sha256=runtime.digest(data / "splits.json"),
        grouping_status="provisional",
        target_steps_per_job=4000,
        primary_checkpoint="final",
    )
    plan["jobs"][0].update(
        config=str(cfg), config_sha256=runtime.digest(cfg), source_checkpoint=None
    )
    runtime.write(root / "plan.json", plan)
    config = SimpleNamespace(
        stages=[SimpleNamespace(data=[SimpleNamespace(root=str(data))])],
        output_root=str(root / "future-runs"),
    )
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda layers: config)
    )
    monkeypatch.setattr(
        runtime, "git", lambda repo, *args: "code" if args[0] == "rev-parse" else ""
    )
    patch_live(monkeypatch)
    return root, plan


@pytest.mark.parametrize("change", ["missing_priority", "wrong_allowlist", "wrong_queue_number"])
def test_init_refuses_missing_guards_before_gpu_inventory(tmp_path, monkeypatch, change):
    root, plan = init_fixture(tmp_path, monkeypatch)
    if change == "missing_priority":
        del plan["queue_priority_provenance"]
    elif change == "wrong_allowlist":
        plan["gpu_allowlist"] = [2, 3, 4, 5, 6, 7, 8, 9]
    else:
        plan["jobs"][0]["queue_priority"] = 8
    runtime.write(root / "plan.json", plan)
    monkeypatch.setattr(
        gpu_policy, "inventory", lambda: pytest.fail("must refuse before GPU inventory")
    )
    with pytest.raises((ValueError, gpu_policy.GpuPolicyError)):
        runtime.initialize(root, tmp_path)
    assert not (root / "campaign.json").exists()
    assert not (root / "state").exists()


def test_opt_in_propagates_to_campaign_and_source_guard_runs_before_inventory(
    tmp_path, monkeypatch
):
    root, plan = init_fixture(tmp_path, monkeypatch)
    plan["launch_requirements"]["require_non_rad_sources"] = True
    plan["source_manifest"] = {"path": "/frozen/source.json", "sha256": "a" * 64}
    runtime.write(root / "plan.json", plan)
    events = []
    report = {"verified": True, "config_sha256": "b" * 64}
    monkeypatch.setattr(
        runtime, "verify_initializer_sources", lambda *a: (events.append("source-check"), report)[1]
    )
    original_inventory = gpu_policy.inventory
    monkeypatch.setattr(
        gpu_policy, "inventory", lambda: (events.append("inventory"), original_inventory())[1]
    )
    runtime.initialize(root, tmp_path)
    campaign = runtime.read(root / "campaign.json")
    assert events[0] == "source-check"
    assert campaign["launch_requirements"] == plan["launch_requirements"]
    assert campaign["source_manifest"] == plan["source_manifest"]
    assert campaign["initializer_verification"] == report
    monkeypatch.setattr(
        runtime,
        "verify_initializer_sources",
        lambda *a: {"verified": True, "config_sha256": "changed"},
    )
    monkeypatch.setattr(
        gpu_policy, "inventory", lambda: pytest.fail("changed sources must refuse before inventory")
    )
    with pytest.raises(RuntimeError, match="source configurations changed"):
        runtime.verify_frozen(root, tmp_path)


@pytest.mark.parametrize("opt_in", [False, True])
def test_planner_preserves_legacy_and_propagates_opt_in_only(tmp_path, monkeypatch, opt_in):
    root = tmp_path / "dataset"
    root.mkdir()
    runtime.write(root / "splits.json", {"_grouping_status": "draft"})
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(yaml.safe_dump({"models": [{"id": "model", "config": "unused.yaml"}]}))
    manifest = tmp_path / "manifest.yaml"
    spec = {
        "dataset": "new-rad",
        "dataset_config": "unused.yaml",
        "model_catalog": str(catalog),
        "primary_checkpoint": "final",
        "target_steps": 4000,
        "protocols": {"rtis_only": {"source_protocol": None}},
    }
    if opt_in:
        spec["launch_requirements"] = {
            "expected_gpu_allowlist": ALLOWED,
            "require_queue_priority": True,
            "shared_gpu_lock_and_idle": True,
            "require_non_rad_sources": True,
        }
    manifest.write_text(yaml.safe_dump(spec))
    sources = tmp_path / "sources.json"
    sources.write_text("[]")
    out = tmp_path / "new-plan"
    monkeypatch.setattr(planner, "build_jobs", lambda *a: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "planner",
            "--manifest",
            str(manifest),
            "--checkpoints",
            str(sources),
            "--dataset-root",
            str(root),
            "--out",
            str(out),
            "--gpus",
            ",".join(map(str, ALLOWED)),
        ],
    )
    planner.main()
    plan = runtime.read(out / "plan.json")
    assert ("launch_requirements" in plan) == opt_in
    assert ("source_manifest" in plan) == opt_in
    if opt_in:
        assert plan["launch_requirements"] == spec["launch_requirements"]
        assert plan["source_manifest"] == {
            "path": str(sources.resolve()),
            "sha256": runtime.digest(sources),
        }


@pytest.mark.parametrize(
    "apps,memory,util,expected",
    [
        ([], "0", "0", True),
        ([], "64", "0", True),
        ([], "65", "0", False),
        ([], "0", "1", False),
        ([(123, uuid_of(0))], "0", "0", False),
        ([(123, uuid_of(4))], "0", "0", True),
    ],
)
def test_idle_requires_no_compute_pid_memory_and_utilization(
    monkeypatch, apps, memory, util, expected
):
    policy = make_policy(ALLOWED)
    monkeypatch.setattr(gpu_policy, "compute_apps", lambda: apps)
    monkeypatch.setattr(
        guards.subprocess, "check_output", lambda *a, **kw: f"0, {uuid_of(0)}, {memory}, {util}\n"
    )
    assert guards.gpu_is_idle(policy, 0) is expected


@pytest.mark.parametrize(
    "telemetry",
    [
        "",
        "bad",
        f"0, {uuid_of(0)}, N/A, 0",
        f"0, {uuid_of(0)}, nan, 0",
        f"0, {uuid_of(0)}, 0, inf",
        f"0, {uuid_of(0)}, -1, 0",
    ],
)
def test_idle_never_guesses_when_telemetry_is_missing_or_invalid(monkeypatch, telemetry):
    monkeypatch.setattr(gpu_policy, "compute_apps", lambda: [])
    monkeypatch.setattr(guards.subprocess, "check_output", lambda *a, **kw: telemetry)
    with pytest.raises(gpu_policy.GpuInspectionError):
        guards.gpu_is_idle(make_policy(ALLOWED), 0)


def test_shared_lock_identities_match_other_launchers(monkeypatch):
    monkeypatch.setattr(guards.tempfile, "gettempdir", lambda: "/tmp")
    paths = guards.shared_lock_paths(7, uuid_of(7))
    assert paths == [
        Path("/data/izadia1/projects/segmentary-runs/.gpu-locks/gpu-7.lock"),
        Path("/tmp/segmentary-exclusive-gpu-7.lock"),
        Path(f"/tmp/segmentary-gpu-{uuid_of(7)}.lock"),
        Path(f"/tmp/segmentary-medical-{guards.os.getuid()}/gpu-7.lock"),
    ]


def test_busy_shared_lock_does_not_release_foreign_owner(tmp_path):
    path = tmp_path / "shared-gpu.lock"
    with guards.exclusive_locks([path]) as owner:
        assert owner
        with guards.exclusive_locks([path]) as blocked:
            assert not blocked
        with guards.exclusive_locks([path]) as still_blocked:
            assert not still_blocked
        assert path.exists()
    with guards.exclusive_locks([path]) as free:
        assert free
    assert path.exists()  # Lock files are never deleted as stale.


def worker_fixture(tmp_path, monkeypatch):
    campaign = write_campaign(
        tmp_path,
        allowed=ALLOWED,
        jobs=["first", "second"],
        launch_requirements={"shared_gpu_lock_and_idle": True},
    )
    monkeypatch.setattr(runtime, "verify_frozen", lambda *a: campaign)
    monkeypatch.setattr(runtime.os, "environ", pinned_env(0))
    shared = tmp_path / "host-shared.lock"
    monkeypatch.setattr(guards, "shared_lock_paths", lambda *a: [shared])
    return campaign, shared


def test_worker_rechecks_every_job_and_busy_gpu_never_fails_the_job(tmp_path, monkeypatch):
    _, shared = worker_fixture(tmp_path, monkeypatch)
    idle = iter([True, False])
    calls = []
    monkeypatch.setattr(guards, "gpu_is_idle", lambda *a: next(idle))

    def run(root, repo, job, gpu, campaign):
        calls.append(job["name"])
        with guards.exclusive_locks([shared]) as acquired:
            assert not acquired  # Host ownership lasts through the whole job.
        runtime.write(root / "state" / (job["name"] + ".json"), {"status": "completed"})

    runtime.worker(tmp_path, tmp_path, 0, run=run)
    assert calls == ["first"]
    assert runtime.read(tmp_path / "state/second.json") == {"name": "second", "status": "queued"}
    with guards.exclusive_locks([shared]) as acquired:
        assert acquired


def test_worker_shared_contention_leaves_all_jobs_unchanged(tmp_path, monkeypatch):
    _, shared = worker_fixture(tmp_path, monkeypatch)
    with guards.exclusive_locks([shared]):
        runtime.worker(
            tmp_path, tmp_path, 0, run=lambda *a: pytest.fail("shared GPU is already owned")
        )
    assert runtime.read(tmp_path / "state/first.json")["status"] == "queued"
    assert runtime.read(tmp_path / "state/second.json")["status"] == "queued"


def test_worker_inspection_failure_leaves_job_queued(tmp_path, monkeypatch):
    worker_fixture(tmp_path, monkeypatch)

    def fail(*a):
        raise gpu_policy.GpuInspectionError("temporary nvidia-smi failure")

    monkeypatch.setattr(guards, "gpu_is_idle", fail)
    with pytest.raises(gpu_policy.GpuInspectionError):
        runtime.worker(tmp_path, tmp_path, 0, run=lambda *a: pytest.fail("no telemetry"))
    assert runtime.read(tmp_path / "state/first.json") == {"name": "first", "status": "queued"}
