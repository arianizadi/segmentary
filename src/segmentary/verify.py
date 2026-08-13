#!/usr/bin/env python
"""Dump augmented image/mask overlays and audit a semantic-segmentation mapping.

LOOK AT THE PNGs. Misalignment, a wrong palette and bad ignore-padding are all
obvious in one glance and completely invisible in a loss curve. This script also
runs the checks that can be automated:

  * every native id present on disk is declared by the taxonomy mapping;
  * the augmented masks never contain an id outside the canonical space;
  * padding introduced by augmentation is ignore_index, never class 0;
  * for the built-in RailSem19 loader, its class file still agrees with the YAML;
  * class pixel frequencies, so you can see which classes are rare before you
    are surprised by their IoU.

Usage:
  segmentary-verify --dataset my_data --loader folder --root /data/my_data \
      --space my_space --taxonomy taxonomy
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from .config import DataConfig
from .data.loaders import build_dataset, load_data_mapping, resolve_dataset_loader
from .data.railsem19 import load_native_classes
from .data.transforms import AugConfig, build_train_transform, denormalize
from .taxonomy import colorize, load_space
from .utils.seed import seed_transforms

IGNORE = 255


def overlay(image: np.ndarray, mask: np.ndarray, space, alpha: float = 0.55) -> np.ndarray:
    """Blend a colourised mask onto the image; ignore stays as raw image."""
    rgb = colorize(mask.astype(np.uint8), space)
    out = image.astype(np.float32).copy()
    known = mask != IGNORE
    out[known] = (1 - alpha) * out[known] + alpha * rgb[known].astype(np.float32)
    # Ignored pixels get a magenta hatch so padding is unmistakable.
    yy, xx = np.nonzero(~known)
    stripe = ((yy + xx) % 16) < 3
    out[yy[stripe], xx[stripe]] = (255, 0, 255)
    return out.round().clip(0, 255).astype(np.uint8)


def _scan_native_labels(dataset, indices) -> tuple[set[int], Counter[int]]:
    """Read labels through the dataset contract, including custom decoders."""
    native_ids: set[int] = set()
    native_hist: Counter[int] = Counter()
    for index in indices:
        sample = dataset.samples[int(index)]
        arr = np.asarray(dataset.load_label(sample.label))
        if arr.ndim != 2:
            raise ValueError(
                f"{sample.label}: load_label() returned shape {arr.shape}; expected one HW mask"
            )
        ids, counts = np.unique(arr, return_counts=True)
        native_ids.update(int(value) for value in ids)
        native_hist.update(
            {int(value): int(count) for value, count in zip(ids, counts, strict=True)}
        )
    return native_ids, native_hist


def _overlay_filename(dataset: str, index: int, key: str) -> str:
    """Create one flat, collision-resistant filename from an untrusted sample key."""
    raw = f"{dataset}:{key}"
    safe = "".join(
        char if char.isascii() and (char.isalnum() or char in "-_") else "_" for char in raw
    ).strip("_")
    safe = safe[:96] or "sample"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{index:02d}_{safe}_{digest}.png"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dataset", required=True, help="logical dataset name")
    ap.add_argument(
        "--loader",
        default=None,
        help="built-in loader id (for example folder) or package.module:DatasetClass",
    )
    ap.add_argument("--mapping", default=None, help="taxonomy mapping stem; defaults to dataset")
    ap.add_argument(
        "--loader-options",
        default="{}",
        metavar="JSON",
        help="loader-specific JSON object, for example '{\"recursive\": false}'",
    )
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--split", default="train")
    ap.add_argument("--split-file", type=Path, default=None)
    ap.add_argument("--space", required=True, help="canonical label-space name")
    ap.add_argument("--variant", default=None)
    ap.add_argument("--taxonomy", type=Path, default=Path("taxonomy"))
    ap.add_argument("--out", type=Path, default=Path("debug") / "verify")
    ap.add_argument("--n-overlays", type=int, default=20)
    ap.add_argument("--n-scan", type=int, default=200, help="masks to scan for id coverage")
    ap.add_argument("--crop", type=int, nargs=2, default=(1024, 1024))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    if args.n_scan < 1:
        ap.error("--n-scan must be at least 1")
    if args.n_overlays < 0:
        ap.error("--n-overlays cannot be negative")
    if any(size < 1 for size in args.crop):
        ap.error("--crop dimensions must be positive")

    try:
        loader_options = json.loads(args.loader_options)
    except json.JSONDecodeError as exc:
        ap.error(f"--loader-options must be valid JSON: {exc}")
    if not isinstance(loader_options, dict):
        ap.error("--loader-options must decode to a JSON object")

    space = load_space(args.taxonomy, args.space)
    data = DataConfig(
        name=args.dataset,
        root=str(args.root),
        loader=args.loader,
        mapping=args.mapping,
        loader_options=loader_options,
        variant=args.variant,
        split_file=str(args.split_file) if args.split_file is not None else None,
    )
    mapping = load_data_mapping(data, space, args.taxonomy)
    loader_name, _ = resolve_dataset_loader(data)
    aug = AugConfig(crop=tuple(args.crop))
    ds = build_dataset(data, space, args.taxonomy, args.split, build_train_transform(aug))
    seed_transforms(ds, args.seed)

    print(f"space   : {space.name} ({space.num_classes} classes, ignore={space.ignore_index})")
    print(
        f"mapping : {mapping.dataset}{'/' + mapping.variant if mapping.variant else ''}"
        f"  <- {mapping.source}"
    )
    print(f"dataset : {ds.describe()}")
    print(
        f"active  : {len(mapping.active_ids)} classes"
        f"  inactive: {[space.classes[i].name for i in mapping.inactive_ids]}"
    )

    failures: list[str] = []

    # --- the dataset's own class list must still agree with our YAML ----------
    if loader_name == "railsem19":
        native = load_native_classes(args.root)
        declared = set(mapping._declared) - {IGNORE}
        if declared != set(native):
            failures.append(
                f"rs19-config.json defines ids {sorted(native)} but the mapping declares "
                f"{sorted(declared)}"
            )
        else:
            print(f"rs19-config.json agrees with the mapping ({len(native)} native classes)")

    # --- native id coverage on real files ------------------------------------
    rng = np.random.default_rng(args.seed)
    idx = rng.choice(len(ds), size=min(args.n_scan, len(ds)), replace=False)
    native_ids, native_hist = _scan_native_labels(ds, idx)
    print(f"\nscanned {len(idx)} label files; native ids present: {sorted(native_ids)}")
    coverage_ok = True
    try:
        mapping.assert_covers(native_ids)
        print("coverage: PASS (every native id on disk is declared)")
    except Exception as exc:  # surfaced, never swallowed
        failures.append(str(exc))
        coverage_ok = False

    # Dataset __getitem__ applies a uint8 LUT. Invalid native ids must be
    # reported without continuing into that indexing operation and replacing
    # the useful taxonomy error with an IndexError.
    if not coverage_ok:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        print("overlays skipped until native-id coverage is fixed")
        return 1

    # --- canonical distribution ----------------------------------------------
    canon: Counter[int] = Counter()
    for nid, n in native_hist.items():
        if 0 <= nid < len(mapping.lut):
            canon[int(mapping.lut[nid])] += n
    total = sum(canon.values())
    print(f"\n{'id':>3} {'class':<16} {'pixels':>14} {'share':>8}")
    for cid in sorted(canon):
        name = "IGNORE" if cid == IGNORE else space.classes[cid].name
        print(f"{cid:>3} {name:<16} {canon[cid]:>14,} {100 * canon[cid] / total:>7.3f}%")
    rare = [
        space.classes[c].name for c in sorted(canon) if c != IGNORE and canon[c] / total < 0.005
    ]
    if rare:
        print(f"\nrare classes (<0.5% of pixels): {rare}")
        print("  these dominate the mIoU variance; report their per-class IoU explicitly")

    # --- augmented samples ----------------------------------------------------
    args.out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    pad_seen = 0
    for n in range(min(args.n_overlays, len(ds))):
        sample = ds[int(rng.integers(len(ds)))]
        img = denormalize(sample["image"], aug)
        mask = sample["mask"].numpy()

        bad = sorted(set(np.unique(mask).tolist()) - set(range(space.num_classes)) - {IGNORE})
        if bad:
            failures.append(f"augmented mask holds out-of-space ids {bad}")
        not_active = sorted(set(np.unique(mask).tolist()) - {IGNORE} - set(mapping.active_ids))
        if not_active:
            failures.append(f"augmented mask holds inactive ids {not_active}")
        pad_seen += int((mask == IGNORE).any())

        display_mask = mask.copy()
        if bad:
            display_mask[~np.isin(display_mask, [*range(space.num_classes), IGNORE])] = IGNORE
        Image.fromarray(overlay(img, display_mask, space)).save(
            args.out / _overlay_filename(args.dataset, n, str(sample["key"]))
        )

    print(f"\nwrote {min(args.n_overlays, len(ds))} overlays to {args.out}")
    print(f"  {pad_seen} of them contain ignore pixels (magenta hatch)")
    print(
        "  LOOK AT THEM: check mask/image alignment, colours, and that hatching only "
        "appears on real padding or genuinely unlabelled regions."
    )

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nall automated checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
