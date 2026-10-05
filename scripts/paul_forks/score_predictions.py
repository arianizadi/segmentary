#!/usr/bin/env python3
"""Score a fork run's dumped label PNGs with the Segmentary campaign's own metric code.

    SEGMENTARY_REPO=<checkout of this branch> score_predictions.py \\
        --pred-dir <run_dir>/dumps/<split>-single-<ckpt>/pred --arm-root <prepared arm> \\
        --split test --provenance <run_dir>/dumps/<split>-single-<ckpt>/dump-provenance.json \\
        --out <run_dir>/results-test.json

``--pred-dir`` holds one single-channel uint8 PNG per image of the split, named like the
adapter's links: ``<group>__<stem>.png`` (no missing, no extra files). Ground truth is read
from the prepared arm itself (``masks/<split>/<group>/<stem>.png``) and must match the
audit's decoded-mask sha256.

Metrics are exactly what the campaign reports, from the same code:
``segmentary.engine.metrics.ConfusionMatrix`` accumulated per image (ignore 255), then
``scripts/collect_rtis_statistics.matrix_metrics`` (per-class IoU, mIoU = mean over
classes with non-zero union, precision, recall, ...), ``mud_counts`` (mud-pumping, class
13: IoU, precision, recall) and ``scripts/publish_rtis_results.fixed_miou`` (mean over
classes with ground truth). The confusion matrix's ground-truth row sums must equal the
arm's audit (``audit/samples.json`` class_pixels) and the adapter's
``validation-support.json``/``test-support.json``. The metric code is imported from
``$SEGMENTARY_REPO`` (default: the checkout this file sits in); a directory without it is
refused, and the result records its git commit and the sha256 of the three files.

The run label comes from ``provenance.json`` and must be a RAD-stage label
``<base>__arm-<arm>[__recipe-<variant>]`` whose arm matches ``--arm-root`` (no suffix = the
default recipe ``paul-shared-20260923``; the training run's ``extra.recipe_variant`` must
equal it); its checkpoint owners, the exact set of chain stages (``mapcity-direct`` has no
``rs19``) and the sha256 of every Paul/NVIDIA/public checkpoint must match the label (a label naming a
checkpoint we did not train and have no pin for, i.e. ``paper-sfnet__rs19-paul``, is
refused). The reference label ``paul-reference__rr22-0.8964`` is refused: that model may
have trained on these images.

The predictions are tied to the run that made them (all fail closed):

- ``--provenance`` is the ``dump-provenance.json`` next to ``--pred-dir`` and its command's
  ``--dump_preds`` is ``--pred-dir``; it is not a dry run, a timing probe or a pins override,
  and the dump's ``gpu-assignment.json`` says it exited 0;
- ``<pred-dir>.manifest.json`` (P4) names the same split and image set, the dumped
  checkpoint's sha256 equals ``checkpoints.rad.sha256``, and inference was whole-image
  single-scale (``--allow-multi-scale`` scores a ``native`` dump as a secondary number);
- the dump's single ``init-coverage.json`` (P2) loaded that checkpoint with no skipped tensor;
- the training run's ``provenance.json`` is the one the dump recorded (sha256), is a
  finished run of the same label, and trained on the same adapter (``manifest.json``);
- that adapter was built from ``--arm-root`` and the arm has not changed since
  (``arm_name``, ``splits``/``classes``/``samples`` sha256).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

METRIC_FILES = (
    "src/segmentary/engine/metrics.py",
    "scripts/collect_rtis_statistics.py",
    "scripts/publish_rtis_results.py",
)


def metric_repo() -> Path:
    """The Segmentary checkout whose metric code is used; refuse one that lacks it."""
    configured = os.environ.get("SEGMENTARY_REPO")
    repo = Path(configured) if configured else Path(__file__).resolve().parents[2]
    repo = repo.resolve()
    missing = [name for name in METRIC_FILES if not (repo / name).is_file()]
    if missing:
        raise SystemExit(
            f"score_predictions: {repo} is not a Segmentary checkout with the campaign metric "
            f"code (missing {missing}); set SEGMENTARY_REPO to a checkout of this branch"
        )
    return repo


REPO = metric_repo()
for entry in (REPO, REPO / "src"):
    if str(entry) in sys.path:
        sys.path.remove(str(entry))
    sys.path.insert(0, str(entry))

from scripts.collect_rtis_statistics import matrix_metrics, mud_counts
from scripts.publish_rtis_results import fixed_miou

import segmentary.engine.metrics as metrics_module
from segmentary.engine.metrics import ConfusionMatrix

NUM_CLASSES = 21
IGNORE = 255
MUD = "mud-pumping"
ARMS = ("paul", "fixed-stratified", "fixed-grouped")
ARM_DATASET = "rad_9_24_2026-{arm}"
STAGES = ("map_city", "rs19", "rad")
OWNERS = ("paul", "nvidia", "ours", "public-sfnet-authors")
# Owner of each checkpoint in the init chain, per base label.
CHAINS = {
    "paper-hrnet__rs19-paul": {"map_city": "nvidia", "rs19": "paul", "rad": "ours"},
    "paper-hrnet__rs19-ours": {"map_city": "nvidia", "rs19": "ours", "rad": "ours"},
    "paper-hrnet__mapcity-direct": {"map_city": "nvidia", "rad": "ours"},
    "paper-sfnet__rs19-ours": {"map_city": "public-sfnet-authors", "rs19": "ours", "rad": "ours"},
    "paper-sfnet__rs19-paul": {"map_city": "public-sfnet-authors", "rs19": "paul", "rad": "ours"},
    "paper-sfnet__mapcity-direct": {"map_city": "public-sfnet-authors", "rad": "ours"},
}
# Default RAD recipe (plain label) and the other variants, which carry "__recipe-<variant>"
# (same table as recipes/write_provenance.py). mapcity-direct runs the default only.
DEFAULT_RECIPE = "paul-shared-20260923"
RECIPE_VARIANTS = {
    "paper-hrnet__rs19-paul": ("train_2", "train_1"),
    "paper-hrnet__rs19-ours": ("train_2", "train_1"),
    "paper-hrnet__mapcity-direct": (),
    "paper-sfnet__rs19-ours": ("train_2",),
    "paper-sfnet__rs19-paul": ("train_2",),
    "paper-sfnet__mapcity-direct": (),
}
REFERENCE_ONLY = ("paul-reference__rr22-0.8964",)
# Checkpoints we did not train, pinned by sha256 (SHA256SUMS on HDRFS / September provenance).
PINNED = {
    ("paper-hrnet", "map_city"): (
        "9c3779cd266b0c8474bfa01026e701be623738a304b2d08bfa61df60395a77ae"
    ),  # cityscapes_trainval_ocr.HRNet_Mscale_nimble-chihuahua.pth (NVIDIA)
    ("paper-hrnet", "rs19-paul"): (
        "873fa92ca7ceb4286a5b80ae24434180e36b0768065c37092be213d4f09ea08f"
    ),  # rs19_cityscapes_ep98_miou_0.7385.pth (Paul)
    ("paper-sfnet", "map_city"): (
        "133f1b6a1502ef7e685ef4c1a32569c75a03f233f3c6d009a0a0aafc73dd4c0f"
    ),  # pretrained_cityscapes_mapillary_rs18_miou-0.799.pth (SFNet authors)
}
FORBIDDEN_GPU_UUIDS = {
    "84f5ca4d-68db-ae98-d056-40654d859dd9",  # GPU 0
    "d411d86a-6d1d-1967-55e7-9f9ec85d13f5",  # GPU 1
}
PROVENANCE_KEYS = (
    "label",
    "owner_of_each_checkpoint_in_chain",
    "checkpoints",
    "fork",
    "recipe_args",
    "deviations",
    "gpu_assignment",
)


class ScoreError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def parse_label(label: str) -> tuple[str, str, str]:
    """``(base, arm, recipe variant)`` of ``<base>__arm-<arm>[__recipe-<variant>]``."""
    if label in REFERENCE_ONLY or label.startswith("paul-reference__"):
        raise ScoreError(
            f"{label} is a reference model that may have trained on our val/test images; "
            "it is never scored on our splits"
        )
    match = re.fullmatch(
        r"(.+?)__arm-(" + "|".join(ARMS) + r")(?:__recipe-([A-Za-z0-9_.-]+))?", label
    )
    if not match or match.group(1) not in CHAINS:
        raise ScoreError(
            f"{label!r} is not a RAD-stage label <base>__arm-<arm>[__recipe-<variant>] with "
            f"base in {sorted(CHAINS)} and arm in {list(ARMS)}"
        )
    base, arm, recipe = match.group(1), match.group(2), match.group(3)
    if recipe is not None and recipe not in RECIPE_VARIANTS[base]:
        raise ScoreError(
            f"{label!r}: recipe {recipe!r} is not a variant of {base} "
            f"(allowed: {list(RECIPE_VARIANTS[base])}; the default has no suffix)"
        )
    return base, arm, recipe or DEFAULT_RECIPE


def check_provenance(provenance: dict[str, Any], arm: str) -> tuple[str, str]:
    missing = [key for key in PROVENANCE_KEYS if key not in provenance]
    if missing:
        raise ScoreError(f"provenance.json lacks {missing}")
    base, label_arm, _ = parse_label(str(provenance["label"]))
    if label_arm != arm:
        raise ScoreError(f"label arm {label_arm!r} differs from the scored arm {arm!r}")
    for flag in ("dry_run", "probe_epochs", "pins_override"):
        if provenance.get(flag):
            raise ScoreError(f"provenance has {flag}={provenance[flag]!r}; it is not a scored run")
    owners = provenance["owner_of_each_checkpoint_in_chain"]
    if owners != CHAINS[base]:
        raise ScoreError(f"{base} needs checkpoint owners {CHAINS[base]}, provenance has {owners}")
    checkpoints = provenance["checkpoints"]
    if not isinstance(checkpoints, dict) or set(checkpoints) != set(owners):
        raise ScoreError(f"provenance checkpoints must be exactly the chain stages {list(owners)}")
    for stage in owners:
        entry = checkpoints[stage]
        if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
            raise ScoreError(f"provenance checkpoints.{stage} needs path and sha256")
    family, chain = base.split("__")
    for stage in owners:
        key = "map_city" if stage == "map_city" else chain
        if owners[stage] == "ours":
            continue
        pin = PINNED.get((family, key))
        if pin is None:
            raise ScoreError(
                f"{base}: no pinned sha256 for the {owners[stage]} {stage} checkpoint; the "
                "label stays reserved until that checkpoint is pinned"
            )
        if checkpoints[stage]["sha256"] != pin:
            raise ScoreError(f"{stage} checkpoint sha256 is not the pinned {owners[stage]} one")
    if not isinstance(provenance["fork"], dict) or not provenance["fork"].get("git_commit"):
        raise ScoreError("provenance fork needs git_commit (and patch sha256s)")
    gpus = provenance["gpu_assignment"]
    indices = gpus.get("indices", []) if isinstance(gpus, dict) else []
    uuids = gpus.get("uuids", []) if isinstance(gpus, dict) else []
    if not indices or any(int(i) not in range(2, 10) for i in indices):
        raise ScoreError(f"gpu_assignment indices {indices} are not within 2-9")
    if any(str(u).lower().removeprefix("gpu-") in FORBIDDEN_GPU_UUIDS for u in uuids):
        raise ScoreError("gpu_assignment lists a forbidden GPU UUID")
    return base, label_arm


def arm_of(arm_root: Path) -> str:
    for arm in ARMS:
        if arm_root.name == ARM_DATASET.format(arm=arm):
            return arm
    raise ScoreError(
        f"arm root {arm_root.name!r} is not one of {[ARM_DATASET.format(arm=a) for a in ARMS]}"
    )


def load_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ScoreError(f"cannot read {what} {path}: {error}") from error


def finished(launch_dir: Path, what: str) -> dict[str, Any]:
    """fork_gpu_run.py's record must say the command exited 0."""
    record = load_json(launch_dir / "gpu-assignment.json", f"{what} launcher record")
    if record.get("status") != "exited" or record.get("exit_code") != 0:
        raise ScoreError(
            f"{what} in {launch_dir} did not finish cleanly (status={record.get('status')}, "
            f"exit_code={record.get('exit_code')})"
        )
    return record


