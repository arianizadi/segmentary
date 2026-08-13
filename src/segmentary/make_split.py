#!/usr/bin/env python
"""Create a deterministic, group-disjoint folder segmentation dataset.

The input is an unsplit image directory and an unsplit mask directory.  Every
frame must have an explicit run/sequence id, supplied either by a JSON mapping
or by a regular expression.  The output has the layout consumed by
``CustomRailDataset``::

    <out>/images/{train,val,test}/<frame>.<ext>
    <out>/masks/{train,val,test}/<frame>.png
    <out>/splits.json

Fractions are applied to groups, not frames.  This is deliberate: a run is the
indivisible statistical unit.  The manifest records both group and frame counts
so a heavily imbalanced collection is visible before training.

Installed command:
    segmentary-make-split --images capture/images --masks capture/masks \
        --groups capture/groups.json --out-root data/my_project

Equivalent source-checkout examples:
    python scripts/make_custom_split.py \\
        --images /data/capture/images --masks /data/capture/masks \\
        --groups /data/capture/groups.json \\
        --out-root /datasets/my_project

    python scripts/make_custom_split.py \\
        --images /data/capture/images --masks /data/capture/masks \\
        --group-regex '^(?P<group>run_[^_]+)_' \\
        --out-root /datasets/my_project

By default the output tree contains absolute symlinks to the immutable source
files.  Use ``--materialize hardlink`` or ``--materialize copy`` when the output
must be self-contained.  Existing output roots are never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})
SPLIT_NAMES = ("train", "val", "test")


class SplitError(ValueError):
    """The requested split is unsafe or the source dataset is malformed."""


@dataclass(frozen=True)
class FramePair:
    key: str
    image: Path
    mask: Path


def _files_by_stem(directory: Path, extensions: frozenset[str], kind: str) -> dict[str, Path]:
    if not directory.is_dir():
        raise SplitError(f"{kind} directory not found: {directory}")

    found: dict[str, Path] = {}
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        if path.suffix.lower() not in extensions:
            continue
        previous = found.get(path.stem)
        if previous is not None:
            raise SplitError(
                f"duplicate {kind} key {path.stem!r}: {previous} and {path}; "
                "frame stems must be globally unique"
            )
        found[path.stem] = path.resolve()
    if not found:
        raise SplitError(f"no {kind} files with extensions {sorted(extensions)} under {directory}")
    return found


def discover_pairs(images: Path, masks: Path) -> dict[str, FramePair]:
    """Index a strict one-image/one-PNG-mask source collection."""
    image_by_key = _files_by_stem(images, IMAGE_EXTENSIONS, "image")
    mask_by_key = _files_by_stem(masks, frozenset({".png"}), "mask")

    image_keys = set(image_by_key)
    mask_keys = set(mask_by_key)
    missing_masks = sorted(image_keys - mask_keys)
    missing_images = sorted(mask_keys - image_keys)
    if missing_masks or missing_images:
        details: list[str] = []
        if missing_masks:
            details.append(
                f"{len(missing_masks)} image(s) lack a PNG mask; first: {missing_masks[0]}"
            )
        if missing_images:
            details.append(
                f"{len(missing_images)} mask(s) lack an image; first: {missing_images[0]}"
            )
        raise SplitError("source image/mask mismatch: " + "; ".join(details))

    return {
        key: FramePair(key=key, image=image_by_key[key], mask=mask_by_key[key])
        for key in sorted(image_keys)
    }


def load_group_manifest(path: Path, frame_keys: Iterable[str]) -> dict[str, str]:
    """Load either ``{frame: group}`` or ``{"groups": {frame: group}}`` JSON."""
    if not path.is_file():
        raise SplitError(f"group manifest not found: {path}")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SplitError(f"invalid JSON in group manifest {path}: {exc}") from exc
    if isinstance(raw, dict) and "groups" in raw:
        raw = raw["groups"]
    if not isinstance(raw, dict):
        raise SplitError(f"{path}: expected an object mapping each frame key to a run/sequence")

    groups: dict[str, str] = {}
    for key, group in raw.items():
        if not isinstance(key, str) or not isinstance(group, str) or not group.strip():
            raise SplitError(
                f"{path}: group entries must be non-empty string pairs, got {key!r}: {group!r}"
            )
        groups[key] = group.strip()

    expected = set(frame_keys)
    supplied = set(groups)
    missing = sorted(expected - supplied)
    unknown = sorted(supplied - expected)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing {len(missing)} frame(s), first {missing[0]!r}")
        if unknown:
            details.append(f"contains {len(unknown)} unknown frame(s), first {unknown[0]!r}")
        raise SplitError(
            f"{path}: group manifest does not exactly match the source: " + "; ".join(details)
        )
    return {key: groups[key] for key in sorted(groups)}


def groups_from_regex(pattern: str, frame_keys: Iterable[str]) -> dict[str, str]:
    """Extract groups with a named ``group`` capture or one positional capture."""
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise SplitError(f"invalid --group-regex {pattern!r}: {exc}") from exc

    has_named_group = "group" in regex.groupindex
    if not has_named_group and regex.groups != 1:
        raise SplitError(
            "--group-regex must contain a named (?P<group>...) capture or exactly one "
            "positional capture"
        )

    groups: dict[str, str] = {}
    for key in sorted(frame_keys):
        match = regex.search(key)
        if match is None:
            raise SplitError(f"--group-regex did not match frame key {key!r}")
        group = match.group("group") if has_named_group else match.group(1)
        if not group:
            raise SplitError(f"--group-regex captured an empty group for frame key {key!r}")
        groups[key] = group
    return groups


def _group_counts(groups: Mapping[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for group in groups.values():
        counts[group] = counts.get(group, 0) + 1
    return dict(sorted(counts.items()))


def _split_sizes(num_groups: int, val_frac: float, test_frac: float) -> tuple[int, int, int]:
    if not 0.0 <= val_frac < 1.0 or not 0.0 <= test_frac < 1.0:
        raise SplitError("--val-frac and --test-frac must each be in [0, 1)")
    if val_frac + test_frac >= 1.0:
        raise SplitError("--val-frac + --test-frac must be less than 1")

    requested = 1 + int(val_frac > 0.0) + int(test_frac > 0.0)
    if num_groups < requested:
        raise SplitError(
            f"need at least {requested} groups for the requested non-empty splits, got {num_groups}"
        )

    n_val = round(num_groups * val_frac)
    n_test = round(num_groups * test_frac)
    if val_frac > 0.0:
        n_val = max(1, n_val)
    if test_frac > 0.0:
        n_test = max(1, n_test)

    # Rounding two held-out fractions independently can consume every group.
    # Give groups back to the more over-represented held-out split until train
    # is non-empty.
    while n_val + n_test >= num_groups:
        val_excess = n_val - num_groups * val_frac
        test_excess = n_test - num_groups * test_frac
        if n_test > int(test_frac > 0.0) and test_excess >= val_excess:
            n_test -= 1
        elif n_val > int(val_frac > 0.0):
            n_val -= 1
        else:
            raise SplitError("the requested fractions leave no group for training")
    return num_groups - n_val - n_test, n_val, n_test


def split_by_group(
    frame_keys: Iterable[str],
    groups: Mapping[str, str],
    *,
    seed: int,
    val_frac: float,
    test_frac: float,
) -> dict[str, list[str]]:
    """Partition whole groups; no group can appear in more than one split."""
    keys = sorted(frame_keys)
    if set(keys) != set(groups):
        raise SplitError("group mapping must contain exactly one entry for every frame")

    unique_groups = sorted(set(groups.values()))
    n_train, n_val, n_test = _split_sizes(len(unique_groups), val_frac, test_frac)
    random.Random(seed).shuffle(unique_groups)
    group_sets = {
        "val": set(unique_groups[:n_val]),
        "test": set(unique_groups[n_val : n_val + n_test]),
        "train": set(unique_groups[n_val + n_test :]),
    }
    if len(group_sets["train"]) != n_train:
        raise AssertionError("internal split-size mismatch")

    splits = {
        name: sorted(key for key in keys if groups[key] in group_sets[name]) for name in SPLIT_NAMES
    }
    validate_split(splits, groups)
    return splits


def validate_split(splits: Mapping[str, Iterable[str]], groups: Mapping[str, str]) -> None:
    """Prove frame coverage, frame disjointness, and group disjointness."""
    seen_frames: set[str] = set()
    group_membership: dict[str, str] = {}
    for split_name in SPLIT_NAMES:
        frames = list(splits.get(split_name, ()))
        local_frames: set[str] = set()
        for key in frames:
            if key in local_frames:
                raise SplitError(f"frame {key!r} appears more than once in split {split_name!r}")
            local_frames.add(key)
        duplicate_frames = seen_frames.intersection(frames)
        if duplicate_frames:
            first = sorted(duplicate_frames)[0]
            raise SplitError(f"frame {first!r} appears in more than one split")
        seen_frames.update(frames)
        for key in frames:
            if key not in groups:
                raise SplitError(f"split {split_name!r} references frame {key!r} without a group")
            group = groups[key]
            previous = group_membership.setdefault(group, split_name)
            if previous != split_name:
                raise SplitError(
                    f"group {group!r} leaks across splits {previous!r} and {split_name!r}"
                )
    if seen_frames != set(groups):
        missing = sorted(set(groups) - seen_frames)
        raise SplitError(f"split does not cover every frame; first missing key is {missing[0]!r}")


def build_manifest(
    pairs: Mapping[str, FramePair],
    groups: Mapping[str, str],
    *,
    seed: int,
    val_frac: float,
    test_frac: float,
    image_source: Path,
    mask_source: Path,
) -> dict:
    splits = split_by_group(
        pairs,
        groups,
        seed=seed,
        val_frac=val_frac,
        test_frac=test_frac,
    )
    ordered_groups = {key: groups[key] for key in sorted(groups)}
    return {
        "_dataset": "custom",
        "_source": {
            "images": str(image_source.resolve()),
            "masks": str(mask_source.resolve()),
        },
        "_seed": seed,
        "_fractions_by_group": {
            "train": 1.0 - val_frac - test_frac,
            "val": val_frac,
            "test": test_frac,
        },
        "_frame_counts": {name: len(splits[name]) for name in SPLIT_NAMES},
        "_group_counts": {name: len({groups[key] for key in splits[name]}) for name in SPLIT_NAMES},
        "_total_frames": len(pairs),
        "_total_groups": len(set(groups.values())),
        "_frame_list_sha256": hashlib.sha256("\n".join(sorted(pairs)).encode()).hexdigest(),
        "_note": (
            "Split by whole run/sequence groups. Fractions apply to groups, never frames; "
            "adjacent frames from one run cannot cross split boundaries."
        ),
        "groups": ordered_groups,
        **splits,
    }


def _place_file(source: Path, destination: Path, materialize: str) -> None:
    if materialize == "symlink":
        destination.symlink_to(source)
    elif materialize == "hardlink":
        os.link(source, destination)
    elif materialize == "copy":
        shutil.copy2(source, destination)
    else:  # pragma: no cover - argparse and callers constrain this
        raise SplitError(f"unknown materialization mode {materialize!r}")


def write_dataset(
    out_root: Path,
    pairs: Mapping[str, FramePair],
    manifest: Mapping,
    *,
    materialize: str,
) -> None:
    """Write a complete dataset atomically, refusing to replace any output."""
    if out_root.exists():
        raise SplitError(
            f"output root already exists: {out_root}. Refusing to overwrite a dataset; "
            "choose a new --out-root."
        )
    out_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out_root.name}.tmp-", dir=out_root.parent))
    try:
        for split_name in SPLIT_NAMES:
            image_dir = staging / "images" / split_name
            mask_dir = staging / "masks" / split_name
            image_dir.mkdir(parents=True)
            mask_dir.mkdir(parents=True)
            for key in manifest[split_name]:
                pair = pairs[key]
                _place_file(
                    pair.image, image_dir / f"{key}{pair.image.suffix.lower()}", materialize
                )
                _place_file(pair.mask, mask_dir / f"{key}.png", materialize)
        (staging / "splits.json").write_text(json.dumps(manifest, indent=2) + "\n")
        staging.rename(out_root)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--images", required=True, type=Path, help="unsplit image directory")
    parser.add_argument(
        "--masks", required=True, type=Path, help="unsplit PNG index-mask directory"
    )
    parser.add_argument("--out-root", required=True, type=Path, help="new custom dataset root")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--groups", type=Path, help='JSON {"frame_key": "run_id"} (or a groups object)'
    )
    source.add_argument(
        "--group-regex",
        help="regex over frame stems with a named (?P<group>...) or one positional capture",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--val-frac", type=float, default=0.10, help="fraction of groups for val")
    parser.add_argument("--test-frac", type=float, default=0.10, help="fraction of groups for test")
    parser.add_argument(
        "--materialize",
        choices=("symlink", "hardlink", "copy"),
        default="symlink",
        help="how output files reference source data (default: symlink)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        pairs = discover_pairs(args.images, args.masks)
        if args.groups is not None:
            groups = load_group_manifest(args.groups, pairs)
        else:
            groups = groups_from_regex(args.group_regex, pairs)
        manifest = build_manifest(
            pairs,
            groups,
            seed=args.seed,
            val_frac=args.val_frac,
            test_frac=args.test_frac,
            image_source=args.images,
            mask_source=args.masks,
        )
        write_dataset(args.out_root, pairs, manifest, materialize=args.materialize)
    except (OSError, SplitError) as exc:
        parser.error(str(exc))

    print(
        f"wrote {args.out_root}: {manifest['_total_frames']} frames in "
        f"{manifest['_total_groups']} disjoint groups (seed={args.seed})"
    )
    for name in SPLIT_NAMES:
        print(
            f"  {name:<5} {manifest['_frame_counts'][name]:>6} frames  "
            f"{manifest['_group_counts'][name]:>5} groups"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
