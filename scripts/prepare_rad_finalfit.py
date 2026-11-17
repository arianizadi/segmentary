"""Optionally materialize RAD train+validation for a frozen final-fit protocol.

The parent 187/68/59 split is bound by an explicit SHA-256. Its exact train and
validation union becomes training, validation stays explicitly empty, and the
59 test images, masks, keys and groups are byte-preserved. Only manifest-listed
native samples are copied. This CPU-only command never launches training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_rad_allclasses import SPLITS, digest, read, write

PARENT_SIZES = {"train": 187, "val": 68, "test": 59}


def prepare(source: Path, target: Path, parent_split_sha256: str) -> dict:
    source = source.resolve(strict=True)
    target = target.absolute()
    resolved_target = target.resolve()
    if (
        resolved_target == source
        or resolved_target.is_relative_to(source)
        or source.is_relative_to(resolved_target)
    ):
        raise ValueError("Source and target must be separate non-nested dataset directories")
    staging = target.with_name(target.name + ".preparing")
    if os.path.lexists(target) or os.path.lexists(staging):
        raise FileExistsError("Refusing to overwrite target or staging directory")
    if not isinstance(parent_split_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", parent_split_sha256
    ):
        raise ValueError("parent_split_sha256 must be a lowercase SHA-256")
    paths = {
        "parent_split_sha256": source / "splits.json",
        "parent_samples_sha256": source / "audit/samples.json",
        "parent_validation_sha256": source / "audit/validation.json",
        "parent_classes_sha256": source / "classes.json",
    }
    hashes = {key: digest(path) for key, path in paths.items()}
    if hashes["parent_split_sha256"] != parent_split_sha256:
        raise ValueError("Parent split SHA-256 differs from the frozen requested parent")
    splits = read(paths["parent_split_sha256"])
    samples = read(paths["parent_samples_sha256"])
    validation = read(paths["parent_validation_sha256"])
    schema = read(paths["parent_classes_sha256"])
    if validation.get("passed") is not True:
        raise ValueError("Parent dataset validation did not pass")
    if validation.get("split_sha256") != parent_split_sha256:
        raise ValueError("Parent validation does not bind the current split SHA-256")
    if validation.get("samples_sha256") != hashes["parent_samples_sha256"]:
        raise ValueError("Parent validation does not bind the current sample SHA-256")
    if any(not isinstance(splits.get(split), list) for split in SPLITS):
        raise ValueError("Parent must explicitly contain train, val and test lists")
    if {split: len(splits[split]) for split in SPLITS} != PARENT_SIZES:
        raise ValueError("Expected the approved 187/68/59 parent split")
    membership = [key for split in SPLITS for key in splits[split]]
    if any(not isinstance(key, str) for key in membership) or len(set(membership)) != 314:
        raise ValueError("Parent keys must be 314 unique strings across disjoint splits")
    if not isinstance(samples, list) or len(samples) != 314:
        raise ValueError("Parent must contain exactly the approved 314 native sample records")
    by_key = {sample["key"]: sample for sample in samples}
    if len(by_key) != len(samples) or set(by_key) != set(membership):
        raise ValueError("Parent sample audit differs from exact split membership")
    groups = splits.get("groups")
    if not isinstance(groups, dict) or set(groups) != set(membership):
        raise ValueError("Parent groups must cover every sample exactly")
    group_splits = {}
    for split in SPLITS:
        for key in splits[split]:
            sample = by_key[key]
            if (
                not key
                or Path(key).is_absolute()
                or ".." in Path(key).parts
                or Path(key).as_posix() != key
            ):
                raise ValueError("Unsafe sample key")
            if sample.get("split") != split or sample.get("group") != groups[key]:
                raise ValueError("Parent sample split/group differs from manifest")
            group = groups[key]
            if not isinstance(group, str) or not group:
                raise ValueError("Parent scene groups must be nonempty strings")
            previous = group_splits.setdefault(group, split)
            if previous != split:
                raise ValueError("Parent scene group crosses splits")
    classes = sorted(schema["classes"], key=lambda row: row["id"])
    if [row["id"] for row in classes] != list(range(21)):
        raise ValueError("Parent must preserve the ordered 21-class taxonomy")
    names = [row["name"] for row in classes]
    if len(set(names)) != 21:
        raise ValueError("Parent class names must be unique")
    train_keys = sorted(set(splits["train"]) | set(splits["val"]))
    test_keys = list(splits["test"])
    test_files = []
    copied = []
    rendered = []
    image_hashes = set()
    decoded_hashes = set()
    support = {split: dict.fromkeys(names, 0) for split in SPLITS}
    pixels = {split: dict.fromkeys(names, 0) for split in SPLITS}
    target.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    try:
        for split in SPLITS:
            (staging / "images" / split).mkdir(parents=True)
            (staging / "masks" / split).mkdir(parents=True)
        for key in sorted(by_key):
            sample = by_key[key]
            old_split = sample["split"]
            split = "test" if old_split == "test" else "train"
            extension = sample.get("image_extension")
            if not isinstance(extension, str) or not re.fullmatch(r"\.[A-Za-z0-9]+", extension):
                raise ValueError("Unsafe image extension")
            image = source / "images" / old_split / (key + extension)
            mask = source / "masks" / old_split / (key + ".png")
            annotation_path = Path(
                sample.get("annotation_path", "source-annotations/" + key + ".json")
            )
            if annotation_path.is_absolute() or ".." in annotation_path.parts:
                raise ValueError("Unsafe source annotation path")
            annotation = source / annotation_path
            image_hash, mask_hash, annotation_hash = (
                digest(path) for path in (image, mask, annotation)
            )
            if image_hash != sample.get("image_sha256"):
                raise ValueError("Source image content changed: " + key)
            if mask_hash != sample.get("mask_file_sha256"):
                raise ValueError("Encoded mask content changed: " + key)
            if annotation_hash != sample.get("annotation_sha256"):
                raise ValueError("Native annotation content changed: " + key)
            if image_hash in image_hashes:
                raise ValueError("Duplicate encoded image bytes across parent samples")
            image_hashes.add(image_hash)
            with Image.open(image) as stream:
                rgb = np.asarray(stream.convert("RGB"))
            if rgb.shape[:2] != (sample["height"], sample["width"]):
                raise ValueError("Source image dimensions changed: " + key)
            decoded = hashlib.sha256(str(rgb.shape[:2]).encode() + rgb.tobytes()).hexdigest()
            if decoded in decoded_hashes:
                raise ValueError("Duplicate decoded RGB image across parent samples")
            decoded_hashes.add(decoded)
            with Image.open(mask) as stream:
                if stream.mode != "L" or stream.size != (sample["width"], sample["height"]):
                    raise ValueError("Invalid mask encoding/dimensions: " + key)
                label = np.asarray(stream).copy()
            if hashlib.sha256(label.tobytes()).hexdigest() != sample.get("mask_sha256"):
                raise ValueError("Decoded mask content changed: " + key)
            values, counts = np.unique(label, return_counts=True)
            actual = {
                str(int(value)): int(count) for value, count in zip(values, counts, strict=True)
            }
            if set(map(int, actual)) - set(range(21)) - {255}:
                raise ValueError("Invalid mask class IDs: " + key)
            if actual != {str(k): int(v) for k, v in sample["class_pixels"].items() if int(v) > 0}:
                raise ValueError("Mask-derived class counts differ from parent audit: " + key)
            for index, name in enumerate(names):
                count = actual.get(str(index), 0)
                pixels[split][name] += count
                support[split][name] += int(count > 0)
            for original, relative, expected_hash in (
                (image, Path("images") / split / (key + extension), image_hash),
                (mask, Path("masks") / split / (key + ".png"), mask_hash),
                (annotation, Path("source-annotations") / (key + ".json"), annotation_hash),
            ):
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, destination)
                if digest(destination) != expected_hash or digest(original) != expected_hash:
                    raise ValueError("Copied bytes or source changed: " + key)
                copied.append(
                    {
                        "path": str(relative),
                        "sha256": expected_hash,
                        "bytes": destination.stat().st_size,
                    }
                )
            if split == "test":
                test_files.append(
                    {"key": key, "image_sha256": image_hash, "mask_file_sha256": mask_hash}
                )
            rendered.append(
                {
                    **sample,
                    "development_split": old_split,
                    "split": split,
                    "decoded_image_sha256": decoded,
                    "annotation_path": str(Path("source-annotations") / (key + ".json")),
                }
            )
        final_fit = {
            "schema_version": 1,
            "parent_root": str(source),
            **hashes,
            "parent_sizes": dict(PARENT_SIZES),
            "merge_splits": ["train", "val"],
            "training_membership": "exact_parent_train_union_val",
            "test_keys_sha256": hashlib.sha256(
                json.dumps(test_keys, separators=(",", ":")).encode()
            ).hexdigest(),
            "test_files_sha256": hashlib.sha256(
                json.dumps(test_files, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "test_bytes_identical": True,
            "groups_preserved": True,
            "no_additional_samples": True,
        }
        split_map = {
            **{key: value for key, value in splits.items() if key not in SPLITS},
            "train": train_keys,
            "val": [],
            "test": test_keys,
            "_split_method": "frozen_final_fit_train_union_val",
            "_parent_split_sha256": parent_split_sha256,
            "_final_fit": final_fit,
        }
        write(staging / "splits.json", split_map)
        write(staging / "audit/samples.json", rendered)
        shutil.copy2(source / "classes.json", staging / "classes.json")
        shutil.copy2(source / "splits.json", staging / "audit/parent-splits.json")
        write(staging / "audit/copied-files.json", copied)
        write(
            staging / "audit/class-coverage.json",
            {
                split: {
                    name: {"positive_images": support[split][name], "pixels": pixels[split][name]}
                    for name in names
                }
                for split in SPLITS
            },
        )
        result = {
            "passed": True,
            "dataset": target.name,
            "source": str(source),
            "images": 314,
            "sizes": {"train": 255, "val": 0, "test": 59},
            "class_names": names,
            "split_sha256": digest(staging / "splits.json"),
            "samples_sha256": digest(staging / "audit/samples.json"),
            "final_fit": final_fit,
            "encoded_and_decoded_images_unique": True,
            "groups_enforced": True,
            "image_mask_annotation_copies_verified": len(copied),
            "legacy_cvat_import_policy": "Only the parent's approved 314 native samples copied; no additional CVAT-origin frames included",
            "test_evaluated": False,
            "training_started": False,
        }
        write(staging / "audit/validation.json", result)
        if any(digest(path) != hashes[key] for key, path in paths.items()):
            raise ValueError("Parent metadata changed during materialization")
        if os.path.lexists(target):
            raise FileExistsError("Target appeared during preparation; refusing to overwrite it")
        os.rename(staging, target)
        return result
    except BaseException:
        shutil.rmtree(staging)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--parent-split-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.target, args.parent_split_sha256), indent=2))


if __name__ == "__main__":
    main()