def check_dump(
    provenance: dict[str, Any],
    provenance_path: Path,
    pred_dir: Path,
    split: str,
    keys: list[str],
    allow_multi_scale: bool,
) -> dict[str, Any]:
    """Tie the predictions to the dumped checkpoint, the run and its training provenance."""
    if provenance.get("stage") != "dump":
        raise ScoreError("--provenance must be the dump-provenance.json written for this dump")
    dump_dir = provenance_path.resolve().parent
    if pred_dir.resolve().parent != dump_dir:
        raise ScoreError(f"{pred_dir} is not in the dump directory of {provenance_path}")
    command = [str(token) for token in provenance.get("command", [])]
    if "--dump_preds" not in command or command.index("--dump_preds") + 1 >= len(command):
        raise ScoreError("dump provenance command has no --dump_preds")
    dumped_to = Path(command[command.index("--dump_preds") + 1])
    if dumped_to.resolve() != pred_dir.resolve():
        raise ScoreError(f"dump provenance wrote {dumped_to}, not --pred-dir {pred_dir}")
    finished(dump_dir, "the dump")
    rad = provenance["checkpoints"]["rad"]

    manifest_path = Path(os.path.normpath(pred_dir) + ".manifest.json")
    manifest = load_json(manifest_path, "P4 dump manifest")
    stems = sorted(key.replace("/", "__") for key in keys)
    if manifest.get("split") != split:
        raise ScoreError(f"{manifest_path} is a {manifest.get('split')!r} dump, not {split!r}")
    if manifest.get("count") != len(stems) or sorted(manifest.get("images", [])) != stems:
        raise ScoreError(f"{manifest_path} does not list exactly the {split} images")
    if manifest.get("snapshot_sha256") != rad["sha256"]:
        raise ScoreError(
            f"{manifest_path} dumped checkpoint sha256 {manifest.get('snapshot_sha256')} is not "
            f"checkpoints.rad {rad['sha256']}"
        )
    single = manifest.get("single_scale_whole_image") is True
    if not single and not allow_multi_scale:
        raise ScoreError(
            f"{manifest_path} is not whole-image single-scale (n_scales "
            f"{manifest.get('n_scales')}); the primary number is single-scale"
        )

    coverage_files = sorted((dump_dir / "log").rglob("init-coverage.json"))
    if len(coverage_files) != 1:
        raise ScoreError(
            f"expected one init-coverage.json under {dump_dir}/log, found "
            f"{[str(p) for p in coverage_files]}"
        )
    coverage = load_json(coverage_files[0], "P2 init coverage")
    if (
        coverage.get("status") != "ok"
        or coverage.get("skipped_tensors") != 0
        or coverage.get("source_sha256") != rad["sha256"]
    ):
        raise ScoreError(
            f"{coverage_files[0]}: the dump did not load checkpoints.rad completely "
            f"(status={coverage.get('status')}, skipped={coverage.get('skipped_tensors')}, "
            f"source_sha256={coverage.get('source_sha256')})"
        )

    dump = provenance.get("dump") or {}
    training_path = Path(str(dump.get("training_provenance", "")))
    if not training_path.is_file() or sha256_file(training_path) != dump.get(
        "training_provenance_sha256"
    ):
        raise ScoreError(
            f"training provenance {training_path} is missing or changed since the dump"
        )
    training = load_json(training_path, "training provenance")
    if training.get("label") != provenance["label"] or training.get("stage") != "rad":
        raise ScoreError(f"{training_path} is not the RAD training run of {provenance['label']}")
    for flag in ("dry_run", "probe_epochs", "pins_override"):
        if training.get(flag):
            raise ScoreError(f"training provenance has {flag}={training[flag]!r}")
    upstream = [
        stage for stage in provenance["owner_of_each_checkpoint_in_chain"] if stage != "rad"
    ]
    if set(training["checkpoints"]) != set(provenance["checkpoints"]):
        raise ScoreError("dump and training provenance list different chain stages")
    for stage in upstream:
        if training["checkpoints"][stage] != provenance["checkpoints"][stage]:
            raise ScoreError(f"dump and training provenance differ in checkpoints.{stage}")
    _, _, recipe = parse_label(str(provenance["label"]))
    if (training.get("extra") or {}).get("recipe_variant") != recipe:
        raise ScoreError(
            f"{training_path} recipe_variant "
            f"{(training.get('extra') or {}).get('recipe_variant')!r} is not the label's {recipe!r}"
        )
    finished(training_path.parent, "the training run")
    run_dir = training_path.parent.resolve()
    dumped_ckpt = Path(rad.get("resolved_path") or rad["path"]).resolve()
    if run_dir not in dumped_ckpt.parents or run_dir not in dump_dir.parents:
        raise ScoreError(f"the dump or its checkpoint {dumped_ckpt} is not inside run {run_dir}")

    def adapter_manifest(record: dict[str, Any]) -> str | None:
        return ((record.get("data") or {}).get("sha256") or {}).get("manifest.json")

    if adapter_manifest(training) != adapter_manifest(provenance):
        raise ScoreError("the dump used a different adapter than the training run")
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "single_scale_whole_image": single,
        "n_scales": manifest.get("n_scales"),
        "init_coverage": str(coverage_files[0]),
        "training_provenance": str(training_path),
        "training_provenance_sha256": sha256_file(training_path),
    }


