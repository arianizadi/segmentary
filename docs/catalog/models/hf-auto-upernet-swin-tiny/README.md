# Swin-Tiny + UPerNet

Use [`hf_auto_upernet_swin_tiny.yaml`](../../../../configs/models/hf_auto_upernet_swin_tiny.yaml)
when you want the classic separation of hierarchical backbone, feature pyramid,
pyramid pooling, and semantic decode head.

## What it is

Swin applies shifted-window attention in a hierarchy that produces naturally
multi-scale features. UPerNet combines a Feature Pyramid Network with Pyramid
Pooling to fuse local detail and global context. The source checkpoint was
fine-tuned on ADE20K.

| item | value |
|---|---|
| checkpoint | [`openmmlab/upernet-swin-tiny`](https://huggingface.co/openmmlab/upernet-swin-tiny) |
| pinned revision | `dc8e8c94669c6f14d5cc4c21a141daebd2280d59` |
| source task | ADE20K, 150 classes |
| source preprocessing | RGB, ImageNet mean/std, `1/255` rescale |
| Segmentary parameters with 19 classes | 58,952,397 |

## Why choose it

Pros:

- clean backbone/pyramid/decode-head structure;
- hierarchical features suit large scale variation;
- common reference architecture across OpenMMLab and Transformers;
- supports full, frozen, and compatible attention-LoRA tuning.

Cons:

- heavier decoder and memory cost than SegFormer-B0 or mobile arms;
- Segmentary drops the separately supervised auxiliary head and uses its own one
  dense-loss contract;
- explicit module paths are required because the upstream model lacks an
  unambiguous top-level base-model prefix;
- no comparable Segmentary accuracy benchmark exists yet.

## Verified Segmentary evidence

The real pinned checkpoint passed strict loading, explicit parameter partition,
processor reproduction, and five FP32 AdamW steps on one L40S at batch 2 /
128×128. It used 1.132 GiB peak allocated CUDA memory; all losses and gradients
were finite. This is compatibility evidence, not a latency or accuracy result.
The later BF16 strict audit froze only the declared terminal norm, verified
every remaining trainable gradient, and updated the classifier.

## Advanced settings

- Keep the explicit `backbone_path`, `head_paths`, and `classifier_path`; they
  are audited assertions, not arbitrary constructor knobs.
- `llrd: 0.9` gently lowers earlier-layer learning rates.
- Compare the same crop, schedule, effective batch, and evaluation endpoint
  against other models before interpreting an mIoU difference.
- UPerNet consumes the hierarchical Swin stages before the backbone's terminal
  `backbone.swin.layernorm`. That exact norm is explicitly frozen as
  loss-unreachable; this is a pinned implementation detail, not a general Swin
  recommendation.

See the [Hugging Face component contract](../../components/hf-auto/README.md).
