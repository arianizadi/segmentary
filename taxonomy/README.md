# Taxonomy and label-space catalog

A taxonomy gives every output channel one stable semantic meaning. Dataset
mapping files convert native mask IDs into that canonical space at load time.
This is what lets several datasets share one model without silently treating an
unlabeled class as a negative.

## Beginner choice

Copy the [`example`](example/README.md) space for a new project. Define the
classes you truly need, then make one mapping file per native annotation schema.
Do this before long training: changing class order or meaning creates a new
experiment and invalidates old checkpoints.

```text
taxonomy/<space>/canonical.yaml
taxonomy/<space>/<mapping>.yaml
taxonomy/<space>/<mapping>_<variant>.yaml
```

In experiment YAML:

```yaml
space: my_space
taxonomy_root: taxonomy
stages:
  - name: train
    data:
      - name: my_dataset
        loader: folder
        mapping: my_dataset
        variant: null
```

## Canonical file contract

```yaml
name: my_space
description: What every class means.
ignore_index: 255
classes:
  - {id: 0, name: background, color: [30, 30, 30]}
  - {id: 1, name: object, color: [220, 60, 60]}
thin_classes: []
```

Class IDs must be unique, contiguous, and start at 0. Names are unique. Colors
are RGB bytes. There must be fewer than 255 classes, and ignore is exactly 255
so masks remain uint8. `thin_classes` lists valid canonical IDs for reporting;
it does not automatically change the loss.

## Dataset mapping contract

```yaml
space: my_space
dataset: my_dataset
source: Native schema/version or authoritative file.
default: 255
map:
  0: 0
  7: 1
  255: 255
allow_merge: {}
```

Every undeclared native byte becomes ignore, never supervision. Every mapped
target must be a canonical ID or 255. If two native IDs map to one canonical
class, `allow_merge` must name that canonical ID and give a non-empty reason.
Missing declarations fail; stale declarations also fail.

The verifier scans real mask IDs and calls `assert_covers`, closing the gap
between a valid YAML file and what the dataset actually emits.

## Active and inactive classes

The mapping derives its active canonical classes from values in `map`. A sample
carries that boolean vector into the loss. Inactive output channels are removed
from the softmax for that sample, so a coarse dataset does not train the model to
reject distinctions it cannot annotate. Evaluation reports inactive classes as
`null` and excludes them from means.

## Shipped spaces

| space | classes | use | mappings/variants |
|---|---:|---|---|
| [`example`](example/README.md) | 3 | generic folder starter | `my_dataset` identity example |
| [`cityscapes19`](cityscapes19/README.md) | 19 | standard Cityscapes comparison | official Cityscapes; lossy RailSem19 cross-eval |
| [`rail_union`](rail_union/README.md) | 21 | urban/rail transfer case study | Cityscapes default + rail-bridge variant; RailSem19; custom identity |

## Pros and cons of a canonical space

Pros:

- one stable classifier across stages and mixed batches;
- executable documentation of every ignored/merged native ID;
- vectorized mapping with no drifting derived label copies;
- explicit colors, active classes, and thin-class reporting.

Cons:

- semantics must be designed before training;
- fine distinctions cannot be reconstructed from a coarser native label;
- a union may require coarsening one source and leaving other classes inactive;
- mIoU from different spaces is never directly comparable.

## Adding a variant

Use a suffix only for a deliberate mapping ablation:

```text
taxonomy/my_space/source.yaml
taxonomy/my_space/source_experimental.yaml
```

Then set `mapping: source` and `variant: experimental`. Keep the default file
unchanged and put the variant name in experiment/results provenance. A variant
changes supervision and must not be silently grouped with the baseline.

## Evidence and benchmark boundary

Tests validate every shipped space, LUT, active set, ignored fallback, merge
reason, color range, and observed real-data IDs where data is available. These
are correctness checks, not accuracy benchmarks. The tracked Cityscapes
reference uses exactly `cityscapes19`; no result in another space may borrow its
number. See [benchmark evidence](https://github.com/arianizadi/segmentary/blob/main/docs/benchmarks/README.md).

## Related documentation

- [Dataset catalog](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/datasets/README.md)
- [Loss semantics](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/components/losses/README.md)
- [Core concepts](https://github.com/arianizadi/segmentary/blob/main/docs/tutorials/core-concepts.md)
- [Custom-data guide](https://github.com/arianizadi/segmentary/blob/main/docs/guides/custom-data.md)