def check_adapter(provenance: dict[str, Any], arm_root: Path, split: str) -> tuple[Path, dict]:
    """The adapter the run used was built from this arm, which has not changed since."""
    data = provenance.get("data") or {}
    if not data.get("resolved"):
        raise ScoreError("provenance data.resolved (the adapter directory) is missing")
    adapter = Path(data["resolved"])
    manifest_file = adapter / "manifest.json"
    if not manifest_file.is_file() or sha256_file(manifest_file) != data.get("sha256", {}).get(
        "manifest.json"
    ):
        raise ScoreError(f"{manifest_file} is missing or differs from the run's provenance")
    manifest = load_json(manifest_file, "adapter manifest")
    if manifest.get("arm_name") != arm_root.name:
        raise ScoreError(
            f"adapter {adapter} was built from {manifest.get('arm_name')!r}, not {arm_root.name!r}"
        )
    for name, key in (
        ("splits.json", "splits_sha256"),
        ("classes.json", "classes_sha256"),
        ("audit/samples.json", "samples_sha256"),
    ):
        if sha256_file(arm_root / name) != manifest.get(key):
            raise ScoreError(f"{arm_root / name} changed since adapter {adapter} was built")
    support = adapter / ("validation-support.json" if split == "val" else "test-support.json")
    return support, manifest


