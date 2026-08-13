#!/usr/bin/env python
"""Generate a reproducible RailSem19 train/val/test split and commit it to git.

RailSem19 ships no official split ("We do not recommend specific frames for
validation, training, testing" -- readme.txt), so the split is an experimental
choice that must be versioned with the code. This writes a JSON file recording
the seed, the ratios and the resulting file lists.

A random split is defensible HERE because the v1 release contains exactly one
frame per sequence, so there are no near-duplicate neighbouring frames to leak.
The optional --official mode instead converts the shipped rs19_splits4000 lists,
which cover only 4000 of the 8500 frames.

Usage:
    python scripts/make_railsem19_split.py --root data/railsem19
    python scripts/make_railsem19_split.py --root ... --official <dir with train.txt>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", required=True, type=Path, help="RailSem19 dataset root")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output JSON (default: splits/railsem19_seed<S>.json)",
    )
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--val-frac", type=float, default=0.10)
    ap.add_argument("--test-frac", type=float, default=0.10)
    ap.add_argument(
        "--official", type=Path, default=None, help="dir holding the shipped train/val/test.txt"
    )
    args = ap.parse_args()

    image_dir = args.root / "jpgs" / "rs19_val"
    label_dir = args.root / "uint8" / "rs19_val"
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise SystemExit(f"RailSem19 layout not found under {args.root}")

    keys = sorted(
        p.stem for p in image_dir.glob("*.jpg") if (label_dir / f"{p.stem}.png").is_file()
    )
    if not keys:
        raise SystemExit(f"no matched image/label pairs under {args.root}")
    print(f"found {len(keys)} matched frames")

    if args.official:
        splits = {}
        for name in ("train", "val", "test"):
            txt = args.official / f"{name}.txt"
            if not txt.is_file():
                raise SystemExit(f"missing {txt}")
            listed = [ln.strip() for ln in txt.read_text().splitlines() if ln.strip()]
            unknown = sorted(set(listed) - set(keys))
            if unknown:
                raise SystemExit(f"{txt} lists {len(unknown)} unknown frames, first {unknown[0]}")
            splits[name] = sorted(listed)
        source = f"official rs19_splits4000 from {args.official}"
        covered = sum(len(v) for v in splits.values())
        print(f"official split covers {covered}/{len(keys)} frames ({covered / len(keys):.0%})")
    else:
        shuffled = list(keys)
        random.Random(args.seed).shuffle(shuffled)
        n = len(shuffled)
        n_val = round(n * args.val_frac)
        n_test = round(n * args.test_frac)
        splits = {
            "val": sorted(shuffled[:n_val]),
            "test": sorted(shuffled[n_val : n_val + n_test]),
            "train": sorted(shuffled[n_val + n_test :]),
        }
        source = f"seeded random split (seed={args.seed}) over all {n} frames"

    # Splits must be disjoint -- this is the leakage check, asserted not assumed.
    for a in splits:
        for b in splits:
            if a < b:
                overlap = set(splits[a]) & set(splits[b])
                if overlap:
                    raise SystemExit(
                        f"{a}/{b} overlap on {len(overlap)} frames: {sorted(overlap)[:5]}"
                    )

    payload = {
        "_dataset": "railsem19",
        "_source": source,
        "_seed": args.seed,
        "_counts": {k: len(v) for k, v in splits.items()},
        "_total_frames_available": len(keys),
        "_frame_list_sha256": hashlib.sha256("\n".join(keys).encode()).hexdigest(),
        "_note": (
            "RailSem19 v1 has one frame per sequence, so a random split does not leak "
            "neighbouring frames. Do not copy this policy to video datasets."
        ),
        **splits,
    }

    out = args.out or REPO / "splits" / f"railsem19_seed{args.seed}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {out}")
    for k, v in splits.items():
        print(f"  {k:<6} {len(v):>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
