"""Materialize an explicitly selected, versioned all-class RAD split using CPU only.

All images, masks and native annotations are byte-preserved; only split/group
metadata changes. No existing target is overwritten, no GPU is imported, and the
historical source dataset is never changed. The candidate must have passed the
external review required by the operator before this command is executed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

SPLITS = ("train", "val", "test")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path: Path):
    return json.loads(path.read_text())


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def assignment(samples: list[dict], proposal: dict, index: int, minimum: int) -> tuple[dict, dict]:
    if proposal.get("schema_version") != 1 or len(proposal.get("class_names", [])) != 21:
        raise ValueError("Expected schema-1 proposal with all 21 classes")
    candidates = proposal.get("alternatives", [])
    if isinstance(index, bool) or index < 0 or index >= len(candidates):
        raise ValueError("Explicit candidate index is out of range")
    candidate = candidates[index]
    if candidate.get("solver_status") != 0:
        raise ValueError("Candidate did not solve successfully")
    if candidate.get("hard_minimum_positive_images_per_class_per_split", 0) < minimum:
        raise ValueError("Candidate minimum support is below the required minimum")
    keys = [s["key"] for s in samples]
    if len(keys) != len(set(keys)) or len(samples) != proposal.get("images"):
        raise ValueError("Source sample count/uniqueness differs from proposal")
    expected = {s["key"]: s for s in proposal.get("samples", [])}
    if set(keys) != set(expected):
        raise ValueError("Proposal sample keys differ from source")
    blocks = proposal["groups"]
    candidate_groups = candidate["group_assignment"]
    if set(blocks) != set(candidate_groups):
        raise ValueError("Candidate does not assign every conservative block exactly once")
    by_key = {}
    original_groups = {}
    for block, entry in blocks.items():
        split = candidate_groups[block]
        if split not in SPLITS:
            raise ValueError("Unknown candidate split")
        if entry.get("images") != len(entry["keys"]):
            raise ValueError("Block image count differs")
        for key in entry["keys"]:
            if key in by_key:
                raise ValueError("Sample appears in multiple conservative blocks")
            by_key[key] = {"split": split, "group": block}
        for group in entry["original_groups"]:
            if group in original_groups:
                raise ValueError("Original group belongs to multiple conservative blocks")
            original_groups[group] = block
    if set(by_key) != set(keys):
        raise ValueError("Conservative blocks do not cover all source images")
    for s in samples:
        e = expected[s["key"]]
        if s["image_sha256"] != e["image_sha256"] or s["mask_sha256"] != e["mask_sha256"]:
            raise ValueError("Source sample hashes differ from proposal")
        if original_groups.get(s["group"]) != by_key[s["key"]]["group"]:
            raise ValueError("Original scene group was divided across blocks")
        if Path(s["key"]).is_absolute() or ".." in Path(s["key"]).parts:
            raise ValueError("Unsafe sample key")
    for pair in proposal["constraints"].get("must_link_groups", []):
        assignments = {candidate_groups[original_groups[group]] for group in pair}
        if len(assignments) != 1:
            raise ValueError("Must-link scene groups cross splits")
    constraints = proposal["constraints"]
    required_minimum = constraints.get("minimum_positive_images_per_class_per_split", minimum)
    if minimum < required_minimum:
        raise ValueError("Requested minimum weakens the reviewed support constraint")
    for block in constraints.get("train_only_blocks", []):
        if candidate_groups.get(block) != "train":
            raise ValueError("A reviewed train-only block was moved to evaluation")
    if constraints.get("all_miscellaneous_groups_pinned_to_train") and any(
        by_key[s["key"]]["split"] != "train"
        for s in samples
        if s["group"].startswith("miscellaneous-")
    ):
        raise ValueError("A miscellaneous source group was moved to evaluation")
    if constraints.get("both_54_image_mud_groups_pinned_to_train") and any(
        by_key[s["key"]]["split"] != "train"
        for s in samples
        if s["group"] in {"sunny-mainline-cab-view", "trackside-maintenance"}
    ):
        raise ValueError("A large mud-pumping scene was moved to evaluation")
    small = constraints.get("small_images")
    if small:
        threshold = small["min_side_threshold_pixels"]
        affected = [s for s in samples if min(s["width"], s["height"]) < threshold]
        groups_with_small = {s["group"] for s in affected}
        if len(affected) != small["images"] or groups_with_small != set(
            small["whole_original_groups_pinned_to_train"]
        ):
            raise ValueError("Small-image group census differs from reviewed constraint")
        if any(
            by_key[s["key"]]["split"] != "train" for s in samples if s["group"] in groups_with_small
        ):
            raise ValueError("A group containing small images was moved to evaluation")
    minimum_blocks = constraints.get("minimum_conservative_blocks_per_evaluation_split", 1)
    maximum_share = constraints.get("maximum_dominant_block_fraction_per_evaluation_split", 1.0)
    if not isinstance(minimum_blocks, int) or minimum_blocks < 1 or not 0 < maximum_share <= 1:
        raise ValueError("Invalid evaluation block-count/dominance constraints")
    for split in ("val", "test"):
        sizes = [
            entry["images"] for block, entry in blocks.items() if candidate_groups[block] == split
        ]
        if len(sizes) < minimum_blocks or not sizes or max(sizes) / sum(sizes) > maximum_share:
            raise ValueError("Evaluation block count/dominance violates reviewed constraints")
    return by_key, candidate


def prepare(
    source: Path, proposal_path: Path, target: Path, candidate_index: int, minimum: int = 5
) -> dict:
    source = source.resolve()
    target = target.resolve()
    proposal_path = proposal_path.resolve()
    if minimum < 1:
        raise ValueError("Minimum positive images must be positive")
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("Source and target must be separate non-nested dataset directories")
    staging = target.with_name(target.name + ".preparing")
    if target.exists() or staging.exists():
        raise FileExistsError("Refusing to overwrite target or staging directory")
    proposal = read(proposal_path)
    samples_path = source / "audit/samples.json"
    samples = read(samples_path)
    if digest(samples_path) != proposal["source_samples_sha256"]:
        raise ValueError("Source sample audit hash differs from reviewed proposal")
    by_key, candidate = assignment(samples, proposal, candidate_index, minimum)
    if len({s["image_sha256"] for s in samples}) != len(samples):
        raise ValueError("Duplicate encoded source image hashes")
    old_splits = read(source / "splits.json")
    if {s["key"] for s in samples} != set().union(*(set(old_splits[k]) for k in SPLITS)):
        raise ValueError("Source split membership differs from sample audit")
    membership = [key for split in SPLITS for key in old_splits[split]]
    if len(membership) != len(set(membership)):
        raise ValueError("Duplicate source split membership")
    for s in samples:
        if s["key"] not in old_splits[s["split"]]:
            raise ValueError("Source sample split differs from manifest")
    validation = read(source / "audit/validation.json")
    annotation_root = Path(validation["source"]) / "jsons"
    names = proposal["class_names"]
    schema = read(source / "classes.json")
    source_classes = sorted(schema["classes"], key=lambda c: c["id"])
    if (
        [c["id"] for c in source_classes] != list(range(21))
        or [c["name"] for c in source_classes] != names
        or len(set(names)) != 21
    ):
        raise ValueError("Source taxonomy does not match exact ordered proposal classes")
    if validation.get("passed") is not True:
        raise ValueError("Source dataset validation did not pass")
    support = {split: dict.fromkeys(names, 0) for split in SPLITS}
    pixels = {split: dict.fromkeys(names, 0) for split in SPLITS}
    rendered = []
    seen_decoded = set()
    counts = Counter()
    copies = []
    staging.mkdir(parents=True)
    try:
        for s in sorted(samples, key=lambda x: x["key"]):
            key = s["key"]
            new = by_key[key]
            split = new["split"]
            counts[split] += 1
            image = source / "images" / s["split"] / (key + s["image_extension"])
            mask = source / "masks" / s["split"] / (key + ".png")
            if digest(image) != s["image_sha256"]:
                raise ValueError("Source image content changed: " + key)
            with Image.open(image) as im:
                rgb = np.asarray(im.convert("RGB"))
            if rgb.shape[:2] != (s["height"], s["width"]):
                raise ValueError("Image dimensions changed: " + key)
            decoded = hashlib.sha256(str(rgb.shape[:2]).encode() + rgb.tobytes()).hexdigest()
            if decoded in seen_decoded:
                raise ValueError("Duplicate decoded RGB image detected: " + key)
            seen_decoded.add(decoded)
            if s.get("mask_file_sha256") and digest(mask) != s["mask_file_sha256"]:
                raise ValueError("Encoded mask content changed: " + key)
            with Image.open(mask) as im:
                if im.mode != "L" or im.size != (s["width"], s["height"]):
                    raise ValueError("Invalid mask encoding/dimensions: " + key)
                label = np.asarray(im).copy()
            if hashlib.sha256(label.tobytes()).hexdigest() != s["mask_sha256"]:
                raise ValueError("Decoded mask content changed: " + key)
            values, nn = np.unique(label, return_counts=True)
            actual = {str(int(v)): int(n) for v, n in zip(values, nn, strict=True)}
            if set(map(int, actual)) - set(range(21)) - {255}:
                raise ValueError("Invalid mask class IDs: " + key)
            audited = {k: int(v) for k, v in s["class_pixels"].items() if int(v) > 0}
            if actual != audited:
                raise ValueError("Actual mask class counts differ from audit: " + key)
            if not any(int(k) < 21 and v > 0 for k, v in actual.items()):
                raise ValueError("No trainable pixels: " + key)
            for c, name in enumerate(names):
                n = actual.get(str(c), 0)
                pixels[split][name] += n
                support[split][name] += int(n > 0)
            annotation = annotation_root / (s.get("stem", Path(key).name) + ".json")
            if digest(annotation) != s["annotation_sha256"]:
                raise ValueError("Native annotation content changed: " + key)
            for src, rel in [
                (image, Path("images") / split / (key + s["image_extension"])),
                (mask, Path("masks") / split / (key + ".png")),
                (annotation, Path("source-annotations") / (key + ".json")),
            ]:
                dest = staging / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                if digest(src) != digest(dest):
                    raise ValueError("Copied bytes differ: " + str(rel))
                copies.append(
                    {"path": str(rel), "sha256": digest(dest), "bytes": dest.stat().st_size}
                )
            row = {
                **s,
                "original_split": s["split"],
                "original_group": s["group"],
                "split": split,
                "group": new["group"],
                "decoded_image_sha256": decoded,
                "annotation_path": str(Path("source-annotations") / (key + ".json")),
            }
            rendered.append(row)
        if dict(counts) != candidate["counts"]:
            raise ValueError("Materialized image counts differ from reviewed candidate")
        if support != candidate["positive_images"]:
            raise ValueError("Mask-derived support differs from reviewed candidate")
        if any(support[split][name] < minimum for split in SPLITS for name in names):
            raise ValueError("At least one class lacks required support")
        split_map = {
            split: sorted(s["key"] for s in rendered if s["split"] == split) for split in SPLITS
        }
        split_map.update(
            groups={s["key"]: s["group"] for s in rendered},
            _grouping_status="conservative_visual_blocks_recording_provenance_unconfirmed",
            _split_method="reviewed_allclass_group_milp",
            _source_samples_sha256=proposal["source_samples_sha256"],
            _proposal_sha256=digest(proposal_path),
            _candidate_index=candidate_index,
        )
        write(staging / "splits.json", split_map)
        write(staging / "audit/samples.json", rendered)
        shutil.copy2(source / "classes.json", staging / "classes.json")
        shutil.copy2(proposal_path, staging / "audit/split-proposal.json")
        write(
            staging / "audit/selected-candidate.json",
            {
                "candidate_index": candidate_index,
                "proposal_sha256": digest(proposal_path),
                **candidate,
            },
        )
        write(staging / "audit/copied-files.json", copies)
        coverage = {
            split: {
                name: {"positive_images": support[split][name], "pixels": pixels[split][name]}
                for name in names
            }
            for split in SPLITS
        }
        write(staging / "audit/class-coverage.json", coverage)
        result = {
            "passed": True,
            "dataset": target.name,
            "source": str(source),
            "images": len(rendered),
            "sizes": dict(counts),
            "class_names": names,
            "minimum_positive_images_per_class_per_split": minimum,
            "candidate_index": candidate_index,
            "source_samples_sha256": digest(samples_path),
            "source_splits_sha256": digest(source / "splits.json"),
            "proposal_sha256": digest(proposal_path),
            "split_sha256": digest(staging / "splits.json"),
            "samples_sha256": digest(staging / "audit/samples.json"),
            "encoded_and_decoded_images_unique": True,
            "groups_enforced": True,
            "must_link_groups": proposal["constraints"].get("must_link_groups", []),
            "image_mask_annotation_copies_verified": len(copies),
            "legacy_cvat_import_policy": "Original 314-image source corpus preserved; excluded CVAT-origin frames not reintroduced",
            "test_evaluated": False,
            "training_started": False,
            "recording_provenance": "Provisional visual groups; must-link closes documented potential sunny-mountain boundary, not proof of all recording independence",
        }
        write(staging / "audit/validation.json", result)
        (staging / "README.md").write_text(f"""# {target.name}

