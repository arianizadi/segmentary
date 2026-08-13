# Local Meta DINOv3 checkpoint loader

The local DINOv3 loader is a strict backbone utility, not a complete semantic
segmentation model and not a valid `model.arch` by itself. Use it when you have
licensed Meta `.pth` files and are implementing a reviewed head/adapter that
needs a Transformers DINOv3 backbone.

## Supported files

The loader supports only the released LVD-1689M ViT-S, ViT-B, and ViT-L
FC-MLP checkpoint schemas. It infers architecture from tensor shapes rather than
trusting the filename.

It deliberately rejects:

- ViT-S+, ViT-H+, and ViT-7B SwiGLU schemas;
- biasless-QKV variants;
- SAT-493M files with local-crop normalization state;
- DINOv3 ConvNeXt files;
- unknown or partially matching tensor dictionaries.

Use Meta's native implementation for unsupported schemas. A clear failure is
safer than a partly initialized backbone that appears to train.

## What conversion does

Meta checkpoints use fused QKV projections and different parameter names.
Segmentary:

1. creates the exact `DINOv3ViTConfig` inferred from tensors;
2. splits fused Q, K, and V weights and applies the checkpoint's bias mask;
3. maps every supported parameter into the Transformers module tree;
4. converts stored RoPE periods to the inverse-frequency buffer;
5. requires every model tensor and checkpoint tensor to be accounted for.

Two entry points are available:

```python
from segmentary.models.dinov3 import (
    load_local_dinov3_backbone,
    load_local_dinov3_model,
)

backbone = load_local_dinov3_backbone("/path/to/licensed_weights.pth")
plain_model = load_local_dinov3_model("/path/to/licensed_weights.pth")
```

The backbone form exposes four transformer taps. Neither function adds a
decoder, classifier, dense loss, or segmentation preprocessing pipeline.

## Pros and cons

Pros:

- uses already downloaded licensed files without a second Hub download;
- strict bidirectional tensor accounting;
- exact fused-QKV and RoPE conversion is regression-tested;
- schema failures explain which family needs the native implementation.

Cons:

- only three LVD ViT schemas are supported;
- a plain ViT's same-stride taps are not a true 4/8/16/32 pyramid;
- a compatible segmentation adapter/head still must be implemented and tested;
- local weight licensing and redistribution restrictions remain the user's
  responsibility.

## Verified evidence and safe use

When the licensed files are present, slow regressions compare converted class
tokens, register tokens, first/last block weights, split QKV weights, and RoPE
frequencies directly against the source tensors for ViT-S and ViT-L. Separate
tests prove unsupported schemas fail.

Do not pass this backbone directly to Mask2Former and call its repeated
stride-16 taps a pyramid; that is why
[`mask2former_dinov3`](../builtin-mask2former-dinov3/README.md) is blocked. A
complete architecture must document the adapter, feature strides, head,
preprocessing, loss, tuning partition, and checkpoint provenance.

Source: [`dinov3.py`](../../../../src/segmentary/models/dinov3.py). Shared model
rules: [built-in model component](../../components/builtin-models/README.md).
