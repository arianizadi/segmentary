"""Exercise checkpoint retention boundaries and real isolated Git publishing."""

from pathlib import Path

import pytest
from scripts import run_rtis_campaign as rtis


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
    jobs = [{"name": "bad"}, {"name": "good"}]
    rtis.write(tmp_path / "plan.json", {"jobs": jobs})
    for job in jobs:
        rtis.write(tmp_path / "state" / f"{job['name']}.json", {"status": "queued"})
    monkeypatch.setattr(rtis, "verify_frozen", lambda *_: {})

    def run_job(root, repo, job, gpu, campaign):
        if job["name"] == "bad":
            raise RuntimeError("model incompatible")
        rtis.write(root / "state/good.json", {"status": "completed"})

    monkeypatch.setattr(rtis, "run_job", run_job)
    rtis.worker(tmp_path, Path.cwd(), 0)
    assert rtis.read(tmp_path / "state/bad.json")["status"] == "failed"
    assert rtis.read(tmp_path / "state/good.json")["status"] == "completed"


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
