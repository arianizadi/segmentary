# Cityscapes dataset

`loader: cityscapes` reads the official finely annotated Cityscapes layout and
raw `labelIds`, then maps them through the selected canonical taxonomy.

## Required layout

```text
<root>/leftImg8bit/<split>/<city>/*_leftImg8bit.png
<root>/gtFine/<split>/<city>/*_gtFine_labelIds.png
```

The verified extraction contains 2,975 training, 500 validation, and 1,525 test
images at 1024x2048. The public test labels are not usable locally; Segmentary
accepts only `train` and `val` and rejects `test` rather than scoring blank masks.

## Beginner choice

Use the standard taxonomy only for literature-comparable Cityscapes work:

```yaml
space: cityscapes19
data:
  - name: cityscapes
    root: data/cityscapes
```

Omitting `loader` and `mapping` works because both default to `cityscapes`.

## Taxonomy choices

| space/variant | active classes | use | limitation |
|---|---:|---|---|
| `cityscapes19`, default | 19 | standard trainIds protocol and reference comparison | has no evaluated rail classes |
| `rail_union`, default | 16 of 21 | source stage for urban-to-rail transfer | five rail classes are inactive; urban classes are coarsened where RailSem19 is coarser |
| `rail_union`, `variant: railbridge` | 18 of 21 | named ablation enabling native rail-track and guard-rail IDs | not comparable to official Cityscapes evaluation; guard rail is a lossy proxy |

The loader reads `*_labelIds.png`, not pre-generated `trainIds`. The mapping
files declare every raw ID from 0 through 33 and map official ignored labels to
255.

## Pros and cons

Pros:

- mature, finely annotated urban source domain;
- official city-disjoint train/validation organization;
- standard 19-class benchmark protocol;
- native high resolution is useful for boundary testing.

Cons:

- no public local test labels;
- urban images do not supply ordinary rail supervision;
- full-resolution validation is expensive and normally uses sliding windows;
- the rail-bridge variant changes the protocol and uses a semantically noisy
  guard-rail mapping.

City name is recorded as each sample's group. The official split already keeps
cities separate, so this is audit information rather than a new split.

## Evidence and benchmarks

Real-data tests verify the 2,975/500 counts, paths, modes, raw IDs, taxonomy
coverage, and native 1024x2048 validation behavior. The fixed SegFormer-B2
reference run recorded `0.805073` mIoU on all 500 `cityscapes19` validation
images during its final in-memory EMA validation at step 40k. See the
[benchmark evidence page](../../../benchmarks/README.md) for protocol and raw
artifact caveats. That result does not transfer to `rail_union` or rail-bridge.

## Related documentation

- [Dataset catalog](../README.md)
- [`cityscapes19` taxonomy](../../../../taxonomy/cityscapes19/README.md)
- [`rail_union` taxonomy](../../../../taxonomy/rail_union/README.md)
- [Reference curriculum](../../curricula/reference_cityscapes19/README.md)
