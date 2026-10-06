"""Exercise checkpoint retention boundaries and real isolated Git publishing."""

import subprocess
import sys
from pathlib import Path

import pytest
from scripts import run_rtis_campaign as rtis

from helpers_gpu_policy import (
    INVENTORY,
    make_policy,
    patch_live,
    pinned_env,
    uuid_of,
    write_campaign,
)
from segmentary.gpu_policy import GpuPolicyError


def test_cleanup_keeps_anchors_and_unrelated_files(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    for name in [
        "best.ckpt",
        "last.ckpt",
        "step-00000500.ckpt",
        "step-00001000.ckpt",
        "notes.ckpt",
    ]:
        (run / name).write_bytes(name.encode())
    evidence = {
        "status": "completed",
        "checkpoints": {
            key: {"path": str(run / name), "sha256": rtis.digest(run / name)}
            for key, name in [("best", "best.ckpt"), ("final", "last.ckpt")]
        },
    }
    log = tmp_path / "cleanup.json"
    removed = rtis.cleanup(run, evidence, log)
    assert removed > 0
    assert {p.name for p in run.iterdir()} == {"best.ckpt", "last.ckpt", "notes.ckpt"}
    assert all(row["deleted"] for row in rtis.read(log))
    assert rtis.cleanup(run, evidence, log) == removed


def test_cleanup_refuses_failed_or_changed_anchors(tmp_path):
    anchor = tmp_path / "last.ckpt"
    anchor.write_bytes(b"final")
    periodic = tmp_path / "step-00000500.ckpt"
    periodic.write_bytes(b"recovery")
    evidence = {
        "status": "failed",
        "checkpoints": {"final": {"path": str(anchor), "sha256": rtis.digest(anchor)}},
    }
    with pytest.raises(RuntimeError, match="completed"):
        rtis.cleanup(tmp_path, evidence, tmp_path / "log.json")
    evidence["status"] = "completed"
    anchor.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed"):
        rtis.cleanup(tmp_path, evidence, tmp_path / "log.json")
    assert periodic.exists()


def test_cleanup_never_follows_periodic_symlink(tmp_path):
    outside = tmp_path / "historical.ckpt"
    outside.write_bytes(b"source")
    run = tmp_path / "run"
    run.mkdir()
    anchor = run / "last.ckpt"
    anchor.write_bytes(b"last")
    (run / "step-00000500.ckpt").symlink_to(outside)
    evidence = {
        "status": "completed",
        "checkpoints": {"final": {"path": str(anchor), "sha256": rtis.digest(anchor)}},
    }
    with pytest.raises(RuntimeError, match="Unexpected"):
        rtis.cleanup(run, evidence, tmp_path / "log.json")
    assert outside.read_bytes() == b"source"


@pytest.mark.parametrize("detailed", [False, True])
def test_publisher_real_git_updates_only_report_and_retries(tmp_path, monkeypatch, detailed):
    from scripts import publish_rtis_results as reports

    publish = reports.publish_once if detailed else rtis.publish_once
    remote, author, publisher = [tmp_path / name for name in ("origin.git", "author", "publisher")]
    rtis.git(tmp_path, "init", "--bare", str(remote))
    rtis.git(tmp_path, "clone", str(remote), str(author))
    rtis.git(author, "checkout", "-b", "main")
    for repo in [author]:
        rtis.git(repo, "config", "user.name", "Test")
        rtis.git(repo, "config", "user.email", "test@example.invalid")
    (author / "README.md").write_text("Preserve author work\n")
    rtis.git(author, "add", ".")
    rtis.git(author, "commit", "-m", "Initial")
    rtis.git(author, "push", "origin", "main")
    rtis.git(tmp_path, "clone", "--branch", "main", str(remote), str(publisher))
    rtis.git(publisher, "config", "user.name", "Test")
    rtis.git(publisher, "config", "user.email", "test@example.invalid")
    data = {
        "campaign": {"code_sha": "abc", "split_sha256": "def"},
        "jobs": [{"model": "example", "protocol": "rtis_only", "status": "queued"}],
    }
    monkeypatch.setattr(rtis, "snapshot", lambda _: data)
    monkeypatch.setattr(reports, "capture", lambda _: data)
    root = tmp_path / "campaign"
    root.mkdir()
    publish(root, publisher)
    first = rtis.git(publisher, "rev-parse", "HEAD")
    publish(root, publisher)
    assert rtis.git(publisher, "rev-parse", "HEAD") == first
    # A human publishes between automatic result updates.
    rtis.git(author, "pull", "--ff-only", "origin", "main")
    (author / "README.md").write_text("New unrelated author work\n")
    rtis.git(author, "commit", "-am", "Human edit")
    rtis.git(author, "push", "origin", "main")
    data["jobs"][0].update(status="completed", evaluation={"metrics": {"miou": 0.625}})
    original_git = rtis.git

    def fail_push(repo, *args):
        if args[0] == "push":
            raise RuntimeError("Simulated network failure")
        return original_git(repo, *args)

    monkeypatch.setattr(rtis, "git", fail_push)
    with pytest.raises(RuntimeError, match="network"):
        publish(root, publisher)
    monkeypatch.setattr(rtis, "git", original_git)
    publish(root, publisher)
    assert (publisher / "README.md").read_text() == "New unrelated author work\n"
    assert "62.50" in (publisher / rtis.REPORT / "README.md").read_text()
    assert rtis.git(publisher, "rev-parse", "HEAD") == rtis.git(
        publisher, "rev-parse", "origin/main"
    )
    (publisher / "README.md").write_text("Pending human edit\n")
    with pytest.raises(RuntimeError, match="unrelated edits"):
        publish(root, publisher)
    assert (publisher / "README.md").read_text() == "Pending human edit\n"


def test_worker_records_failure_and_continues(tmp_path, monkeypatch):
    campaign = write_campaign(tmp_path, jobs=["bad", "good"])
    monkeypatch.setattr(rtis, "verify_frozen", lambda *_: campaign)
    monkeypatch.setattr(rtis.os, "environ", pinned_env(2))

    def run_job(root, repo, job, gpu, campaign):
        if job["name"] == "bad":
            raise RuntimeError("model incompatible")
        rtis.write(root / "state/good.json", {"status": "completed"})

    monkeypatch.setattr(rtis, "run_job", run_job)
    rtis.worker(tmp_path, Path.cwd(), 2)
    assert rtis.read(tmp_path / "state/bad.json")["status"] == "failed"
    assert rtis.read(tmp_path / "state/good.json")["status"] == "completed"


def test_worker_exits_without_failing_a_job_when_inventory_is_unavailable(tmp_path, monkeypatch):
    """A transient nvidia-smi outage must not terminalise a queued job."""
    from segmentary.gpu_policy import GpuInspectionError

    campaign = write_campaign(tmp_path, jobs=["job"])
    calls = []

    def verify(*_):
        calls.append(1)
        if len(calls) > 1:
            raise GpuInspectionError("Could not read the GPU inventory after 3 attempt(s)")
        return campaign

    monkeypatch.setattr(rtis, "verify_frozen", verify)
    monkeypatch.setattr(rtis.os, "environ", pinned_env(2))
    monkeypatch.setattr(rtis, "run_job", lambda *a: pytest.fail("must not run"))
    with pytest.raises(GpuInspectionError):
        rtis.worker(tmp_path, Path.cwd(), 2)
    assert rtis.read(tmp_path / "state/job.json") == {"name": "job", "status": "queued"}


def test_verify_frozen_checks_smoke_against_the_hashed_plan(tmp_path, monkeypatch):
    campaign = write_campaign(tmp_path)
    patch_live(monkeypatch)
    monkeypatch.setattr(rtis, "git", lambda repo, *args: "code" if args[0] == "rev-parse" else "")
    rtis.verify_frozen(tmp_path, tmp_path)
    rtis.write(tmp_path / "campaign.json", {**campaign, "smoke": True})
    with pytest.raises(RuntimeError, match="smoke flag disagrees"):
        rtis.verify_frozen(tmp_path, tmp_path)


@pytest.mark.parametrize("gpu,visible", [(0, "0"), (1, "1"), (2, "3"), (2, "0,1,2"), (2, None)])
def test_worker_refuses_forbidden_or_unpinned_gpu_before_locking(
    tmp_path, monkeypatch, gpu, visible
):
    campaign = write_campaign(tmp_path, jobs=["job"])
    monkeypatch.setattr(rtis, "verify_frozen", lambda *_: campaign)
    env = pinned_env(gpu)
    if visible is None:
        del env["CUDA_VISIBLE_DEVICES"]
    else:
        env["CUDA_VISIBLE_DEVICES"] = visible
    monkeypatch.setattr(rtis.os, "environ", env)
    monkeypatch.setattr(rtis, "run_job", lambda *a: pytest.fail("must not run"))
    with pytest.raises(GpuPolicyError):
        rtis.worker(tmp_path, Path.cwd(), gpu)
    assert not (tmp_path / "locks").exists()
    assert rtis.read(tmp_path / "state/job.json")["status"] == "queued"


def test_verify_frozen_requires_matching_untouched_policy(tmp_path, monkeypatch):
    campaign = write_campaign(tmp_path)
    patch_live(monkeypatch)
    monkeypatch.setattr(rtis, "git", lambda repo, *args: "code" if args[0] == "rev-parse" else "")
    assert rtis.verify_frozen(tmp_path, tmp_path)["gpu_policy"] == campaign["gpu_policy"]
    edited = {**campaign, "gpu_policy": make_policy(range(0, 10))}
    rtis.write(tmp_path / "campaign.json", edited)
    with pytest.raises(GpuPolicyError, match="disagrees with plan"):
        rtis.verify_frozen(tmp_path, tmp_path)
    plan = rtis.read(tmp_path / "plan.json")
    plan_bytes = (tmp_path / "plan.json").read_bytes()
    rtis.write(tmp_path / "plan.json", {**plan, "gpu_allowlist": list(range(10))})
    edited["plan_sha256"] = rtis.digest(tmp_path / "plan.json")
    rtis.write(tmp_path / "campaign.json", edited)
    with pytest.raises(GpuPolicyError, match="edited after initialization"):
        rtis.verify_frozen(tmp_path, tmp_path)
    rtis.write(tmp_path / "campaign.json", {k: v for k, v in campaign.items() if k != "gpu_policy"})
    (tmp_path / "plan.json").write_bytes(plan_bytes)
    with pytest.raises(GpuPolicyError, match="no frozen gpu_policy"):
        rtis.verify_frozen(tmp_path, tmp_path)
    rtis.write(tmp_path / "campaign.json", campaign)
    monkeypatch.setattr(rtis.gpu_policy, "inventory", lambda: INVENTORY[:9])
    with pytest.raises(GpuPolicyError, match="now has 9"):
        rtis.verify_frozen(tmp_path, tmp_path)


def _initialize_fixture(tmp_path, monkeypatch, plan):
    from types import SimpleNamespace

    data_root = tmp_path / "data"
    (data_root / "audit").mkdir(parents=True)
    (data_root / "audit/samples.json").write_text("[]")
    rtis.write(
        data_root / "splits.json",
        {"train": ["a", "b"], "val": ["c"], "test": [], "groups": {}, "_grouping_status": "x"},
    )
    config = tmp_path / "job.yaml"
    config.write_text("job")
    plan = {
        "dataset": "ds",
        "split_sha256": rtis.digest(data_root / "splits.json"),
        "grouping_status": "x",
        "target_steps_per_job": 4,
        "jobs": [
            {
                "name": "job",
                "config": str(config),
                "config_sha256": rtis.digest(config),
                "source_checkpoint": None,
            }
        ],
        **plan,
    }
    root = tmp_path / "campaign"
    root.mkdir()
    rtis.write(root / "plan.json", plan)
    cfg = SimpleNamespace(
        stages=[SimpleNamespace(data=[SimpleNamespace(root=str(data_root))])],
        output_root=str(root / "future-runs"),
    )
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda layers: cfg)
    )
    monkeypatch.setattr(rtis, "git", lambda repo, *args: "code" if args[0] == "rev-parse" else "")
    patch_live(monkeypatch)
    return root


