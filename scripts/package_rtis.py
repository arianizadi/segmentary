"""Materialize the manually reviewed RTIS group assignments with readable paths."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import yaml


def assign(filename: str, rules: dict) -> dict:
    stem = Path(filename).stem
    match = re.fullmatch(r"(?:(.*)_)?(\d+)", stem)
    if match is None:
        raise ValueError(f"Filename needs manual assignment: {filename}")
    family, number = match.group(1) or "numbered", int(match.group(2))
    hits = [
        g
        for g in rules["groups"]
        if g["family"] == family and any(lo <= number <= hi for lo, hi in g["ranges"])
    ]
    if len(hits) != 1:
        raise ValueError(f"Expected exactly one manual group for {filename}; got {len(hits)}")
    return hits[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prepared", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rules = yaml.safe_load(args.groups.read_text())
    rows = json.loads((args.prepared / "audit/samples.json").read_text())
    assignments = [(row, assign(row["filename"], rules)) for row in rows]
    group_splits = {}
    for _, g in assignments:
        if group_splits.setdefault(g["name"], g["split"]) != g["split"]:
            raise ValueError(f"Group {g['name']} crosses splits")
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {s: [] for s in ("train", "val", "test")}
    manifest["groups"] = {}
    manifest["_grouping_status"] = rules["status"]
    counts = {s: Counter() for s in ("train", "val", "test")}
    images_per_class = {s: Counter() for s in counts}
    seen = set()
    for row, g in assignments:
        split, group = g["split"], g["name"]
        old_key = row["key"]
        key = f"{group}/{Path(row['filename']).stem}"
        if key in seen:
            raise ValueError(f"Readable path collision: {key}")
        seen.add(key)
        for kind, source, suffix in (
            (
                "images",
                args.prepared / "images" / (old_key + row["image_extension"]),
                row["image_extension"],
            ),
            ("masks", args.prepared / "masks" / (old_key + ".png"), ".png"),
            ("previews", args.prepared / "overlays" / (old_key + ".jpg"), ".jpg"),
        ):
            dest = args.out / kind / split / (key + suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        manifest[split].append(key)
        manifest["groups"][key] = group
        row.update(key=key, split=split, group=group, prepared_key=old_key)
        counts[split].update({k: int(v) for k, v in row["class_pixels"].items()})
        images_per_class[split].update(row["class_pixels"].keys())
    for split in counts:
        manifest[split].sort()
    (args.out / "splits.json").write_text(json.dumps(manifest, indent=2) + "\n")
    audit = args.out / "audit"
    audit.mkdir()
    for name in ("exclusions.json", "summary.json", "source-meta.json"):
        shutil.copyfile(args.prepared / "audit" / name, audit / name)
    shutil.copyfile(args.groups, audit / "scene-groups.yaml")
    (audit / "samples.json").write_text(json.dumps(rows, indent=2) + "\n")
    fields = [
        "split",
        "group",
        "filename",
        "key",
        "source",
        "source_dataset",
        "width",
        "height",
        "annotation_count",
        "ignore_pixels",
        "overlap_pixels",
        "image_sha256",
        "mask_sha256",
    ]
    with (audit / "samples.csv").open("w") as f:
        writer = csv.DictWriter(f, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    excluded = json.loads((audit / "exclusions.json").read_text())
    readable_keys = {row["prepared_key"]: row["key"] for row in rows}
    for row in excluded:
        if "retained_key" in row:
            row["retained_key"] = readable_keys[row["retained_key"]]
    (audit / "exclusions.json").write_text(json.dumps(excluded, indent=2) + "\n")
    with (audit / "excluded-images.csv").open("w") as f:
        writer = csv.DictWriter(
            f,
            [
                "source",
                "source_dataset",
                "filename",
                "reason",
                "retained_key",
                "differing_mask_pixels",
                "image_sha256",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(excluded)
    schema = yaml.safe_load((args.prepared / "canonical.yaml").read_text())
    (args.out / "classes.json").write_text(json.dumps(schema, indent=2) + "\n")
    with (audit / "class-distribution.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "id",
                "class",
                "train_images",
                "val_images",
                "test_images",
                "train_pixels",
                "val_pixels",
                "test_pixels",
            ]
        )
        for c in schema["classes"] + [{"id": 255, "name": "ignore"}]:
            key = str(c["id"])
            writer.writerow(
                [
                    c["id"],
                    c["name"],
                    *[images_per_class[s][key] for s in counts],
                    *[counts[s][key] for s in counts],
                ]
            )
    summary = json.loads((audit / "summary.json").read_text())
    summary.update(
        split_status=rules["status"],
        splits={s: len(manifest[s]) for s in counts},
        split_groups={s: len({manifest["groups"][k] for k in manifest[s]}) for s in counts},
    )
    (audit / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