def score(
    pred_dir: Path,
    arm_root: Path,
    split: str,
    provenance_path: Path,
    allow_multi_scale: bool = False,
) -> dict[str, Any]:
    arm_root = arm_root.resolve()
    arm = arm_of(arm_root)
    provenance = load_json(provenance_path, "provenance")
    base, _ = check_provenance(provenance, arm)
    recipe = parse_label(str(provenance["label"]))[2]
    schema = json.loads((arm_root / "classes.json").read_text())
    names = [c["name"] for c in schema["classes"]]
    if len(names) != NUM_CLASSES or names.index(MUD) != 13 or schema["ignore_index"] != IGNORE:
        raise ScoreError("arm classes.json is not the 21-class space with mud-pumping = 13")
    splits = json.loads((arm_root / "splits.json").read_text())
    audit = {row["key"]: row for row in json.loads((arm_root / "audit/samples.json").read_text())}
    keys = sorted(splits[split])
    support_json, _ = check_adapter(provenance, arm_root, split)
    dump = check_dump(provenance, provenance_path, pred_dir, split, keys, allow_multi_scale)
    wanted = {key.replace("/", "__") + ".png": key for key in keys}
    present = {p.name for p in pred_dir.iterdir() if p.is_file() and not p.name.startswith(".")}
    if present != set(wanted):
        raise ScoreError(
            f"predictions do not cover the {split} split exactly: missing "
            f"{sorted(set(wanted) - present)[:5]}, extra {sorted(present - set(wanted))[:5]}"
        )
    total = np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64)
    expected_support = np.zeros(NUM_CLASSES, np.int64)
    per_image, pred_hashes = [], {}
    mud = names.index(MUD)
    for name, key in sorted(wanted.items()):
        row = audit[key]
        if row["split"] != split:
            raise ScoreError(f"{key} is not in {split} according to the audit")
        with Image.open(arm_root / "masks" / split / f"{key}.png") as im:
            target = np.asarray(im)
        if hashlib.sha256(target.tobytes()).hexdigest() != row["mask_sha256"]:
            raise ScoreError(f"{key}: ground-truth mask differs from the audit")
        with Image.open(pred_dir / name) as im:
            if im.mode not in ("L", "P"):
                raise ScoreError(f"{name}: prediction mode {im.mode}, expected uint8 labels")
            pred = np.asarray(im)
        if pred.dtype != np.uint8 or pred.shape != target.shape:
            raise ScoreError(f"{name}: prediction {pred.dtype}{pred.shape} vs mask {target.shape}")
        metric = ConfusionMatrix(NUM_CLASSES, IGNORE, device="cpu")
        metric.update(
            torch.from_numpy(pred.astype(np.int64)), torch.from_numpy(target.astype(np.int64))
        )
        matrix = metric.mat.numpy().copy()
        total += matrix
        for value, n in row["class_pixels"].items():
            if int(value) < NUM_CLASSES:
                expected_support[int(value)] += int(n)
        pred_hashes[name] = sha256_file(pred_dir / name)
        per_image.append({"key": key, "mud": mud_counts(matrix, mud)})
    support = total.sum(axis=1)
    if not np.array_equal(support, expected_support):
        raise ScoreError(
            f"support {support.tolist()} differs from the audit {expected_support.tolist()}"
        )
    recorded = load_json(support_json, "adapter support file")
    if recorded.get("split") != split or recorded.get("class_pixel_counts") != support.tolist():
        raise ScoreError(f"support differs from {support_json}")
    metrics = matrix_metrics(total, names)
    return {
        "schema_version": 2,
        "label": provenance["label"],
        "base_label": base,
        "recipe_variant": recipe,
        "arm": arm,
        "split": split,
        "images": len(keys),
        "inference": "whole-image single-scale"
        if dump["single_scale_whole_image"]
        else f"multi-scale {dump['n_scales']} (secondary; not the primary number)",
        "metrics": metrics,
        "miou": metrics["miou"],
        "fixed_gt_class_miou": fixed_miou(metrics),
        "mud": mud_counts(total, mud),
        "per_image": per_image,
        "support": support.tolist(),
        "support_check": {"audit_samples": True, str(support_json): True},
        "predictions": {"dir": str(pred_dir.resolve()), "sha256": pred_hashes},
        "dump": dump,
        "arm_root": {
            "path": str(arm_root),
            "splits_sha256": sha256_file(arm_root / "splits.json"),
            "samples_sha256": sha256_file(arm_root / "audit/samples.json"),
        },
        "metric_code": metric_code(),
        "provenance_path": str(provenance_path.resolve()),
        "provenance_sha256": sha256_file(provenance_path),
        "provenance": provenance,
        "scored_at": time.time(),
    }


