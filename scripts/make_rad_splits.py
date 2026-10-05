"""Write a split specification for a flat rail-anomalies delivery (``img/`` + ``jsons/``).

``grouped`` carries split and scene group over from a prepared reference dataset by
image sha256 and takes the remaining images from a tracked YAML keyed by sha256.
``stratified`` is multi-label iterative stratification (Sechidis et al. 2011) on
anomaly presence and rare-class presence; frames of one recording may cross splits.

Both subcommands are deterministic for a given input and write no wall-clock time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image

SPLITS = ("train", "val", "test")
STRATIFIED_STATUS = (
    "none_stratified_random_per_paul_stanik_2026-09-23_same_recording_frames_may_cross_splits"
)
PIN_MIN_SIDE = 1024


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def delivery_images(source: Path) -> dict[str, Path]:
    """Map stem -> image path; every image needs exactly one file and one annotation."""
    images: dict[str, Path] = {}
    for path in sorted((source / "img").iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.stem in images:
            raise ValueError(f"Duplicate image stem in delivery: {path.stem}")
        if not (source / "jsons" / f"{path.stem}.json").is_file():
            raise ValueError(f"Missing annotation for delivery image: {path.name}")
        images[path.stem] = path
    if not images:
        raise ValueError(f"No images under {source / 'img'}")
    return images


def titles(source: Path, stem: str) -> list[str]:
    data = json.loads((source / "jsons" / f"{stem}.json").read_text())
    return [obj["classTitle"] for obj in data["objects"]]


def class_image_counts(
    assignments: dict[str, dict], classes: dict[str, set[str]]
) -> dict[str, dict[str, int]]:
    counts = {
        name: dict.fromkeys(SPLITS, 0) for name in sorted({c for v in classes.values() for c in v})
    }
    for stem, row in assignments.items():
        for name in classes[stem]:
            counts[name][row["split"]] += 1
    return counts


def write_spec(out: Path, spec: dict) -> None:
    spec["assignments"] = dict(sorted(spec["assignments"].items()))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")


def grouped(source: Path, reference: Path, new_images: Path) -> dict:
    images = delivery_images(source)
    samples = json.loads((reference / "audit/samples.json").read_text())
    splits = json.loads((reference / "splits.json").read_text())
    membership = {key: split for split in SPLITS for key in splits[split]}
    by_sha: dict[str, dict] = {}
    for row in samples:
        if row["image_sha256"] in by_sha:
            raise ValueError(f"Reference has two samples with one image sha256: {row['key']}")
        by_sha[row["image_sha256"]] = row
    listed = yaml.safe_load(new_images.read_text())
    extra = listed["images"]
    assignments: dict[str, dict] = {}
    matched_keys: set[str] = set()
    for stem, path in images.items():
        sha = digest(path)
        if sha in by_sha:
            row = by_sha[sha]
            key = row["key"]
            split, group = membership[key], splits["groups"][key]
            if row.get("split", split) != split or row.get("group", group) != group:
                raise ValueError(f"Reference audit and splits.json disagree for {key}")
            matched_keys.add(key)
            origin = {"reference_key": key}
        elif sha in extra:
            entry = extra[sha]
            if entry["stem"] != stem:
                raise ValueError(
                    f"{new_images.name}: sha256 {sha[:12]} lists stem {entry['stem']!r} "
                    f"but the delivery file is {stem!r}"
                )
            split, group = entry["split"], entry["group"]
            origin = {"reference_key": None, "listed_in": new_images.name}
        else:
            raise ValueError(
                f"Delivery image {path.name} (sha256 {sha}) is neither in the reference "
                f"nor listed in {new_images.name}"
            )
        if split not in SPLITS:
            raise ValueError(f"Unknown split {split!r} for {stem}")
        assignments[stem] = {"split": split, "group": group, "image_sha256": sha} | origin
    delivered = {row["image_sha256"] for row in assignments.values()}
    absent = sorted(set(extra) - delivered)
    if absent:
        raise ValueError(f"{new_images.name} lists images absent from the delivery: {absent}")
    for split in ("val", "test"):
        missing = sorted(set(splits[split]) - matched_keys)
        if missing:
            raise ValueError(f"Reference {split} images absent from the delivery: {missing}")
    group_splits: dict[str, set[str]] = {}
    for row in assignments.values():
        group_splits.setdefault(row["group"], set()).add(row["split"])
    crossing = sorted(g for g, s in group_splits.items() if len(s) > 1)
    if crossing:
        raise ValueError(f"Scene groups present in more than one split: {crossing}")
    classes = {stem: set(titles(source, stem)) - {"void"} for stem in images}
    unmatched_train = sorted(set(splits["train"]) - matched_keys)
    sizes = Counter(row["split"] for row in assignments.values())
    return {
        "dataset": source.name,
        "method": {
            "name": "grouped",
            "reference": reference.name,
            "reference_splits_sha256": digest(reference / "splits.json"),
            "reference_samples_sha256": digest(reference / "audit/samples.json"),
            "new_images_file": new_images.name,
            "new_images_sha256": digest(new_images),
            "match": "image file sha256",
            "seed": None,
        },
        "_grouping_status": listed["status"],
        "groups_enforced": True,
        "assignments": assignments,
        "report": {
            "sizes": {split: sizes[split] for split in SPLITS},
            "matched_reference_images": len(matched_keys),
            "reference_train_images_absent_from_delivery": unmatched_train,
            "new_images": sorted(
                stem for stem, row in assignments.items() if row["reference_key"] is None
            ),
            "groups_per_split": {
                split: sorted(g for g, s in group_splits.items() if s == {split})
                for split in SPLITS
            },
            "class_image_counts": class_image_counts(assignments, classes),
        },
    }


def iterative_stratification(
    labels: dict[str, frozenset[str]],
    capacity: dict[str, int],
    desired: dict[str, dict[str, float]],
    rng: random.Random,
) -> dict[str, str]:
    """Sechidis et al. 2011 with exact per-split capacities and seeded tie-breaking."""
    remaining = dict(labels)
    capacity = dict(capacity)
    desired = {s: dict(d) for s, d in desired.items()}
    result: dict[str, str] = {}

    def place(item: str, split: str) -> None:
        result[item] = split
        capacity[split] -= 1
        for label in remaining.pop(item):
            desired[split][label] -= 1

    while remaining:
        counts = Counter(label for labels_ in remaining.values() for label in labels_)
        if not counts:
            # Only label-free images remain: fill the most under-filled splits first.
            for item in sorted(remaining, key=lambda s: (rng.random(), s)):
                open_ = [s for s in SPLITS if capacity[s] > 0]
                place(item, max(open_, key=lambda s: (capacity[s], rng.random())))
            break
        fewest = min(counts.values())
        label = rng.choice(sorted(k for k, n in counts.items() if n == fewest))
        items = sorted(s for s, labels_ in remaining.items() if label in labels_)
        rng.shuffle(items)
        for item in items:
            open_ = [s for s in SPLITS if capacity[s] > 0]
            best = max(desired[s][label] for s in open_)
            tied = [s for s in open_ if desired[s][label] == best]
            if len(tied) > 1:
                most = max(capacity[s] for s in tied)
                tied = [s for s in tied if capacity[s] == most]
            place(item, rng.choice(tied))
    return result


def stratified(
    source: Path,
    group_spec: Path,
    seed: int,
    sizes: dict[str, int],
    rare_threshold: int,
    anomaly_classes: list[str],
) -> dict:
    images = delivery_images(source)
    spec = json.loads(group_spec.read_text())
    if set(spec["assignments"]) != set(images):
        raise ValueError("Group spec does not cover exactly the delivery images")
    if sum(sizes.values()) != len(images):
        raise ValueError(f"Split sizes {sizes} do not sum to {len(images)} images")
    classes = {stem: set(titles(source, stem)) - {"void"} for stem in images}
    image_counts = Counter(name for names in classes.values() for name in names)
    missing_anomaly = sorted(set(anomaly_classes) - set(image_counts))
    if missing_anomaly:
        raise ValueError(f"Anomaly classes absent from the delivery: {missing_anomaly}")
    rare = sorted(name for name, n in image_counts.items() if n < rare_threshold)
    strat = sorted(set(anomaly_classes) | set(rare))
    labels = {stem: frozenset(names & set(strat)) for stem, names in classes.items()}
    dims = {}
    for stem, path in images.items():
        with Image.open(path) as im:
            dims[stem] = im.size
    pinned = sorted(stem for stem, (w, h) in dims.items() if min(w, h) < PIN_MIN_SIDE)
    if len(pinned) > sizes["train"]:
        raise ValueError("More small images pinned to train than train capacity")
    total = len(images)
    ratio = {split: sizes[split] / total for split in SPLITS}
    label_total = Counter(label for labels_ in labels.values() for label in labels_)
    desired = {
        split: {label: ratio[split] * label_total[label] for label in strat} for split in SPLITS
    }
    for stem in pinned:
        for label in labels[stem]:
            desired["train"][label] -= 1
    capacity = dict(sizes)
    capacity["train"] -= len(pinned)
    pool = {stem: labels[stem] for stem in images if stem not in set(pinned)}
    rng = random.Random(seed)
    placed = iterative_stratification(pool, capacity, desired, rng)
    placed.update(dict.fromkeys(pinned, "train"))
    assignments = {
        stem: {
            "split": placed[stem],
            "group": spec["assignments"][stem]["group"],
            "image_sha256": digest(path),
            "pinned_small_image": stem in set(pinned),
            "stratification_labels": sorted(labels[stem]),
        }
        for stem, path in images.items()
    }
    counts = class_image_counts(assignments, classes)
    gaps = [
        (label, split)
        for label in strat
        if image_counts[label] >= 3
        for split in SPLITS
        if counts[label][split] == 0
    ]
    if gaps:
        raise ValueError(f"Stratification labels missing from a split: {gaps}")
    group_splits: dict[str, set[str]] = {}
    for row in assignments.values():
        group_splits.setdefault(row["group"], set()).add(row["split"])
    actual = Counter(row["split"] for row in assignments.values())
    if {s: actual[s] for s in SPLITS} != sizes:
        raise AssertionError(f"Split sizes {dict(actual)} differ from requested {sizes}")
    return {
        "dataset": source.name,
        "method": {
            "name": "stratified",
            "algorithm": "multi-label iterative stratification (Sechidis, Tsoumakas, Vlahavas 2011)",
            "seed": seed,
            "sizes": sizes,
            "rare_threshold": rare_threshold,
            "presence_rule": "a class is present in an image when any JSON object carries its classTitle (void excluded); painted-mask presence is not used",
            "anomaly_classes": sorted(anomaly_classes),
            "stratification_labels": strat,
            "rare_classes": rare,
            "pinned_small_images_to_train": pinned,
            "pin_rule": f"min(width, height) < {PIN_MIN_SIDE} -> train",
            "group_spec": group_spec.name,
            "group_spec_sha256": digest(group_spec),
            "group_use": "scene-group names for directory layout and diagnostics only",
        },
        "_grouping_status": STRATIFIED_STATUS,
        "groups_enforced": False,
        "assignments": assignments,
        "report": {
            "sizes": {split: actual[split] for split in SPLITS},
            "class_image_counts": counts,
            "stratification_label_image_counts": {
                label: counts[label] | {"total": image_counts[label]} for label in strat
            },
            "groups_crossing_splits": sorted(g for g, s in group_splits.items() if len(s) > 1),
            "pinned_small_images": pinned,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    g = sub.add_parser("grouped", help="carry split and group over from a reference dataset")
    g.add_argument("--source", type=Path, required=True)
    g.add_argument("--reference", type=Path, required=True)
    g.add_argument("--new-images", type=Path, required=True)
    g.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("stratified", help="multi-label stratified random split")
    s.add_argument("--source", type=Path, required=True)
    s.add_argument("--group-spec", type=Path, required=True)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--sizes", default="227,37,50", help="train,val,test image counts")
    s.add_argument("--rare-threshold", type=int, default=50)
    s.add_argument("--anomaly-classes", default="mud-pumping,standing-water,vegetation-overgrowth")
    s.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.command == "grouped":
        spec = grouped(args.source, args.reference, args.new_images)
    else:
        sizes = dict(zip(SPLITS, (int(v) for v in args.sizes.split(",")), strict=True))
        spec = stratified(
            args.source,
            args.group_spec,
            args.seed,
            sizes,
            args.rare_threshold,
            [c for c in args.anomaly_classes.split(",") if c],
        )
    write_spec(args.out, spec)
    print(json.dumps(spec["report"]["sizes"]))


if __name__ == "__main__":
    main()
