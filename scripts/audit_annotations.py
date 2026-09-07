"""Review native Supervisely/CVAT geometry against packaged semantic masks.

Run from a Segmentary checkout: python -m scripts.audit_annotations --help.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image
from scripts.prepare_rtis import ALIASES, digest, render


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes root: {relative}")
    return path


def source_path(value: str, source_root: Path | None) -> Path:
    if source_root is None:
        return Path(value)
    parts = Path(value).parts
    indexes = [i for i, part in enumerate(parts) if part in {"supervisely", "cvat"}]
    if not indexes:
        raise ValueError(f"Cannot relocate source path: {value}")
    return safe_path(source_root, str(Path(*parts[indexes[-1] :])))


def layers_for(row: dict, labels: dict, source_root: Path | None) -> tuple[list, Path]:
    annotation = source_path(row["source_annotation"], source_root)
    shape = (row["height"], row["width"])
    if row["source"] == "supervisely":
        data = json.loads(annotation.read_text())
        if (data["size"]["height"], data["size"]["width"]) != shape:
            raise ValueError("Source annotation dimensions differ")
        objects = data["objects"]
    elif row["source"] == "cvat":
        nodes = ET.parse(annotation).getroot().findall("image")
        original = Path(row["source_image"]).as_posix()
        exact = [node for node in nodes if original.endswith("/" + node.attrib["name"])]
        matches = exact or [
            node for node in nodes if Path(node.attrib["name"]).name == row["filename"]
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one CVAT image for {row['key']}; got {len(matches)}")
        node = matches[0]
        if (int(node.attrib["height"]), int(node.attrib["width"])) != shape:
            raise ValueError("Source annotation dimensions differ")
        objects = sorted(list(node), key=lambda obj: int(obj.attrib.get("z_order", 0)))
    else:
        raise ValueError(f"Unsupported source: {row['source']}")
    layers = []
    for index, obj in enumerate(objects):
        title = obj["classTitle"] if row["source"] == "supervisely" else obj.attrib["label"]
        title = ALIASES.get(title, title)
        class_id = labels[title]
        # Paint the single shape with zero to retain explicitly annotated void.
        mask, _ = render([obj], shape, {title: 0}, row["source"])
        layers.append(
            (
                str(obj.get("id", index)) if isinstance(obj, dict) else str(index),
                class_id,
                mask != 255,
            )
        )
    return layers, annotation


def inspect_layers(
    layers: list, final: np.ndarray, ignore: int, coverage: float, overwrite: float
) -> tuple[dict, dict]:
    expected = np.full(final.shape, ignore, dtype=np.int64)
    owner = np.full(final.shape, -1, dtype=np.int32)
    overlap = np.zeros(final.shape, bool)
    cross_class = np.zeros(final.shape, bool)
    events = []
    for index, (object_id, class_id, region) in enumerate(layers):
        overlap |= region & (owner >= 0)
        collision = region & (owner >= 0) & (expected != class_id)
        cross_class |= collision
        for previous in np.unique(owner[collision]):
            events.append(
                {
                    "from_object": layers[int(previous)][0],
                    "to_object": object_id,
                    "from_class": layers[int(previous)][1],
                    "to_class": class_id,
                    "pixels": int(np.count_nonzero(collision & (owner == previous))),
                }
            )
        expected[region] = class_id
        owner[region] = index
    flags, objects = [], []
    for index, (object_id, class_id, region) in enumerate(layers):
        area = int(region.sum())
        hidden = int(np.count_nonzero(region & (owner != index)))
        different = int(np.count_nonzero(region & (expected != class_id)))
        objects.append(
            {
                "id": object_id,
                "class_id": class_id,
                "source_pixels": area,
                "overwritten_pixels": hidden,
                "cross_class_lost_pixels": different,
                "remaining_class_pixels": area - different,
                "lost_fraction": different / area if area else None,
            }
        )
        if area == 0:
            flags.append(f"empty_object:{object_id}")
        elif different / area >= overwrite:
            flags.append(f"object_class_coverage_lost:{object_id}")
    counts = {
        str(int(k)): int(v) for k, v in zip(*np.unique(final, return_counts=True), strict=True)
    }
    for class_id, count in counts.items():
        if count / final.size >= coverage:
            flags.append(f"dominant_class:{class_id}")
    mismatch = expected != final
    if mismatch.any():
        flags.append("training_mask_differs_from_native_render")
    return {
        "pixels": final.size,
        "overlap_pixels": int(overlap.sum()),
        "cross_class_overlap_pixels": int(cross_class.sum()),
        "mismatch_pixels": int(mismatch.sum()),
        "uncovered_source_pixels": int(np.count_nonzero(owner < 0)),
        "class_pixels": counts,
        "objects": objects,
        "overwrite_events": events,
        "flags": flags,
    }, {"native": expected, "overlap": overlap, "cross_class": cross_class, "mismatch": mismatch}


def audit(
    dataset: Path,
    out: Path,
    source_root: Path | None = None,
    coverage: float = 0.85,
    overwrite: float = 0.5,
) -> dict:
    dataset, out = dataset.resolve(), out.resolve()
    if not 0 < coverage <= 1 or not 0 < overwrite <= 1:
        raise ValueError("Coverage and overwrite thresholds must be in (0,1]")
    if out.resolve().is_relative_to(dataset.resolve()):
        raise ValueError("Audit output must be outside the immutable dataset")
    out.mkdir(parents=True, exist_ok=False)
    schema = json.loads((dataset / "classes.json").read_text())
    ignore = schema.get("ignore_index", 255)
    labels = {c["name"]: c["id"] for c in schema["classes"]} | {"void": ignore}
    colors = {c["id"]: c["color"] for c in schema["classes"]}
    rows = json.loads((dataset / "audit/samples.json").read_text())
    results = []
    for row in rows:
        record = {"key": row["key"], "split": row["split"], "source": row["source"]}
        try:
            mask_path = safe_path(dataset, f"masks/{row['split']}/{row['key']}.png")
            with Image.open(mask_path) as im:
                final = np.array(im)
            if final.shape != (row["height"], row["width"]):
                raise ValueError("Training mask dimensions differ")
            layers, annotation = layers_for(row, labels, source_root)
            stats, maps = inspect_layers(layers, final, ignore, coverage, overwrite)
            record.update(
                stats, annotation_sha256=digest(annotation), mask_file_sha256=digest(mask_path)
            )
            record["source_annotation_packaging_hash_status"] = (
                "verified"
                if row.get("annotation_sha256") == record["annotation_sha256"]
                else "mismatch"
                if row.get("annotation_sha256")
                else "unavailable"
            )
            if not row.get("annotation_sha256"):
                record["flags"].append("source_annotation_packaging_hash_unavailable")
            if row.get("annotation_sha256") and digest(annotation) != row["annotation_sha256"]:
                record["flags"].append("source_annotation_changed_since_packaging")
            unknown = set(np.unique(final).tolist()) - set(labels.values())
            if unknown:
                record["flags"].append(f"unknown_training_class_ids:{sorted(unknown)}")
            original_image = source_path(row["source_image"], source_root)
            record["source_image_sha256"] = digest(original_image)
            if row.get("image_sha256") and record["source_image_sha256"] != row["image_sha256"]:
                record["flags"].append("source_image_changed_since_packaging")
            image_extension = row.get("image_extension", original_image.suffix)
            packaged_image = safe_path(
                dataset, f"images/{row['split']}/{row['key']}{image_extension}"
            )
            if not packaged_image.is_file():
                raise ValueError("Packaged training image is missing")
            record["packaged_image_sha256"] = digest(packaged_image)
            if record["packaged_image_sha256"] != record["source_image_sha256"]:
                record["flags"].append("packaged_image_differs_from_native_source")
            with Image.open(original_image) as im:
                rgb = np.asarray(im.convert("RGB"))
            if rgb.shape[:2] != final.shape:
                raise ValueError("Source image dimensions differ")
            panels = [rgb]
            for mask in (maps["native"], final):
                color = np.zeros_like(rgb)
                for class_id, color_value in colors.items():
                    color[mask == class_id] = color_value
                panels.append(
                    np.where((mask != ignore)[..., None], 0.5 * rgb + 0.5 * color, rgb).astype(
                        np.uint8
                    )
                )
            diagnostic = (rgb * 0.3).astype(np.uint8)
            diagnostic[maps["overlap"]] = [255, 210, 0]
            diagnostic[maps["cross_class"]] = [255, 70, 0]
            diagnostic[maps["mismatch"]] = [255, 0, 255]
            panels.append(diagnostic)
            preview = safe_path(out, f"previews/{row['split']}/{row['key']}.jpg")
            preview.parent.mkdir(parents=True, exist_ok=True)
            contact = Image.fromarray(np.concatenate(panels, axis=1))
            contact.thumbnail((2400, 900))
            contact.save(preview)
            record["preview"] = str(preview.relative_to(out))
        except (OSError, ValueError, KeyError, ET.ParseError) as exc:
            record["error"] = str(exc)
            record.setdefault("flags", []).append("audit_error")
        results.append(record)
    report = {
        "schema_version": 1,
        "dataset": str(dataset.resolve()),
        "thresholds": {"dominant_coverage": coverage, "object_class_loss": overwrite},
        "images": len(results),
        "flagged_images": sum(bool(r["flags"]) for r in results),
        "errors": sum("error" in r for r in results),
        "samples": results,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (out / "review.csv").open("w", newline="") as stream:
        fields = [
            "key",
            "split",
            "source",
            "flags",
            "mismatch_pixels",
            "cross_class_overlap_pixels",
            "preview",
            "error",
        ]
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**r, "flags": ";".join(r["flags"])} for r in results if r["flags"])
    (out / "README.md").write_text(
        "# Annotation review\n\nPanels: original image, native annotation render, training mask, diagnostics.\n\n"
        "Diagnostics: yellow = any overlap; orange = cross-class overwrite; magenta = native/training mismatch.\n\n"
        "See review.csv and report.json. Flags are review heuristics, not proof of bad labels. "
        "Overwrites follow source order, not an inferred sky/vegetation hierarchy. "
        "Per-object loss measures pixels whose final class differs; event counts can count the same pixel repeatedly.\n"
    )
    return report


def version_dataset(dataset: Path, corrections: Path, out: Path) -> dict:
    """Copy a dataset into a new version and apply explicitly reviewed replacement masks."""
    dataset, out = dataset.resolve(), out.resolve()
    if out.exists() or out.is_relative_to(dataset) or dataset.is_relative_to(out):
        raise ValueError("Output must be a new separate dataset directory")
    plan = json.loads(corrections.read_text())
    if not plan.get("version") or not plan.get("reviewer") or not plan.get("corrections"):
        raise ValueError("Plan requires version, reviewer and nonempty corrections")
    schema = json.loads((dataset / "classes.json").read_text())
    valid = {c["id"] for c in schema["classes"]} | {schema.get("ignore_index", 255)}
    samples = json.loads((dataset / "audit/samples.json").read_text())
    indexed = {(r["split"], r["key"]): r for r in samples}
    replacements, seen = [], set()
    for correction in plan["corrections"]:
        identity = (correction["split"], correction["key"])
        if identity not in indexed or identity in seen or not correction.get("reason"):
            raise ValueError("Unknown/duplicate sample or missing correction reason")
        seen.add(identity)
        relative = f"masks/{identity[0]}/{identity[1]}.png"
        original = safe_path(dataset, relative)
        if digest(original) != correction["expected_mask_sha256"]:
            raise ValueError(f"Original mask hash mismatch: {identity}")
        replacement = (corrections.parent / correction["replacement_mask"]).resolve()
        with Image.open(replacement) as im:
            mask = np.array(im)
        with Image.open(original) as im:
            shape = np.array(im).shape
        if (
            mask.ndim != 2
            or mask.shape != shape
            or not np.issubdtype(mask.dtype, np.integer)
            or not set(np.unique(mask).tolist()) <= valid
        ):
            raise ValueError(
                "Replacement mask must have original dimensions and valid integer class IDs"
            )
        replacements.append((relative, replacement, mask, indexed[identity]))
    # Reject symlinks: new versions must not alias parent files or external paths.
    if any(p.is_symlink() for p in dataset.rglob("*")):
        raise ValueError("Dataset contains symlinks; materialize them before versioning")
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    try:
        target = temporary / "dataset"
        shutil.copytree(dataset, target)
        parent_files = {
            str(p.relative_to(dataset)): digest(p)
            for p in sorted(dataset.rglob("*"))
            if p.is_file()
        }
        changes = []
        for relative, _replacement, mask, row in replacements:
            Image.fromarray(mask).save(target / relative)
            changes.append(
                {
                    "path": relative,
                    "old_sha256": parent_files[relative],
                    "new_sha256": digest(target / relative),
                }
            )
            row["mask_sha256"] = hashlib.sha256(mask.tobytes()).hexdigest()
            row["class_pixels"] = {
                str(int(k)): int(v)
                for k, v in zip(*np.unique(mask, return_counts=True), strict=True)
            }
            row["ignore_pixels"] = int(np.count_nonzero(mask == schema.get("ignore_index", 255)))
            row["annotation_status"] = "reviewed_replacement_mask; native source preserved"
        # Archive stale derived artifacts so they cannot masquerade as current statistics.
        stale = target / "audit/parent-version-artifacts"
        stale.mkdir(exist_ok=True)
        for relative in (
            "previews",
            "audit/samples.csv",
            "audit/class-distribution.csv",
            "audit/summary.json",
            "dataset-version.json",
        ):
            path = target / relative
            if path.exists():
                dest = stale / relative.replace("/", "-")
                if dest.exists():
                    dest = stale / (
                        hashlib.sha256(
                            json.dumps(parent_files, sort_keys=True).encode()
                        ).hexdigest()[:12]
                        + "-"
                        + dest.name
                    )
                shutil.move(str(path), dest)
        (target / "audit/samples.json").write_text(json.dumps(samples, indent=2) + "\n")
        provenance = {
            "version": plan["version"],
            "reviewer": plan["reviewer"],
            "parent": str(dataset),
            "parent_files_sha256": parent_files,
            "corrections": plan["corrections"],
            "changes": changes,
            "statistics_status": "Regenerate statistics and previews for this version before training.",
        }
        (target / "dataset-version.json").write_text(json.dumps(provenance, indent=2) + "\n")
        target.rename(out)
    finally:
        shutil.rmtree(temporary)
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("audit")
    check.add_argument("--dataset", type=Path, required=True)
    check.add_argument("--out", type=Path, required=True)
    check.add_argument("--source-root", type=Path)
    check.add_argument("--dominant-coverage", type=float, default=0.85)
    check.add_argument("--overwrite-fraction", type=float, default=0.5)
    version = sub.add_parser("version")
    version.add_argument("--dataset", type=Path, required=True)
    version.add_argument("--corrections", type=Path, required=True)
    version.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "audit":
        result = audit(
            args.dataset,
            args.out,
            args.source_root,
            args.dominant_coverage,
            args.overwrite_fraction,
        )
        print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))
        if result["errors"]:
            raise SystemExit(1)
    else:
        result = version_dataset(args.dataset, args.corrections, args.out)
        print(json.dumps(result["changes"], indent=2))


if __name__ == "__main__":
    main()
