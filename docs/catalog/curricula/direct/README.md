# `direct`: custom-data-only floor

This curriculum trains directly on the custom rail dataset from the model's
upstream pretrained weights. It is the no-domain-transfer baseline every custom
transfer strategy must beat to justify its extra stages.

## Status

**Blocked until real custom data exists** at the configured root with indexed
masks and a valid group-safe `splits.json`.

```text
custom: 10,000 steps from upstream pretrained weights
```

The [source YAML](../../../../configs/curricula/direct.yaml) uses `rail_union`
and CE + Lovász at auxiliary weight 0.5.

## Beginner choice

Once the dataset exists, verify it, inspect overlays, and pass the eight-image
overfit test before launching this baseline. Keep its exact custom split fixed
for every later comparison.

## Advanced switches

The stage `iters`, model/tuning config, and loss can be ablated. A different
upstream model checkpoint is still “direct” only if no earlier Segmentary training
checkpoint is loaded. If `init_from` points to a previous source-domain model,
rename the experiment because it is no longer the direct floor.

## Pros and cons

Pros: cheapest custom target baseline; simple causal interpretation; exposes
whether source stages add anything beyond generic pretraining.

Cons: small custom data may overfit; has no public-data warmup; currently cannot
run; a 10k budget may need an explicitly named schedule study.

## Evidence and benchmark boundary

No real custom dataset or accuracy result exists. Unit/synthetic smoke tests do
not establish this curriculum's quality or even its future class distribution.
Keep it labeled blocked until real verification evidence is available.

## Related documentation

- [Legacy custom loader](../../datasets/custom-legacy/README.md)
- [`rail_union` taxonomy](../../../../taxonomy/rail_union/README.md)
- [`rs_custom`](../rs_custom/README.md)
- [`cs_rs_custom`](../cs_rs_custom/README.md)
- [All curricula](../README.md)
