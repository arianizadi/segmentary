# Custom datasets and loaders

Most projects should begin with the generic `folder` loader. It pairs ordinary
images with single-channel integer masks, applies a validated native-ID mapping,
and works with one stage, several stages, or mixed training.

Use a Python `SegDataset` subclass only when the source format cannot reasonably
be represented as paired files.

## Default folder layout

```text
my_dataset/
  images/train/scene_001.jpg
  images/val/scene_101.jpg
  masks/train/scene_001.png
  masks/val/scene_101.png
```

The image and mask share a relative path and stem. Nested directories are
supported. Default image extensions are PNG, JPEG, TIFF, BMP, and WebP; masks
default to PNG.

```yaml
space: my_space
taxonomy_root: taxonomy

stages:
  - name: train
    data:
      - name: my_dataset
        root: data/my_dataset
        loader: folder
        mapping: my_dataset
        train_split: train
        val_split: val
```

The three identity fields are deliberately separate:

- `name` is the logical dataset identity used in batches, sampling weights,
  logs, and result records;
- `loader` selects file-reading code (`folder`, a built-in loader ID, or
  `package.module:Class`);
- `mapping` selects `taxonomy/<space>/<mapping>.yaml` and defaults to `name`.

This lets two logical datasets reuse one annotation mapping or one loader without
pretending they are the same experimental source.

## Masks and native IDs

A mask must be a single-channel index image. Palette PNG (`P`) is valid because
Segmentary keeps palette indices. An RGB color visualization is not valid.

Masks do not have to contain canonical IDs already. Define the intended mapping:

```yaml
# taxonomy/my_space/camera_a.yaml
space: my_space
dataset: camera_a
source: Annotation schema v2
default: 255
map:
  0: 0
  7: 1
  11: 2
```

Every observed native ID should be listed, even when it maps to 255. Unlisted
values default to ignore so an unknown annotation cannot silently become real
supervision. Many-to-one mappings require `allow_merge` with a reason.

## Advanced folder layouts

`loader_options` are typed as a JSON/YAML mapping and forwarded only after core
arguments are protected:

```yaml
data:
  - name: aerial_tiles
    root: data/aerial
    loader: folder
    mapping: aerial_v3
    loader_options:
      image_dir: RGB/{split}
      mask_dir: Labels/{split}
      image_extensions: [.png, .tif]
      mask_extension: .png
      recursive: true
```

Available folder options:

| Option | Default | Meaning |
|---|---|---|
| `image_dir` | `images/{split}` | image directory relative to root |
| `mask_dir` | `masks/{split}` | mask directory relative to root |
| `image_extensions` | common image formats | accepted image suffixes |
| `mask_extension` | `.png` | paired-mask suffix |
| `recursive` | `true` | scan nested image directories |
| `require_groups` | `false` | require a group for every sample and reject cross-split group leakage |

Only the literal `{split}` placeholder is allowed in directory templates. Two
images with different extensions cannot share one relative stem, and every image
must have its paired mask.

## Independent images versus video frames

For independent images, split directories are sufficient and a manifest is
optional.

For video, burst, subject, site, or route data, related samples must not cross
train/validation/test. Add `splits.json` at the dataset root (or set
`split_file`) and enable `require_groups`:

```json
{
  "train": ["run_001/frame_0001", "run_001/frame_0002"],
  "val": ["run_002/frame_0001"],
  "groups": {
    "run_001/frame_0001": "run_001",
    "run_001/frame_0002": "run_001",
    "run_002/frame_0001": "run_002"
  }
}
```

```yaml
    split_file: splits.json
    loader_options:
      require_groups: true
```

The loader checks that:

- the requested split exists;
- manifest keys exactly match files on disk for that split;
- every required sample has a group;
- no group appears in two splits.

Adjacent frames are near-duplicates. A frame-random split can make validation
look excellent while measuring memorization of the same recording.

The bundled split helper creates a new paired dataset from source files and an
explicit group mapping or filename regex:

```bash
segmentary-make-split \
  --images source/images \
  --masks source/masks \
  --groups source/groups.json \
  --out-root data/my_grouped_dataset \
  --seed 0 --val-frac 0.10 --test-frac 0.10
```

It refuses an existing output root. Symlinks avoid duplicate storage; hardlinks
work on one filesystem; copies are independent but consume storage. Fractions
apply to groups, so also report frame counts when group sizes vary.

## Verify before training

```bash
segmentary-verify \
  --dataset aerial_tiles \
  --loader folder \
  --mapping aerial_v3 \
  --root data/aerial \
  --space my_space \
  --taxonomy taxonomy \
  --loader-options '{"image_dir":"RGB/{split}","mask_dir":"Labels/{split}"}'
```

The verifier scans mask IDs and frequencies, constructs the real loader and
augmentation, and writes overlays. Inspect them. Then run `segmentary-overfit` on
a small but class-representative set.

## Python loader extensions

Subclass `segmentary.data.base.SegDataset` when data live in a database/archive,
labels require specialized decoding, or pairing cannot be expressed by folder
options:

```python
from pathlib import Path

from albumentations import Compose

from segmentary.data.base import Sample, SegDataset
from segmentary.taxonomy import DatasetMapping


class MyDataset(SegDataset):
    def __init__(
        self,
        root: Path | str,
        split: str,
        mapping: DatasetMapping,
        transform: Compose,
        limit: int | None = None,
        *,
        metadata_file: str | Path,
        split_file: str | Path | None = None,
    ) -> None:
        metadata_path = Path(metadata_file)
        self.metadata_file = (
            metadata_path if metadata_path.is_absolute() else Path(root) / metadata_path
        )
        manifest_path = Path(split_file) if split_file is not None else None
        self.split_file = (
            manifest_path
            if manifest_path is None or manifest_path.is_absolute()
            else Path(root) / manifest_path
        )
        # SegDataset.__init__ calls index(), so save extension options first.
        super().__init__(root, split, mapping, transform, limit=limit)

    def index(self) -> list[Sample]:
        # Read self.metadata_file and optionally self.split_file. Return
        # deterministic, sorted Sample(image, label, key, group) objects.
        ...
```

Configure it without editing Segmentary's factory:

```yaml
data:
  - name: experiment_source
    root: data/source
    loader: my_package.datasets:MyDataset
    mapping: source_schema
    loader_options:
      metadata_file: annotations.json
```

The imported object must be a `SegDataset` subclass. Its constructor receives
`root`, `split`, validated `mapping`, `transform`, `limit`, and the configured
loader options. A top-level `split_file` is also forwarded when configured.
Store extension fields before calling `super().__init__()`, because the base
constructor immediately calls `index()`. Core arguments cannot be overridden
through `loader_options`.

Keep extension code versioned with the run. Import paths make extension easy;
they do not make unreviewed Python safe.

## Built-in format loaders

`cityscapes`, `railsem19`, and the legacy grouped `custom` loader remain for the
bundled reproduction study. Use them when you actually have those formats. The
generic folder loader is the portable default for new work.

## Data checklist

- class definitions and annotation policy are written down;
- images/masks pair one-to-one and dimensions match;
- native IDs and ignore regions are audited;
- train/val/test groups cannot leak;
- class frequency and rare/thin-class support are known;
- overlays are visually correct after augmentation;
- the tiny overfit check passes;
- raw/licensed data, credentials, and large artifacts stay out of Git;
- mapping and split manifests are versioned with results.
