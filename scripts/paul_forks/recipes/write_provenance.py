#!/usr/bin/env python3
"""Write ``provenance.json`` for a Paul-fork run, before anything is launched.

Called by the recipe scripts in this directory (standard library only, so it runs with the
fork environment's Python on HDRFS). It refuses to overwrite an existing file, so a run
directory describes exactly one run.

The record follows the contract checked by ``scripts/paul_forks/score_predictions.py``:
``label``, ``owner_of_each_checkpoint_in_chain`` and ``checkpoints`` keyed by stage
(``map_city``, ``rs19``, ``rad``), ``fork`` (``name``, ``git_commit``, ``patches`` with
sha256), ``recipe_args`` (the ``train.py`` argv, verbatim), ``deviations`` and
``gpu_assignment`` (indices and UUIDs). It adds the full command, the build-time weight
files, the data files' sha256, the ``PAUL_*`` environment and the probe / dry-run flags.

Before writing it refuses: a label outside the frozen set (the reference label is never
run), a RAD label whose ``__recipe-<variant>`` suffix (absent = the default
``paul-shared-20260923``) differs from the recorded ``recipe_variant``, owners that do not
match the label's chain (``mapcity-direct`` has no ``rs19`` stage), a Paul/NVIDIA/public checkpoint whose
sha256 differs from its pin or that has no pin at all (so ``paper-sfnet__rs19-paul`` stays
reserved until Paul's SFNet RS19 checkpoint is pinned), a GPU outside 2-9, a launcher other
than the ``fork_gpu_run.py`` next to these recipes (outside ``--dry-run``), a fork clone
whose applied patches differ from the shipped patch files, and a fork working tree whose
content digest differs from the one ``apply_patches.sh`` recorded (``PAUL_PATCHES_TREE``),
so a hand edit after patching is refused.

A training run's ``checkpoints.rad`` (or ``rs19`` for an RS19 run) is this run and has no
file yet. ``--stage dump`` writes ``dump-provenance.json`` for one dumped checkpoint: it
copies the chain from the training run's ``provenance.json`` and fills ``checkpoints.rad``
with the dumped file, so that file is what ``score_predictions.py --provenance`` reads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ARMS = ("paul", "fixed-grouped")
RS19_LABELS = ("hrnet-rs19-ours", "sfnet-rs19-ours")
RAD_BASES = (
    "paper-hrnet__rs19-paul",
    "paper-hrnet__rs19-ours",
    "paper-hrnet__mapcity-direct",  # NVIDIA Map->City -> RAD, no RS19 stage
    "paper-sfnet__rs19-ours",
    "paper-sfnet__rs19-paul",  # reserved: only if Paul sends his SFNet RS19 checkpoint
    "paper-sfnet__mapcity-direct",  # public SFNet Map->City -> RAD, no RS19 stage
)
# The default RAD recipe (Paul's shared 2026-09-23 files) keeps the plain label; any other
# variant the recipe accepts appends "__recipe-<variant>", so two recipes of one chain and
# arm never share a label. mapcity-direct runs the default only.
DEFAULT_RECIPE = "paul-shared-20260923"
RECIPE_VARIANTS = {
    "paper-hrnet__rs19-paul": ("train_2", "train_1"),
    "paper-hrnet__rs19-ours": ("train_2", "train_1"),
    "paper-hrnet__mapcity-direct": (),
    "paper-sfnet__rs19-ours": ("train_2",),
    "paper-sfnet__rs19-paul": ("train_2",),
    "paper-sfnet__mapcity-direct": (),
}
REFERENCE_LABELS = ("paul-reference__rr22-0.8964",)  # never trained here, never scored
RAD_LABEL = re.compile(
    r"(?P<base>paper-(?:hrnet|sfnet)__[a-z0-9-]+)__arm-(?P<arm>" + "|".join(ARMS) + r")"
    r"(?:__recipe-(?P<recipe>[A-Za-z0-9_.-]+))?"
)


def rad_label(base: str, arm: str, recipe: str = DEFAULT_RECIPE) -> str:
    label = f"{base}__arm-{arm}"
    return label if recipe == DEFAULT_RECIPE else f"{label}__recipe-{recipe}"


ALLOWED_LABELS = RS19_LABELS + tuple(
    rad_label(base, arm, recipe)
    for base in RAD_BASES
    for arm in ARMS
    for recipe in (DEFAULT_RECIPE, *RECIPE_VARIANTS[base])
)
OWNERS = ("paul", "nvidia", "ours", "public-sfnet-authors")
STAGES = ("map_city", "rs19", "rad")
CHAINS = {
    "hrnet-rs19-ours": {"map_city": "nvidia", "rs19": "ours"},
    "sfnet-rs19-ours": {"map_city": "public-sfnet-authors", "rs19": "ours"},
    "paper-hrnet__rs19-paul": {"map_city": "nvidia", "rs19": "paul", "rad": "ours"},
    "paper-hrnet__rs19-ours": {"map_city": "nvidia", "rs19": "ours", "rad": "ours"},
    "paper-hrnet__mapcity-direct": {"map_city": "nvidia", "rad": "ours"},
    "paper-sfnet__rs19-ours": {"map_city": "public-sfnet-authors", "rs19": "ours", "rad": "ours"},
    "paper-sfnet__rs19-paul": {"map_city": "public-sfnet-authors", "rs19": "paul", "rad": "ours"},
    "paper-sfnet__mapcity-direct": {"map_city": "public-sfnet-authors", "rad": "ours"},
}
# Same pins as score_predictions.py (SHA256SUMS on HDRFS / the public SFNet download).
PINS = {
    ("nvidia", "map_city"): "9c3779cd266b0c8474bfa01026e701be623738a304b2d08bfa61df60395a77ae",
    ("paul", "rs19", "hrnet"): "873fa92ca7ceb4286a5b80ae24434180e36b0768065c37092be213d4f09ea08f",
    ("public-sfnet-authors", "map_city"): (
        "133f1b6a1502ef7e685ef4c1a32569c75a03f233f3c6d009a0a0aafc73dd4c0f"
    ),
}
FORBIDDEN_GPU_INDICES = (0, 1)
HERE = Path(__file__).resolve().parent
OFFICIAL_LAUNCHER = HERE.parent / "fork_gpu_run.py"
TREE_FILE = "PAUL_PATCHES_TREE"


def load_tree_digest():
    """``patches/tree_digest.py`` (shared with apply_patches.sh)."""
    path = HERE.parent / "patches" / "tree_digest.py"
    spec = importlib.util.spec_from_file_location("paul_tree_digest", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"REFUSING: cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def split_label(label: str) -> tuple[str, str | None, str | None]:
    """``(base, arm, recipe variant)``; an RS19-stage label is its own base (no arm/recipe)."""
    if label in RS19_LABELS:
        return label, None, None
    match = RAD_LABEL.fullmatch(label)
    if not match:
        raise SystemExit(f"REFUSING: {label!r} is not <base>__arm-<arm>[__recipe-<variant>]")
    recipe = match.group("recipe")
    if recipe == DEFAULT_RECIPE:
        raise SystemExit(f"REFUSING: {label!r}: the default recipe carries no __recipe- suffix")
    return match.group("base"), match.group("arm"), recipe or DEFAULT_RECIPE


def base_of(label: str) -> str:
    return split_label(label)[0]


def load_pins() -> tuple[dict, str | None]:
    """Pinned sha256s; PAUL_FORK_PINS_FILE replaces them (tests only; recorded, unscorable)."""
    override = os.environ.get("PAUL_FORK_PINS_FILE")
    if not override:
        return PINS, None
    rows = json.loads(Path(override).read_text())
    return {tuple(row["key"]): row["sha256"] for row in rows}, override


def load_launcher(path: Path):
    spec = importlib.util.spec_from_file_location("fork_gpu_run", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"REFUSING: cannot import GPU launcher {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["fork_gpu_run"] = module
    spec.loader.exec_module(module)
    return module


def gpu_assignment(gpus: str, launcher: Path, dry_run: bool = False) -> dict:
    if not dry_run and launcher.resolve() != OFFICIAL_LAUNCHER.resolve():
        raise SystemExit(
            f"REFUSING: launcher {launcher} is not {OFFICIAL_LAUNCHER}; FORK_GPU_RUN may only "
            "point elsewhere for --dry-run"
        )
    try:
        indices = sorted(int(x) for x in gpus.split(","))
    except ValueError:
        raise SystemExit(f"REFUSING: bad GPU list {gpus!r}") from None
    if len(set(indices)) != len(indices) or not indices:
        raise SystemExit(f"REFUSING: bad GPU list {gpus!r}")
    if any(i in FORBIDDEN_GPU_INDICES or not 2 <= i <= 9 for i in indices):
        raise SystemExit(f"REFUSING: GPUs {gpus!r} outside 2-9 (0 and 1 are reserved)")
    table = load_launcher(launcher).ALLOWED
    missing = [i for i in indices if i not in table]
    if missing:
        raise SystemExit(f"REFUSING: launcher allowlist lacks GPUs {missing}")
    return {
        "indices": indices,
        "uuids": [table[i][0] for i in indices],
        "pci_bus_ids": [table[i][1] for i in indices],
        "source": f"frozen table in {launcher}; the launcher re-checks the live inventory",
        "launcher": str(launcher),
        "launcher_sha256": sha256(launcher),
    }


def git(src: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(src), *args], text=True).strip()


def fork_state(name: str, src: Path, patches_dir: Path | None) -> dict:
    manifest = src / "PAUL_PATCHES_APPLIED"
    if not manifest.is_file():
        raise SystemExit(f"REFUSING: {manifest} missing; patch the clone with apply_patches.sh")
    applied = []
    for line in manifest.read_text().splitlines():
        digest, patch = line.split(None, 1)
        applied.append({"path": patch.strip(), "sha256": digest})
    if patches_dir is not None:
        for item in applied:
            shipped = patches_dir / item["path"]
            if not shipped.is_file() or sha256(shipped) != item["sha256"]:
                raise SystemExit(
                    f"REFUSING: {src} was patched with a {item['path']} that differs from "
                    f"{shipped}; re-clone and re-apply the current patch series"
                )
    diff = subprocess.check_output(["git", "-C", str(src), "diff", "--binary", "HEAD"])
    untracked = git(src, "ls-files", "--others", "--exclude-standard")
    recorded_file = src / TREE_FILE
    if not recorded_file.is_file():
        raise SystemExit(f"REFUSING: {recorded_file} missing; re-run apply_patches.sh")
    recorded = recorded_file.read_text().split()[0]
    actual = load_tree_digest().tree_digest(src)
    if actual != recorded:
        raise SystemExit(
            f"REFUSING: {src} differs from the tree apply_patches.sh produced (digest {actual}, "
            f"recorded {recorded}); re-clone and re-apply the patch series"
        )
    return {
        "name": name,
        "git_commit": git(src, "rev-parse", "HEAD"),
        "origin": git(src, "remote", "get-url", "origin"),
        "src": str(src),
        "patches": applied,
        "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "tree_digest": actual,
        "untracked_files": sorted(untracked.splitlines()),
    }


def checkpoint_entry(role: str, path: str) -> dict:
    if not path:
        return {"role": role, "path": None, "sha256": None}
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise SystemExit(f"REFUSING: checkpoint {path} missing")
    return {"role": role, "path": path, "resolved_path": str(resolved), "sha256": sha256(resolved)}


def parse_chain(items: list[str]) -> tuple[dict, dict]:
    owners, checkpoints = {}, {}
    for item in items:
        parts = item.split("|")
        if len(parts) != 4:
            raise SystemExit(f"REFUSING: chain entry needs stage|owner|role|path, got {item!r}")
        stage, owner, role, path = parts
        if stage not in STAGES or stage in owners:
            raise SystemExit(f"REFUSING: bad or repeated chain stage {stage!r}")
        if owner not in OWNERS:
            raise SystemExit(f"REFUSING: owner {owner!r} not in {OWNERS}")
        owners[stage] = owner
        checkpoints[stage] = checkpoint_entry(role, path)
    return owners, checkpoints


def check_pins(fork: str, owners: dict, checkpoints: dict, pins: dict) -> None:
    """Every checkpoint we did not train must match its pin; one without a pin is refused."""
    for stage, owner in owners.items():
        if owner == "ours":
            continue
        pin = pins.get((owner, stage, fork), pins.get((owner, stage)))
        if pin is None:
            raise SystemExit(
                f"REFUSING: no pinned sha256 for the {owner} {stage} checkpoint of {fork}; "
                "a label naming a checkpoint we did not train stays reserved until it is pinned"
            )
        got = checkpoints[stage]["sha256"]
        if got != pin:
            raise SystemExit(
                f"REFUSING: {stage} checkpoint ({owner}) sha256 {got} is not the pinned {pin}"
            )


def data_files(root: str | None) -> dict:
    if not root:
        return {}
    base = Path(root)
    found = {}
    names = (
        "classes.json",
        "rs19-config.json",
        "manifest.json",
        "splits.json",
        "validation-support.json",
        "test-support.json",
    )
    for name in names:
        path = base / name
        if path.is_file():
            found[name] = sha256(path)
    return {"root": root, "resolved": str(base.resolve()), "sha256": found}


def train_argv(command: list[str]) -> list[str]:
    for index, token in enumerate(command):
        if token.endswith("/train.py") or token == "train.py":
            return command[index + 1 :]
    raise SystemExit("REFUSING: command has no train.py")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--label", required=True)
    p.add_argument("--stage", required=True, choices=("rs19", "rad", "dump"))
    p.add_argument("--fork", required=True, choices=("hrnet", "sfnet"))
    p.add_argument("--arm", default="")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--out", default="provenance.json", help="file name inside --run-dir")
    p.add_argument("--src", required=True)
    p.add_argument("--patches-dir", default="")
    p.add_argument("--gpus", required=True)
    p.add_argument("--launcher", required=True)
    p.add_argument("--recipe-source", required=True)
    p.add_argument("--recipe-script", required=True)
    p.add_argument("--chain", action="append", default=[], help="stage|owner|role|path")
    p.add_argument("--base-provenance", default="", help="dump: the training provenance.json")
    p.add_argument("--weights", action="append", default=[], help="role|path (build-time loads)")
    p.add_argument("--deviation", action="append", default=[])
    p.add_argument("--data-root", default="")
    p.add_argument("--probe-epochs", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--extra", action="append", default=[], help="key=value recorded verbatim")
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args(argv)

    label = args.label
    if label in REFERENCE_LABELS or label.startswith("paul-reference"):
        raise SystemExit("REFUSING: reference labels are never run or scored")
    if label not in ALLOWED_LABELS:
        raise SystemExit(f"REFUSING: label {label!r} not in the allowed set")
    base, label_arm, recipe = split_label(label)
    is_rad_label = label_arm is not None
    if (args.stage == "rs19") == is_rad_label:
        raise SystemExit(f"REFUSING: stage {args.stage} does not fit label {label}")
    if is_rad_label and label_arm != args.arm:
        raise SystemExit(f"REFUSING: label {label} does not match arm {args.arm!r}")
    extras = dict(item.split("=", 1) for item in args.extra)
    if args.stage == "rad" and extras.get("recipe_variant") != recipe:
        raise SystemExit(
            f"REFUSING: label {label} names recipe {recipe!r} but the run records "
            f"recipe_variant={extras.get('recipe_variant')!r}"
        )
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("REFUSING: no command recorded")
    out = Path(args.run_dir) / args.out
    if out.exists():
        raise SystemExit(f"REFUSING: {out} already exists; use a fresh run directory")

    owners, checkpoints = parse_chain(args.chain)
    dump = None
    if args.stage == "dump":
        base_path = Path(args.base_provenance)
        training = json.loads(base_path.read_text())
        if (
            training.get("label") != label
            or training.get("dry_run")
            or training.get("probe_epochs")
        ):
            raise SystemExit(f"REFUSING: {base_path} is not a finished run of {label}")
        if (training.get("extra") or {}).get("recipe_variant") != recipe:
            raise SystemExit(f"REFUSING: {base_path} recipe_variant is not {recipe!r}")
        if set(owners) != {"rad"} or not checkpoints["rad"]["path"]:
            raise SystemExit("REFUSING: a dump records exactly the dumped rad checkpoint")
        rad_owner, rad_entry = owners["rad"], checkpoints["rad"]
        owners = dict(training["owner_of_each_checkpoint_in_chain"])
        checkpoints = dict(training["checkpoints"])
        if owners.get("rad") != rad_owner:
            raise SystemExit("REFUSING: dumped checkpoint owner differs from the run's chain")
        checkpoints["rad"] = rad_entry
        dump = {
            "training_provenance": str(base_path),
            "training_provenance_sha256": sha256(base_path),
            "training_recipe_args": training.get("recipe_args"),
            "training_gpu_assignment": training.get("gpu_assignment"),
        }
    expected = CHAINS[base]
    if owners != expected:
        raise SystemExit(f"REFUSING: {label} needs owners {expected}, got {owners}")
    pins, pins_override = load_pins()
    check_pins(args.fork, owners, checkpoints, pins)

    weights = {}
    for item in args.weights:
        role, _, path = item.partition("|")
        weights[role] = checkpoint_entry(role, path)
    patches_dir = Path(args.patches_dir) if args.patches_dir else None
    record = {
        "label": label,
        "stage": args.stage,
        "arm": args.arm or None,
        "owner_of_each_checkpoint_in_chain": owners,
        "checkpoints": checkpoints,
        "fork": fork_state(args.fork, Path(args.src), patches_dir),
        "recipe_args": train_argv(command),
        "command": command,
        "recipe": {
            "source": args.recipe_source,
            "script": args.recipe_script,
            "script_sha256": sha256(Path(args.recipe_script)),
        },
        "deviations": args.deviation,
        "gpu_assignment": gpu_assignment(args.gpus, Path(args.launcher), args.dry_run),
        "build_time_weights": weights,
        "data": data_files(args.data_root),
        "environment": {k: v for k, v in sorted(os.environ.items()) if k.startswith("PAUL_")},
        "probe_epochs": int(args.probe_epochs) if args.probe_epochs else None,
        "dry_run": args.dry_run,
        "pins_override": pins_override,
        "extra": extras,
        "created_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "host": os.uname().nodename,
    }
    if dump is not None:
        record["dump"] = dump
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n")
    os.replace(tmp, out)
    print(f"provenance: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
