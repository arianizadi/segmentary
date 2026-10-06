"""Stratified group k-fold CV end to end on a tiny synthetic folder dataset (no GPU)."""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import os
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
import yaml
from albumentations import Compose
from PIL import Image

from segmentary.data import group_cv
from segmentary.taxonomy import load_space

ROOT = Path(__file__).resolve().parents[1]
NAMES = list(load_space(ROOT / "taxonomy", "paul-test-rtis").names)
ID = {name: i for i, name in enumerate(NAMES)}
MUD = ID["mud-pumping"]
W, H = 12, 10
# key: (split, extra classes, small image, viewpoint); the group is the key's directory.
IMAGES = {
    "a/0000": ("train", ["mud-pumping"], False, "cab-view"),
    "a/0001": ("train", ["mud-pumping", "person"], False, "cab-view"),
    "a/0002": ("train", [], False, "track-level"),
    "b/0003": ("val", ["mud-pumping"], False, "track-level"),
    "b/0004": ("val", ["standing-water"], False, "cab-view"),
    "c/0005": ("train", ["mud-pumping"], False, "cab-view"),
    "c/0006": ("train", ["mud-pumping"], True, "track-level"),
    "d/0007": ("train", ["truck"], False, "other"),
    "d/0008": ("train", [], False, "cab-view"),
    "e/0009": ("val", ["standing-water"], False, "cab-view"),
    "e/0010": ("val", [], False, "track-level"),
    "f/0011": ("train", ["standing-water"], True, "cab-view"),
    "t/0012": ("test", ["mud-pumping"], False, "cab-view"),
    "t/0013": ("test", [], False, "cab-view"),
}
OPTIONS = dict(
    folds=3,
    seed=0,
    restarts=20,
    anomaly_classes=("mud-pumping", "standing-water"),
    rare_threshold=3,
    val_min_side=8,
    require_classes=("mud-pumping",),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_dataset(root: Path, images=IMAGES) -> Path:
    """A prepared grouped folder dataset with classes.json and an audit like prepare_rad's."""
    splits: dict = {"train": [], "val": [], "test": [], "groups": {}, "_grouping_status": "visual"}
    samples, views = [], {}
    for i, (key, (split, extra, small, view)) in enumerate(images.items()):
        w, h = (6, 6) if small else (W, H)
        mask = np.full((h, w), ID["terrain"], np.uint8)
        for row, name in enumerate(extra):
            mask[row] = ID[name]
        mask[-1, -1] = 255
        image = root / "images" / split / f"{key}.png"
        target = root / "masks" / split / f"{key}.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), (i * 15, 40, 90)).save(image)
        Image.fromarray(mask).save(target)
        splits[split].append(key)
        splits["groups"][key] = key.split("/")[0]
        counts = np.bincount(mask.ravel(), minlength=256)
        samples.append(
            {
                "key": key,
                "split": split,
                "group": key.split("/")[0],
                "stem": key.split("/")[1],
                "image_extension": ".png",
                "width": w,
                "height": h,
                "image_sha256": sha(image),
                "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest(),
                "class_pixels": {str(c): int(n) for c, n in enumerate(counts) if n},
            }
        )
        views[sha(image)] = {"stem": key.split("/")[1], "viewpoint": view}
    (root / "splits.json").write_text(json.dumps(splits))
    (root / "audit").mkdir()
    (root / "audit/samples.json").write_text(json.dumps(samples))
    classes = [{"id": i, "name": n} for i, n in enumerate(NAMES)]
    (root / "classes.json").write_text(json.dumps({"classes": classes, "ignore_index": 255}))
    (root.parent / "viewpoints.yaml").write_text(yaml.safe_dump({"images": views}))
    return root


@pytest.fixture
def dataset(tmp_path):
    return write_dataset(tmp_path / "ds")


def make(root: Path, **extra):
    return group_cv.make_spec(root, viewpoints=root.parent / "viewpoints.yaml", **(OPTIONS | extra))


def objective(spec: dict, fold_of: dict[str, int]) -> Fraction:
    """The documented objective recomputed with exact fractions from the assignments."""
    rows = spec["assignments"]
    scored = [k for k, r in rows.items() if r["scored"]]
    total = Fraction(0)
    for column in spec["method"]["balance_columns"]:
        members = [
            k for k in scored if column == group_cv.IMAGES_COLUMN or column in rows[k]["labels"]
        ]
        for k in range(spec["method"]["folds"]):
            hits = sum(fold_of[rows[m]["group"]] == k for m in members)
            total += (Fraction(hits, len(members)) - Fraction(1, spec["method"]["folds"])) ** 2
    return total


def test_spec_assigns_whole_groups_and_is_a_global_optimum(dataset):
    spec = make(dataset)
    assert json.dumps(spec, sort_keys=True) == json.dumps(make(dataset), sort_keys=True)
    rows = spec["assignments"]
    assert rows["t/0012"]["role"] == "holdout" and rows["t/0012"]["fold"] is None
    assert rows["f/0011"]["role"] == "train_all_folds"  # no scorable image in group f
    assert rows["c/0006"]["role"] == "cv_fold" and rows["c/0006"]["scored"] is False
    for group in "abcde":
        assert len({r["fold"] for r in rows.values() if r["group"] == group}) == 1
    report = spec["report"]
    assert report["small_images_never_scored"] == ["c/0006", "f/0011"]
    assert report["holdout_groups"] == ["t"] and report["scored_images"] == 10
    assert sum(f["label_images"]["mud-pumping"] for f in report["folds"]) == 4
    assert sum(f["label_pixel_share"]["mud-pumping"] for f in report["folds"]) == pytest.approx(1)
    cab = [f["label_images_by_viewpoint"]["cab-view"]["mud-pumping"] for f in report["folds"]]
    assert sum(cab) == 3
    assert spec["method"]["rare_classes"] == ["person", "truck"]
    warned = {w["label"]: w for w in report["label_coverage_warnings"]}
    # Labels with fewer source groups than folds must miss a fold: listed, not fatal.
    assert set(warned) == {"person", "standing-water", "truck"}
    assert warned["standing-water"]["source_groups"] == 2
    groups = sorted({r["group"] for r in rows.values() if r["role"] == "cv_fold"})
    scored_groups = {r["group"] for r in rows.values() if r["scored"]}
    feasible = [
        objective(spec, fold_of)
        for combo in itertools.product(range(3), repeat=len(groups))
        if {(fold_of := dict(zip(groups, combo, strict=True)))[g] for g in scored_groups}
        == {0, 1, 2}
    ]
    chosen = {r["group"]: r["fold"] for r in rows.values() if r["role"] == "cv_fold"}
    assert objective(spec, chosen) == min(feasible)
    assert Fraction(report["search"]["objective_exact"]) == min(feasible)
    table = group_cv.fold_table(spec)
    assert "cab-view mud-pumping images" in table and "person absent from folds" in table


def test_spec_fails_closed(tmp_path, dataset):
    one = {
        k: v
        for k, v in IMAGES.items()
        if not (k.startswith(("b/", "c/")) and "mud-pumping" in v[1])
    }
    with pytest.raises(group_cv.CvError, match="scored in 1 fold"):
        make(write_dataset(tmp_path / "x" / "one", one))
    with pytest.raises(group_cv.CvError, match="cannot fill 6 folds"):
        make(dataset, folds=6)
    with pytest.raises(group_cv.CvError, match="absent from every mask"):
        make(dataset, anomaly_classes=("flood",))
    splits = json.loads((dataset / "splits.json").read_text())
    del splits["groups"]
    (dataset / "splits.json").write_text(json.dumps(splits))
    with pytest.raises(group_cv.CvError, match="no groups map"):
        make(dataset)


def test_materialized_fold_views_are_standard_grouped_datasets(tmp_path, dataset):
    from dataclasses import replace

    from scripts import run_rtis_campaign as rtis

    from segmentary.config import load_experiment
    from segmentary.data.loaders import build_dataset

    spec = make(dataset)
    out = tmp_path / "cv"
    record = group_cv.materialize(dataset, spec, out)
    assert record["files"] == {"hardlinked": 2 * (14 * 3 - 1)}  # c/0006 left out of its fold
    assert json.loads((out / group_cv.SPEC_NAME).read_text()) == spec
    fold = spec["assignments"]["c/0005"]["fold"]
    view = out / f"fold-{fold}"
    splits = json.loads((view / "splits.json").read_text())
    assert splits["_cv_fold"] == fold and splits["_cv_excluded_small_images"] == ["c/0006"]
    assert splits["_cv_spec_sha256"] == sha(out / group_cv.SPEC_NAME)
    assert "c/0005" in splits["val"] and "f/0011" in splits["train"]
    assert splits["test"] == ["t/0012", "t/0013"] and splits["groups"]["c/0005"] == "c"
    image = view / "images/val/c/0005.png"
    assert os.stat(image).st_nlink >= 2
    samples = json.loads((view / "audit/samples.json").read_text())
    rtis.verify_samples(view, samples)
    assert {s["key"]: s["split"] for s in samples}["c/0005"] == "val"
    cfg = load_experiment(
        [
            ROOT / "configs/base.yaml",
            ROOT / "configs/models/segformer_b2.yaml",
            ROOT / "configs/datasets/rad_9_24_2026-cv.yaml",
        ]
    )
    data = replace(cfg.stages[0].data[0], root=str(view))
    space = load_space(ROOT / "taxonomy", "paul-test-rtis")
    for split in ("train", "val", "test"):
        loaded = build_dataset(data, space, ROOT / "taxonomy", split, Compose([]))
        assert sorted(s.key for s in loaded.samples) == sorted(splits[split])
    with pytest.raises(group_cv.CvError, match="already exists"):
        group_cv.materialize(dataset, spec, out)
    spec["assignments"]["a/0000"]["image_sha256"] = "0" * 64
    with pytest.raises(group_cv.CvError, match="images differ"):
        group_cv.materialize(dataset, spec, tmp_path / "bad")


def test_make_split_entry_point_dispatches_the_cv_scheme(tmp_path, dataset, capsys):
    from segmentary import make_split

    spec_out = tmp_path / "spec.json"
    argv = ["--scheme", "stratified-group-kfold", "--root", str(dataset), "--folds", "3"]
    argv += ["--restarts", "5", "--anomaly-classes", "mud-pumping,standing-water"]
    argv += ["--rare-threshold", "3", "--val-min-side", "8", "--spec-out", str(spec_out)]
    assert make_split.main(argv) == 0
    assert "| fold | groups |" in capsys.readouterr().out
    spec = json.loads(spec_out.read_text())
    assert (
        make_split.main([*argv[:4], "--spec", str(spec_out), "--out-root", str(tmp_path / "v")])
        == 0
    )
    assert sha(tmp_path / "v" / group_cv.SPEC_NAME) == sha(spec_out)
    assert spec["method"]["folds"] == 3


# ----------------------------------------------------------------------------- campaign


@pytest.fixture
def cv_root(tmp_path, dataset):
    root = tmp_path / "cv"
    group_cv.materialize(dataset, make(dataset), root)
    return root


MANIFEST = {
    "dataset_config": str(ROOT / "configs/datasets/rad_9_24_2026-cv.yaml"),
    "model_catalog": str(ROOT / "configs/campaigns/all_models_cityscapes_railsem19.yaml"),
    "target_steps": 4,
    "batch_size": 2,
    "accumulation": 1,
    "validation_interval": 2,
    "protocols": {"rtis_only": {"label": "x", "source_protocol": None}},
    "seeds": [0],
    "models": ["smp_fpn_resnet50"],
    "cross_validation": {
        "scheme": "stratified-group-kfold",
        "folds": 3,
        "seed": 0,
        "restarts": 20,
        "stratify": {"anomaly_classes": ["standing-water", "mud-pumping"], "rare_threshold": 3},
        "holdout": "test",
        "val_min_side": 8,
    },
}


def plan(tmp_path, root, manifest, real_jobs=False, monkeypatch=None):
    from scripts import plan_rtis_campaign as planner

    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest))
    (tmp_path / "checkpoints.json").write_text("[]")
    out = tmp_path / "plan"
    if not real_jobs:
        monkeypatch.setattr(
            planner, "build_jobs", lambda *a, folds=None: [{"folds": sorted(folds)}]
        )
    sys.argv = [
        "plan",
        "--manifest",
        str(path),
        "--checkpoints",
        str(tmp_path / "checkpoints.json"),
    ]
    sys.argv += ["--dataset-root", str(root), "--out", str(out), "--gpus", "2,3"]
    planner.main()
    return json.loads((out / "plan.json").read_text()), out


