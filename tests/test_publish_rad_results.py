"""publish_rad_results: rendering of the study page and real git publishing to a bare remote."""

from __future__ import annotations

import fcntl
import json
import re
import subprocess
from pathlib import Path

import pytest
from scripts import publish_rad_results as pub
from scripts import publish_rtis_results as reports
from scripts import rad_report

TREE = pub.TREE


def sh(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def identity(repo: Path) -> None:
    sh(repo, "config", "user.name", "Test")
    sh(repo, "config", "user.email", "test@example.invalid")


@pytest.fixture
def repos(tmp_path):
    remote, author, publisher = (tmp_path / n for n in ("remote.git", "author", "publisher"))
    sh(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(remote))
    sh(tmp_path, "clone", "--quiet", str(remote), str(author))
    sh(author, "checkout", "--quiet", "-B", "main")
    identity(author)
    (author / "README.md").write_text("Author work\n")
    index = author / pub.INDEX
    index.parent.mkdir(parents=True)
    index.write_text("# Results\n\n| Study | x |\n| --- | --- |\n| [A](a/README.md) | a |\n\nEnd\n")
    (index.parent / "a").mkdir()
    (index.parent / "a/README.md").write_text("# A\n")
    docs_test = author / "tests/test_documentation.py"
    docs_test.parent.mkdir()
    docs_test.write_text(f'EXEMPT = "{TREE}/*/models/*/record.json"\n')
    sh(author, "add", ".")
    sh(author, "commit", "--quiet", "-m", "Initial")
    sh(author, "push", "--quiet", "origin", "main")
    sh(tmp_path, "clone", "--quiet", "--branch", "main", str(remote), str(publisher))
    identity(publisher)
    return remote, author, publisher


@pytest.fixture
def files(monkeypatch):
    content: dict[str, str | bytes] = {"README.md": "# RAD\n\nv1\n", "paul/results.csv": "a,b\n"}

    def render(*_args, **_kwargs):
        pub.check_paths(content)
        return dict(content), None

    monkeypatch.setattr(pub, "render_tree", render)
    return content


def args_for(tmp_path, remote, publisher, *extra):
    return pub.parse(
        [
            "--checkout",
            str(publisher),
            "--campaign",
            str(tmp_path / "no-campaign"),
            "--no-forks",
            "--datasets-root",
            str(tmp_path / "datasets"),
            "--state-dir",
            str(tmp_path / "state"),
            "--dry-run-remote",
            str(remote),
            "--once",
            *extra,
        ]
    )


def remote_files(remote: Path) -> set[str]:
    return set(sh(remote, "ls-tree", "-r", "--name-only", "main").splitlines())


def test_first_publish_commits_and_unchanged_cycle_does_not(tmp_path, repos, files):
    remote, _, publisher = repos
    args = args_for(tmp_path, remote, publisher)
    first = pub.publish_once(args)
    assert first["pushed"] and first["changed_files"] == 3  # two files + the index row
    assert sh(remote, "log", "-1", "--format=%s", "main") == pub.COMMIT_MESSAGE
    assert {f"{TREE}/README.md", f"{TREE}/paul/results.csv"} <= remote_files(remote)
    index = sh(remote, "show", f"main:{pub.INDEX}")
    assert pub.INDEX_ROW in index and index.index(pub.INDEX_ROW) < index.index("End")
    head = sh(remote, "rev-parse", "main")
    second = pub.publish_once(args)
    assert not second["pushed"] and second["changed_files"] == 0
    assert sh(remote, "rev-parse", "main") == head == second["commit"]
    # A removed file is removed from the tree; nothing outside it changes.
    files.pop("paul/results.csv")
    files["README.md"] = "# RAD\n\nv2\n"
    assert pub.publish_once(args)["pushed"]
    changed = sh(remote, "diff", "--name-only", "main~1", "main").splitlines()
    assert changed == [f"{TREE}/README.md", f"{TREE}/paul/results.csv"]
    assert f"{TREE}/paul/results.csv" not in remote_files(remote)


def test_refuses_dirty_checkout_outside_tree_and_stops(tmp_path, repos, files):
    remote, _, publisher = repos
    (publisher / "README.md").write_text("Pending human edit\n")
    args = args_for(tmp_path, remote, publisher)
    with pytest.raises(pub.Refusal, match="outside"):
        pub.publish_once(args)
    assert (publisher / "README.md").read_text() == "Pending human edit\n"
    assert pub.run(args) == 2
    status = json.loads((tmp_path / "state/publisher-status.json").read_text())
    assert status["stopped"] and status["error"].startswith("refused")
    assert sh(remote, "log", "--format=%s", "main") == "Initial"
    # Untracked files count too; edits inside the tree are the publisher's own and are reset.
    (publisher / "README.md").write_text("Author work\n")
    (publisher / "notes.txt").write_text("x")
    with pytest.raises(pub.Refusal):
        pub.publish_once(args)
    (publisher / "notes.txt").unlink()
    (publisher / TREE).mkdir(parents=True)
    (publisher / TREE / "stale.md").write_text("stale")
    pub.publish_once(args)
    assert f"{TREE}/stale.md" not in remote_files(remote)


def test_refuses_unpushed_foreign_commit(tmp_path, repos, files):
    remote, _, publisher = repos
    (publisher / "other.txt").write_text("human\n")
    sh(publisher, "add", "other.txt")
    sh(publisher, "commit", "--quiet", "-m", "Human local commit")
    with pytest.raises(pub.Refusal, match="unpushed"):
        pub.publish_once(args_for(tmp_path, remote, publisher))
    assert (publisher / "other.txt").exists()


def test_refuses_wrong_remote_branch_and_code_checkout(tmp_path, repos, files):
    remote, _, publisher = repos
    with pytest.raises(pub.Refusal, match="not the target"):
        pub.publish_once(pub.parse(["--checkout", str(publisher), "--once", "--no-forks"]))
    with pytest.raises(pub.Refusal, match="separate"):
        pub.publish_once(args_for(tmp_path, remote, pub.CODE))
    args = args_for(tmp_path, remote, publisher, "--frozen-checkout", str(publisher))
    with pytest.raises(pub.Refusal, match="campaign code checkout"):
        pub.publish_once(args)
    sh(publisher, "checkout", "--quiet", "-b", "other")
    with pytest.raises(pub.Refusal, match="not 'main'"):
        pub.publish_once(args_for(tmp_path, remote, publisher))
    with pytest.raises(SystemExit):
        pub.parse(["--checkout", str(publisher), "--state-dir", str(publisher / "state")])


def test_non_fast_forward_race_is_rebased_and_retried(tmp_path, repos, files, monkeypatch):
    remote, author, publisher = repos
    real = pub.git
    raced = []

    def racing_git(repo, *args):
        if args[0] == "push" and not raced:
            raced.append(True)
            (author / "README.md").write_text("Concurrent human edit\n")
            sh(author, "commit", "--quiet", "-am", "Human edit")
            sh(author, "push", "--quiet", "origin", "main")
        return real(repo, *args)

    monkeypatch.setattr(pub, "git", racing_git)
    result = pub.publish_once(args_for(tmp_path, remote, publisher))
    assert raced and result["pushed"]
    log = sh(remote, "log", "--format=%s", "main").splitlines()
    assert log == [pub.COMMIT_MESSAGE, "Human edit", "Initial"]
    assert sh(remote, "show", "main:README.md") == "Concurrent human edit"


def test_push_gives_up_after_three_rejections_and_never_forces(tmp_path, repos, files, monkeypatch):
    remote, _, publisher = repos
    real, pushes = pub.git, []

    def rejecting_git(repo, *args):
        if args[0] == "push":
            assert "--force" not in args and not any(a.startswith("+") for a in args)
            pushes.append(args)
            raise pub.GitError("! [rejected] HEAD -> main (non-fast-forward)")
        return real(repo, *args)

    monkeypatch.setattr(pub, "git", rejecting_git)
    with pytest.raises(pub.GitError, match="3 times"):
        pub.publish_once(args_for(tmp_path, remote, publisher))
    assert len(pushes) == 3
    assert sh(remote, "log", "--format=%s", "main") == "Initial"


def test_size_guard(tmp_path, repos, files):
    remote, _, publisher = repos
    files["paul/big.json.gz"] = b"x" * (2 << 20)
    with pytest.raises(pub.SizeError, match="over 1 MiB"):
        pub.publish_once(args_for(tmp_path, remote, publisher, "--max-tree-mb", "1"))
    args = args_for(tmp_path, remote, publisher, "--max-file-mb", "1")
    with pytest.raises(pub.SizeError, match=r"big\.json\.gz is 2\.0 MiB"):
        pub.publish_once(args)
    assert sh(remote, "log", "--format=%s", "main") == "Initial"
    assert pub.run(args) == 1  # a size failure is recorded, not a refusal
    status = json.loads((tmp_path / "state/publisher-status.json").read_text())
    assert "SizeError" in status["error"] and not status["stopped"]


def test_prediction_directories_are_never_published(tmp_path, repos, files):
    remote, _, publisher = repos
    files["paul/models/m/run/pred/0001.png"] = b"\x89PNG"
    with pytest.raises(ValueError, match="prediction directory"):
        pub.publish_once(args_for(tmp_path, remote, publisher))
    for bad in ("../escape.md", "/abs.md"):
        with pytest.raises(ValueError, match="unsafe"):
            pub.check_paths({bad: ""})


def test_stop_file_and_single_instance(tmp_path, repos, files, monkeypatch):
    remote, _, publisher = repos
    state = tmp_path / "state"
    state.mkdir()
    (state / "STOP").write_text("")
    args = args_for(tmp_path, remote, publisher)
    args.once = False
    assert pub.run(args) == 0
    assert sh(remote, "log", "--format=%s", "main") == "Initial"
    (state / "STOP").unlink()
    # One loop cycle, then STOP appears while waiting: the loop ends.
    real = pub.publish_once

    def once_then_stop(a):
        result = real(a)
        (state / "STOP").write_text("")
        return result

    monkeypatch.setattr(pub, "publish_once", once_then_stop)
    args.interval_seconds = 3600
    assert pub.run(args) == 0
    status = json.loads((state / "publisher-status.json").read_text())
    assert status["commit"] == sh(remote, "rev-parse", "main") and status["error"] is None
    (state / "STOP").unlink()
    with (state / "publisher.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert pub.run(args) == 3


# ----------------------------------------------------------------------------- rendering


def fork_run(runs: Path, name: str, status: str, **provenance) -> Path:
    run = runs / name
    (run / "train").mkdir(parents=True)
    (run / "provenance.json").write_text(
        json.dumps(
            {
                "label": name,
                "owner_of_each_checkpoint_in_chain": {"map_city": "nvidia", "rs19": "paul"}
                | {"rad": "ours"},
                "recipe_args": ["--lr", "7e-5", "--max_epoch", "1000"],
                **provenance,
            }
        )
    )
    (run / "gpu-assignment.json").write_text(json.dumps({"status": status}))
    return run


def test_study_page_renders_arms_audit_forks_and_resolving_links(tmp_path, monkeypatch):
    root = tmp_path / "paul-seed0"
    root.mkdir()
    (root / "campaign.json").write_text(json.dumps({"dataset": "rad_9_24_2026-paul"}))
    data = {
        "campaign": {
            "code_sha": "d864b72bd907",
            "split_sha256": "s",
            "dataset": "rad_9_24_2026-paul",
            "dataset_sizes": {"train": 227, "val": 37, "test": 50},
            "grouping_status": "none_stratified",
            "collection_contract": "rtis-full-statistics-v1",
        },
        "jobs": [
            {"name": "m--rtis_only--seed-0", "model": "m", "protocol": "rtis_only", "seed": 0}
            | {"status": status}
            for status in ("completed", "training")
        ],
    }
    monkeypatch.setattr(reports, "capture", lambda _root: data)

    def no_report(*_args):
        raise rad_report.ReportError("samples changed")

    monkeypatch.setattr(rad_report, "build", no_report)
    audit = tmp_path / "datasets/rad_9_24_2026-paul/audit/label-audit.json"
    audit.parent.mkdir(parents=True)
    classes = [{"id": i, "name": n} for i, n in enumerate(rad_report.subsets.class_names())]
    (audit.parent.parent / "classes.json").write_text(json.dumps({"classes": classes}))
    audit.write_text(
        json.dumps(
            {
                "label_source": "paul",
                "images_with_disagreement": 314,
                "images_with_uncovered_px": 63,
                "totals": {"disagreement_px": 1000, "uncovered_px": 10, "hole_px_changed": 5},
                "per_class_totals": {"0": {"paul_px": 90_000}, "13": {"paul_px": 10_000}}
                | {"13": {"paul_px": 10_000, "paul_px_differing": 7, "rendered_px_differing": 9}},
            }
        )
    )
    other = json.loads(audit.read_text()) | {"label_source": "rendered", "per_image": [1]}
    second = tmp_path / "datasets/rad_9_24_2026-fixed-stratified/audit/label-audit.json"
    second.parent.mkdir(parents=True)
    second.write_text(json.dumps(other))
    runs = tmp_path / "forks/runs"
    run = fork_run(runs, "paper-hrnet__rs19-paul__arm-paul", "running")
    (run / "console.log").write_text(
        "[epoch 603], [iter 1 / 57]\n"
        "best : [epoch 594], [val loss 0.5], [acc 0.9], [mean_iu 0.70238], [fwavacc 0.8]\n"
        "[epoch 604], [iter 1 / 57]\n"
        "best : [epoch 594], [val loss 0.5], [acc 0.9], [mean_iu 0.70238], [fwavacc 0.8]\n"
    )
    rs19 = fork_run(runs, "hrnet-rs19-ours", "running")
    (rs19 / "console.log").write_text(
        "[epoch 12], [iter 1 / 57]\n"
        "best : [epoch 11], [val loss 0.5], [acc 0.9], [mean_iu 0.61234], [fwavacc 0.8]\n"
    )
    (run / "train/best_mud.json").write_text(json.dumps({"epoch": 460, "mud_iou": 0.938}))
    fork_run(runs, "probe2-x", "running", probe_epochs=2, label=run.name)
    (runs.parent / "queue-state.json").write_text(
        json.dumps(
            {
                "jobs": {
                    "q": {
                        "label": "paper-sfnet__mapcity-direct__arm-paul",
                        "run_dir": str(runs / "paper-sfnet__mapcity-direct__arm-paul"),
                        "status": "pending",
                    }
                }
            }
        )
    )
    files, error = pub.render_tree(
        [root, tmp_path / "missing"], runs, tmp_path / "datasets", tmp_path / "v.yaml"
    )
    assert error == "samples changed"
    readme = files["README.md"]
    assert "Not rendered this cycle: samples changed" in readme
    assert "| [`paul`](paul/README.md) |" in readme and "| 1/2 | training 1 |" in readme
    assert "not initialized" in readme  # fixed arms have no campaign yet
    assert "| Total disagreement pixels | 1,000 (1.00%) |" in readme
    assert "| 7 / 9 of 10,000 |" in readme and "`paul` paul" in readme
    assert "mud-pumping 9, person 0" in readme
    # The last epoch is the training line, not the older epoch repeated by ``best :``.
    assert "training, epoch 604 (0-based, of 1000)" in readme
    # RS19-stage printouts validate on RailSem19 test / trainVal: status only, no numbers.
    rs19_row = next(line for line in readme.splitlines() if "`hrnet-rs19-ours`" in line)
    assert "— (RS19 stage)" in rs19_row and "training, epoch 12" in rs19_row
    assert "61.2" not in readme and rs19_row.rstrip().endswith("| — | — |")
    assert pub.FORK_SECTION in readme and f"]({pub.FORK_ANCHOR})" in readme
    assert "retrained by us" in readme and "Paul's paper models" not in readme
    assert "- Publisher code: `" in readme and "Campaign records last changed:" in readme
    assert "mud IoU 93.8 @ epoch 460; mIoU 70.2 @ epoch 594" in readme
    assert "not comparable" in readme
    assert "| Quantity | `paul`, `fixed-stratified` |" in readme
    assert "`fixed-stratified` rendered" in readme
    assert "`paper-hrnet__rs19-paul__arm-paul` (run `probe2-x`)" in readme
    assert "excluded (probe_epochs)" in readme and "queue: pending" in readme
    assert "Single seed" in readme and "Optimistic" in readme and "shares scenes" in readme
    arm = files["paul/README.md"]
    assert arm.startswith("# RAD 9/24: `paul` arm")
    assert "[RAD 9/24 study](../README.md)" in arm and "none_stratified" in arm
    assert "not who trained: every model on this page was trained by us" in arm
    assert "[RAD 9/24 `paul` arm](../../README.md)" in files["paul/models/m/README.md"]
    assert "RTIS comparison" not in files["paul/models/m/README.md"]
    assert "paul/models/m/README.md" in files and "paul/models/m/record.json" in files
    # Every relative link inside the published tree resolves within it.
    out = tmp_path / "out"
    for name, content in files.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(content) if isinstance(content, str) else None
    for name, content in files.items():
        if not name.endswith(".md"):
            continue
        for target in re.findall(r"\]\(([^)#]+)\)", content):
            path = (out / name).parent / target
            if not target.startswith(("http", "../paul-test-rtis", "../../guides")):
                assert path.exists(), (name, target)


def test_comparison_section_has_no_timestamp_and_links_published_arms():
    report = rad_report.Report(
        results=[],
        coverage=[],
        composition={},
        inputs={"campaign paul": "/data/x/paul-seed0", "fork runs": "/data/forks"},
    )
    text = pub.comparison_markdown(report, {"paul"})
    assert "Generated" not in text
    assert text.startswith("## Cab-view comparison (validation split)")
    assert "### How to read this" in text
    assert "- campaign paul: [published arm](paul/README.md); source `/data/x/paul-seed0`" in text
    assert "- fork runs: `/data/forks`" in text


def test_comparison_embed_drops_sections_the_study_page_covers(monkeypatch):
    def render(_report, _generated):
        return "\n".join(
            [
                "# RAD 9/24 comparison (validation split)",
                "Generated: now",
                "## Headline: Segmentary campaign models",
                "row",
                "## Paul-fork runs",
                "fork table 0/2",
                "## Coverage",
                "coverage table",
                "## Inputs",
                "- campaign paul: `/data/x`",
            ]
        )

    monkeypatch.setattr(rad_report, "render", render)
    report = rad_report.Report(results=[], coverage=[], composition={}, inputs={})
    text = pub.comparison_markdown(report, {"paul"})
    assert "### Headline" in text and "### Inputs" in text and "published arm" in text
    assert "Paul-fork runs" not in text and "Coverage" not in text and "0/2" not in text


def test_refuses_push_url_that_differs_from_fetch_url(tmp_path, repos, files):
    remote, _, publisher = repos
    other = tmp_path / "other.git"
    sh(tmp_path, "init", "--quiet", "--bare", str(other))
    sh(publisher, "config", "remote.origin.pushurl", str(other))
    with pytest.raises(pub.Refusal, match="not the target"):
        pub.publish_once(args_for(tmp_path, remote, publisher))
    sh(publisher, "config", "--unset", "remote.origin.pushurl")
    sh(publisher, "config", f"url.{other}.pushInsteadOf", str(remote))
    with pytest.raises(pub.Refusal, match="not the target"):
        pub.publish_once(args_for(tmp_path, remote, publisher))


def test_refuses_clone_at_campaign_code_sha_or_inside_an_input(tmp_path, repos, files):
    remote, _, publisher = repos
    root = tmp_path / "campaign"
    root.mkdir()
    head = sh(publisher, "rev-parse", "HEAD")
    (root / "campaign.json").write_text(json.dumps({"code_sha": head}))
    args = args_for(tmp_path, remote, publisher)
    args.campaign = [root]
    with pytest.raises(pub.Refusal, match="code_sha"):
        pub.publish_once(args)
    args.campaign = [publisher / "runs"]
    with pytest.raises(pub.Refusal, match="overlaps input"):
        pub.publish_once(args)


def test_rebase_conflict_aborts_and_never_forces(tmp_path, repos, files, monkeypatch):
    remote, author, publisher = repos
    real = pub.git

    def conflicting_git(repo, *args):
        if args[0] == "push" and repo == publisher and not (author / TREE).exists():
            (author / TREE).mkdir(parents=True)
            (author / TREE / "README.md").write_text("Human edit of the same file\n")
            sh(author, "add", ".")
            sh(author, "commit", "--quiet", "-m", "Human edit")
            sh(author, "push", "--quiet", "origin", "main")
        return real(repo, *args)

    monkeypatch.setattr(pub, "git", conflicting_git)
    with pytest.raises(pub.GitError, match="rebase"):
        pub.publish_once(args_for(tmp_path, remote, publisher))
    assert sh(remote, "log", "--format=%s", "main").splitlines() == ["Human edit", "Initial"]
    assert not (publisher / ".git/rebase-merge").exists()
    assert not (publisher / ".git/rebase-apply").exists()


def test_test_split_and_unexpected_file_types_are_refused():
    for bad in ("paul/models/m/seed-0/best-auto-test/per-image.csv", "paul/test/x.json"):
        with pytest.raises(ValueError, match="test-split"):
            pub.check_paths({bad: ""})
    for bad in ("paul/models/m/seed-0/best-auto-val/0001.png", "paul/x.npy"):
        with pytest.raises(ValueError, match="file type"):
            pub.check_paths({bad: b""})
    pub.check_paths(
        {
            "paul/models/m/seed-0/best-auto-val/per-image-confusion.json.gz": b"",
            "paul/models/m/seed-0/best-auto-val/examples.jpg": b"",
            "paul/models/m/README.md": "",
        }
    )


def test_docs_checks_run_on_the_rendered_tree_before_commit(tmp_path, repos, files):
    remote, author, publisher = repos
    args = args_for(tmp_path, remote, publisher)
    files["paul/README.md"] = "[gone](models/x/README.md)\n"
    with pytest.raises(pub.DocsError, match=r"models/x/README\.md"):
        pub.publish_once(args)
    files["paul/README.md"] = "env /data/izadia1/envs/" + "rail" + "yard" + "/bin/python\n"
    with pytest.raises(pub.DocsError, match="legacy name"):
        pub.publish_once(args)
    assert sh(remote, "log", "--format=%s", "main") == "Initial"
    # The exact interpreter path in an arm record.json passes once main carries the exemption.
    files.pop("paul/README.md")
    files["paul/models/m/record.json"] = '{"python": "' + pub.LEGACY_ENV + 'bin/python"}\n'
    assert pub.publish_once(args)["pushed"]
    sh(author, "pull", "--quiet", "--ff-only", "origin", "main")
    (author / "tests/test_documentation.py").write_text("# no exemption\n")
    sh(author, "commit", "--quiet", "-am", "Drop exemption")
    sh(author, "push", "--quiet", "origin", "main")
    files["README.md"] = "# RAD\n\nv2\n"
    with pytest.raises(pub.Refusal, match="exemption"):
        pub.publish_once(args)


def test_failed_comparison_keeps_the_published_one(tmp_path, repos, monkeypatch):
    remote, _, publisher = repos
    outcome: dict = {"error": None}

    def render(*_args, **_kwargs):
        content = {"README.md": "# RAD\n"}
        if outcome["error"] is None:
            content["rad-comparison.csv"] = "a\n"
        return content, outcome["error"]

    monkeypatch.setattr(pub, "render_tree", render)
    args = args_for(tmp_path, remote, publisher)
    assert pub.publish_once(args)["pushed"]
    head = sh(remote, "rev-parse", "main")
    outcome["error"] = "samples changed"
    with pytest.raises(pub.ComparisonError, match="kept the published one"):
        pub.publish_once(args)
    assert sh(remote, "rev-parse", "main") == head
    assert f"{TREE}/rad-comparison.csv" in remote_files(remote)


def test_ci_skips_published_rad_results():
    workflow = (pub.CODE / ".github/workflows/checks.yml").read_text()
    import yaml

    ignored = yaml.safe_load(workflow)[True]["push"]["paths-ignore"]
    assert f"{TREE}/**" in ignored
