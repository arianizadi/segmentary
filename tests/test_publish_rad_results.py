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
        return dict(content), None, None

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
    # A dropped arm's whole directory disappears on the next cycle, with no special case.
    files["dropped-arm/README.md"] = "# dropped\n"
    files["dropped-arm/models/m/record.json"] = "{}\n"
    assert pub.publish_once(args)["pushed"]
    del files["dropped-arm/README.md"], files["dropped-arm/models/m/record.json"]
    assert pub.publish_once(args)["pushed"]
    assert not any(p.startswith(f"{TREE}/dropped-arm/") for p in remote_files(remote))
    assert not (publisher / TREE / "dropped-arm").exists()


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
    second = tmp_path / "datasets/rad_9_24_2026-fixed-grouped/audit/label-audit.json"
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
    files, error, cv_error = pub.render_tree(
        [root, tmp_path / "missing"], runs, tmp_path / "datasets", tmp_path / "v.yaml"
    )
    assert error == "samples changed" and cv_error is None
    assert not any(name.startswith(f"{pub.CV_DIR}/") for name in files)  # no --cv-campaign
    # The short study page: plain sections in order, details linked, no jargon headings.
    short = files["README.md"]
    headings = [line for line in short.splitlines() if line.startswith("## ")]
    assert headings == [
        "## What we tested",
        "## Key result",
        "## Results by split",
        "## Paul's paper model",
        "## Caveats",
        "## Details",
    ]
    assert "### Paul's split" in short and "### Scene-grouped split" in short
    assert "Not available this cycle: samples changed" in short
    assert "### Cross-validation over scenes\n\nNot published yet." in short
    assert "314 rail images labelled with 21 classes" in short
    assert "[Full details](details.md)" in short and "Label defects" not in short
    assert "HRNet-OCR, Paul's RailSem19 checkpoint | Paul's split | not scored yet" in short
    caveats = short.split("## Caveats", 1)[1].split("## Details", 1)[0]
    assert 0 < caveats.count("\n- ") <= 5
    assert "Images without mud-pumping are not counted" in caveats
    assert "still selected on the older mud-pumping IoU with pixels pooled" in caveats
    assert "each validation image that contains mud-pumping" in short
    assert " arm" not in short and "protocol" not in short and "±" not in short
    readme = files[pub.DETAILS]
    assert "Not rendered this cycle: samples changed" in readme
    assert "| [`paul`](paul/README.md) |" in readme and "| 1/2 | training 1 |" in readme
    assert "not initialized" in readme  # the fixed-grouped arm has no campaign yet
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
    assert "| Quantity | `paul`, `fixed-grouped` |" in readme
    assert "`fixed-grouped` rendered" in readme
    assert "fixed-stratified" not in readme and "two arms" in readme
    assert "stopped on 2026-10-05 at 8 of 40 jobs" in readme
    assert "`paper-hrnet__rs19-paul__arm-paul` (run `probe2-x`)" in readme
    assert "excluded (probe_epochs)" in readme and "queue: pending" in readme
    assert "Single seed" in readme and "Optimistic" in readme and "shares scenes" in readme
    arm = files["paul/README.md"]
    assert arm.startswith("# RAD 9/24: Paul's split (`paul`)")
    assert "[RAD 9/24 study](../README.md)" in arm and "none_stratified" in arm
    assert "Every model on this page was trained by us" in arm
    # Present-image tables (no comparison this cycle: unavailable cells), pooled runs relabelled.
    assert "Validation **mIoU (%)**: each class's IoU averaged over the validation images" in arm
    assert "All images with mud:" in arm and "Train-camera images with mud:" in arm
    assert "| Mud IoU, pixels pooled (%) |" in arm and "| Mud IoU (%) |" not in arm
    assert files["paul/results.csv"].startswith("Model,Initialization path,Seed,Status")
    assert "Mud IoU, pixels pooled (%)" in files["paul/results.csv"].splitlines()[0]
    page = files["paul/models/m/README.md"]
    assert "Study metrics, counting each class only on the validation images" in page
    assert f"| {pub.MUD_CAB} (%) | {pub.MUD_ALL} (%) |" in page
    assert "| rtis_only | 0 | — | — | — | — | — |" in page
    assert "**mud-pumping validation IoU, pixels pooled over all validation images**" in page
    assert "| Mud IoU, pixels pooled (%) |" in page
    assert f"## {pub.PER_CLASS}\n\nValidation IoU (%) of every class" in arm
    assert f"{pub.PER_CLASS}: IoU (%) of every class" in page
    assert page.count("Not available this cycle.") == 1  # no comparison: no per-class values
    assert f"[IoU of every class](paul/README.md{pub.PER_CLASS_ANCHOR})" in short
    assert "`rtis_only` = recipe pretrained weights" in arm
    assert "[RAD 9/24: Paul's split](../../README.md)" in files["paul/models/m/README.md"]
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
        return content, outcome["error"], None

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


