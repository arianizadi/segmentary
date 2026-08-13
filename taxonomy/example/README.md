# `example` taxonomy

This minimal three-class label space is the packaged starter for the generic
folder loader. It demonstrates the file contract without imposing rail or urban
semantics on a new project.

## Classes

| id | name | color |
|---:|---|---|
| 0 | `background` | `[30, 30, 30]` |
| 1 | `object-a` | `[220, 60, 60]` |
| 2 | `object-b` | `[60, 180, 220]` |

Ignore is 255 and no class is marked thin.

## Mapping

[`my_dataset.yaml`](my_dataset.yaml) is an identity example for native IDs 0,
1, and 2. Any other native byte falls through to 255. Its `source` text is a
placeholder and must be replaced with the real annotation schema/version.

```yaml
space: example
dataset: my_dataset
default: 255
map: {0: 0, 1: 1, 2: 2}
```

## Beginner use

Use it unchanged only for the generated toy data or a real three-class dataset
with exactly those ID meanings. Normally, rename the space/classes and edit the
mapping before training:

```yaml
space: example
data:
  - name: my_dataset
    root: data/my_dataset
    loader: folder
    mapping: my_dataset
```

## Pros and cons

Pros: tiny, readable, and ideal for learning the folder/mapping flow.

Cons: the names are placeholders; it contains no task-specific thin classes or
external benchmark protocol; using it for different semantics without editing
would make results meaningless.

## Evidence and benchmark boundary

The starter loader/config and taxonomy validation are tested. No accuracy
benchmark exists for this placeholder space. A synthetic or tiny overfit result
proves wiring only.

## Related documentation

- [Taxonomy catalog](../README.md)
- [Folder dataset](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/datasets/folder/README.md)
- [Getting started](https://github.com/arianizadi/segmentary/blob/main/docs/tutorials/getting-started.md)