New benchmark version: {len(rendered)} byte-preserved annotated images, 21 trainable classes, ignore 255.
Train / validation / test: {counts["train"]} / {counts["val"]} / {counts["test"]}.
Every class has at least {minimum} positive-mask images in every split. The split uses whole conservative scene blocks and recorded must-link groups. Group and original recording provenance remain provisional.

Candidate {candidate_index} of the frozen split proposal was selected explicitly. Original sample keys are retained; `group` records the conservative block and `original_group` records the prior visual group. Copies of images, masks and source annotation JSONs are verified byte-for-byte.

The old test set was previously evaluated and is reassigned here. This is a new benchmark, not an untouched original holdout. Models must be freshly trained from declared non-RAD initialization, without reusing old RAD-adapted weights. Validation selects configurations; test is evaluated after the training/selection rule is frozen. No training or test evaluation was performed by this preparation.

The source corpus remains the approved 314 native images. The excluded legacy CVAT-origin images are not restored. `audit/class-coverage.json` contains exact per-split positive-image and labeled-pixel counts. `audit/validation.json`, `audit/copied-files.json` and the copied proposal record integrity and provenance. Original source dataset is unchanged.
""")
        # Same-filesystem rename makes the verified complete version visible atomically.
        if target.exists():
            raise FileExistsError("Target appeared during preparation; refusing to overwrite it")
        os.rename(staging, target)
        return result
    except BaseException:
        shutil.rmtree(staging)
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--proposal", type=Path, required=True)
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--candidate-index", type=int, required=True)
    ap.add_argument("--min-positive-images", type=int, default=5)
    args = ap.parse_args()
    print(
        json.dumps(
            prepare(
                args.source,
                args.proposal,
                args.target,
                args.candidate_index,
                args.min_positive_images,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