def test_one_campaign_plans_every_fold_against_the_spec(tmp_path, cv_root, monkeypatch):
    result, _ = plan(tmp_path / "a", cv_root, MANIFEST, monkeypatch=monkeypatch)
    cv = result["cross_validation"]
    assert result["primary_checkpoint"] == "final"  # the CV default
    assert result["split_sha256"] == cv["spec_sha256"] == sha(cv_root / group_cv.SPEC_NAME)
    assert cv["planned_folds"] == [0, 1, 2] and result["jobs"] == [{"folds": [0, 1, 2]}]
    assert cv["fold_datasets"]["1"]["split_sha256"] == sha(cv_root / "fold-1/splits.json")
    smoke = MANIFEST | {"cross_validation": MANIFEST["cross_validation"] | {"run_folds": [2]}}
    assert plan(tmp_path / "b", cv_root, smoke, monkeypatch=monkeypatch)[0]["jobs"] == [
        {"folds": [2]}
    ]
    bad = MANIFEST | {"cross_validation": MANIFEST["cross_validation"] | {"seed": 1}}
    with pytest.raises(ValueError, match="differs from"):
        plan(tmp_path / "c", cv_root, bad, monkeypatch=monkeypatch)
    stops = MANIFEST | {"early_stopping_patience": 3}
    with pytest.raises(ValueError, match="early_stopping_patience"):
        plan(tmp_path / "d", cv_root, stops, monkeypatch=monkeypatch)
    with pytest.raises(ValueError, match="model_protocols names unknown"):
        plan(
            tmp_path / "f",
            cv_root,
            MANIFEST | {"model_protocols": {"x": ["rtis_only"]}},
            monkeypatch=monkeypatch,
        )
    with pytest.raises(ValueError, match=r"cv-spec\.json"):
        plan(tmp_path / "e", cv_root / "fold-0", MANIFEST, monkeypatch=monkeypatch)


