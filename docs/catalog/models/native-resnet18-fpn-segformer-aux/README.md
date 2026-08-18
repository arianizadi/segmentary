# Native ResNet-18 + FPN + SegFormer + FCN auxiliary head

Recipe: [`native_resnet18_fpn_segformer_aux.yaml`](../../../../configs/models/native_resnet18_fpn_segformer_aux.yaml)

This is the composition tutorial in executable YAML. The exact
`resnet18.a1_in1k` backbone and FPN produce a uniform feature pyramid; a
SegFormer-style MLP head predicts the main logits;
an FCN head on the stride-16 FPN level adds a training-only loss weighted `0.4`.

Pros:

- demonstrates independently switchable native components in one small stack;
- auxiliary supervision supplies a shorter gradient path;
- main deployment `forward` stays a single dense tensor.

Cons:

- auxiliary logits and loss add training memory/compute;
- the `0.4` weight is an engineering starting point, not an optimum;
- coarse auxiliary supervision may work against fine boundaries.

## Advanced settings and compatibility

The auxiliary name must stay unique. Its feature index is evaluated after FPN;
index `2` is the third returned pyramid level. Set `loss_weight` lower to reduce
its influence or remove the entire list for a controlled ablation. The same
configured objective suite applies to main and auxiliary logits. Export and
ordinary inference use only the main logits.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes. The corresponding scratch
ResNet-18/FPN/SegFormer/FCN-aux stack passed four CPU optimizer steps with finite
loss, changed parameters, and a CPU Gloo DDP no-unused-parameter check. The
pretrained YAML has parser evidence but not an assembled optimizer smoke. No
common Segmentary mIoU benchmark exists.

See [native heads](../../components/native-heads/README.md),
[native necks](../../components/native-necks/README.md), and the
[smoke ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 73.54 | 82.55 | 85.58 | 83.93 | 99.70 | 95.23 | 91.26 | 77.95 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 6h 13m 46s | 6.23 | 3.07 GiB | 7.455 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.47 |
| sidewalk | 80.80 |
| building | 91.11 |
| wall | 49.69 |
| fence | 54.77 |
| pole | 56.20 |
| traffic-light | 65.00 |
| traffic-sign | 74.45 |
| vegetation | 91.53 |
| terrain | 62.03 |
| sky | 93.73 |
| person | 78.75 |
| rider | 57.24 |
| car | 94.02 |
| truck | 73.59 |
| bus | 76.80 |
| train | 67.86 |
| motorcycle | 57.94 |
| bicycle | 74.33 |

### Provenance

- Model recipe: `configs/models/native_resnet18_fpn_segformer_aux.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0.
- Quality evaluation weights: Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
