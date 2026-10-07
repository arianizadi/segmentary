# Built-in ESPNet

Use [`espnet.yaml`](../../../../configs/models/espnet.yaml) for ESPNet v1
(Mehta et al., ECCV 2018), the full encoder-decoder network.

## What it is

The encoder (ESPNet-C) is built from efficient spatial pyramid (ESP) modules:
a 1x1 reduction, five parallel dilated 3x3 convolutions (rates 1-16), and
hierarchical feature fusion that sums the dilated outputs before concatenation
to suppress gridding. Downsampled copies of the RGB input are concatenated at
strides 2 and 4. The full ESPNet decoder projects to class space at stride 8
and upsamples with transposed convolutions, fusing the stride-4 and stride-2
taps through another ESP module. Reference depths p=2 and q=8 give about 0.36M
parameters (366,589 with 21 classes; the paper reports 0.364M).

The layers are adapted from the authors' MIT-licensed reference
(sacmehta/ESPNet, pinned commit `afe71c3`); the changes are listed in the
header of [`espnet.py`](../../../../src/segmentary/models/espnet.py). They do not
change the computation when the input sides are divisible by 8.

Pros:

- by far the smallest arm in the catalog;
- no pretrained dependency and no auxiliary losses (one cross-entropy loss, as
  in the paper);
- low training memory (estimated ~2-3 GiB per GPU at batch 2, 1024x1024).

Cons:

- trained from scratch. The reference recipe warm-starts from its own
  Cityscapes ESPNet-C encoder, which is not an ImageNet backbone and is not on a
  pinned weight registry, so Segmentary does not use it;
- the whole decoder operates in class space, so a stage hand-off to a different
  taxonomy (`reset_head: true`) re-initializes the entire decoder; only the
  encoder transfers;
- with fewer than five classes the decoder width is floored at five (an ESP
  module cannot be narrower); the last layer still emits one channel per class;
- low capacity: expect a clear accuracy gap to larger arms.

## Settings and checkpoints

The factory rejects `model.checkpoint` and `drop_path`. `reset_head` restores
PyTorch default initialization for every decoder layer and declares the
decoder's BatchNorm/PReLU state through `reset_head_state_keys()`, so curriculum
hand-off can keep class-count-shaped tensors. The encoder is the only
`backbone_modules()` entry.

Recipe: AdamW + poly with one uniform learning rate of 5e-4 (`head_lr_mult`
1.0), the reference Adam learning rate. Segmentary's shared augmentation, crop
and loss are used instead of the reference class-weighted loss.

## Verified evidence

CPU contract tests cover config construction, input-resolution logits including
odd non-square sizes, a loss/backward step reaching every parameter, the
standardized FPS output contract, decoder-only reset, small class counts and
the parameter count. This is implementation evidence, not accuracy evidence.