def test_cv_jobs_train_on_their_fold_and_runtime_checks_each_fold(tmp_path, cv_root, monkeypatch):
    from scripts import run_rtis_campaign as rtis
    from scripts.collect_rtis_statistics import validate_dataset

    from helpers_gpu_policy import patch_live
    from segmentary.config import load_experiment

    two = MANIFEST | {
        "protocols": MANIFEST["protocols"] | {"q": {"label": "q", "source_protocol": None}}
    }
    only = two | {"model_protocols": {"smp_fpn_resnet50": ["rtis_only"]}}
    result, out = plan(tmp_path, cv_root, only, real_jobs=True)
    names = [j["name"] for j in result["jobs"]]
    assert names == [f"smp_fpn_resnet50--rtis_only--fold-{k}--seed-0" for k in range(3)]
    for job in result["jobs"]:
        cfg = load_experiment([Path(job["config"])])
        assert cfg.stages[0].data[0].root == str(cv_root.resolve() / f"fold-{job['fold']}")
        assert cfg.train.early_stopping_patience is None and cfg.name == job["name"]

    monkeypatch.setattr(rtis, "git", lambda repo, *a: "code" if a[0] == "rev-parse" else "")
    patch_live(monkeypatch)
    rtis.initialize(out, tmp_path)
    campaign = rtis.read(out / "campaign.json")
    folds = campaign["cross_validation"]["fold_datasets"]
    assert campaign["primary_checkpoint"] == "final" and campaign["dataset_sizes"] is None
    assert campaign["dataset_samples_verified"] == sum(
        f["dataset_samples_verified"] for f in folds.values()
    )
    for job in result["jobs"]:
        entry = rtis.job_dataset(campaign, job)
        assert entry is folds[str(job["fold"])]
        validate_dataset(out, job, load_experiment([Path(job["config"])]), campaign)
    # A job pointed at another fold's data is refused by the collector's contract.
    job = dict(result["jobs"][0], fold=1)
    with pytest.raises(RuntimeError, match="Integrity mismatch"):
        validate_dataset(out, job, load_experiment([Path(job["config"])]), campaign)


