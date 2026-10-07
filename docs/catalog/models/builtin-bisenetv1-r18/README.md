# Built-in BiSeNet V1 with a ResNet-18 context path

Use [`bisenetv1_r18.yaml`](../../../../configs/models/bisenetv1_r18.yaml) for the
widely benchmarked real-time BiSeNet variant (Yu et al., ECCV 2018).

## What it is

BiSeNet splits the job between two paths. A shallow **spatial path** (three
stride-2 convolutions) keeps stride-8 detail. A **context path** — timm's
ImageNet ResNet-18 `resnet18.tv_in1k`, the same torchvision weights the
reference implementation loads — supplies stride-16/32 semantics, refined by
two attention refinement modules and a global-context vector. A feature fusion
module merges the paths and a 3x3 + 1x1 head predicts at stride 8; the logits
are bilinearly resized to the input.

Layer widths, attention placement and initialization follow CoinCheung/BiSeNet
(MIT, pinned commit `6b4b67a`), as recorded in the header of
[`bisenet.py`](../../../../src/segmentary/models/bisenet.py). About 13.43M
parameters with 21 classes (13.28M without the two auxiliary heads).

## Auxiliary supervision

Training adds the paper's two context-path auxiliary losses
(`context_path_s8`, `context_path_s16`, weight 1.0 each, alpha = 1 in the
paper). They run only when the module is in training mode. Public `forward` —
evaluation, sliding windows, the standardized FPS benchmark and export — runs
only the fused head and returns one `(N, C, H, W)` logits tensor.

Pros:

- strong real-time accuracy/speed reference that many papers report;
- ImageNet-pretrained trunk with a small, well-understood decoder;
- low training memory (estimated ~2-3 GiB per GPU at batch 2, 1024x1024).

Cons:

- the attention modules apply BatchNorm to globally pooled 1x1 maps, so
  training needs at least two images per device (the campaigns use 2);
  `segmentary-models probe` therefore needs `--batch-size 2`;
- not export-validated;
- no same-protocol Segmentary dataset-quality benchmark is recorded yet.

## Settings and checkpoints

The factory rejects `model.checkpoint` and `drop_path`. Use a stage's
`init_from` for a Segmentary checkpoint. `reset_head` re-initializes the three
1x1 classifiers only; attention, fusion and the spatial path carry across a
stage boundary. `frozen` tuning freezes the ResNet-18; LoRA has no attention
projections to target.

Recipe: AdamW + poly (Segmentary's shared optimizer for every catalog arm),
`backbone_lr` 1e-4 on the ResNet-18 and 10x on every freshly initialized BiSeNet
module, matching the native ResNet recipes. The paper's SGD settings are not
reproduced. Use RGB ImageNet normalization; any crop size works.

## Verified evidence

CPU contract tests cover config construction, input-resolution logits for
square and odd non-square inputs, training outputs with both auxiliary heads,
a loss/backward step that reaches every parameter, eval mode with no auxiliary
outputs, the standardized FPS output contract, classifier-only reset and the
parameter count. This is implementation evidence, not accuracy evidence.
