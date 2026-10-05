#!/usr/bin/env python3
"""Build Paul's RailSem19 ``custom_split`` symlink layout for the forks' RS19 loaders.

    make_rs19_split.py --rs19 /data/izadia1/datasets/railsem19 \\
        --split-dir scripts/paul_forks/rs19_split --out /data/izadia1/datasets/railsem19-paul-split

Inputs: the official RailSem19 release (``jpgs/rs19_val/<id>.jpg``,
``uint8/rs19_val/<id>.png``, ``rs19-config.json``) and Paul's split lists
``{train,val,test}_split.txt`` (6800 / 850 / 850 ids, from ``pauls3/rail_segmentation``
``scripts/ai_server_splits``; tracked copies in ``scripts/paul_forks/rs19_split``).

Output (``<out>`` must be absent or empty; it is built in place and ``manifest.json`` is
written last, so a directory without it is incomplete; on failure everything is removed):

- ``trainVal_{images,masks}``: train + val (7650). SFNet's ``datasets/railsem19.py``
  trains here, as Paul did.
- ``train_{images,masks}``: train only (6800). HRNet's ``datasets/railsem19.py`` trains on
  ``train_images`` (the name Paul's ``custom_split`` used, see his ``list_files.py``).
- ``val_{images,masks}``: val (850). SFNet selects checkpoints here; these images are also
  in ``trainVal_``, so that selection is in-sample (Paul's protocol, kept for fidelity).
- ``test_{images,masks}``: test (850). HRNet's loader uses ``test_images`` for both
  ``val`` and ``test`` mode (``datasets/railsem19.py:57``), so HRNet selects on test.
- ``rs19-config.json``: symlink to the release's class config that both loaders read.
- ``manifest.json``: counts, split-file sha256s, source root, per-loader notes.

Images are ``<id>.jpg`` and masks ``<id>.png``: SFNet derives the mask name with
``.replace('.jpg', '.png')`` and HRNet globs ``*.jpg`` with mask extension ``png``.
Unless ``--skip-mask-check``, every mask is decoded and must be single-channel uint8 with
values within {0..18, 255} and the same size as its image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

SPLIT_FILES = {"train": "train_split.txt", "val": "val_split.txt", "test": "test_split.txt"}
PAUL_COUNTS = {"train": 6800, "val": 850, "test": 850}
NUM_CLASSES = 19
LAYOUT = {
    "trainVal": ("train", "val"),
    "train": ("train",),
    "val": ("val",),
    "test": ("test",),
}
LOADER_NOTES = {
    "sfnet": "datasets/railsem19.py make_dataset: train=trainVal_*, val=val_*, test=test_* "
    "(test=True); mask = image name with .jpg -> .png",
    "hrnet": "datasets/railsem19.py: train=train_*, val and test both = test_* "
    "(lines 50-57; the validation_* branch is commented out); images *.jpg, masks .png",
}
PROTOCOL_NOTES = [
    "trainVal = Paul's train + val (6800 + 850), as Paul did, for fidelity.",
    "SFNet selects its RS19 checkpoint on val_, which is inside trainVal_ (in-sample "
    "selection, Paul's protocol). It only chooses the upstream RS19 checkpoint, not RAD.",
    "HRNet's RS19 loader validates on test_images, so an HRNet RS19 run selects on test "
    "(Paul's protocol). Report RS19 test mIoU for comparison with the paper only.",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"make_rs19_split: {message}")


def read_split(path: Path) -> list[str]:
    ids = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    bad = [i for i in ids if not re.fullmatch(r"rs\d{5}", i)]
    if bad:
        fail(f"{path.name}: malformed ids {bad[:5]}")
    if len(set(ids)) != len(ids):
        fail(f"{path.name}: duplicate ids")
    return ids


def check_mask(image: Path, mask: Path) -> None:
    import numpy as np
    from PIL import Image

    with Image.open(mask) as im:
        values = np.asarray(im)
    if values.ndim != 2 or values.dtype != np.uint8:
        fail(f"{mask.name}: not a single-channel uint8 mask")
    bad = sorted(set(np.unique(values).tolist()) - set(range(NUM_CLASSES)) - {255})
    if bad:
        fail(f"{mask.name}: values {bad} outside 0..{NUM_CLASSES - 1} and 255")
    with Image.open(image) as im:
        if im.size != (values.shape[1], values.shape[0]):
            fail(f"{image.name}: size {im.size} differs from its mask {values.shape[::-1]}")


def build(
    rs19: Path, split_dir: Path, out: Path, expect: dict[str, int], check_masks: bool
) -> dict:
    rs19, split_dir, out = rs19.resolve(), split_dir.resolve(), out.absolute()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        fail(f"output exists and is not an empty directory: {out}")
    splits = {name: read_split(split_dir / filename) for name, filename in SPLIT_FILES.items()}
    for name, ids in splits.items():
        if len(ids) != expect[name]:
            fail(f"{name}: {len(ids)} ids, expected {expect[name]}")
    seen: dict[str, str] = {}
    for name, ids in splits.items():
        for i in ids:
            if i in seen:
                fail(f"{i} is in both {seen[i]} and {name}")
            seen[i] = name
    images_dir, masks_dir = rs19 / "jpgs" / "rs19_val", rs19 / "uint8" / "rs19_val"
    config = rs19 / "rs19-config.json"
    if not config.is_file():
        fail(f"missing {config}")
    for i in sorted(seen):
        image, mask = images_dir / f"{i}.jpg", masks_dir / f"{i}.png"
        if not image.is_file() or not mask.is_file():
            fail(f"{i}: missing image or mask under {rs19}")
        if check_masks:
            check_mask(image, mask)

    created = not out.exists()
    out.mkdir(parents=True, exist_ok=True)
    try:
        for prefix, members in LAYOUT.items():
            for kind in ("images", "masks"):
                (out / f"{prefix}_{kind}").mkdir()
            for name in members:
                for i in splits[name]:
                    (out / f"{prefix}_images" / f"{i}.jpg").symlink_to(images_dir / f"{i}.jpg")
                    (out / f"{prefix}_masks" / f"{i}.png").symlink_to(masks_dir / f"{i}.png")
        (out / "rs19-config.json").symlink_to(config)
        manifest = {
            "schema_version": 1,
            "source_root": str(rs19),
            "images_dir": str(images_dir),
            "masks_dir": str(masks_dir),
            "rs19_config_sha256": sha256_file(config),
            "split_source": "pauls3/rail_segmentation scripts/ai_server_splits",
            "split_files": {
                name: {"path": str(split_dir / f), "sha256": sha256_file(split_dir / f)}
                for name, f in SPLIT_FILES.items()
            },
            "counts": {
                prefix: sum(len(splits[n]) for n in members) for prefix, members in LAYOUT.items()
            },
            "layout": {prefix: list(members) for prefix, members in LAYOUT.items()},
            "masks_checked": check_masks,
            "loaders": LOADER_NOTES,
            "protocol_notes": PROTOCOL_NOTES,
            "builder": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    except BaseException:
        if created:
            shutil.rmtree(out, ignore_errors=True)
        else:
            for child in out.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
        raise
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--rs19", type=Path, required=True, help="RailSem19 release root")
    p.add_argument("--split-dir", type=Path, required=True, help="has {train,val,test}_split.txt")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--expect-counts",
        default="6800,850,850",
        help="train,val,test sizes the split files must have (Paul's: 6800,850,850)",
    )
    p.add_argument("--skip-mask-check", action="store_true")
    args = p.parse_args(argv)
    counts = [int(x) for x in args.expect_counts.split(",")]
    if len(counts) != 3:
        fail("--expect-counts needs three numbers")
    manifest = build(
        args.rs19,
        args.split_dir,
        args.out,
        dict(zip(("train", "val", "test"), counts, strict=True)),
        not args.skip_mask_check,
    )
    print(json.dumps({"out": str(args.out), "counts": manifest["counts"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
