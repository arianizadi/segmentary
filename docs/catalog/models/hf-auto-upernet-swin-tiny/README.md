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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.76 | 85.94 | 89.55 | 87.61 | 99.77 | 96.26 | 93.01 | 84.61 |
| RailSem19 | 40,000 / 40,000 | 69.75 | 81.58 | 81.29 | 81.39 | 99.40 | 89.90 | 82.37 | 77.96 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 67.26 | 80.59 | 78.87 | 79.60 | 99.34 | 88.63 | 80.57 | 75.43 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 58,953,423 | 224.9 MiB | 900.3 MiB | 42.33 | 23.48 ms | 24.47 ms | 2.41 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 14h 21m 30s | 14.36 | 8.85 GiB | 5.719 |
| RailSem19 | 17h 53m 41s | 17.89 | 8.88 GiB | 4.513 |
| Cityscapes → RailSem19 | not retained | not retained | not retained | 4.498 |

`not retained` means the exact original training-duration record is no longer available. The validated quality result, final checkpoint, iteration count, and inference evidence are still complete; the model is not retrained only to recreate timing metadata.

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.16 |
| sidewalk | 85.12 |
| building | 92.98 |
| wall | 64.72 |
| fence | 62.88 |
| pole | 63.83 |
| traffic-light | 72.28 |
| traffic-sign | 81.08 |
| vegetation | 92.66 |
| terrain | 64.92 |
| sky | 95.17 |
| person | 82.84 |
| rider | 64.69 |
| car | 95.13 |
| truck | 79.62 |
| bus | 84.77 |
| train | 70.33 |
| motorcycle | 66.57 |
| bicycle | 78.66 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 61.84 | 57.41 |
| sidewalk | 62.85 | 62.59 |
| construction | 79.49 | 77.23 |
| fence | 56.85 | 54.33 |
| pole | 62.93 | 62.06 |
| traffic-light | 57.08 | 54.45 |
| traffic-sign | 49.51 | 49.34 |
| vegetation | 87.69 | 86.36 |
| terrain | 70.40 | 68.74 |
| sky | 95.89 | 94.92 |
| human | 66.61 | 65.00 |
| car | 81.77 | 81.33 |
| truck | 43.00 | 40.21 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 78.74 | 73.77 |
| rail-track | 90.19 | 87.77 |
| rail-raised | 73.79 | 70.52 |
| rail-embedded | 56.42 | 52.81 |
| tram-track | 74.69 | 65.70 |
| trackbed | 75.58 | 73.52 |

### Provenance

- Model recipe: `configs/models/hf_auto_upernet_swin_tiny.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
