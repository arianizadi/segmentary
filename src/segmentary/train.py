"""Train a curriculum end to end.

    python -m segmentary.train configs/base.yaml configs/models/segformer_b2.yaml \
        configs/curricula/cs_rs.yaml --seed 0 --devices 8

Configs merge left to right; --set applies dotted overrides on top, so an
ablation never needs a copy-pasted YAML file that drifts from its baseline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ExperimentConfig, config_hash, deep_merge, from_dict, load_yaml, to_dict
from .curriculum import run_curriculum
from .utils.provenance import discover_git_root
from .utils.seed import seed_everything


def parse_override(item: str) -> dict:
    """Turn ``train.iters=100`` into ``{"train": {"iters": 100}}``."""
    if "=" not in item:
        raise ValueError(f"--set expects key=value, got {item!r}")
    key, raw = item.split("=", 1)
    try:
        value = json.loads(raw)  # numbers, bools, lists, null
    except json.JSONDecodeError:
        value = raw  # bare string
    out: dict = value
    for part in reversed(key.split(".")):
        out = {part: out}
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("configs", nargs="+", type=Path, help="YAML configs, merged left to right")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--devices", default=None, help="'auto', an int, or a comma list of ids")
    ap.add_argument("--name", default=None, help="override the experiment name")
    ap.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="dotted config override, repeatable",
    )
    ap.add_argument(
        "--deterministic", action="store_true", help="fully deterministic kernels; costs throughput"
    )
    ap.add_argument(
        "--resume-checkpoint",
        type=Path,
        default=None,
        help=(
            "resume model, optimizer, scheduler, EMA, callbacks, and global step from a "
            "compatible Segmentary periodic checkpoint"
        ),
    )
    ap.add_argument("--print-config", action="store_true", help="print merged config and exit")
    return ap


def resolve_devices(spec):
    if spec is None or spec == "auto":
        return "auto"
    if "," in str(spec):
        return [int(x) for x in str(spec).split(",")]
    return int(spec)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    merged: dict = {}
    for path in args.configs:
        merged = deep_merge(merged, load_yaml(path))
    for item in args.set:
        merged = deep_merge(merged, parse_override(item))
    if args.seed is not None:
        merged = deep_merge(merged, {"train": {"seed": args.seed}})
    if args.name:
        merged["name"] = args.name

    cfg = from_dict(ExperimentConfig, merged)

    if args.print_config:
        print(json.dumps(to_dict(cfg), indent=2, sort_keys=True))
        return 0

    seed_everything(cfg.train.seed, deterministic=args.deterministic)
    devices = resolve_devices(args.devices if args.devices is not None else cfg.train.devices)

    print(f"experiment : {cfg.name}  (hash {config_hash(cfg)})")
    print(f"space      : {cfg.space}")
    print(f"model      : {cfg.model.arch}  tuning={cfg.model.tuning}  head={cfg.model.head}")
    print(f"stages     : {' -> '.join(s.name for s in cfg.stages)}")
    print(f"seed       : {cfg.train.seed}   devices: {devices}")

    provenance_root = discover_git_root([*args.configs, Path.cwd()]) or Path.cwd()
    results = run_curriculum(
        cfg,
        devices=devices,
        provenance_root=provenance_root,
        resume_checkpoint=args.resume_checkpoint,
    )

    print("\n=== curriculum complete ===")
    for r in results:
        miou = r.metrics.get("miou")
        print(f"  {r.name:<16} mIoU={miou if miou is None else f'{miou:.4f}'}  {r.results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
