#!/usr/bin/env python
"""Generate reproducible benchmark tables from runs/**/results.json.

Emits markdown and CSV. Runs differing only in seed are aggregated into
mean +/- std, because single-seed segmentation deltas under ~1 mIoU are noise and
staged-transfer effects land right in that band.

    segmentary-table --runs runs --out reports
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from segmentary.config import config_hash
from segmentary.utils.results import load_results


def find_results(root: Path) -> list[dict]:
    records = []
    for path in sorted(root.rglob("results.json")):
        try:
            record = load_results(path).to_dict()
        except (OSError, TypeError, ValueError) as exc:
            # Fail closed: silently omitting one seed changes both the mean and its
            # uncertainty while still leaving a plausible-looking benchmark table.
            raise SystemExit(f"invalid result record {path}: {exc}") from exc
        records.append({"_path": path, **record})
    return records


def _fail(record: dict, message: str) -> None:
    raise SystemExit(f"{record.get('_path', '<result>')}: {message}")


def _metric(record: dict, value: object, label: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(record, f"{label} must be a finite number in [0, 1], got {value!r}")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        _fail(record, f"{label} must be a finite number in [0, 1], got {value!r}")
    return number


def _validate_record(record: dict, classes: list[str]) -> tuple[str, str, str]:
    """Return arch plus seed-neutral config and preprocessing signatures."""
    for field in ("name", "stage"):
        if not isinstance(record.get(field), str) or not record[field]:
            _fail(record, f"{field} must be a non-empty string")

    seed = record.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        _fail(record, f"seed must be an integer, got {seed!r}")

    config = record.get("config")
    if not isinstance(config, dict):
        _fail(record, "config must be a mapping")
    if config.get("name") != record["name"]:
        _fail(
            record,
            f"record name {record['name']!r} does not match config.name {config.get('name')!r}",
        )
    train = config.get("train")
    if not isinstance(train, dict):
        _fail(record, "config.train must be a mapping containing the replicate seed")
    config_seed = train.get("seed")
    if isinstance(config_seed, bool) or not isinstance(config_seed, int):
        _fail(record, f"config.train.seed must be an integer, got {config_seed!r}")
    if config_seed != seed:
        _fail(record, f"record seed {seed} does not match config.train.seed {config_seed}")

    model = config.get("model")
    if not isinstance(model, dict) or not isinstance(model.get("arch"), str) or not model["arch"]:
        _fail(record, "config.model.arch must be a non-empty string")
    arch = model["arch"]

    recorded_hash = record.get("config_hash")
    expected_hash = config_hash(config)
    if recorded_hash != expected_hash:
        _fail(
            record,
            f"config_hash {recorded_hash!r} does not match the embedded config ({expected_hash})",
        )

    sha = record.get("git_sha")
    if not isinstance(sha, str) or not sha:
        _fail(record, "git_sha must be a non-empty string")
    if record.get("git_dirty") not in (True, False) or not isinstance(record["git_dirty"], bool):
        _fail(record, "git_dirty must be a boolean")

    metrics = record.get("metrics")
    if not isinstance(metrics, dict):
        _fail(record, "metrics must be a mapping")
    _metric(record, metrics.get("miou"), "metrics.miou")
    _metric(record, metrics.get("macc"), "metrics.macc")
    _metric(record, metrics.get("pixel_accuracy"), "metrics.pixel_accuracy")
    boundary = metrics.get("boundary")
    if not isinstance(boundary, dict):
        _fail(record, "metrics.boundary must be a mapping")
    _metric(record, boundary.get("macro_f1"), "metrics.boundary.macro_f1")
    per_class = metrics.get("per_class_iou")
    if not isinstance(per_class, dict):
        _fail(record, "metrics.per_class_iou must be a mapping")
    for cls in classes:
        if cls in per_class:
            _metric(record, per_class[cls], f"metrics.per_class_iou.{cls}", optional=True)

    wall_clock = record.get("wall_clock_s")
    if (
        isinstance(wall_clock, bool)
        or not isinstance(wall_clock, (int, float))
        or not math.isfinite(float(wall_clock))
        or wall_clock < 0
    ):
        _fail(record, f"wall_clock_s must be a finite non-negative number, got {wall_clock!r}")
    peak = record.get("peak_vram_bytes")
    if not isinstance(peak, dict):
        _fail(record, "peak_vram_bytes must be a mapping")
    for device, value in peak.items():
        if (
            not isinstance(device, str)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            _fail(record, f"peak_vram_bytes has invalid entry {device!r}: {value!r}")

    env = record.get("env")
    if not isinstance(env, dict):
        _fail(record, "env must be a mapping")
    normalization = env.get("input_normalization")
    if normalization is not None and not isinstance(normalization, dict):
        _fail(record, "env.input_normalization must be a mapping when present")
    normalization_signature = json.dumps(normalization, sort_keys=True, separators=(",", ":"))

    # Replicates may differ in exactly one config leaf: their seed. Keeping the
    # rest in a canonical string makes an accidental tuning/LR/head change fatal.
    normalized = json.loads(json.dumps(config, sort_keys=True))
    del normalized["train"]["seed"]
    signature = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return arch, signature, normalization_signature


def agg(values: list[float | None]) -> tuple[float, float, int]:
    clean = [v for v in values if v is not None and v == v]
    if not clean:
        return float("nan"), float("nan"), 0
    mean = statistics.fmean(clean)
    std = statistics.stdev(clean) if len(clean) > 1 else 0.0
    return mean, std, len(clean)


def fmt(mean: float, std: float, n: int) -> str:
    if n == 0:
        return "--"
    if n == 1:
        return f"{100 * mean:.2f}"
    return f"{100 * mean:.2f} ± {100 * std:.2f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--runs", type=Path, default=Path("runs"))
    ap.add_argument("--out", type=Path, default=Path("reports"))
    ap.add_argument(
        "--classes",
        nargs="*",
        default=[],
        help="optional per-class IoU columns (class names must exist in result records)",
    )
    ap.add_argument(
        "--stage",
        dest="stages",
        action="append",
        default=[],
        help="include only this exact stage (repeatable; all records are still validated)",
    )
    ap.add_argument(
        "--experiment",
        dest="experiments",
        action="append",
        default=[],
        help="include only this experiment name (repeatable; all records are still validated)",
    )
    args = ap.parse_args(argv)

    if not args.runs.is_dir():
        raise SystemExit(f"no runs directory at {args.runs}")
    records = find_results(args.runs)
    if not records:
        raise SystemExit(f"no results.json found under {args.runs}")
    # Validate every discovered record before applying presentation filters. A
    # corrupt or schema-incompatible run must not disappear from a plausible-
    # looking filtered table merely because its stage/name could not be trusted.
    for r in records:
        arch, signature, normalization_signature = _validate_record(r, args.classes)
        r["_arch"] = arch
        r["_config_signature"] = signature
        r["_normalization_signature"] = normalization_signature

    selected = [
        record
        for record in records
        if (not args.stages or record["stage"] in args.stages)
        and (not args.experiments or record["name"] in args.experiments)
    ]
    if not selected:
        raise SystemExit(
            f"no result records matched stage={args.stages or 'ALL'} "
            f"experiment={args.experiments or 'ALL'} under {args.runs}"
        )
    print(f"found {len(records)} result files; selected {len(selected)}")

    # Group by the human-readable identity first, then prove that the members are
    # true seed replicates before allowing their numbers to collapse into one row.
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in selected:
        groups[(r["name"], r["stage"], r["_arch"])].append(r)

    rows = []
    for (name, stage, arch), items in sorted(groups.items()):
        by_seed: dict[int, dict] = {}
        for item in items:
            seed = item["seed"]
            if seed in by_seed:
                raise SystemExit(
                    f"duplicate seed {seed} for {name}/{stage}/{arch}: "
                    f"{by_seed[seed]['_path']} and {item['_path']}"
                )
            by_seed[seed] = item
        items = [by_seed[seed] for seed in sorted(by_seed)]

        if len({item["_config_signature"] for item in items}) != 1:
            paths = ", ".join(str(item["_path"]) for item in items)
            raise SystemExit(
                f"cannot aggregate {name}/{stage}/{arch}: configs differ beyond train.seed ({paths})"
            )
        if len({item["_normalization_signature"] for item in items}) != 1:
            paths = ", ".join(str(item["_path"]) for item in items)
            raise SystemExit(
                f"cannot aggregate {name}/{stage}/{arch}: effective input normalization "
                f"differs ({paths})"
            )
        provenance = {(item["git_sha"], item["git_dirty"]) for item in items}
        if len(provenance) != 1:
            paths = ", ".join(str(item["_path"]) for item in items)
            raise SystemExit(
                f"cannot aggregate {name}/{stage}/{arch}: git provenance differs ({paths})"
            )
        if len(items) > 1 and items[0]["git_dirty"]:
            raise SystemExit(
                f"cannot aggregate {name}/{stage}/{arch}: dirty runs do not prove that "
                "the same uncommitted code produced every seed"
            )

        metrics = [i.get("metrics") or {} for i in items]
        row = {
            "experiment": name,
            "stage": stage,
            "arch": arch,
            "seeds": len(items),
            "miou": fmt(*agg([m.get("miou") for m in metrics])),
            "macc": fmt(*agg([m.get("macc") for m in metrics])),
            "pixel_accuracy": fmt(*agg([m.get("pixel_accuracy") for m in metrics])),
            "boundary_f1": fmt(*agg([(m.get("boundary") or {}).get("macro_f1") for m in metrics])),
            "wall_clock_h": f"{agg([i.get('wall_clock_s') for i in items])[0] / 3600:.2f}",
            "peak_vram_gb": f"{max((max((v or {}).values(), default=0) for v in (i.get('peak_vram_bytes') for i in items)), default=0) / 2**30:.1f}",
            "git": (items[0].get("git_sha") or "?")[:8]
            + ("*" if items[0].get("git_dirty") else ""),
        }
        for cls in args.classes:
            values = [(m.get("per_class_iou") or {}).get(cls) for m in metrics]
            present = [value is not None for value in values]
            if any(present) and not all(present):
                missing_seeds = [
                    item["seed"] for item, exists in zip(items, present, strict=True) if not exists
                ]
                raise SystemExit(
                    f"cannot aggregate {name}/{stage}/{arch}: class {cls!r} is missing for "
                    f"only seeds {missing_seeds}; unavailable classes must be null for every seed"
                )
            row[cls] = fmt(*agg(values))
        rows.append(row)

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "results.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    headers = list(rows[0])
    md = [
        "# Results",
        "",
        "Generated by `segmentary-table` from `runs/**/results.json`. "
        "Do not edit by hand. `*` on a git sha marks a dirty working tree.",
        "",
        "All values are percentages; mean ± std over seeds where more than one exists.",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        md.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
    md += [
        "",
        "## Notes",
        "",
        "* mIoU is over the active classes in the experiment's canonical label space; "
        "optional per-class columns are selected with `--classes`.",
        "* A single-seed row (seeds=1) carries no error bar and should not be used to "
        "claim a sub-1-point difference.",
        "* `wall_clock_h` and `peak_vram_gb` describe only the selected result stage. "
        "When the table filters standalone evaluation records, they are evaluation "
        "costs—not total curriculum training costs.",
    ]
    md_path = args.out / "results.md"
    md_path.write_text("\n".join(md) + "\n")

    print(f"wrote {csv_path}\nwrote {md_path}\n")
    print("\n".join(md[6:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
