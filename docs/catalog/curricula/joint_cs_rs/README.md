# `joint_cs_rs`: mixed Cityscapes and RailSem19

This runnable baseline pools Cityscapes and RailSem19 in one mixed stage instead
of training them sequentially.

## Status and flow

Runnable with both datasets:

```text
{Cityscapes 50%, RailSem19 50%}: 60,000 steps from upstream pretrained weights
```

Sampling uses replacement and spreads each dataset's requested share across its
own items, so the 50/50 ratio does not collapse to the larger dataset's natural
frequency. Every sample carries its own active-class mask.

## Beginner choice

Use `model.head: unified_head` (already set by this curriculum), keep both
positive sample weights, and compare the final checkpoint with `cs_rs` on the
same explicit common RailSem19 evaluation.

## Exact switches and a major caveat

The [source YAML](../../../../configs/curricula/joint_cs_rs.yaml) exposes the
two `sample_weights`, total `iters`, roots, and split. Keys must exactly match
both data names and weights are relative—they do not need to sum to one.

In-training validation evaluates only the first listed data entry, Cityscapes,
using only its active classes. It is not the RailSem19 endpoint. Reordering data
would also change validation and therefore `best.ckpt` selection; do not do that
inside an otherwise identical comparison.

## Pros and cons

Pros: both domains influence every part of training; no stage handoff; direct
baseline for “just pool the data”; sampling ratio is explicit.

Cons: ratio is a hyperparameter; mixed training cannot answer whether order
matters; first-dataset validation can hide rail behavior; batch contents are
stochastic and total compute must be matched carefully.

## Evidence and benchmark boundary

Tests verify exact weighted-sampler shares, deterministic seeds, per-sample
active masks, and first-dataset validation masking. No model-quality result is
bundled; compare this curriculum only under a fixed common-target protocol.

## Related documentation

- [`cs_rs` sequential baseline](../cs_rs/README.md)
- [Mixed datasets](../../datasets/README.md)
- [Heads and active masks](../../components/heads/README.md)
- [Evaluation choices](../../components/evaluation/README.md)
- [All curricula](../README.md)