def test_initialize_freezes_policy_sizes_and_smoke_from_plan(tmp_path, monkeypatch):
    root = _initialize_fixture(tmp_path, monkeypatch, {"gpu_allowlist": [9, 2], "smoke": True})
    rtis.initialize(root, tmp_path)
    campaign = rtis.read(root / "campaign.json")
    assert campaign["gpu_policy"] == make_policy([2, 9])
    assert campaign["gpu_policy_sha256"] == rtis.gpu_policy.policy_sha256(make_policy([2, 9]))
    assert [e["uuid"] for e in campaign["gpu_policy"]["forbidden"]] == [
        uuid_of(i) for i in range(10) if i not in (2, 9)
    ]
    assert campaign["smoke"] is True
    assert campaign["dataset_sizes"] == {"train": 2, "val": 1, "test": 0}
    assert rtis.read(root / "state/job.json")["status"] == "queued"
    assert rtis.verify_frozen(root, tmp_path)["gpu_policy_sha256"] == campaign["gpu_policy_sha256"]


@pytest.mark.parametrize("primary", [None, "best", "final"])
def test_initialize_records_primary_checkpoint_only_when_planned(tmp_path, monkeypatch, primary):
    plan = {"gpu_allowlist": [2]} | ({"primary_checkpoint": primary} if primary else {})
    root = _initialize_fixture(tmp_path, monkeypatch, plan)
    rtis.initialize(root, tmp_path)
    campaign = rtis.read(root / "campaign.json")
    assert campaign.get("primary_checkpoint") == primary
    if primary == "final":
        assert campaign["selection"].startswith("final checkpoint at the fixed step budget")
    else:
        assert campaign["selection"] == (
            "best validation checkpoint; auto raw/EMA-safe weights; no TTA"
        )


