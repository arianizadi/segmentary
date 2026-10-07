# Built-in DenseASPP with DenseNet-121

Use [`denseaspp121.yaml`](../../../../configs/models/denseaspp121.yaml) for
DenseASPP (Yang et al., CVPR 2018) on an ImageNet DenseNet-121. The paper's
headline DenseNet-161 variant is [`denseaspp161`](../builtin-denseaspp161/README.md).

## What it is

The DenseNet backbone (timm `densenet121.tv_in1k`, torchvision ImageNet
weights) runs at output stride 8: the pooling of transitions 2 and 3 is removed
and dense blocks 3 and 4 are dilated by 2 and 4. A fresh stride-1 transition
halves the channels. Five atrous layers with rates 3, 6, 12, 18 and 24 are then
**densely connected**: each sees the backbone feature plus every earlier atrous
output, which yields a large, densely sampled range of receptive fields. A
dropout + 1x1 classifier predicts at stride 8 and the logits are bilinearly
resized to the input. ASPP widths are 128/64 for this backbone, as in the
authors' configuration. About 8.28M parameters.

This is a clean Segmentary implementation in
[`denseaspp.py`](../../../../src/segmentary/models/denseaspp.py): the authors'
repository publishes no license, so no code is copied. Recorded differences
(explicit ReLU after the final BatchNorm, PyTorch-default BatchNorm momentum)
are listed in the file header. There are no auxiliary heads; the paper trains
with one loss.

Pros:

- paper-faithful dense multi-rate context at stride 8;
- ImageNet-pretrained backbone, compact parameter count;
- no pooled BatchNorm, so batch-one training is valid.

Cons:

- DenseNet concatenation at stride 8 is memory-hungry: an estimated ~20 GiB
  peak per GPU at batch 2, 1024x1024 (CPU activation count scaled by the ratio
  observed for two measured catalog arms) — measure before a long run;
- slow per parameter compared with ResNet decoders;
- not export-validated; no same-protocol dataset benchmark yet.

## Settings and checkpoints

The factory rejects `model.checkpoint` and `drop_path`. `reset_head`
re-initializes only the final 1x1 classifier; the transition and ASPP layers
carry across a stage boundary. `frozen` tuning freezes the DenseNet.

Recipe: AdamW + poly (Segmentary's shared optimizer for every catalog arm),
`backbone_lr` 1e-4 on the DenseNet and 10x on the fresh transition, ASPP and
classifier. Use RGB ImageNet normalization.

## Verified evidence

CPU contract tests cover config construction, input-resolution logits including
odd non-square sizes, a loss/backward step reaching every parameter, the
standardized FPS output contract, stride-8 surgery, classifier-only reset and
the parameter count. This is implementation evidence, not accuracy evidence.
