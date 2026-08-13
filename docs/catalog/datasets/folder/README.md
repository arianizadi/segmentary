# Generic folder dataset

`loader: folder` is the portable path for arbitrary paired semantic-segmentation
data. It matches images and masks by their relative path and stem.

## Beginner layout and config

```text
my_dataset/
  images/train/a.jpg
  images/val/b.jpg
  masks/train/a.png
  masks/val/b.png
```

```yaml
data:
  - name: my_dataset
    root: data/my_dataset
    loader: folder
    mapping: my_dataset
```

Masks must be single-channel integer-index images. RGB colors are not class IDs.
Create `taxonomy/<space>/my_dataset.yaml` to map native IDs to canonical IDs.

## Exact `loader_options`

```yaml
loader_options:
  image_dir: images/{split}
  mask_dir: masks/{split}
  image_extensions: [.png, .jpg, .jpeg, .tif, .tiff, .bmp, .webp]
  mask_extension: .png
  recursive: true
  require_groups: false
```

`image_dir` and `mask_dir` may contain only the `{split}` placeholder and may be
absolute or relative to `root`. Extensions are case-normalized and may be
written with or without a leading dot. `recursive: false` scans only the split
directory's first level.

Pairs must be exactly one-to-one. Nested keys preserve the relative path, so
`images/train/run1/frame.jpg` matches
`masks/train/run1/frame.png`. Duplicate extensions resolving to one key,
unmatched images, and orphan masks are fatal.

## Group-safe manifest

For independent still images, a manifest is optional. For video or burst data,
set `require_groups: true` and provide `split_file` or `<root>/splits.json`:

```json
{
  "train": ["run1/frame001"],
  "val": ["run2/frame001"],
  "groups": {
    "run1/frame001": "run1",
    "run2/frame001": "run2"
  }
}
```

Manifest split keys must exactly match files on disk. Duplicate keys, absent
splits, missing required groups, or one group crossing two splits are fatal.
Relative `split_file` paths resolve under the dataset root.

## Pros and cons

Pros:

- works without custom Python;
- nested directories and several image formats;
- strict one-to-one pairing and optional leakage proof;
- logical dataset name and taxonomy mapping are independent.

Cons:

- indexed masks only; RGB/polygon/RLE/database annotations need preprocessing
  or a reviewed Python extension;
- split directories must already exist;
- `limit` keeps the sorted first N items, so it can be distributionally biased
  and is diagnostic only.

## Advanced example

```yaml
data:
  - name: inspection_v2
    root: data/inspection_v2
    loader: folder
    mapping: camera_schema
    split_file: splits.json
    loader_options:
      image_dir: RGB/{split}
      mask_dir: Labels/{split}
      image_extensions: [.png, .tif]
      mask_extension: .png
      recursive: true
      require_groups: true
```

## Evidence and benchmark boundary

Tests exercise custom layouts, nested keys, extension normalization, duplicates,
pair mismatch, bad placeholders/manifests, and group leakage. The packaged
starter project uses this loader. No comparable accuracy benchmark is attached
to a storage layout.

## Related documentation

- [Dataset catalog](../README.md)
- [Example taxonomy](../../../../taxonomy/example/README.md)
- [Custom-data guide](../../../guides/custom-data.md)
- [Dataset verification](../../../tutorials/getting-started.md)