def metric_code() -> dict[str, Any]:
    module = Path(metrics_module.__file__).resolve()
    if REPO not in module.parents:
        raise ScoreError(f"segmentary was imported from {module}, not from {REPO}")
    try:
        commit = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    snapshot = REPO / "SNAPSHOT_COMMIT"
    if not commit and snapshot.is_file():
        commit = snapshot.read_text().strip()
    return {
        "repo": str(REPO),
        "git_commit": commit or None,
        "sha256": {name: sha256_file(REPO / name) for name in METRIC_FILES},
        "confusion": "segmentary.engine.metrics.ConfusionMatrix (ignore 255)",
        "metrics": "scripts/collect_rtis_statistics.py matrix_metrics + mud_counts",
        "fixed_gt_class_miou": "scripts/publish_rtis_results.py fixed_miou",
        "miou_rule": "mean IoU over classes with non-zero union (gt or prediction)",
        "scorer_sha256": sha256_file(Path(__file__).resolve()),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--pred-dir", type=Path, required=True)
    p.add_argument("--arm-root", type=Path, required=True)
    p.add_argument("--split", choices=("val", "test"), required=True)
    p.add_argument("--provenance", type=Path, required=True, help="the dump-provenance.json")
    p.add_argument(
        "--allow-multi-scale",
        action="store_true",
        help="score a multi-scale (native) dump; recorded as a secondary number",
    )
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"score_predictions: refusing to overwrite {args.out}")
    try:
        result = score(
            args.pred_dir, args.arm_root, args.split, args.provenance, args.allow_multi_scale
        )
    except ScoreError as error:
        raise SystemExit(f"score_predictions: {error}") from error
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "label": result["label"],
                "split": args.split,
                "inference": result["inference"],
                "miou": result["miou"],
                "mud_iou": result["mud"]["iou"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
