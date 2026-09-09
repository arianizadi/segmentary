"""Copy RTIS without the disputed CVAT import; verify native labels and preserved pixels."""

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from scripts.prepare_rtis import render

REMOVED = {f"no_anomalies_{i:04}.png" for i in range(251, 266)}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source, target):
    if target.exists():
        raise ValueError(f"Destination exists: {target}")
    samples = json.loads((source / "audit/samples.json").read_text())
    removed = [r for r in samples if r["filename"] in REMOVED]
    retained = [r for r in samples if r["filename"] not in REMOVED]
    assert {r["filename"] for r in removed} == REMOVED and len(removed) == 15
    assert all(r["split"] == "train" for r in removed)
    splits = json.loads((source / "splits.json").read_text())
    original_splits = json.loads(json.dumps(splits))
    keys = {r["key"] for r in removed}
    for split in ("train", "val", "test"):
        splits[split] = [k for k in splits[split] if k not in keys]
    splits["groups"] = {k: v for k, v in splits["groups"].items() if k not in keys}
    meta = json.loads((source / "source-annotations/supervisely/meta.json").read_text())
    meta["classes"] = [c for c in meta["classes"] if not c["title"].endswith("_1")]
    assert len(meta["classes"]) == 22 and all(c["shape"] == "polygon" for c in meta["classes"])
    by_name = {c["title"]: c for c in meta["classes"]}
    taxonomy = json.loads((source / "classes.json").read_text())
    labels = {c["name"]: c["id"] for c in taxonomy["classes"]}
    assert len(labels) == 21 and set(labels) | {"void"} == set(by_name)
    for c in taxonomy["classes"]:
        assert by_name[c["name"]]["color"].upper() == "#" + "".join(f"{x:02X}" for x in c["color"])
    labels["void"] = 255
    staging = target.with_name(target.name + ".preparing")
    staging.mkdir()
    counts = Counter()
    for r in retained:
        split, key = r["split"], r["key"]
        for folder, ext in (
            ("images", r["image_extension"]),
            ("masks", ".png"),
            ("previews", ".jpg"),
        ):
            rel = Path(folder) / split / (key + ext)
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, dest)
            assert digest(dest) == digest(source / rel)
        image = staging / "images" / split / (key + r["image_extension"])
        assert digest(image) == r["image_sha256"]
        annotation = source / "source-annotations/supervisely" / (key + ".json")
        native = json.loads(annotation.read_text())
        assert digest(annotation) == r["annotation_sha256"]
        for obj in native["objects"]:
            assert obj["classTitle"] in by_name and obj["geometryType"] == "polygon"
            assert obj["classId"] == by_name[obj["classTitle"]]["id"]
            counts[obj["classTitle"]] += 1
        mask = np.array(Image.open(staging / "masks" / split / (key + ".png")))
        assert mask.dtype == np.uint8 and mask.shape == (r["height"], r["width"])
        assert hashlib.sha256(mask.tobytes()).hexdigest() == r["mask_sha256"]
        assert set(np.unique(mask)) <= set(range(21)) | {255}
        raster, _ = render(native["objects"], mask.shape, labels, "supervisely")
        assert np.array_equal(raster, mask), f"Native rendering differs: {key}"
        dest = staging / "source-annotations/supervisely" / (key + ".json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(annotation, dest)
        for name, src in (
            (Path("ann") / (r["filename"] + ".json"), dest),
            (Path("img") / r["filename"], image),
        ):
            dst = staging / "supervisely-project" / Path(key).parent / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.link(src, dst)
    write(staging / "source-annotations/supervisely/meta.json", meta)
    write(staging / "supervisely-project/meta.json", meta)
    shutil.copy2(source / "classes.json", staging / "classes.json")
    write(staging / "splits.json", splits)
    write(staging / "audit/samples.json", retained)
    write(staging / "audit/removed-cvat-import.json", removed)
    write(staging / "audit/source-meta.json", meta)
    with (staging / "audit/samples.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(retained[0]))
        writer.writeheader()
        writer.writerows(retained)
    sizes = {s: len(splits[s]) for s in ("train", "val", "test")}
    validation = {
        "passed": True,
        "source": str(source),
        "dataset": target.name,
        "sizes": sizes,
        "retained": len(retained),
        "removed": sorted(REMOVED),
        "removed_split": "train",
        "validation_membership_unchanged": splits["val"] == original_splits["val"],
        "test_membership_unchanged": splits["test"] == original_splits["test"],
        "retained_image_mask_annotation_hashes_verified": len(retained),
        "native_supervisely_raster_exact_matches": len(retained),
        "native_polygon_counts": dict(counts),
        "native_classes": 22,
        "training_classes": 21,
        "ignore_id": 255,
        "retained_alias_objects": 0,
        "retained_bitmap_objects": 0,
        "source_split_sha256": digest(source / "splits.json"),
        "split_sha256": digest(staging / "splits.json"),
    }
    write(staging / "audit/validation.json", validation)
    listing = "\n".join(f"- `{name}`" for name in sorted(REMOVED))
    (staging / "README.md").write_text(f"""# {target.name}

Removed the disputed CVAT-to-Supervisely import from `{source}`.
292 images remain: 205 training, 37 validation, 50 held-out test.
Every retained image keeps its original split. Removed training images:

{listing}

Remaining images, masks and native annotations are byte-identical to v1.
All 292 masks were regenerated in memory from Supervisely objects in saved order
and matched exactly. This does not re-adjudicate the remaining annotations.

`supervisely-project/` is a native Supervisely project (meta.json and group/img, group/ann).
Its 22 original polygon classes retain their names, colors and IDs, with no `_1`
classes or bitmap objects. `images/` and `masks/` are the Segmentary training layout.
`classes.json` keeps training IDs 0-20; void and uncovered pixels remain ignored as 255.
Native platform IDs are not training channel indices. Polygon order and geometry are preserved.

`audit/validation.json` records verification; `audit/removed-cvat-import.json` records removals.
The original dataset and results are preserved. Historical audit outputs were not copied as v2 evidence.
Recording groups remain provisional until recording provenance is confirmed.
The comparison uses seed 0 only, unchanged training settings and historical source checkpoints,
and the same 37 validation images. One seed is exploratory, not a variance estimate.
""")
    staging.rename(target)
    old = source / "README.md"
    backup = source / "README.before-v2.md"
    if not backup.exists():
        shutil.copy2(old, backup)
    old.write_text(
        f"""# Annotation warning: original paul-test-rtis (v1)

This original dataset contains the bad/disputed CVAT-to-Supervisely annotations for
`no_anomalies_0251.png` through `no_anomalies_0265.png` (15 training images).
The imports include `_1` classes and polygon differences; overlap/order is also disputed.
Historical training results include these images. Original data and annotations are preserved.

The cleaned copy is `{target}`; its README lists every removed image.
Validation and test are unchanged. The old README below predates the completed 432-job campaign;
its statement that full training had not started is historical, not current.

---

"""
        + backup.read_text()
    )
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source.resolve(), args.target.resolve())
