# BEiT-Base + pyramid decode head

Use [`hf_auto_beit_base_ade.yaml`](../../../../configs/models/hf_auto_beit_base_ade.yaml)
when a larger, self-supervised transformer backbone and pyramid-style semantic
head are worth substantially more compute than a lightweight baseline.

## What it is

BEiT is a patch transformer pretrained by predicting visual tokens. This
checkpoint adds feature-pyramid and UPerNet-style decode modules and was
fine-tuned on ADE20K. Segmentary trains the primary dense head and deliberately
drops the checkpoint's separate auxiliary training branch. Only keys below the
exact `auxiliary_head.` prefix may be discarded; any other load gap is fatal.

| item | value |
|---|---|
| checkpoint | [`microsoft/beit-base-finetuned-ade-640-640`](https://huggingface.co/microsoft/beit-base-finetuned-ade-640-640) |
| pinned revision | `a8b6f5ef4acb2ea55d882989deaa02d39401e2b2` |
| source task | ADE20K, 150 classes, 640×640 fine-tuning |
| source preprocessing | RGB, mean/std `(0.5, 0.5, 0.5)`, `1/255` rescale |
| Segmentary parameters with 19 classes | 161,498,707 |

## Why choose it

Pros:

- high-capacity transformer representation;
- multi-level pyramid/decode path is appropriate for dense prediction;
- source checkpoint includes segmentation training rather than encoder-only
  pretraining;
- supports full, frozen, and compatible attention-LoRA tuning.

Cons:

- by far the largest shipped `hf_auto` example;
- slower and more memory-hungry than SegFormer-B0 or the mobile recipes;
- Segmentary does not reproduce the upstream auxiliary-loss objective;
- a new classifier and domain transfer still require careful optimization.

## Verified Segmentary evidence

The pinned real checkpoint passed the full strict load audit and five FP32 AdamW
steps on one L40S with batch 2 and 128×128 synthetic inputs. It used 2.827 GiB
peak allocated CUDA memory; all losses and trainable gradients were finite.
The later BF16 strict audit froze only the two declared unreachable blocks,
verified a finite gradient on every remaining trainable tensor, and updated the
classifier.

That small-crop memory number is only a compatibility reference. It excludes a
production crop, distributed buffers, and a realistic dataset, and it is not an
accuracy or latency benchmark. No comparable Segmentary mIoU exists yet.

## Advanced settings

- Begin with a smaller crop/batch and use accumulation to reach the intended
  effective batch.
- `llrd: 0.8` gives lower learning rates to earlier backbone layers.
- Frozen tuning is useful to establish how much of the gain comes from the
  pretrained representation; full tuning is the main adaptation path.
- Treat changing/removing the auxiliary-head policy as a new objective, not a
  harmless loader option.
- This pinned implementation's final two BEiT blocks are not consumed by its
  selected feature outputs. The recipe explicitly freezes only
  `beit.layers.10` and `beit.layers.11`; deleting that declaration will make a
  strict multi-GPU full-tuning run fail on unused gradients.

See the [Hugging Face component contract](../../components/hf-auto/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 57.26 | 66.22 | 78.55 | 70.28 | 99.45 | 91.60 | 85.00 | 64.72 |
| RailSem19 | 40,000 / 40,000 | 53.98 | 66.41 | 73.14 | 68.73 | 98.92 | 82.06 | 70.72 | 61.72 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 49.89 | 63.55 | 69.82 | 65.05 | 98.80 | 79.78 | 67.98 | 58.35 |

### Transfer checkpoints

The cumulative count includes the reused 40,000-step Cityscapes source. The historical row is retained as a baseline and is not mixed with corrected runs.

| optimizer contract | Rail iterations | cumulative iterations | mIoU | boundary F1 |
|---|---:|---:|---:|---:|
| historical 0.1x backbone + 0.1x head groups | 20,000 | 60,000 | 49.89 | 58.35 |
| corrected 0.1x backbone + 1.0x head groups | 20,000 | 60,000 | — | — |
| corrected 0.1x backbone + 1.0x head groups | 40,000 | 80,000 | 49.89 | 58.35 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class EMA checkpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 161,500,245 | 616.1 MiB | 2355.5 MiB | 2.51 | 396.55 ms | 413.88 ms | 3.77 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 14h 40m 07s | 14.67 | 19.53 GiB | 0.775 |
| RailSem19 | 21h 55m 28s | 21.92 | 16.06 GiB | 0.406 |
| Cityscapes → RailSem19 | 11h 00m 38s | 11.01 | 16.06 GiB | 0.407 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 93.06 |
| sidewalk | 56.20 |
| building | 87.82 |
| wall | 34.02 |
| fence | 33.68 |
| pole | 39.69 |
| traffic-light | 45.41 |
| traffic-sign | 59.56 |
| vegetation | 88.48 |
| terrain | 53.36 |
| sky | 93.67 |
| person | 66.44 |
| rider | 41.65 |
| car | 83.43 |
| truck | 48.99 |
| bus | 61.69 |
| train | 37.38 |
| motorcycle | 16.09 |
| bicycle | 47.34 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 48.45 | 43.54 |
| sidewalk | 47.34 | 40.01 |
| construction | 67.81 | 66.15 |
| fence | 29.28 | 30.75 |
| pole | 46.77 | 43.63 |
| traffic-light | 37.47 | 39.00 |
| traffic-sign | 30.69 | 30.85 |
| vegetation | 78.95 | 79.77 |
| terrain | 54.67 | 55.04 |
| sky | 93.75 | 92.85 |
| human | 50.08 | 53.64 |
| car | 69.29 | 62.98 |
| truck | 37.94 | 27.89 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 65.34 | 60.12 |
| rail-track | 63.72 | 45.69 |
| rail-raised | 57.77 | 51.42 |
| rail-embedded | 39.28 | 38.54 |
| tram-track | 49.41 | 34.33 |
| trackbed | 57.56 | 51.74 |

### Provenance

- Model recipe: `configs/models/hf_auto_beit_base_ade.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- EMA quality evaluation uses 1024x1024 sliding windows, stride 768, no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