# ----------------------------------------------------------------------------- cross-validation


@pytest.fixture
def cv_campaign(tmp_path):
    """A synthetic 3-fold CV campaign (tests/test_group_cv.py) with fold 2 not yet run."""
    from segmentary.data import group_cv
    from test_group_cv import fake_campaign, make, write_dataset

    dataset = write_dataset(tmp_path / "cv-data" / "ds")
    folds = tmp_path / "cv-data" / "cv"
    group_cv.materialize(dataset, make(dataset), folds)
    root, _ = fake_campaign(tmp_path / "cv-run", folds)
    (root / "state" / "m1--p--fold-2--seed-0.json").unlink()  # planned, not started
    return root, tmp_path / "cv-data" / "viewpoints.yaml"


def write_checkout(base: Path, files: dict[str, str | bytes]) -> Path:
    """The rendered tree inside a checkout-like directory with the guides it links."""
    for page in (
        pub.GUIDE,
        pub.CASE_GUIDE,
        pub.CV_GUIDE,
        "docs/results/paul-test-rtis/v2/README.md",
    ):
        (base / page).parent.mkdir(parents=True, exist_ok=True)
        (base / page).write_text("# page\n")
    (base / "tests").mkdir(exist_ok=True)
    (base / "tests/test_documentation.py").write_text(f'EXEMPT = "{TREE}/"\n')
    pub.write_tree(base, files)
    return base


