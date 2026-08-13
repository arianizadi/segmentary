# Dataset loader choices

A loader finds image/mask pairs and attaches the correct taxonomy mapping. It
does not decide what the native mask IDs mean; that stays in versioned taxonomy
YAML.

## Beginner choice

Use `loader: folder` for a new paired semantic-segmentation dataset:

```yaml
data:
  - name: my_dataset
    root: data/my_dataset
    loader: folder
    mapping: my_dataset
```

The default layout is `images/<split>/...` and `masks/<split>/...` with matching
relative stems. It is strict, portable, and supports nested directories.

## Available choices

| `loader` | use it for | important requirement |
|---|---|---|
| `folder` | arbitrary paired indexed masks | one-to-one relative stems; add a group manifest for video/sequence data |
| `cityscapes` | official gtFine layout | only labeled `train` and `val`; raw `*_labelIds.png` masks |
| `railsem19` | RailSem19 v1 archive | explicit committed `split_file` is mandatory |
| `custom` | legacy flat rail layout | `<root>/splits.json` is mandatory and group overlap is fatal |
| `package.module:DatasetClass` | genuinely different storage/decoding | reviewed, importable `SegDataset` subclass |

`loader` defaults to the data entry's `name`. `mapping` independently defaults
to `name`, so a logical dataset identity can reuse a differently named loader or
mapping without changing sampling/result labels.

## Shared switches

Every data entry supports `name`, `root`, `loader`, `mapping`, `variant`,
`split_file`, `train_split`, `val_split`, positive diagnostic `limit`, and a
`loader_options` mapping. Core constructor arguments cannot be replaced through
`loader_options`; collisions are rejected.

For a stage containing several datasets, Segmentary builds `MixedDataset` and can
use exact positive `sample_weights` keyed by every logical dataset name. Each
sample carries its own active-class mask. In-training validation always uses the
first dataset in the list, so common-target evaluation must be run separately.

## Pros and cons

- Built-ins make known layout and split rules executable, but are intentionally
  strict about unsupported forms.
- The folder loader avoids new Python, but cannot decode a proprietary database,
  polygon annotation, or RGB color mask without preprocessing or an extension.
- Python extensions support arbitrary sources, but execute local code and must
  be versioned, reviewed, deterministic, and picklable when evaluator workers
  are nonzero.
- `limit` is useful for smoke checks and invalid for a full benchmark claim.

## Evidence and benchmark boundary

Loader tests cover pairing, duplicate keys/extensions, bad masks, manifest/disk
mismatch, group leakage, import failures, mixed sampling ratios, and per-sample
active masks. Loader correctness does not provide a model benchmark. Dataset
sizes and class evidence are listed on the dedicated pages below.

## Dedicated and related pages

- [All dataset choices and extensions](../../datasets/README.md)
- [Generic folder loader](../../datasets/folder/README.md)
- [Cityscapes](../../datasets/cityscapes/README.md)
- [RailSem19](../../datasets/railsem19/README.md)
- [Legacy custom loader](../../datasets/custom-legacy/README.md)
- [Custom-data guide](../../../guides/custom-data.md)
