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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 57.06 | 65.74 | 78.56 | 70.04 | 99.45 | 91.65 | 85.07 | 64.70 |
| RailSem19 | 40,000 / 40,000 | 54.17 | 66.07 | 73.65 | 68.88 | 98.93 | 82.11 | 70.77 | 62.18 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 51.42 | 62.96 | 73.22 | 66.46 | 98.82 | 80.32 | 68.42 | 61.41 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 161,500,245 | 616.1 MiB | 2355.5 MiB | 2.52 | 394.46 ms | 411.51 ms | 3.77 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 14h 40m 07s | 14.67 | 19.53 GiB | 0.780 |
| RailSem19 | Rail40 standalone | 21h 55m 28s | 21.92 | 16.06 GiB | 0.409 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 11h 05m 16s | 11.09 | 15.36 GiB | 0.407 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 25h 45m 24s | 25.76 | 19.53 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 93.16 |
| sidewalk | 56.27 |
| building | 87.85 |
| wall | 32.54 |
| fence | 34.53 |
| pole | 38.68 |
| traffic-light | 44.13 |
| traffic-sign | 58.37 |
| vegetation | 88.48 |
| terrain | 53.26 |
| sky | 93.59 |
| person | 67.42 |
| rider | 41.10 |
| car | 84.12 |
| truck | 48.82 |
| bus | 61.62 |
| train | 37.13 |
| motorcycle | 15.68 |
| bicycle | 47.29 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 48.25 | 44.07 |
| sidewalk | 47.11 | 43.54 |
| construction | 67.80 | 67.23 |
| fence | 29.19 | 27.66 |
| pole | 46.46 | 44.78 |
| traffic-light | 38.90 | 42.30 |
| traffic-sign | 30.84 | 32.17 |
| vegetation | 78.92 | 78.60 |
| terrain | 54.56 | 54.77 |
| sky | 93.81 | 92.96 |
| human | 50.61 | 50.79 |
| car | 70.47 | 71.33 |
| truck | 37.80 | 30.25 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 66.25 | 62.04 |
| rail-track | 64.87 | 48.96 |
| rail-raised | 57.41 | 51.32 |
| rail-embedded | 38.94 | 40.09 |
| tram-track | 49.58 | 40.76 |
| trackbed | 57.50 | 53.42 |

### Provenance

- Model recipe: `configs/models/hf_auto_beit_base_ade.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