def assert_documentation_rules(base: Path) -> None:
    """tests/test_documentation.py's link and legacy-name rules (and the no-± rule of
    tests/test_model_comparison_results.py) on the rendered tree."""
    import test_documentation as docs

    pub.docs_check(base)
    for page in sorted((base / TREE).rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        assert "±" not in text, page
        assert not re.search("rail" + "yard", text, re.IGNORECASE), page
        for raw in docs.MARKDOWN_LINK.findall(text):
            target = docs._local_target(page, raw)
            assert target is None or target.exists(), (page, raw)
            if target is not None:
                assert base.resolve() in target.parents, (page, raw)  # repo-relative


def test_cv_pages_render_with_partial_coverage_and_resolving_links(tmp_path, cv_campaign):
    root, viewpoints = cv_campaign
    files, _, cv_error = pub.render_tree(
        [], None, tmp_path / "datasets", viewpoints, cv_campaign=root
    )
    assert cv_error is None
    cv_readme = files[f"{pub.CV_DIR}/README.md"]
    csv_rows = files[f"{pub.CV_DIR}/cv-report.csv"].splitlines()
    header = csv_rows[0].split(",")
    assert header[: len(pub.cv_report.CSV_FIELDS)] == list(pub.cv_report.CSV_FIELDS)
    assert "iou_present_images:mud-pumping" in header
    assert any(r.startswith("m1,p,0,final,pooled,2,cab-view,") for r in csv_rows)
    assert "Generated:" not in cv_readme  # deterministic: unchanged records, no new commit
    assert cv_readme.startswith("# RAD 9/24: cross-validation over scenes (`synthetic-cv`)")
    assert "[RAD 9/24 study](../README.md)" in cv_readme
    assert "[How the cross-validation works](../../../guides/cross-validation.md)" in cv_readme
    assert "[`cv-report.csv`](cv-report.csv)" in cv_readme
    # Partial coverage: 2 of 3 folds of m1/p, nothing of m1/q; unfinished cells carry `*`.
    assert "2 of 4 runs done" in cv_readme
    p_row = next(x for x in cv_readme.splitlines() if x.startswith("| `m1` | p | 2/3 |"))
    assert p_row.count("*") == 4
    assert "| `m1` | q | 0/3 | — | — | — | — |" in cv_readme
    assert "| 2 | 0 | no state 1 | 1 |" in cv_readme  # cv_report's coverage table
    assert "Fold caveat" not in cv_readme  # fold 2 has no scored run yet: counts incomplete
    assert "Mud-pumping IoU, train-camera images with mud (n=" in cv_readme
    per_class = cv_readme.split(f"## {pub.PER_CLASS}", 1)[1].split("\n## ", 1)[0]
    assert "| Model | Starting point | mIoU (each class over images that contain it) |" in (
        per_class
    )
    assert "mud-pumping (n=" in per_class and "| `m1` | q* | — |" in per_class
    assert "mIoU (each class over images that contain it), all images" in cv_readme
    # The study page: CV section with folds done, link, and the caveat bullet.
    short = files["README.md"]
    section = short.split("### Cross-validation over scenes", 1)[1].split("## ", 1)[0]
    assert "3 of 4 runs done" not in section and "2 of 4 runs done" in section
    assert f"[Full report]({pub.CV_DIR}/README.md)" in section
    # No performance records in the synthetic campaign: speed, memory and parameters are "—".
    assert "| m1 | p | 50.0* | " in section and "* | — | — | — | 2/3 |" in section
    costs = " | ".join(pub.COST_HEADERS)
    assert f"| {pub.MUD_CAB} | {pub.MUD_ALL} | {pub.MIOU} | {costs} | Folds done |" in section
    assert pub.ALLOCATOR_NOTE not in section  # no allocator-only memory cell to explain
    assert f"[Cross-validation report]({pub.CV_DIR}/README.md)" in short
    assert_documentation_rules(write_checkout(tmp_path / "checkout", files))


def test_cv_failure_keeps_the_previous_pages(tmp_path, cv_campaign):
    root, viewpoints = cv_campaign
    previous = {
        f"{pub.CV_DIR}/README.md": b"# Last good CV report\n",
        f"{pub.CV_DIR}/cv-report.csv": b"model\n",
    }
    missing = tmp_path / "no-such-cv"
    files, _, cv_error = pub.render_tree(
        [], None, tmp_path / "datasets", viewpoints, cv_campaign=missing, cv_previous=previous
    )
    assert cv_error == f"{missing}/campaign.json does not exist"
    assert {k: files[k] for k in previous} == previous
    assert "Not refreshed this cycle:" in files["README.md"]
    assert f"[last published report]({pub.CV_DIR}/README.md) is kept" in files["README.md"]
    assert_documentation_rules(write_checkout(tmp_path / "kept", files))
    # A broken campaign record behaves the same; with nothing published, nothing is linked.
    (root / "plan.json").write_text("{")
    files, _, cv_error = pub.render_tree(
        [], None, tmp_path / "datasets", viewpoints, cv_campaign=root
    )
    assert cv_error and cv_error.startswith("JSONDecodeError")
    assert not any(name.startswith(f"{pub.CV_DIR}/") for name in files)
    assert f"]({pub.CV_DIR}/" not in files["README.md"]


def test_publish_cycle_keeps_published_cv_pages_when_the_cv_render_fails(
    tmp_path, repos, cv_campaign
):
    remote, author, publisher = repos
    root, viewpoints = cv_campaign
    rtis = author / "docs/results/paul-test-rtis/v2/README.md"  # linked from details.md
    rtis.parent.mkdir(parents=True)
    rtis.write_text("# RTIS v2\n")
    sh(author, "add", ".")
    sh(author, "commit", "--quiet", "-m", "RTIS page")
    sh(author, "push", "--quiet", "origin", "main")
    args = args_for(
        tmp_path, remote, publisher, "--cv-campaign", str(root), "--viewpoints", str(viewpoints)
    )
    first = pub.publish_once(args)
    assert first["pushed"] and first["cv_error"] is None
    page = f"{TREE}/{pub.CV_DIR}/README.md"
    assert {page, f"{TREE}/{pub.CV_DIR}/cv-report.csv"} <= remote_files(remote)
    published = sh(remote, "show", f"main:{page}")
    assert not pub.publish_once(args)["pushed"]  # deterministic: nothing changed, no commit
    # The campaign disappears: the cycle still publishes, keeping the CV pages verbatim.
    root.rename(root.with_name("moved"))
    second = pub.publish_once(args)
    assert second["cv_error"].endswith("campaign.json does not exist")
    assert sh(remote, "show", f"main:{page}") == published
    assert "Not refreshed this cycle" in sh(remote, "show", f"main:{TREE}/README.md")
    assert pub.run(args) == 0  # recorded, not a refusal; retried next cycle
    status = json.loads((tmp_path / "state/publisher-status.json").read_text())
    assert status["cv_error"] and status["error"] is None and not status["stopped"]
    # Once the campaign is back, the next cycle renders it again.
    root.with_name("moved").rename(root)
    assert pub.publish_once(args)["cv_error"] is None
    assert "Not refreshed" not in sh(remote, "show", f"main:{TREE}/README.md")


def test_cv_campaign_flag_is_an_input_the_clone_must_not_overlap(tmp_path, repos, files):
    remote, _, publisher = repos
    args = args_for(tmp_path, remote, publisher, "--cv-campaign", str(publisher / "cv"))
    with pytest.raises(pub.Refusal, match="overlaps input"):
        pub.publish_once(args)
    assert pub.parse(["--checkout", str(publisher)]).cv_campaign is None
    with pytest.raises(SystemExit):
        pub.parse(
            [
                *("--checkout", str(publisher), "--cv-campaign", str(tmp_path / "cv")),
                *("--state-dir", str(tmp_path / "cv" / "publisher")),
            ]
        )


def test_fold_caveat_counts_images_with_the_class_per_fold():
    import numpy as np

    cv_report = pub.cv_report
    mud, clean = np.array([[3, 1], [1, 5]]), np.array([[4, 0], [0, 0]])

    def scored(fold, n, view, group, matrix=mud):
        return [
            cv_report.Scored(f"{group}/{fold}{i}{view}", "sha", view, matrix, group)
            for i in range(n)
        ]

    def make(folds):
        runs = [
            cv_report.Run("m", "p", 0, k, f"m--p--fold-{k}", {cv_report.PRIMARY: images})
            for k, images in folds.items()
        ]
        names = ["background", "mud-pumping"]
        report = cv_report.Report({}, [0, 1], names, "mud-pumping", ["cab-view"], runs, {}, None)
        return pub.CrossValidation(report, [])

    # All images: 3 vs 3 (no fold dominates); train-camera: 3 of 4 in fold 0, one scene.
    folds = {
        0: scored(0, 3, "cab-view", "cab-scene") + scored(0, 1, "cab-view", "dry", clean),
        1: scored(1, 2, "track-level", "trackside-maintenance") + scored(1, 1, "cab-view", "x"),
    }
    assert pub.fold_caveat(make(folds), short=True) == (
        "fold 0 holds 3 of the 4 scored train-camera images with mud-pumping, all from one "
        "scene (`cab-scene`), so the train-camera numbers mostly measure that scene."
    )
    assert pub.fold_caveat(make(folds)) == (
        "Fold 0 holds 3 of the 4 scored train-camera images with mud-pumping, all from one "
        "scene (`cab-scene`). Pooled, the train-camera numbers mostly measure that scene, "
        "scored by models that never trained on it."
    )
    # One more track-level mud image: fold 1 now holds 4 of the 7 images with mud-pumping.
    folds[1].append(cv_report.Scored("t/9", "sha", "track-level", mud, "trackside-maintenance"))
    assert pub.fold_caveat(make(folds), short=True) == (
        "fold 1 holds 4 of the 7 scored images with mud-pumping, from 2 scenes "
        "(`trackside-maintenance`, `x`), so the all-images numbers mostly measure those scenes; "
        "fold 0 holds 3 of the 4 scored train-camera images with mud-pumping, all from one "
        "scene (`cab-scene`), so the train-camera numbers mostly measure that scene."
    )
    # Balanced folds, a fold without a scored run yet, or no focus class: no caveat.
    balanced = {0: scored(0, 2, "cab-view", "a"), 1: scored(1, 2, "cab-view", "b")}
    assert pub.fold_caveat(make(balanced)) is None
    assert pub.fold_caveat(make({0: folds[0]})) is None
    unfocused = make(folds)
    unfocused.report.focus = None
    assert pub.fold_caveat(unfocused) is None


def test_inference_cost_prefers_the_process_total_and_marks_allocator_only_memory():
    def record(**measurements):
        return {
            "status": "complete",
            "model": {"parameter_count": 314_917_910},
            "measurements": {"latency": {"fps": 38.35}, **measurements},
        }

    allocator = pub.cost_of(record(peak_reserved_bytes=3_359_637_504))
    assert allocator is not None and allocator.cells() == ["38.4", "3.36†", "314.9"]
    total = pub.cost_of(
        record(peak_reserved_bytes=3_359_637_504, process_total_bytes=3_900_000_000)
    )
    assert total is not None and total.cells() == ["38.4", "3.90", "314.9"]
    assert pub.cost_of(record(process_total_bytes=None, peak_reserved_bytes=1)).cells()[1] == (
        "0.00†"
    )
    assert pub.cost_of({"status": "waiting_for_idle_gpu"}) is None
    assert pub.cost_cells(None) == ["—", "—", "—"]
    # Several folds: mean FPS, the largest memory, total only when every record has it.
    both = pub.combined_cost([allocator, total])
    assert both is not None and both.cells() == ["38.4", "3.90†", "314.9"]
    assert pub.combined_cost([]) is None
    rows = [["m", *allocator.cells()]]
    assert pub.allocator_note(rows) == [pub.ALLOCATOR_NOTE, ""]
    assert "excludes the CUDA context" in pub.ALLOCATOR_NOTE
    assert pub.allocator_note([["m", *total.cells()]]) == []


def test_per_class_table_shows_every_class_and_dashes_for_absent_ones():
    metrics = {
        "present_miou": 0.5,
        "present_class_iou": {"rail": 0.75, "sky": None, "mud-pumping": 0.25},
        "present_class_images": {"rail": 3, "sky": 0, "mud-pumping": 2},
    }
    lines = pub.per_class_table(["Model"], [(["a"], metrics), (["b"], None)])
    assert lines[0] == (f"| Model | {pub.MIOU} | rail (n=3) | sky (n=0) | mud-pumping (n=2) |")
    assert lines[2] == "| a | 50.00 | 75.00 | — | 25.00 |"
    assert lines[3] == "| b | — | — | — | — |"
    assert pub.per_class_table(["Model"], [(["b"], None)]) == ["Not available this cycle."]