@pytest.mark.parametrize("primary", [None, "final"])
def test_run_job_refuses_an_early_stop_when_the_final_checkpoint_is_primary(
    tmp_path, monkeypatch, primary
):
    from types import SimpleNamespace

    campaign = write_campaign(tmp_path, jobs=["job"], collection_contract="rtis-full-statistics-v1")
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "splits.json").write_text("s")
    campaign.update(split_sha256=rtis.digest(data_root / "splits.json"), target_steps=4000)
    if primary:
        campaign["primary_checkpoint"] = primary
    config = tmp_path / "job.yaml"
    config.write_text("job")
    job = {"name": "job", "config": str(config), "config_sha256": rtis.digest(config)}
    job["source_checkpoint"] = None
    run = tmp_path / "future-runs/job_seed0/rtis"
    run.mkdir(parents=True)
    rtis.write(
        run / "results.json",
        {
            "env": {
                "training_stop": {
                    "reason": "validation_plateau",
                    "actual_steps": 1000,
                    "maximum_steps": 4000,
                    "patience": 5,
                }
            },
            "metrics": {"miou": 0.5},
        },
    )
    cfg = SimpleNamespace(
        stages=[SimpleNamespace(data=[SimpleNamespace(root=str(data_root))])],
        output_root=str(tmp_path / "future-runs"),
        name="job",
        train=SimpleNamespace(seed=0),
    )
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda layers: cfg)
    )
    monkeypatch.setitem(
        sys.modules,
        "segmentary.utils.resource_tracking",
        SimpleNamespace(run_recorded=lambda command, **kwargs: None),
    )
    monkeypatch.setattr(
        rtis,
        "checkpoint_info",
        lambda path: {"path": str(path), "sha256": "x", "global_step": 1000},
    )
    # An early-stopped run is valid evidence for the best-checkpoint contract (the job then
    # fails later only because this fixture has no best checkpoint), never for final.
    match = "full step budget" if primary == "final" else "exactly one best checkpoint"
    with pytest.raises(RuntimeError, match=match):
        rtis.run_job(tmp_path, tmp_path, job, 2, campaign)


