"""Prepare a flat rail-anomalies delivery (``img/``, ``jsons/``, ``masks_machine/``) for training.

Labels come either as byte copies of the delivered ``masks_machine`` (``--labels paul``)
or re-rendered from the Supervisely polygons with ``scripts/prepare_rtis.render``
(``--labels rendered``: uncovered and void pixels are 255, holes are honoured,
cv2.fillPoly in saved order). Both modes write ``audit/label-audit.{json,csv}`` that
records how the two label sources differ, and both verify every written file.
The target is staged in ``<target>.preparing`` and renamed only when complete.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import PIL
import yaml
from PIL import Image
from scripts.make_rad_splits import delivery_images
from scripts.prepare_rtis import render

REPO = Path(__file__).resolve().parents[1]
CANONICAL = REPO / "taxonomy/paul-test-rtis/canonical.yaml"
SPLITS = ("train", "val", "test")
# Image sha256 of the two paul-test-rtis train images whose polygons were edited after
# v2 (delivery stems 0249 = no_anomalies_0740 and 0252 = no_anomalies_0749). Their
# rendered masks legitimately differ from the reference audit; any other mismatch fails.
KNOWN_EDITED = {
    "408760b135c0da743871d600304812e352ac956549d1987597238245735e8672": "0249",
    "1749f26376edb32da712444c9e60186ff4bd29e1fed12a43bf0f659bf8e5a11b": "0252",
}
AUDIT_FIELDS = (
    "uncovered_px",
    "paul_zero_uncovered_px",
    "hole_px_changed",
    "disagreement_px",
    "person_px_rendered",
    "person_px_paul",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_classes(path: Path = CANONICAL) -> dict:
    schema = yaml.safe_load(path.read_text())
    ids = [c["id"] for c in schema["classes"]]
    if ids != list(range(len(ids))) or schema["ignore_index"] != 255:
        raise ValueError(f"Unexpected class schema in {path}")
    return schema


def label_audit(objects: list, paul: np.ndarray, rendered: np.ndarray, labels: dict) -> dict:
    """Per-image evidence of how masks_machine differs from the repo render."""
    shape = rendered.shape
    covered, _ = render(objects, shape, dict.fromkeys(labels, 0), "supervisely")
    painted = covered != 255
    without_holes = [
        obj | {"points": {"exterior": obj["points"]["exterior"], "interior": []}} for obj in objects
    ]
    flat, _ = render(without_holes, shape, labels, "supervisely")
    differs = paul != rendered
    per_class = {}
    for value in sorted({int(v) for v in np.unique(paul)} | {int(v) for v in np.unique(rendered)}):
        per_class[str(value)] = {
            "rendered_px": int((rendered == value).sum()),
            "rendered_px_differing": int(((rendered == value) & differs).sum()),
            "paul_px": int((paul == value).sum()),
            "paul_px_differing": int(((paul == value) & differs).sum()),
        }
    return {
        "uncovered_px": int((~painted).sum()),
        "paul_zero_uncovered_px": int(((paul == 0) & ~painted).sum()),
        "hole_px_changed": int((flat != rendered).sum()),
        "disagreement_px": int(differs.sum()),
        "person_px_rendered": int((rendered == 0).sum()),
        "person_px_paul": int((paul == 0).sum()),
        "per_class": per_class,
    }


def readme(name: str, spec: dict, label_source: str, sizes: dict, parity: dict | None) -> str:
    method = spec["method"]
    if label_source == "paul":
        labels = (
            "Labels are **byte copies of the delivered `masks_machine/` PNGs**, exactly as the\n"
            "annotator exported them. Those masks start from a black canvas, so every pixel\n"
            "covered by no polygon is class 0 (person), and polygon holes are not cut out.\n"
            "`audit/label-audit.json` quantifies both effects against the repository render;\n"
            "nothing was corrected here on purpose."
        )
    else:
        labels = (
            "Labels are **re-rendered from `jsons/`** with `scripts/prepare_rtis.render`:\n"
            "cv2.fillPoly in saved object order, polygon holes cut out, `void` polygons and\n"
            "pixels covered by no polygon set to 255 (ignored). `audit/label-audit.json`\n"
            "records how far the delivered `masks_machine/` differ from these masks."
        )
    if spec["groups_enforced"]:
        split = (
            "The split is **scene-grouped**: train/val/test membership for every image that is\n"
            f"also in `{method['reference']}` is carried over by image sha256, and the images\n"
            f"new to this delivery are assigned by `{method['new_images_file']}`. Scene groups\n"
            "never cross splits and `splits.json` carries `groups`, so the loader enforces it."
        )
    else:
        split = (
            "The split is a **stratified random split** (multi-label iterative stratification,\n"
            f"seed {method['seed']}) on image-level presence of {', '.join(method['anomaly_classes'])}\n"
            f"and of every class present in fewer than {method['rare_threshold']} images\n"
            f"({', '.join(method['rare_classes'])}). Images with min(width, height) < 1024 are\n"
            "pinned to train. Frames of one recording may appear in different splits, so\n"
            "`splits.json` deliberately carries no `groups`; the `<group>/` directory names are\n"
            "diagnostic only and must not be read as leakage protection."
        )
    lines = [
        f"# {name}",
        "",
        f"Prepared from the `{spec['dataset']}` delivery ({sum(sizes.values())} images, "
        "Supervisely polygon JSONs).",
        f"**{sizes['train']} train / {sizes['val']} val / {sizes['test']} test; 21 classes; ignore 255.**",
        "",
        labels,
        "",
        split,
        "",
        "- `images/<split>/<group>/<stem>.<ext>`: original image bytes.",
        "- `masks/<split>/<group>/<stem>.png`: mode L class-id masks (0..20 or 255).",
        "- `splits.json`: exact membership; `_grouping_status` states how groups were handled.",
        "- `classes.json`: class ids, names and colours (label space `paul-test-rtis`).",
        "- `audit/samples.json`: per-image hashes of image bytes, decoded mask pixels, mask file"
        " and annotation.",
        "- `audit/split-spec.json`: the split specification this layout was built from.",
        "- `audit/label-audit.{json,csv}`: masks_machine versus repository render, per image.",
        "- `audit/validation.json`: hash verification and render parity results.",
        "",
    ]
    if parity is not None:
        lines.append(
            f"Render parity against the reference audit: {parity['matches']} identical masks, "
            f"{parity['known_edited_mismatches']} known edited images, {parity['new_images']} "
            "images without a reference."
        )
        lines.append("")
    return "\n".join(lines)


def prepare(
    source: Path,
    split_spec: Path,
    label_source: str,
    name: str,
    target: Path,
    reference_samples: Path | None = None,
) -> dict:
    if target.exists():
        raise ValueError(f"Destination exists: {target}")
    staging = target.with_name(target.name + ".preparing")
    if staging.exists():
        raise ValueError(f"Stale staging directory exists: {staging}")
    spec = json.loads(split_spec.read_text())
    schema = load_classes()
    labels = {c["name"]: c["id"] for c in schema["classes"]} | {"void": 255}
    valid = set(range(len(schema["classes"]))) | {255}
    # Same rules as the split writer: one file and one annotation per stem, no
    # silent overwrite when e.g. 0002.png and 0002.jpg are both delivered.
    images = delivery_images(source)
    if set(images) != set(spec["assignments"]):
        raise ValueError("Split spec does not cover exactly the delivered images")
    reference = {}
    if reference_samples is not None:
        for row in json.loads(reference_samples.read_text()):
            reference[row["image_sha256"]] = row
    staging.mkdir(parents=True)
    samples, audits = [], []
    for stem, image in images.items():
        row = spec["assignments"][stem]
        split, group = row["split"], row["group"]
        if split not in SPLITS:
            raise ValueError(f"Unknown split {split!r} for {stem}")
        annotation = source / "jsons" / f"{stem}.json"
        data = json.loads(annotation.read_text())
        objects = data["objects"]
        for obj in objects:
            if obj["geometryType"] != "polygon":
                raise ValueError(f"{stem}: unsupported geometry {obj['geometryType']}")
            if obj["classTitle"] not in labels:
                raise ValueError(f"{stem}: unknown class {obj['classTitle']!r}")
        with Image.open(image) as im:
            width, height = im.size
        if (data["size"]["height"], data["size"]["width"]) != (height, width):
            raise ValueError(f"{stem}: annotation size differs from image size")
        shape = (height, width)
        image_sha = digest(image)
        if image_sha != row["image_sha256"]:
            raise ValueError(f"{stem}: image sha256 differs from the split spec")
        rendered, stats = render(objects, shape, labels, "supervisely")
        paul_path = source / "masks_machine" / f"{stem}.png"
        with Image.open(paul_path) as im:
            if im.mode != "L" or im.size != (width, height):
                raise ValueError(f"{stem}: masks_machine is not a mode L mask of image size")
            paul = np.asarray(im)
        if not set(np.unique(paul).tolist()) <= valid:
            raise ValueError(f"{stem}: masks_machine holds values outside 0..20|255")
        key = f"{group}/{stem}"
        ext = image.suffix.lower()
        dest_image = staging / "images" / split / (key + ext)
        dest_mask = staging / "masks" / split / (key + ".png")
        dest_image.parent.mkdir(parents=True, exist_ok=True)
        dest_mask.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, dest_image)
        if label_source == "paul":
            shutil.copyfile(paul_path, dest_mask)
            mask = paul
        else:
            Image.fromarray(rendered).save(dest_mask)
            mask = rendered
        audit = label_audit(objects, paul, rendered, labels)
        audits.append({"stem": stem, "key": key, "split": split} | audit)
        samples.append(
            {
                "key": key,
                "split": split,
                "group": group,
                "stem": stem,
                "image_extension": ext,
                "width": width,
                "height": height,
                "image_sha256": image_sha,
                "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest(),
                "mask_file_sha256": digest(dest_mask),
                "rendered_mask_sha256": hashlib.sha256(rendered.tobytes()).hexdigest(),
                "label_source": label_source,
                "class_pixels": {
                    str(i): int(n)
                    for i, n in enumerate(np.bincount(mask.ravel(), minlength=256))
                    if n
                },
                "annotation_sha256": digest(annotation),
                "annotation_count": len(objects),
                "render_overlap_pixels": stats["overlap_pixels"],
                "render_uncovered_pixels": stats["uncovered_pixels"],
            }
        )
        if len(samples) % 50 == 0:
            print(f"Prepared {len(samples)} images", flush=True)
    samples.sort(key=lambda s: s["key"])
    audits.sort(key=lambda a: a["key"])
    splits = {split: sorted(s["key"] for s in samples if s["split"] == split) for split in SPLITS}
    if spec["groups_enforced"]:
        splits["groups"] = {s["key"]: s["group"] for s in samples}
    splits["_grouping_status"] = spec["_grouping_status"]
    splits["_split_method"] = spec["method"]["name"]
    splits["_split_spec_sha256"] = digest(split_spec)
    splits["_label_source"] = label_source
    write(staging / "splits.json", splits)
    write(staging / "audit/samples.json", samples)
    shutil.copyfile(split_spec, staging / "audit/split-spec.json")
    write(staging / "classes.json", schema)
    totals = {field: sum(a[field] for a in audits) for field in AUDIT_FIELDS}
    per_class: dict[str, Counter] = {}
    for a in audits:
        for value, counts in a["per_class"].items():
            per_class.setdefault(value, Counter()).update(counts)
    write(
        staging / "audit/label-audit.json",
        {
            "label_source": label_source,
            "semantics": {
                "uncovered_px": "pixels covered by no polygon (255 in the repository render)",
                "paul_zero_uncovered_px": "pixels that masks_machine labels 0 (person) although no polygon covers them",
                "hole_px_changed": "pixels whose repository label changes when polygon holes are ignored",
                "disagreement_px": "pixels where masks_machine and the repository render differ",
            },
            "totals": totals,
            "per_class_totals": {
                k: dict(v) for k, v in sorted(per_class.items(), key=lambda kv: int(kv[0]))
            },
            "images_with_uncovered_px": sum(a["uncovered_px"] > 0 for a in audits),
            "images_with_disagreement": sum(a["disagreement_px"] > 0 for a in audits),
            "per_image": audits,
        },
    )
    with (staging / "audit/label-audit.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("stem", "key", "split", *AUDIT_FIELDS))
        for a in audits:
            writer.writerow((a["stem"], a["key"], a["split"], *(a[f] for f in AUDIT_FIELDS)))
        writer.writerow(("total", "", "", *(totals[f] for f in AUDIT_FIELDS)))
    parity = None
    if reference_samples is not None:
        matches, known, bad, new = [], [], [], []
        for s in samples:
            ref = reference.get(s["image_sha256"])
            if ref is None:
                new.append(s["stem"])
            elif ref["mask_sha256"] == s["rendered_mask_sha256"]:
                matches.append(s["stem"])
            elif s["image_sha256"] in KNOWN_EDITED:
                known.append(s["stem"])
            else:
                bad.append({"stem": s["stem"], "reference_key": ref["key"]})
        if bad:
            raise ValueError(f"Rendered masks differ from the reference audit: {bad}")
        parity = {
            "reference_samples": str(reference_samples),
            "reference_samples_sha256": digest(reference_samples),
            "compared": "sha256 of the repository render against reference mask_sha256",
            "matches": len(matches),
            "known_edited_mismatches": len(known),
            "known_edited_stems": sorted(known),
            "new_images": len(new),
            "new_image_stems": sorted(new),
        }
    # Verify every written file the way the campaign runtime does.
    for s in samples:
        image = staging / "images" / s["split"] / (s["key"] + s["image_extension"])
        mask = staging / "masks" / s["split"] / (s["key"] + ".png")
        if digest(image) != s["image_sha256"]:
            raise RuntimeError(f"Written image differs: {image}")
        with Image.open(mask) as decoded:
            if decoded.mode != "L" or decoded.size != (s["width"], s["height"]):
                raise RuntimeError(f"Mask encoding or dimensions wrong: {mask}")
            if hashlib.sha256(decoded.tobytes()).hexdigest() != s["mask_sha256"]:
                raise RuntimeError(f"Written mask differs: {mask}")
    for kind in ("images", "masks"):
        expected = {
            f"{s['split']}/{s['key']}{s['image_extension'] if kind == 'images' else '.png'}"
            for s in samples
        }
        actual = {
            p.relative_to(staging / kind).as_posix()
            for p in (staging / kind).rglob("*")
            if p.is_file()
        }
        if actual != expected:
            raise RuntimeError(f"Stray or missing files under {kind}/")
    sizes = {split: len(splits[split]) for split in SPLITS}
    validation = {
        "passed": True,
        "dataset": name,
        "source": str(source),
        "label_source": label_source,
        "split_method": spec["method"]["name"],
        "split_spec_sha256": digest(split_spec),
        "groups_enforced": spec["groups_enforced"],
        "grouping_status": spec["_grouping_status"],
        "sizes": sizes,
        "samples": len(samples),
        "written_files_hash_verified": len(samples),
        "stray_files": 0,
        "label_audit_totals": totals,
        "render_parity": parity,
        "versions": {"opencv": cv2.__version__, "pillow": PIL.__version__, "numpy": np.__version__},
    }
    write(staging / "audit/validation.json", validation)
    (staging / "README.md").write_text(readme(name, spec, label_source, sizes, parity))
    staging.rename(target)
    return validation


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--split-spec", type=Path, required=True)
    ap.add_argument("--labels", choices=("paul", "rendered"), required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--reference-samples", type=Path)
    args = ap.parse_args()
    validation = prepare(
        args.source.resolve(),
        args.split_spec.resolve(),
        args.labels,
        args.name,
        args.target.resolve(),
        args.reference_samples.resolve() if args.reference_samples else None,
    )
    print(json.dumps({k: validation[k] for k in ("sizes", "label_audit_totals", "render_parity")}))


if __name__ == "__main__":
    main()
