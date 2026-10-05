"""rad_subset_metrics and rad_report on small synthetic runs with known confusions."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from scripts import rad_report
from scripts import rad_subset_metrics as rsm

ROOT = Path(__file__).resolve().parents[1]
NAMES = rsm.class_names()
MUD = NAMES.index("mud-pumping")
N = rsm.NUM_CLASSES


def matrix(cells: dict[tuple[int, int], int]) -> np.ndarray:
    m = np.zeros((N, N), np.int64)
    for (gt, pred), count in cells.items():
        m[gt, pred] = count
    return m


# A: cab-view, 6 TP / 2 FN / 2 FP mud. B: track-level maintenance close-up, 90 TP / 10 FN.
# C: cab-view without mud; one pixel of class 1 predicted as class 2 (absent from GT).
MATRICES = {
    "g-cab/0001": matrix({(0, 0): 10, (0, MUD): 2, (MUD, MUD): 6, (MUD, 0): 2}),
    "trackside-maintenance/0002": matrix({(0, 0): 20, (MUD, MUD): 90, (MUD, 0): 10}),
    "g-cab/0003": matrix({(1, 1): 4, (1, 2): 1}),
}
VIEWS = {"0001": "cab-view", "0002": "track-level", "0003": "cab-view", "0004": "other"}


def sha(stem: str) -> str:
    return hashlib.sha256(f"image-{stem}".encode()).hexdigest()


def samples() -> list[dict]:
    rows = []
    for key, m in [*MATRICES.items(), ("g-cab/0004", matrix({(0, 0): 3}))]:
        group, stem = key.split("/")
        pixels = {str(c): int(n) for c, n in enumerate(m.sum(axis=1)) if n}
        rows.append(
            {
                "key": key,
                "split": "train" if stem == "0004" else "val",
                "group": group,
                "stem": stem,
                "image_sha256": sha(stem),
                "class_pixels": pixels | {"255": 7},
            }
        )
    return rows


def viewpoints() -> dict:
    return {sha(stem): {"stem": stem, "viewpoint": v} for stem, v in VIEWS.items()}


def total() -> np.ndarray:
    return sum(MATRICES.values(), np.zeros((N, N), np.int64))


def joined():
    return rsm.join(dict(MATRICES), samples(), viewpoints(), "val", total())


def test_subset_math_matches_hand_computation():
    result = rsm.compute(joined(), NAMES)
    everything = result["all"]
    assert everything["images"] == 3 and everything["images_with_mud_gt"] == 2
    assert everything["mud_gt_pixels"] == 108
    assert everything["mud_iou"] == pytest.approx(96 / 110)
    assert everything["mud_precision"] == pytest.approx(96 / 98)
    assert everything["mud_recall"] == pytest.approx(96 / 108)
    assert everything["mud_image_mean_iou"] == pytest.approx((0.6 + 0.9) / 2)
    gt_classes = [30 / 44, 4 / 5, 96 / 110]  # classes 0, 1 and mud have ground truth
    assert everything["gt_class_miou"] == pytest.approx(sum(gt_classes) / 3)
    assert everything["miou"] == pytest.approx(sum(gt_classes) / 4)  # + class 2, IoU 0
    assert everything["top5_mud_share"] == pytest.approx(1.0)

    cab = result["cab-view"]
    assert cab["keys"] == ["g-cab/0001", "g-cab/0003"]
    assert cab["mud_iou"] == pytest.approx(0.6) and cab["mud_image_mean_iou"] == 0.6
    assert result["not-cab-view"]["keys"] == ["trackside-maintenance/0002"]
    assert result["not-cab-view"]["mud_iou"] == pytest.approx(0.9)
    excl = result["excl-trackside-maintenance"]
    assert excl["keys"] == ["g-cab/0001", "g-cab/0003"] and excl["mud_gt_pixels"] == 8


def test_top_k_share_and_empty_subset(monkeypatch):
    monkeypatch.setattr(rsm, "TOP_K", 1)
    images = joined()
    assert rsm.subset_metrics(images, NAMES)["top5_mud_share"] == pytest.approx(100 / 108)
    empty = rsm.subset_metrics([], NAMES)
    assert empty["images"] == 0 and empty["mud_iou"] is None and empty["miou"] is None
    no_mud = rsm.subset_metrics([i for i in images if i.stem == "0003"], NAMES)
    assert no_mud["mud_iou"] is None and no_mud["top5_mud_share"] is None
    assert no_mud["mud_image_mean_iou"] is None and no_mud["gt_class_miou"] == 0.8


def test_join_is_by_image_sha256_not_stem():
    rows = samples()
    # Same stems, swapped image content: the viewpoint must follow the image hash.
    a, b = (r for r in rows if r["stem"] in ("0001", "0002"))
    a["image_sha256"], b["image_sha256"] = b["image_sha256"], a["image_sha256"]
    with pytest.raises(rsm.SubsetError, match="viewpoint stem '0002' differs"):
        rsm.join(dict(MATRICES), rows, viewpoints(), "val", total())
    # An unknown image hash is never resolved through its stem.
    rows = samples()
    rows[0]["image_sha256"] = "f" * 64
    with pytest.raises(rsm.SubsetError, match="has no viewpoint"):
        rsm.join(dict(MATRICES), rows, viewpoints(), "val", total())
    images = {i.stem: i for i in joined()}
    assert images["0002"].viewpoint == "track-level" and images["0002"].image_sha256 == sha("0002")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda m, s, t: m.pop("g-cab/0003"), "missing \\['g-cab/0003'\\]"),
        (lambda m, s, t: m.update({"g-cab/0004": matrix({(0, 0): 3})}), "extra"),
        (lambda m, s, t: t.__setitem__((0, 0), t[0, 0] + 1), "do not sum"),
        (lambda m, s, t: s[0]["class_pixels"].update({"0": 99}), "class_pixels"),
    ],
)
def test_validation_failures(edit, message):
    matrices, rows, reported = dict(MATRICES), samples(), total()
    edit(matrices, rows, reported)
    with pytest.raises(rsm.SubsetError, match=message):
        rsm.join(matrices, rows, viewpoints(), "val", reported)


def test_test_split_is_refused():
    rows = samples()
    for row in rows:
        row["split"] = "test"
    with pytest.raises(rsm.SubsetError, match="never test"):
        rsm.join(dict(MATRICES), rows, viewpoints(), "test", total())


def test_tracked_viewpoint_file_covers_all_314_images():
    path = ROOT / "configs/datasets/rad_9_24_2026-viewpoints.yaml"
    data = yaml.safe_load(path.read_text())
    images = rsm.load_viewpoints(path)
    assert len(images) == 314
    assert sorted(e["stem"] for e in images.values()) == [f"{i:04d}" for i in range(314)]
    counts = {v: sum(e["viewpoint"] == v for e in images.values()) for v in rsm.VIEWPOINTS}
    assert counts == data["counts"] and sum(counts.values()) == 314
    assert all(e["method"] and "note" in e for e in images.values())


# ----------------------------------------------------------------------------- report


def write_gz(path: Path, matrices: dict[str, np.ndarray]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(
        json.dumps({k: v.tolist() for k, v in matrices.items()}, separators=(",", ":")).encode(),
        mtime=0,
    )
    path.write_bytes(data)
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def make_arm(datasets: Path, arm: str) -> str:
    base = datasets / f"rad_9_24_2026-{arm}"
    classes = [{"id": i, "name": n} for i, n in enumerate(NAMES)]
    write_json(base / "classes.json", {"classes": classes, "ignore_index": 255})
    path = write_json(base / "audit/samples.json", samples())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_campaign(tmp: Path, datasets: Path, arm: str, scale: int = 1) -> Path:
    root = tmp / "runs" / f"{arm}-seed0"
    audit = make_arm(datasets, arm)
    write_json(
        root / "campaign.json",
        {"dataset": f"rad_9_24_2026-{arm}", "dataset_audit_sha256": audit},
    )
    jobs = [
        {"name": "m1--rtis_only--seed-0", "model": "m1", "protocol": "rtis_only"},
        {"name": "m2--rtis_only--seed-0", "model": "m2", "protocol": "rtis_only"},
    ]
    write_json(root / "plan.json", {"jobs": jobs})
    matrices = dict(MATRICES)
    if scale != 1:  # a better model: fewer mud false negatives on image A
        matrices["g-cab/0001"] = matrix({(0, 0): 10, (0, MUD): 2, (MUD, MUD): 8})
    reported = sum(matrices.values(), np.zeros((N, N), np.int64)).tolist()
    artifact = write_gz(root / "future-runs/m1/diagnostics/best-auto-val/pic.json.gz", matrices)
    write_json(
        root / "state" / f"{jobs[0]['name']}.json",
        {
            "status": "completed",
            "training": {
                "seed": 0,
                "config": {"train": {"selection_metric": "val_iou/mud-pumping"}},
            },
            "evaluation": {"metrics": {"confusion": reported}},
            "collection": {
                "diagnostics": {
                    "results": {
                        "best-auto-val": {"split": "val", "metrics": {"confusion": reported}}
                    }
                },
                "artifacts": {"best-auto-val": {"per-image-confusion.json.gz": artifact}},
            },
        },
    )
    write_json(root / "state" / f"{jobs[1]['name']}.json", {"status": "queued"})
    return root


def make_fork(tmp: Path, audit: str) -> Path:
    runs = tmp / "runs" / "forks"
    label = "paper-hrnet__rs19-paul__arm-paul"
    owners = {"map_city": "nvidia", "rs19": "paul", "rad": "ours"}
    run = runs / label
    write_json(
        run / "provenance.json", {"label": label, "owner_of_each_checkpoint_in_chain": owners}
    )
    record = write_gz(run / "results-val-per-image-confusion.json.gz", dict(MATRICES))
    write_json(
        run / "results-val.json",
        {
            "label": label,
            "split": "val",
            "inference": "whole-image single-scale",
            "metrics": {"confusion": total().tolist()},
            "arm_root": {"samples_sha256": audit},
            "per_image_confusion": record,
        },
    )
    probe = runs / f"probe2-{label}"
    write_json(
        probe / "provenance.json",
        {"label": label, "probe_epochs": 2, "owner_of_each_checkpoint_in_chain": owners},
    )
    pending = runs / "paper-sfnet__rs19-ours__arm-fixed-grouped"
    write_json(pending / "provenance.json", {"label": pending.name})
    write_json(pending / "gpu-assignment.json", {"status": "running"})
    return runs


def fixture(tmp_path: Path) -> list[str]:
    datasets = tmp_path / "datasets"
    paul = make_campaign(tmp_path, datasets, "paul")
    fixed = make_campaign(tmp_path, datasets, "fixed-grouped", scale=2)
    audit = hashlib.sha256((datasets / "rad_9_24_2026-paul/audit/samples.json").read_bytes())
    forks = make_fork(tmp_path, audit.hexdigest())
    vp = tmp_path / "viewpoints.yaml"
    vp.write_text(yaml.safe_dump({"images": viewpoints()}))
    return [
        "--campaign",
        str(paul),
        "--campaign",
        str(fixed),
        "--fork-runs",
        str(forks),
        "--datasets-root",
        str(datasets),
        "--viewpoints",
        str(vp),
    ]


def test_report_renders_tables_csv_and_coverage(tmp_path):
    args = fixture(tmp_path)
    out = tmp_path / "out"
    assert rad_report.main([*args, "--out", str(out)]) == 0
    readme = (out / "README.md").read_text()
    rows = (out / "rad-comparison.csv").read_text().splitlines()
    assert rows[0].split(",") == list(rad_report.CSV_FIELDS)
    assert len(rows) == 1 + 3 * len(rsm.SUBSETS)  # two campaign jobs + one fork run
    fork_all = next(r for r in rows if r.startswith("fork,") and ",all," in r)
    assert "paper-hrnet__rs19-paul__arm-paul" in fork_all
    assert "map_city:nvidia -> rs19:paul -> rad:ours" in fork_all
    assert f",{96 / 110:.6f}," in fork_all

    # headline: P and FG cells for m1; cab-view mud IoU 60.0 (P) vs 80.0 (FG); m2 not completed
    headline = next(line for line in readme.splitlines() if line.startswith("| m1 |"))
    cells = [c.strip() for c in headline.strip("|").split("|")]
    assert cells[:2] == ["m1", "rtis_only"]
    assert cells[2 + 4 : 2 + 6] == ["60.0", "80.0"]
    assert not any(line.startswith("| m2 |") for line in readme.splitlines())
    effect = next(line for line in readme.splitlines() if "| split |" in line)
    assert "+20.0" in effect  # cab-view mud IoU 0.6 -> 0.8
    assert "| label fix |" not in readme and "fixed-stratified" not in readme
    assert "FS" not in readme
    assert "## How to read this" in readme and "deployment-relevant" in readme
    assert "| `paper-hrnet__rs19-paul__arm-paul` | map_city:nvidia -> rs19:paul -> rad:ours |" in (
        readme
    )
    assert "| segmentary | paul | 1/2 | queued 1 |" in readme
    assert "| segmentary | fixed-grouped | 1/2 | queued 1 |" in readme
    assert "excluded (probe_epochs)" in readme and "fixed-grouped` " in readme
    assert "running" in readme
    assert "best-auto-test" not in readme and "results-test" not in readme
    # caveats: selection on val, single seed, arm definitions, mud image counts per arm
    assert "These val numbers are optimistic" in readme and "`val_iou/mud-pumping`" in readme
    assert "Every campaign result is seed 0" in readme
    assert "`paul` = Paul's delivered masks" in readme and "trained by us" in readme
    assert "changes **both** the labels and the split policy" in readme
    assert "stopped on 2026-10-05 at 8 of 40 jobs" in readme and "-0.1 on average" in readme
    assert "cannot be attributed to the split" in readme
    assert "Split = FG - P" in readme
    assert "mud IoU cab P (n=1)" in readme and "mud IoU P (n=2)" in readme
    assert "1 track-level close-ups from the `trackside-maintenance` scene group" in readme
    assert "one maintenance sequence" not in readme and "shares recordings" not in readme
    assert "`rs19-paul` means the RS19 stage uses Paul's checkpoint" in readme
    assert "All 1 come from the `g-cab` scene group." in readme
    assert "mostly measure that one camera setup" in readme


def test_group_note_is_shown_for_the_deciding_cab_view_group(tmp_path, monkeypatch):
    monkeypatch.setitem(rad_report.GROUP_NOTES, "g-cab", "a low-mounted forward camera")
    out = tmp_path / "out"
    assert rad_report.main([*fixture(tmp_path), "--out", str(out)]) == 0
    assert "`g-cab` scene group; judged visually, a low-mounted forward camera." in (
        (out / "README.md").read_text()
    )


def test_report_is_deterministic_apart_from_generated_line(tmp_path):
    args = fixture(tmp_path)
    for name in ("a", "b"):
        rad_report.main([*args, "--out", str(tmp_path / name)])
    assert (tmp_path / "a/rad-comparison.csv").read_bytes() == (
        tmp_path / "b/rad-comparison.csv"
    ).read_bytes()
    strip = [
        [
            line
            for line in (tmp_path / n / "README.md").read_text().splitlines()
            if "Generated" not in line
        ]
        for n in ("a", "b")
    ]
    assert strip[0] == strip[1]


def test_report_fails_closed(tmp_path):
    args = fixture(tmp_path)
    paul = Path(args[1])
    with pytest.raises(SystemExit, match="inside input root"):
        rad_report.main([*args, "--out", str(paul / "report")])
    gz = paul / "future-runs/m1/diagnostics/best-auto-val/pic.json.gz"
    gz.write_bytes(gzip.compress(b"{}", mtime=0))
    with pytest.raises(SystemExit, match="differs from the SHA-256"):
        rad_report.main([*args, "--out", str(tmp_path / "out")])


def test_report_refuses_changed_arm_samples(tmp_path):
    args = fixture(tmp_path)
    samples_path = tmp_path / "datasets/rad_9_24_2026-paul/audit/samples.json"
    samples_path.write_text(samples_path.read_text() + " ")
    with pytest.raises(SystemExit, match="differs from the campaign"):
        rad_report.main([*args, "--out", str(tmp_path / "out")])


def test_report_path_map_rewrites_recorded_artifact_paths(tmp_path):
    args = fixture(tmp_path)
    moved = tmp_path / "moved"
    (tmp_path / "runs").rename(moved)
    remapped = [a.replace(str(tmp_path / "runs"), str(moved)) for a in args]
    with pytest.raises(SystemExit, match=r"m1--rtis_only--seed-0\.json: .*does not exist|No such"):
        rad_report.main([*remapped, "--out", str(tmp_path / "out")])
    rad_report.main(
        [*remapped, "--out", str(tmp_path / "out"), "--path-map", f"{tmp_path / 'runs'}={moved}"]
    )
    assert (tmp_path / "out/README.md").is_file()


def state_path(args: list[str], arm_index: int = 1) -> Path:
    return Path(args[arm_index]) / "state" / "m1--rtis_only--seed-0.json"


def test_completed_job_without_selected_diagnostics_is_not_counted_completed(tmp_path):
    args = fixture(tmp_path)
    path = state_path(args)
    state = json.loads(path.read_text())
    del state["collection"]
    path.write_text(json.dumps(state))
    out = tmp_path / "out"
    assert rad_report.main([*args, "--out", str(out)]) == 0
    readme = (out / "README.md").read_text()
    assert "| segmentary | paul | 0/2 | completed, no best-auto-val diagnostics 1, queued 1 |" in (
        readme
    )
    assert "`m1--rtis_only--seed-0`: completed, no best-auto-val diagnostics" in readme


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (
            lambda args, tmp: next(Path(args[1]).rglob("pic.json.gz")).unlink(),
            "does not exist|No such",
        ),
        (
            lambda args, tmp: (Path(args[1]) / "campaign.json").unlink(),
            "campaign.json does not exist",
        ),
        (
            lambda args, tmp: state_path(args).write_text(
                json.dumps(
                    {
                        **json.loads(state_path(args).read_text()),
                        "collection": {
                            **json.loads(state_path(args).read_text())["collection"],
                            "artifacts": {},
                        },
                    }
                )
            ),
            "m1--rtis_only--seed-0.json: KeyError",
        ),
    ],
)
def test_missing_inputs_fail_with_a_clean_message_naming_the_job(tmp_path, break_it, message):
    args = fixture(tmp_path)
    break_it(args, tmp_path)
    with pytest.raises(SystemExit, match=message):
        rad_report.main([*args, "--out", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


def test_fork_without_owner_record_fails_cleanly(tmp_path):
    args = fixture(tmp_path)
    forks = Path(args[args.index("--fork-runs") + 1])
    prov = forks / "paper-hrnet__rs19-paul__arm-paul/provenance.json"
    prov.write_text(json.dumps({"label": "paper-hrnet__rs19-paul__arm-paul"}))
    with pytest.raises(SystemExit, match=r"results-val\.json: KeyError"):
        rad_report.main([*args, "--out", str(tmp_path / "out")])


def test_unparseable_fork_label_and_missing_arm_are_reported(tmp_path):
    args = fixture(tmp_path)
    del args[2:4]  # no fixed-grouped campaign either
    forks = Path(args[args.index("--fork-runs") + 1])
    write_json(forks / "odd-run/provenance.json", {"label": "not-a-label"})
    datasets = Path(args[args.index("--datasets-root") + 1])
    (datasets / "rad_9_24_2026-fixed-grouped/audit/samples.json").unlink()
    out = tmp_path / "out"
    assert rad_report.main([*args, "--out", str(out)]) == 0
    readme = (out / "README.md").read_text()
    assert "| fork | ? | 0/1 | not a RAD-stage label 'not-a-label' 1 |" in readme
    assert "| fixed-grouped | dataset not found |" in readme
    assert "Prepared dataset not found for `fixed-grouped`" in readme
    assert "samples fixed-grouped: `not found under" in readme


def test_out_inside_datasets_root_is_refused(tmp_path):
    args = fixture(tmp_path)
    datasets = Path(args[args.index("--datasets-root") + 1])
    with pytest.raises(SystemExit, match="inside input root"):
        rad_report.main([*args, "--out", str(datasets / "report")])


def test_reported_total_checks_selected_diagnostics():
    state = {
        "evaluation": {"metrics": {"confusion": total().tolist()}},
        "collection": {
            "diagnostics": {
                "results": {"best-auto-val": {"metrics": {"confusion": total().tolist()}}}
            }
        },
    }
    assert np.array_equal(rsm.reported_total(state), total())
    state["collection"]["diagnostics"]["results"]["best-auto-val"]["metrics"]["confusion"][0][
        0
    ] += 1
    with pytest.raises(rsm.SubsetError, match="differs from the evaluation"):
        rsm.reported_total(state)