# ----------------------------------------------------------------------------- report


def confusion(mask: np.ndarray, pred: np.ndarray) -> np.ndarray:
    valid = mask != 255
    n = len(NAMES)
    return np.bincount(
        (mask[valid].astype(np.int64) * n + pred[valid]).ravel(), minlength=n * n
    ).reshape(n, n)


def write_gz(path: Path, matrices: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(json.dumps({k: v.tolist() for k, v in matrices.items()}).encode(), mtime=0)
    path.write_bytes(data)
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def fake_campaign(tmp_path, cv_root, folds=(0, 1, 2), stopping="budget_complete"):
    """A completed CV campaign: final predictions miss mud on odd stems, best is perfect."""
    root = tmp_path / "campaign"
    spec_path = cv_root / group_cv.SPEC_NAME
    fold_datasets = {}
    jobs, finals = [], {}
    for k in folds:
        view = cv_root / f"fold-{k}"
        fold_datasets[str(k)] = {
            "root": str(view),
            "split_sha256": sha(view / "splits.json"),
            "dataset_audit_sha256": sha(view / "audit/samples.json"),
        }
        job = {"name": f"m1--p--fold-{k}--seed-0", "model": "m1", "protocol": "p", "seed": 0}
        job |= {"fold": k, "config": "unused.yaml"}
        jobs.append(job)
        matrices: dict[str, dict] = {"final": {}, "best": {}}
        for s in json.loads((view / "audit/samples.json").read_text()):
            if s["split"] != "val":
                continue
            mask = np.asarray(Image.open(view / "masks/val" / f"{s['key']}.png"))
            best = np.where(mask == 255, 0, mask)
            final = best.copy()
            if int(s["stem"]) % 2:
                final[mask == MUD] = ID["terrain"]
            matrices["best"][s["key"]] = confusion(mask, best)
            matrices["final"][s["key"]] = confusion(mask, final)
        finals[k] = matrices["final"]
        totals = {v: sum(m.values()).tolist() for v, m in matrices.items()}
        artifacts = {
            f"{v}-auto-val": {
                "per-image-confusion.json.gz": write_gz(root / "runs" / f"{k}-{v}.json.gz", m)
            }
            for v, m in matrices.items()
        }
        state = {
            "status": "completed",
            "stopping": {"reason": stopping},
            "checkpoints": {
                "best": {"sha256": "b" * 64, "global_step": 2},
                "final": {"sha256": "f" * 64, "global_step": 4},
            },
            "evaluation": {"metrics": {"confusion": totals["best"]}},
            "collection": {
                "artifacts": artifacts,
                "diagnostics": {
                    "results": {
                        f"{v}-auto-val": {
                            "split": "val",
                            "checkpoint_sha256": ("f" if v == "final" else "b") * 64,
                            "metrics": {"confusion": totals[v]},
                        }
                        for v in matrices
                    }
                },
            },
        }
        (root / "state").mkdir(parents=True, exist_ok=True)
        (root / "state" / f"{job['name']}.json").write_text(json.dumps(state))
    jobs.append(
        {"name": "m1--q--fold-0--seed-0", "model": "m1", "protocol": "q", "seed": 0, "fold": 0}
    )
    (root / "state" / "m1--q--fold-0--seed-0.json").write_text(json.dumps({"status": "queued"}))
    (root / "plan.json").write_text(json.dumps({"jobs": jobs}))
    (root / "campaign.json").write_text(
        json.dumps(
            {
                "dataset": "synthetic-cv",
                "code_sha": "c" * 40,
                "target_steps": 4,
                "primary_checkpoint": "final",
                "cross_validation": {
                    "spec": str(spec_path),
                    "spec_sha256": sha(spec_path),
                    "fold_datasets": fold_datasets,
                },
            }
        )
    )
    return root, finals


def test_cv_report_pools_out_of_fold_confusions(tmp_path, cv_root):
    from scripts import cv_report

    root, finals = fake_campaign(tmp_path, cv_root)
    out = tmp_path / "out"
    args = ["--campaign", str(root), "--out", str(out), "--subset", "cab-view"]
    assert cv_report.main([*args, "--viewpoints", str(tmp_path / "viewpoints.yaml")]) == 0
    pooled = sum(m for fold in finals.values() for m in fold.values())
    tp = pooled[MUD, MUD]
    expected = tp / (pooled[MUD].sum() + pooled[:, MUD].sum() - tp)
    rows = (out / "cv-report.csv").read_text().splitlines()
    assert rows[0].split(",") == list(cv_report.CSV_FIELDS)
    row = next(r for r in rows if r.startswith("m1,p,0,final,pooled,3,all,")).split(",")
    assert row[7] == "10" and float(row[10]) == pytest.approx(expected)
    assert any(r.startswith("m1,p,0,best,pooled,3,all,10,4,") and ",1.000000," in r for r in rows)
    per_fold = []
    for fold in finals.values():
        total = sum(fold.values())
        if total[MUD].sum():
            per_fold.append(
                100 * total[MUD, MUD] / (total[MUD].sum() + total[:, MUD].sum() - total[MUD, MUD])
            )
    readme = (out / "README.md").read_text()
    line = next(x for x in readme.splitlines() if x.startswith("| m1 | p | 0 | 3/3 |"))
    assert f"| {100 * expected:.1f} |" in line
    assert f"{np.mean(per_fold):.1f} (SD {np.std(per_fold, ddof=1):.1f}, n={len(per_fold)})" in line
    assert "mud-pumping IoU cab-view" in readme and "mud-pumping IoU track-level" not in readme
    assert "| 0 | 1 | queued 1 | 2 |" in readme and "## Fold composition" in readme
    assert "Secondary (optimistic)" in readme

    partial, _ = fake_campaign(tmp_path / "p", cv_root, folds=(0, 1))
    assert cv_report.main(["--campaign", str(partial), "--out", str(tmp_path / "o2")]) == 0
    line = next(x for x in (tmp_path / "o2/README.md").read_text().splitlines() if "| 2/2 |" in x)
    assert "*" not in line  # only folds 0 and 1 were planned: complete for this campaign


def test_cv_report_refuses_selection_on_the_held_out_fold(tmp_path, cv_root):
    from scripts import cv_report

    root, _ = fake_campaign(tmp_path, cv_root, stopping="validation_plateau")
    with pytest.raises(SystemExit, match="did not run the full budget"):
        cv_report.main(["--campaign", str(root), "--out", str(tmp_path / "out")])
    campaign = json.loads((root / "campaign.json").read_text())
    campaign["cross_validation"]["fold_datasets"]["0"]["split_sha256"] = "0" * 64
    (root / "campaign.json").write_text(json.dumps(campaign))
    with pytest.raises(SystemExit, match="differs from the campaign"):
        cv_report.main(["--campaign", str(root), "--out", str(tmp_path / "out")])
    with pytest.raises(SystemExit, match="not a cross-validation campaign"):
        (tmp_path / "plain").mkdir()
        (tmp_path / "plain/campaign.json").write_text("{}")
        cv_report.main(["--campaign", str(tmp_path / "plain"), "--out", str(tmp_path / "o")])


def test_rad_cv_configs_match_the_tracked_spec():
    manifest = yaml.safe_load((ROOT / "configs/campaigns/rad_9_24_2026-cv.yaml").read_text())
    grouped = yaml.safe_load(
        (ROOT / "configs/campaigns/rad_9_24_2026-fixed-grouped.yaml").read_text()
    )
    spec = json.loads((ROOT / "configs/datasets/rad_9_24_2026-cv-spec.json").read_text())
    cv = manifest["cross_validation"]
    method = spec["method"]
    assert (cv["folds"], cv["seed"], cv["restarts"]) == (
        method["folds"],
        method["seed"],
        method["restarts"],
    )
    assert sorted(cv["stratify"]["anomaly_classes"]) == method["anomaly_classes"]
    assert cv["stratify"]["rare_threshold"] == method["rare_threshold"]
    assert cv["holdout"] == method["holdout_splits"] and cv["pool"] == method["pool_splits"]
    assert cv["val_min_side"] == method["val_min_side"] and cv["primary_checkpoint"] == "final"
    assert "early_stopping_patience" not in manifest
    same = set(grouped) - {"name", "dataset", "dataset_config", "models"}
    same -= {"early_stopping_patience", "early_stopping_min_delta"}
    assert {k: manifest[k] for k in same} == {k: grouped[k] for k in same}
    assert spec["source"]["dataset"] == "rad_9_24_2026-fixed-grouped"
    assert method["viewpoints_sha256"] == sha(
        ROOT / "configs/datasets/rad_9_24_2026-viewpoints.yaml"
    )
    report = spec["report"]
    assert report["pool_images"] == 254 and report["holdout_images"] == 60
    assert report["label_coverage_warnings"] == []
    scored = set()
    for k in range(method["folds"]):
        splits, _ = group_cv.fold_splits(spec, k)
        assert not scored & set(splits["val"])
        scored |= set(splits["val"])
    assert len(scored) == report["scored_images"]
    smoke = yaml.safe_load((ROOT / "configs/campaigns/rad_9_24_2026-cv-smoke.yaml").read_text())
    assert smoke["smoke"] is True and smoke["cross_validation"]["run_folds"] == [1]
    assert set(smoke["models"]) <= set(manifest["models"])
