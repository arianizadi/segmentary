# Built-in DenseASPP with DenseNet-161

Use [`denseaspp161.yaml`](../../../../configs/models/denseaspp161.yaml) for the
paper's main DenseASPP configuration (Yang et al., CVPR 2018).

## What it is

The same architecture as [`denseaspp121`](../builtin-denseaspp121/README.md) on
timm's ImageNet DenseNet-161 (`densenet161.tv_in1k`, torchvision weights) with
the authors' wider ASPP (512/128). About 35.4M parameters, consistent with the
authors' 142.7 MB DenseASPP-161 checkpoint. Implementation notes and recorded
differences are in
[`denseaspp.py`](../../../../src/segmentary/models/denseaspp.py).

Pros:

- the configuration behind the paper's Cityscapes results;
- dense multi-rate context with a strong ImageNet backbone;
- no pooled BatchNorm, so batch-one training is valid.

Cons:

- very high training memory: an estimated ~48 GiB peak per GPU at batch 2,
  1024x1024 (CPU activation count scaled by the ratio observed for two measured
  catalog arms). That does not fit a 48 GB L40S with margin; plan batch 1 with
  doubled accumulation, a smaller crop, or a gradient-checkpointing extension,
  and measure first;
- the slowest arm of the DenseASPP pair;
- not export-validated; no same-protocol dataset benchmark yet.

## Settings and checkpoints

As for `denseaspp121`: `model.checkpoint` and `drop_path` are rejected,
`reset_head` re-initializes only the final classifier, and the recipe is AdamW +
poly with `backbone_lr` 1e-4 and 10x on fresh modules.

## Verified evidence

CPU contract tests cover config construction, input-resolution logits, a
loss/backward step, the standardized FPS output contract and the parameter
count. This is implementation evidence, not accuracy evidence.
