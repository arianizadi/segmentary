# Dataset and loader catalog

Segmentary separates three decisions that many segmentation projects accidentally
mix together:

1. `loader` says how files are found and decoded;
2. `mapping` says what native mask IDs mean;
3. `name` is the stable dataset identity used in batches, sampling, logs, and
   results.

## Beginner choice

For new data, use the [generic folder loader](folder/README.md) and create one
canonical taxonomy plus one native-ID mapping. Use a versioned group manifest
when frames come from recordings.

```yaml
data:
  - name: my_dataset
    root: data/my_dataset
    loader: folder
    mapping: my_dataset
    train_split: train
    val_split: val
```

## Built-in choices

| loader | best for | key limitation |
|---|---|---|
| [`folder`](folder/README.md) | arbitrary paired image/index-mask folders | no polygon/RGB-mask/database decoder; add an extension for those |
| [`cityscapes`](cityscapes/README.md) | official Cityscapes `leftImg8bit` + `gtFine` | labeled `train`/`val` only |
| [`railsem19`](railsem19/README.md) | RailSem19 v1 archive | explicit committed split file required |
| [`custom`](custom-legacy/README.md) | repository's legacy flat custom-rail layout | mandatory `splits.json`; prefer `folder` for a new project |

The four names above are built-ins. If `loader` is omitted, it defaults to the
logical `name`.

## Shared data switches

| field | meaning |
|---|---|
| `name` | non-empty logical identity; must be unique inside a mixed stage |
| `root` | dataset root directory |
| `loader` | built-in ID or `package.module:DatasetClass` |
| `mapping` | taxonomy mapping filename stem; defaults to `name` |
| `variant` | optional suffix, loading `<mapping>_<variant>.yaml` |
| `split_file` | explicit split/manifest path when a loader supports or requires it |
| `train_split`, `val_split` | split strings passed to training and validation |
| `limit` | positive first-N diagnostic cap; invalid as a full benchmark |
| `loader_options` | loader-specific mapping; cannot replace core arguments |

Every loader must yield RGB images, single-channel indexed masks, keys, and
leakage-safe group identities through `SegDataset`. The base class applies the
validated uint8 taxonomy lookup and returns canonical `long` masks plus the
source's active-class vector.

## Python loader extension

Use an explicit import path for a genuinely different source:

```yaml
loader: my_project.datasets:DatabaseSegmentationDataset
loader_options:
  table: frames_v2
```

The class must be importable and subclass `segmentary.data.base.SegDataset`. It
implements deterministic `index()` and may override `load_image()` or
`load_label()` for another encoding. Imported code executes locally; review and
version it. Constructor errors identify the rejected `loader_options` keys.

Advanced requirements:

- return sorted, stable `Sample(image, label, key, group)` entries;
- keep native mask decoding integer and single-channel;
- make objects picklable for standalone evaluation workers, or set
  `eval.num_workers: 0`/`--num-workers 0`;
- test empty roots, missing pairs, duplicate keys, observed-ID coverage,
  transforms, and group leakage;
- keep class semantics in taxonomy YAML rather than hidden Python remaps.

## Mixed-dataset stages

List several data entries under one stage and optionally set positive relative
shares keyed by every dataset name:

```yaml
data:
  - {name: source, root: data/source, loader: folder, mapping: source}
  - {name: target, root: data/target, loader: folder, mapping: target}
sample_weights: {source: 0.5, target: 0.5}
```

With weights, sampling is with replacement and each dataset receives its stated
share regardless of dataset size. With no weights, ordinary concatenation keeps
natural size proportions. Every member must share one canonical label space.
Each sample's active mask prevents a source from treating unlabelable classes as
negatives. In-training validation uses the first listed dataset only.

## Pros and cons of the common loader contract

Pros: one tested taxonomy/augmentation/batch interface works across built-ins,
folders, and reviewed extensions; mixed samples preserve their own active
classes; result records keep logical dataset identities. Cons: an unusual source
must implement the strict `SegDataset` contract, mapping YAML is required even
for identity labels, and native data/split quality remains the user's
responsibility.

## Evidence and benchmark boundary

Loader tests cover strict pairing, file modes/sizes, imports, manifests,
group-disjointness, sampling ratios, active masks, and native-resolution
validation. Dataset class counts and verified layout facts are on the dedicated
pages. No loader itself has an accuracy benchmark; meaningful mIoU also depends
on model, taxonomy, split, schedule, and evaluation policy.

## Related documentation

- [Loader component summary](../components/loaders/README.md)
- [Taxonomy catalog](../../../taxonomy/README.md)
- [Custom-data guide](../../guides/custom-data.md)
- [Configuration guide](../../guides/configuration.md)
