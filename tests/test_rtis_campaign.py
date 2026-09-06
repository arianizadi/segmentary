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


def test_publisher_real_git_updates_only_report_and_retries(tmp_path, monkeypatch):
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
    root = tmp_path / "campaign"
    root.mkdir()
    rtis.publish_once(root, publisher)
    first = rtis.git(publisher, "rev-parse", "HEAD")
    rtis.publish_once(root, publisher)
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
        rtis.publish_once(root, publisher)
    monkeypatch.setattr(rtis, "git", original_git)
    rtis.publish_once(root, publisher)
    assert (publisher / "README.md").read_text() == "New unrelated author work\n"
    assert "62.50" in (publisher / rtis.REPORT / "README.md").read_text()
    assert rtis.git(publisher, "rev-parse", "HEAD") == rtis.git(
        publisher, "rev-parse", "origin/main"
    )
    (publisher / "README.md").write_text("Pending human edit\n")
    with pytest.raises(RuntimeError, match="unrelated edits"):
        rtis.publish_once(root, publisher)
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
