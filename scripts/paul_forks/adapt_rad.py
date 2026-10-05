#!/usr/bin/env python3
"""Expose one prepared RAD 9/24 arm in the flat layout Paul's two forks read.

    adapt_rad.py <arm_root> <out_dir> [--expect-total 314]

``<arm_root>`` is a dataset written by ``scripts/prepare_rad.py`` (``images/<split>/<group>/
<stem>.<ext>``, ``masks/<split>/<group>/<stem>.png``, ``splits.json``, ``classes.json``,
``audit/samples.json``). ``<out_dir>`` must not exist; it is built under
``<out_dir>.partial`` and renamed when every check has passed:

- ``{trainVal,val,test}_{images,masks}/<group>__<stem>.png``: absolute symlinks into the
  arm. ``train`` goes to ``trainVal_``; ``trainVal_`` holds train only (Paul's trainVal
  also contained val; that is a deliberate deviation so selection on ``val_`` is held out).
- Every image link is named ``.png``, including the 9 ``.jpg`` sources: the HRNet loader
  globs ``*.png`` only (``base_loader.find_images``) and the SFNet loader lists the
  directory and derives the mask name with ``.replace('.jpg', '.png')``. Both open images
  with PIL, which decodes by content. The real extension is kept in ``manifest.json``.
  This is what the September ``adapt.py`` did too.
- ``classes.json``: ``{"labels": [{"id", "name", "color"}, ...]}``, the format both forks'
  ``rtisrail22`` loaders read (``config['labels'][i]['color'|'name']``).
- ``manifest.json``: one entry per image with key, split, link name, sources, hashes.
- ``validation-support.json`` / ``test-support.json``: exact per-class ground-truth pixel
  counts (ignore 255 excluded), cross-checked against ``audit/samples.json``.

Checks (all fail closed): 21 classes with ids 0..20, class 13 = mud-pumping, ignore 255;
splits.json and audit/samples.json agree on every key, split and extension; image bytes
and decoded mask pixels match their audit sha256; mask values within {0..20, 255}; mask
size equals image size; no key in two splits; ``--expect-total`` images; link names
unique; for a grouped arm, no group spans two splits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SPLITS = ("train", "val", "test")
PREFIX = {"train": "trainVal", "val": "val", "test": "test"}
NUM_CLASSES = 21
MUD = 13
IGNORE = 255
DEVIATIONS = [
    "trainVal_ holds the train split only; Paul's trainVal also contained val, which made "
    "his checkpoint selection on val in-sample. Here val_ is held out.",
    "Every image link is named <group>__<stem>.png; 9 sources are JPEG files and are "
    "decoded by content (PIL), exactly as in the September adapter.",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"adapt_rad: {message}")


def load_classes(arm: Path) -> dict:
    schema = json.loads((arm / "classes.json").read_text())
    classes = schema.get("classes", [])
    if [c.get("id") for c in classes] != list(range(NUM_CLASSES)):
        fail(f"expected {NUM_CLASSES} classes with ids 0..{NUM_CLASSES - 1}")
    if classes[MUD]["name"] != "mud-pumping":
        fail(f"class {MUD} is {classes[MUD]['name']!r}, not 'mud-pumping'")
    if schema.get("ignore_index") != IGNORE:
        fail(f"ignore_index is {schema.get('ignore_index')!r}, not {IGNORE}")
    if any(len(c.get("color", [])) != 3 for c in classes):
        fail("every class needs an RGB colour for the forks' colormap")
    return schema


def check_splits(splits: dict, samples: list[dict], expect_total: int) -> dict[str, str]:
    membership: dict[str, str] = {}
    for split in SPLITS:
        for key in splits[split]:
            if key in membership:
                fail(f"{key} is in both {membership[key]} and {split}")
            membership[key] = split
    if len(membership) != expect_total:
        fail(f"{len(membership)} images in splits.json, expected {expect_total}")
    audit = {row["key"]: row for row in samples}
    if len(audit) != len(samples) or set(audit) != set(membership):
        fail("audit/samples.json and splits.json do not list the same keys")
    for key, split in membership.items():
        row = audit[key]
        if row["split"] != split or f"{row['group']}/{row['stem']}" != key:
            fail(f"audit row for {key} disagrees with splits.json")
    grouped = splits.get("_split_method") == "grouped" or "groups" in splits
    if grouped:
        groups = splits.get("groups")
        if not isinstance(groups, dict) or set(groups) != set(membership):
            fail("grouped arm: splits.json groups must cover exactly the split keys")
        spans: dict[str, set[str]] = {}
        for key, group in groups.items():
            if key.split("/")[0] != group:
                fail(f"grouped arm: {key} is filed under a different group {group!r}")
            spans.setdefault(group, set()).add(membership[key])
        crossing = {g: sorted(s) for g, s in spans.items() if len(s) > 1}
        if crossing:
            fail(f"grouped arm: groups span splits: {crossing}")
    return membership


def adapt(arm: Path, out: Path, expect_total: int) -> dict:
    arm = arm.resolve()
    out = out.absolute()
    if out.exists():
        fail(f"output exists: {out}")
    staging = out.with_name(out.name + ".partial")
    if staging.exists():
        fail(f"stale staging directory: {staging}")
    schema = load_classes(arm)
    splits = json.loads((arm / "splits.json").read_text())
    samples = json.loads((arm / "audit/samples.json").read_text())
    membership = check_splits(splits, samples, expect_total)
    audit = {row["key"]: row for row in samples}

    staging.mkdir(parents=True)
    try:
        support = {s: np.zeros(NUM_CLASSES, np.int64) for s in SPLITS}
        audited = {s: np.zeros(NUM_CLASSES, np.int64) for s in SPLITS}
        entries = []
        names: set[tuple[str, str]] = set()
        for key in sorted(membership):
            split, row = membership[key], audit[key]
            group, stem = key.split("/")
            matches = sorted((arm / "images" / split / group).glob(f"{stem}.*"))
            matches = [m for m in matches if m.stem == stem and m.is_file()]
            if len(matches) != 1:
                fail(f"{key}: expected exactly one image, found {[m.name for m in matches]}")
            image, mask_path = matches[0], arm / "masks" / split / group / f"{stem}.png"
            if not mask_path.is_file():
                fail(f"{key}: missing mask {mask_path}")
            if image.suffix.lower() != row["image_extension"]:
                fail(f"{key}: image extension {image.suffix} differs from the audit")
            if sha256_file(image) != row["image_sha256"]:
                fail(f"{key}: image bytes differ from the audit sha256")
            with Image.open(mask_path) as im:
                mask = np.asarray(im)
            if mask.ndim != 2 or mask.dtype != np.uint8:
                fail(f"{key}: mask is not a single-channel uint8 image")
            if hashlib.sha256(mask.tobytes()).hexdigest() != row["mask_sha256"]:
                fail(f"{key}: mask pixels differ from the audit sha256")
            with Image.open(image) as im:
                if im.size != (mask.shape[1], mask.shape[0]):
                    fail(f"{key}: image size {im.size} differs from mask {mask.shape[::-1]}")
            counts = np.bincount(mask.ravel(), minlength=256)
            bad = sorted(set(np.flatnonzero(counts).tolist()) - set(range(NUM_CLASSES)) - {255})
            if bad:
                fail(f"{key}: mask values {bad} outside 0..{NUM_CLASSES - 1} and {IGNORE}")
            support[split] += counts[:NUM_CLASSES]
            for value, n in row["class_pixels"].items():
                if int(value) < NUM_CLASSES:
                    audited[split][int(value)] += int(n)
            name = f"{group}__{stem}.png"
            if (split, name) in names:
                fail(f"link name collision: {name}")
            names.add((split, name))
            for kind, source in (("images", image), ("masks", mask_path)):
                link = staging / f"{PREFIX[split]}_{kind}" / name
                link.parent.mkdir(exist_ok=True)
                link.symlink_to(source)
            entries.append(
                {
                    "key": key,
                    "split": split,
                    "group": group,
                    "adapter_name": name,
                    "image_source": str(image),
                    "mask_source": str(mask_path),
                    "source_extension": image.suffix.lower(),
                    "image_sha256": row["image_sha256"],
                    "mask_sha256": row["mask_sha256"],
                }
            )
        for split in SPLITS:
            if not np.array_equal(support[split], audited[split]):
                fail(f"{split}: mask pixel counts differ from audit/samples.json class_pixels")
            (staging / f"{PREFIX[split]}_images").mkdir(exist_ok=True)
            (staging / f"{PREFIX[split]}_masks").mkdir(exist_ok=True)

        (staging / "classes.json").write_text(json.dumps({"labels": schema["classes"]}) + "\n")
        sizes = {split: len(splits[split]) for split in SPLITS}
        for split, filename in (("val", "validation-support.json"), ("test", "test-support.json")):
            keys = sorted(splits[split])
            write(
                staging / filename,
                {
                    "split": split,
                    "images": len(keys),
                    "class_pixel_counts": support[split].tolist(),
                    "class_names": [c["name"] for c in schema["classes"]],
                    "ignore_index": IGNORE,
                    "keys_sha256": hashlib.sha256("\n".join(keys).encode()).hexdigest(),
                },
            )
        manifest = {
            "schema_version": 1,
            "arm_root": str(arm),
            "arm_name": arm.name,
            "splits_sha256": sha256_file(arm / "splits.json"),
            "classes_sha256": sha256_file(arm / "classes.json"),
            "samples_sha256": sha256_file(arm / "audit/samples.json"),
            "split_method": splits.get("_split_method"),
            "grouping_status": splits.get("_grouping_status"),
            "label_source": splits.get("_label_source"),
            "groups_enforced": "groups" in splits,
            "sizes": sizes,
            "layout": {split: f"{PREFIX[split]}_{{images,masks}}" for split in SPLITS},
            "deviations": DEVIATIONS,
            "adapter": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "entries": entries,
        }
        write(staging / "manifest.json", manifest)
        os.replace(staging, out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("arm_root", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--expect-total", type=int, default=314)
    args = p.parse_args(argv)
    manifest = adapt(args.arm_root, args.out_dir, args.expect_total)
    print(json.dumps({"out": str(args.out_dir), "sizes": manifest["sizes"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
