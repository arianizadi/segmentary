# Built-in BiSeNet V2

Use [`bisenetv2.yaml`](../../../../configs/models/bisenetv2.yaml) for the BiSeNet V2
real-time network (Yu et al., IJCV 2021).

## What it is

A wide, shallow **detail branch** (stride 8) and a narrow, deep **semantic
branch** (stride 32, gather-and-expand layers and a context-embedding block)
are merged by a bilateral guided aggregation layer. A 3x3 + 1x1 head predicts
at stride 8.

The architecture code is not duplicated: Segmentary imports the copy already
vendored for the medical pipeline,
[`two_d_bisenet.py`](../../../../src/segmentary/medical/two_d_bisenet.py)
(CoinCheung/BiSeNet, MIT, pinned commit `6b4b67a`). That file is left
byte-identical because the medical runner hashes it into its experiment code
identity. The wrapper is in
[`bisenet.py`](../../../../src/segmentary/models/bisenet.py).

About 3.36M parameters at inference with 21 classes, 5.24M including the four
booster heads.

## Booster supervision

Training adds the paper's four booster heads on the semantic branch
(`booster_s4`, `booster_s8`, `booster_s16`, `booster_s32`, weight 1.0 each).
They run only in training mode. Public `forward` returns one dense logits
tensor and never runs a booster head.

Pros:

- very small inference graph designed for real-time use;
- no pretrained dependency, so nothing to download;
- moderate training memory (estimated ~4 GiB per GPU at batch 2, 1024x1024).

Cons:

- trained from scratch, as in the paper, so it needs the full schedule and is
  expected to trail ImageNet-initialized arms at equal steps;
- the context-embedding block applies BatchNorm to a pooled 1x1 map, so
  training needs at least two images per device (`probe --batch-size 2`);
- the upstream graph needs sides divisible by 32: other sizes are zero-padded
  bottom/right (zero is the normalized mean colour) and the logits cropped back.
  1024x1024 is never padded;
- not export-validated; no same-protocol dataset benchmark yet.

## Settings and checkpoints

The factory rejects `model.checkpoint` and `drop_path`. `reset_head`
re-initializes the five 1x1 class projections only. The detail and semantic
branches are `backbone_modules()`; the aggregation layer and heads are the
decoder.

Recipe: AdamW + poly, one uniform learning rate of 5e-4 (`head_lr_mult` 1.0)
because nothing is pretrained. The paper's SGD (lr 5e-2, 150k iterations) is not
reproduced; Segmentary uses its shared optimizer for every catalog arm.

## Verified evidence

CPU contract tests cover config construction, input-resolution logits including
odd non-square sizes, training outputs with all four boosters, a loss/backward
step reaching every parameter, eval mode without boosters, the standardized FPS
output contract, classifier-only reset and the parameter count. The medical
pipeline's own BiSeNetV2 tests continue to cover the vendored file. This is
implementation evidence, not accuracy evidence.
