"""Package existing image/index-mask pairs for the bundled Inference Checker.

Requires Pillow and PyYAML only; does not load models or run inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

import yaml
from PIL import Image


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_mask(path, size, classes, ignore):
    with Image.open(path) as image:
        if image.format != "PNG" or image.mode not in ("L", "P") or image.size != size:
            raise ValueError(f"Expected matching 8-bit index PNG: {path}")
        values = image.tobytes()
    if any(value >= classes and value != ignore for value in set(values)):
        raise ValueError(f"Unknown class ID in {path}")
    return values


def prepare(images, masks, taxonomy, predictions, out, title):
    images, masks, out = Path(images).resolve(), Path(masks).resolve(), Path(out).absolute()
    if out.exists():
        raise ValueError("Output already exists; use a new bundle directory")
    roots = [images, masks, *[Path(p).resolve() for p in predictions.values()]]
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Missing input directory: {root}")
        if out.resolve().is_relative_to(root) or root.is_relative_to(out.resolve()):
            raise ValueError("Output and input directories must not contain each other")
    space = yaml.safe_load(Path(taxonomy).read_text())
    classes = space["classes"]
    if [c["id"] for c in classes] != list(range(len(classes))) or not 1 <= len(classes) <= 255:
        raise ValueError("Taxonomy IDs must be contiguous from zero, with at most 255 classes")
    ignore = space.get("ignore_index", 255)
    if not isinstance(ignore, int) or not len(classes) <= ignore <= 255:
        raise ValueError("Ignore index must be an unused byte value")
    for name in predictions:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) or name in {"gt", "input"}:
            raise ValueError(f"Unsafe or reserved prediction name: {name}")
    config = {
        "version": 1,
        "title": title,
        "dataset": space.get("name", "custom"),
        "ignoreIndex": ignore,
        "labels": [
            {
                "name": c["name"],
                "readable": c.get("readable", c["name"].replace("-", " ")),
                "color": c["color"],
                "evaluate": c.get("evaluate", True),
            }
            for c in classes
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".viewer-bundle-", dir=out.parent))
    seen = set()
    manifest = []
    try:
        files = sorted(
            p
            for p in images.rglob("*")
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        if not files:
            raise ValueError("No images found")
        for image_path in files:
            key = image_path.relative_to(images).with_suffix("").as_posix()
            if key in seen:
                raise ValueError(f"Multiple images share mask key: {key}")
            seen.add(key)
            slug = re.sub(r"[^A-Za-z0-9_-]", "-", key)[:100].strip("-") or "scene"
            scene_id = slug + "-" + hashlib.sha256(key.encode()).hexdigest()[:12]
            scene = staging / scene_id
            scene.mkdir()
            with Image.open(image_path) as im:
                rgb = im.convert("RGB")
                size = rgb.size
                if max(size) > 16384 or size[0] * size[1] > 16 * 1024 * 1024:
                    raise ValueError(f"Image exceeds viewer size limit: {image_path}")
                rgb.save(scene / "input.png")
            gt_path = masks / (key + ".png")
            gt = index_mask(gt_path, size, len(classes), ignore)
            Image.frombytes("L", size, gt).save(scene / "gt.png")
            sources = {
                "input": {"path": str(image_path), "sha256": digest(image_path)},
                "gt": {"path": str(gt_path), "sha256": digest(gt_path)},
            }
            for name, root in predictions.items():
                p = Path(root).resolve() / (key + ".png")
                pred = index_mask(p, size, len(classes), ignore)
                if ignore in pred and any(
                    v == ignore and g != ignore for v, g in zip(pred, gt, strict=True)
                ):
                    raise ValueError(f"Prediction ignores labeled pixels: {p}")
                Image.frombytes("L", size, pred).save(scene / (name + ".png"))
                sources[name] = {"path": str(p), "sha256": digest(p)}
            (scene / "scene.json").write_text(
                json.dumps(
                    {
                        "title": key,
                        "provenance": {
                            "source": config["dataset"],
                            "frame": key,
                            "notes": "Existing masks; no inference or resizing performed",
                        },
                    },
                    indent=2,
                )
                + "\n"
            )
            manifest.append(
                {
                    "scene": scene_id,
                    "key": key,
                    "sources": sources,
                    "artifacts": {p.name: digest(p) for p in scene.iterdir()},
                }
            )
        (staging / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        (staging / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        staging.rename(out)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return len(manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--masks", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True, help="Canonical taxonomy YAML")
    parser.add_argument("--prediction", action="append", default=[], metavar="NAME=DIRECTORY")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default="Image and mask inspection")
    args = parser.parse_args()
    predictions = {}
    for item in args.prediction:
        name, sep, directory = item.partition("=")
        if not sep or not directory or name in predictions:
            parser.error("Each prediction must have a unique NAME=DIRECTORY")
        predictions[name] = Path(directory)
    count = prepare(args.images, args.masks, args.taxonomy, predictions, args.out, args.title)
    print(f"Prepared {count} scenes at {args.out}; inspect with ./scripts/inspect.sh {args.out}")


if __name__ == "__main__":
    main()
