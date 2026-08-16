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

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.90 | 86.23 | 89.45 | 87.71 | 99.77 | 96.30 | 93.09 | 84.84 |
| RailSem19 | 40,000 / 40,000 | 69.90 | 82.00 | 81.15 | 81.52 | 99.41 | 89.81 | 82.32 | 77.76 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 58,953,423 | 224.9 MiB | 900.3 MiB | 42.16 | 23.48 ms | 24.69 ms | 2.41 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 14h 21m 30s | 14.36 | 8.85 GiB | 5.745 |
| RailSem19 | 17h 53m 41s | 17.89 | 8.88 GiB | 4.482 |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.25 |
| sidewalk | 85.60 |
| building | 92.99 |
| wall | 64.23 |
| fence | 62.99 |
| pole | 64.47 |
| traffic-light | 72.55 |
| traffic-sign | 81.09 |
| vegetation | 92.68 |
| terrain | 64.69 |
| sky | 95.08 |
| person | 82.95 |
| rider | 64.92 |
| car | 95.20 |
| truck | 79.23 |
| bus | 85.27 |
| train | 71.47 |
| motorcycle | 66.87 |
| bicycle | 78.68 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 61.93 | — |
| sidewalk | 62.68 | — |
| construction | 79.62 | — |
| fence | 57.10 | — |
| pole | 63.45 | — |
| traffic-light | 57.19 | — |
| traffic-sign | 49.37 | — |
| vegetation | 87.18 | — |
| terrain | 70.59 | — |
| sky | 95.90 | — |
| human | 66.62 | — |
| car | 81.51 | — |
| truck | 44.39 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 79.34 | — |
| rail-track | 90.19 | — |
| rail-raised | 73.86 | — |
| rail-embedded | 56.51 | — |
| tram-track | 74.98 | — |
| trackbed | 75.66 | — |

### Provenance

- Model recipe: `configs/models/hf_auto_upernet_swin_tiny.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0; Cityscapes: 0.
- Quality evaluation weights: RailSem19: —; Cityscapes: —.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