def test_initialize_refuses_plan_without_allowlist(tmp_path, monkeypatch):
    root = _initialize_fixture(tmp_path, monkeypatch, {})
    with pytest.raises(GpuPolicyError, match="gpu_allowlist"):
        rtis.initialize(root, tmp_path)
    assert not (root / "campaign.json").exists()


def test_run_job_child_env_is_pinned_even_when_parent_sees_everything(tmp_path, monkeypatch):
    from types import SimpleNamespace

    campaign = write_campaign(tmp_path, jobs=["job"], collection_contract="rtis-full-statistics-v1")
    campaign.update(split_sha256="split", target_steps=4)
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "splits.json").write_text("s")
    campaign["split_sha256"] = rtis.digest(data_root / "splits.json")
    config = tmp_path / "job.yaml"
    config.write_text("job")
    job = {
        "name": "job",
        "config": str(config),
        "config_sha256": rtis.digest(config),
        "source_checkpoint": None,
    }
    cfg = SimpleNamespace(
        stages=[SimpleNamespace(data=[SimpleNamespace(root=str(data_root))])],
        output_root=str(tmp_path / "future-runs"),
        name="job",
        train=SimpleNamespace(seed=0),
    )
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda layers: cfg)
    )
    monkeypatch.setattr(rtis.os, "environ", {"CUDA_VISIBLE_DEVICES": "0,1,2", "HOME": "/h"})
    captured = {}

    def recorded(command, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after launch")

    monkeypatch.setitem(
        sys.modules,
        "segmentary.utils.resource_tracking",
        SimpleNamespace(run_recorded=recorded),
    )
    with pytest.raises(RuntimeError, match="stop after launch"):
        rtis.run_job(tmp_path, tmp_path, job, 2, campaign)
    env = captured["env"]
    assert env["CUDA_VISIBLE_DEVICES"] == "2"
    assert env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    assert env[rtis.gpu_policy.POLICY_ENV] == str(tmp_path / "campaign.json")
    assert env[rtis.gpu_policy.ASSIGNED_ENV] == "2"
    assert env["HOME"] == "/h"
    assert captured["expected_gpu_uuid"] == uuid_of(2)
    assert rtis.read(tmp_path / "state/job.json")["gpu_uuid"] == uuid_of(2)
    with pytest.raises(GpuPolicyError):
        rtis.run_job(tmp_path, tmp_path, job, 0, campaign)


def _launch_fixture(tmp_path, monkeypatch, compute_apps=()):
    campaign = write_campaign(tmp_path)
    monkeypatch.setattr(rtis, "verify_frozen", lambda *_: campaign)
    patch_live(monkeypatch, compute_apps)
    calls = []
    monkeypatch.setattr(
        rtis.subprocess,
        "run",
        lambda *a, **k: calls.append(a[0]) or subprocess.CompletedProcess(a, 0, "", ""),
    )
    return calls


def test_launch_defaults_to_allowlist_and_pins_every_tmux_command(tmp_path, monkeypatch):
    calls = _launch_fixture(tmp_path, monkeypatch, compute_apps=[(7, uuid_of(0))])
    rtis.launch(tmp_path, tmp_path / "repo", tmp_path / "publisher", dashboard=False)
    sessions = {call[4]: call[5] for call in calls}
    assert set(sessions) == {f"rtis-{tmp_path.name}-publisher"} | {
        f"rtis-{tmp_path.name}-gpu-{g}" for g in range(2, 10)
    }
    for name, shell in sessions.items():
        if name.endswith("publisher"):
            assert "env CUDA_VISIBLE_DEVICES= " in shell
        else:
            gpu = name.rsplit("-", 1)[1]
            assert f"&& env CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES={gpu} " in shell
            assert f"--gpu {gpu} " in shell
    services = rtis.read(tmp_path / "services.json")
    assert services["gpus"] == list(range(2, 10))
    assert services["gpu_uuids"]["2"] == uuid_of(2)


def test_launch_rejects_gpus_outside_allowlist_and_busy_allowed_gpus(tmp_path, monkeypatch):
    calls = _launch_fixture(tmp_path, monkeypatch)
    with pytest.raises(GpuPolicyError):
        rtis.launch(tmp_path, tmp_path / "repo", tmp_path / "publisher", [0, 2], dashboard=False)
    assert calls == []
    rtis.launch(tmp_path, tmp_path / "repo", tmp_path / "publisher", [3], dashboard=False)
    assert [c[4] for c in calls] == [
        f"rtis-{tmp_path.name}-publisher",
        f"rtis-{tmp_path.name}-gpu-3",
    ]
    calls = _launch_fixture(tmp_path, monkeypatch, compute_apps=[(5, uuid_of(3))])
    with pytest.raises(RuntimeError, match=r"active on \[3\]"):
        rtis.launch(tmp_path, tmp_path / "repo", tmp_path / "publisher", dashboard=False)
    assert calls == []


def test_cli_has_no_gpu_default_and_parses_launch_subset(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(rtis, "launch", lambda *a, **k: captured.update(gpus=a[3]))
    monkeypatch.setattr(sys, "argv", ["runner", "launch", "--campaign", str(tmp_path)])
    rtis.main()
    assert captured["gpus"] is None
    monkeypatch.setattr(
        sys, "argv", ["runner", "launch", "--campaign", str(tmp_path), "--gpus", "3,2"]
    )
    rtis.main()
    assert captured["gpus"] == (3, 2)
    monkeypatch.setattr(
        sys, "argv", ["runner", "launch", "--campaign", str(tmp_path), "--gpus", "2,2"]
    )
    with pytest.raises(GpuPolicyError):
        rtis.main()


def test_dataset_audit_uses_decoded_mask_hash(tmp_path):
    import hashlib

    from PIL import Image

    image = tmp_path / "images/train/example.png"
    mask = tmp_path / "masks/train/example.png"
    image.parent.mkdir(parents=True)
    mask.parent.mkdir(parents=True)
    Image.new("RGB", (3, 2), "red").save(image)
    pixels = Image.new("L", (3, 2), 2)
    pixels.save(mask, compress_level=0)
    sample = {
        "split": "train",
        "key": "example",
        "image_extension": ".png",
        "width": 3,
        "height": 2,
        "image_sha256": rtis.digest(image),
        "mask_sha256": hashlib.sha256(pixels.tobytes()).hexdigest(),
    }
    rtis.verify_samples(tmp_path, [sample])
    pixels.save(mask, compress_level=9)
    rtis.verify_samples(tmp_path, [sample])
    Image.new("L", (3, 2), 3).save(mask)
    with pytest.raises(RuntimeError, match="content changed"):
        rtis.verify_samples(tmp_path, [sample])


def test_early_stop_requires_explicit_finite_validation_evidence():
    with pytest.raises(RuntimeError, match="without valid"):
        rtis.validate_stop({"env": {}, "metrics": {"miou": 0.5}}, 1000, 4000)
    record = {
        "env": {
            "training_stop": {
                "reason": "validation_plateau",
                "actual_steps": 1000,
                "maximum_steps": 4000,
                "patience": 3,
            }
        },
        "metrics": {"miou": 0.5},
    }
    assert rtis.validate_stop(record, 1000, 4000)["reason"] == "validation_plateau"
    record["metrics"]["miou"] = None
    with pytest.raises(RuntimeError, match="without valid"):
        rtis.validate_stop(record, 1000, 4000)


@pytest.mark.parametrize("improves,expected", [(False, 6), (True, 12)])
def test_real_lightning_early_stopping_uses_validation_checks(tmp_path, improves, expected):
    import lightning as L
    import torch
    from torch.utils.data import DataLoader, TensorDataset

    from segmentary.config import TrainConfig
    from segmentary.curriculum import _checkpoint_callbacks

    class Toy(L.LightningModule):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor(1.0))

        def training_step(self, batch, batch_idx):
            return self.weight.square()

        def validation_step(self, batch, batch_idx):
            score = 0.4 + (0.01 * self.global_step if improves else 0.0)
            self.log("val/miou", torch.tensor(score))

        def configure_optimizers(self):
            return torch.optim.SGD(self.parameters(), lr=0.01)

    loader = DataLoader(TensorDataset(torch.zeros(24, 1)), batch_size=1)
    cfg = TrainConfig(
        iters=12,
        val_every=2,
        ckpt_every=2,
        early_stopping_patience=2,
        early_stopping_min_delta=0.002,
    )
    trainer = L.Trainer(
        max_steps=12,
        accelerator="cpu",
        devices=1,
        logger=False,
        callbacks=_checkpoint_callbacks(tmp_path, cfg),
        val_check_interval=2,
        check_val_every_n_epoch=None,
        num_sanity_val_steps=0,
        enable_progress_bar=False,
        enable_model_summary=False,
    )
    trainer.fit(Toy(), loader, loader)
    assert trainer.global_step == expected
    assert len(list(tmp_path.glob("best*.ckpt"))) == 1


def test_detailed_reports_keep_mud_and_denominator_changes_visible():
    from scripts import publish_rtis_results as reports

    metrics = {
        "miou": 0.2,
        "per_class_iou": {"mud-pumping": 0.4, "absent": 0.0},
        "support": {"mud-pumping": 10, "absent": 0},
        "per_class_precision": {"mud-pumping": 0.5},
        "per_class_recall": {"mud-pumping": 0.6},
    }
    data = {
        "campaign": {"code_sha": "frozen", "split_sha256": "split"},
        "jobs": [
            {
                "model": "example",
                "protocol": "rtis_only",
                "status": "completed",
                "evaluation": {"metrics": metrics},
                "training": {"metrics": {"per_class_iou": {"mud-pumping": 0.7}}},
            }
        ],
    }
    files = reports.artifacts(data)
    assert "[example](models/example/README.md)" in files["README.md"]
    assert reports.fixed_miou(metrics) == 0.4
    assert "70.00" in files["README.md"]
    assert "not whole-campaign totals" in files["models/example/README.md"]
    assert "record.json" in files["models/example/README.md"]
    data["jobs"][0]["model"] = "../../outside"
    with pytest.raises(ValueError, match="Unsafe"):
        reports.artifacts(data)


def test_comparison_table_averages_only_completed_seeds_and_keeps_zero():
    from scripts import publish_rtis_results as reports

    jobs = [
        {
            "model": "example",
            "protocol": "rtis_only",
            "status": status,
            "evaluation": {"metrics": {"miou": value}},
        }
        for status, value in [("completed", 0.0), ("completed", 0.4), ("training", 0.99)]
    ]
    summary = reports.seed_summary(jobs)
    assert "| 20.00 |" in summary
    assert "±" not in summary
    assert "(n=" not in summary
    assert "City → RTIS" in summary
    assert "| — | — | — |" in summary


def test_publisher_interval_batches_rapid_status_changes():
    from scripts.publish_rtis_results import publish_due

    assert publish_due(None, 100, 1800)
    assert not publish_due(100, 160, 1800)
    assert not publish_due(100, 1899, 1800)
    assert publish_due(100, 1900, 1800)


def test_v2_comparison_uses_paired_seed_and_completed_jobs_only():
    from scripts.publish_rtis_results import artifacts

    old = {
        "name": "example--rtis_only--seed-0",
        "model": "example",
        "protocol": "rtis_only",
        "seed": 0,
        "status": "completed",
        "evaluation": {"metrics": {"miou": 0.4, "per_class_iou": {"mud-pumping": 0.3}}},
    }
    new = {**old, "evaluation": {"metrics": {"miou": 0.5, "per_class_iou": {"mud-pumping": 0.25}}}}
    data = {
        "campaign": {
            "code_sha": "same",
            "split_sha256": "v2",
            "dataset": "paul-test-rtis_v2",
            "dataset_sizes": {"train": 205, "val": 37, "test": 50},
        },
        "jobs": [new],
        "baseline": {"jobs": [old]},
    }
    files = artifacts(data)
    assert "205/37/50" in files["README.md"]
    assert "Training: 205 images" in files["models/example/README.md"]
    assert "40.00,50.00,10.00,30.00,25.00,-5.00" in files["comparison.csv"]
    new["status"] = "collecting"
    assert "40.00,—,—,30.00,—,—" in artifacts(data)["comparison.csv"]


def test_published_reports_do_not_restore_removed_audit_labels():
    from scripts.publish_rtis_results import artifacts

    campaign = {"code_sha": "frozen", "split_sha256": "split", "dataset_audit_sha256": "manifest"}
    files = artifacts({"campaign": campaign, "jobs": []})
    assert all("audit" not in value.lower() for value in files.values() if isinstance(value, str))
    assert '"dataset_manifest_sha256": "manifest"' in files["status.json"]
    assert campaign["dataset_audit_sha256"] == "manifest"


def test_publisher_restart_preserves_thirty_minute_interval(tmp_path):
    from scripts.publish_rtis_results import previous_publish_time, publish_due

    rtis.write(tmp_path / "publisher-status.json", {"last_success": "2026-09-09T00:00:00+00:00"})
    last = previous_publish_time(tmp_path, monotonic_now=1000, wall_now=1788912300)
    assert not publish_due(last, 1000, 1800)  # Restart five minutes after the last upload.
    assert publish_due(last, 2500, 1800)
