# Built-in SegFormer-B2

Use [`segformer_b2.yaml`](../../../../configs/models/segformer_b2.yaml) for the
default speed/quality baseline and for curriculum comparisons.

## What it is

`segformer_b2` loads the ImageNet-pretrained `nvidia/mit-b2` hierarchical
transformer encoder and attaches a fresh SegFormer all-MLP decode head for the
configured label space. Four encoder resolutions are projected and fused; the
stride-4 prediction is bilinearly resized to the input size with
`align_corners=False`.

The shipped recipe records 27.4 million parameters for its standard head. Its
default optimizer uses a `6e-5` backbone learning rate, a 10x head multiplier,
and no layer-wise learning-rate decay.

## Why it is the default

Pros:

- substantially more capacity than B0 without the cost of B5;
- the complete train/evaluate/checkpoint path has real Cityscapes evidence;
- the same architecture is used for the milestone curriculum sweep, making
  debugging and comparisons easier;
- full, frozen, and LoRA tuning are available.

Cons:

- the decode head starts fresh rather than from a segmentation checkpoint;
- it uses more memory and training time than mobile or B0 choices;
- its built-in checkpoint path rejects the generic Hub `revision` field;
- the one completed reference run is one seed, not a confidence interval.

## Verified Cityscapes result

One result record evaluated the built-in B2 on the 500-image Cityscapes
validation split after a 40,000-step, seed-0 run:

| item | recorded value |
|---|---:|
| mIoU | `0.8050734618` (80.5073%) |
| pixel accuracy | `0.9645175301` |
| mean class accuracy | `0.8748474489` |
| boundary macro F1 | `0.8669386385` |
| training wall time | `5,836.30 s` (about 97.3 minutes) |
| hardware | 8 NVIDIA L40S GPUs |
| effective batch | 16 images (2 per GPU, accumulation 1) |
| crop / validation | 1024×1024 crop; 1024×1024 sliding window, stride 768 |
| TTA | off |
| source revision | Segmentary `082ebac9b9aed210436177badc2faab77091b235` |

The result used EMA validation and the `cityscapes19` taxonomy. It is a useful
single-run sanity reference, not a universal SegFormer benchmark.

The same architecture was later used for the completed
[three-seed rail-transfer case study](../../../findings.md). That comparison
holds the model fixed while varying four curricula and evaluates every final EMA
state on one RailSem19 target. It is curriculum evidence for that protocol, not
an architecture comparison or a replacement for the Cityscapes-19 reference.

Important replay limitation: this run predates the true-final checkpoint fix.
The persisted `best.ckpt` and `last.ckpt` are both at global step 24,000, while
the result record contains the later in-memory validation result. The exact
40,000-step weights were not retained. The number is valid result-record
evidence, but this particular final model artifact cannot be reproduced by
replaying the stored checkpoint. New runs persist explicit periodic snapshots
and the true final state.

## Tuning and resource advice

Start with the shipped full-tuning settings and batch/crop combination that fits
the target GPU. If memory is tight, reduce per-device batch and increase
accumulation while recording the effective batch. Frozen tuning answers whether
the pretrained features alone are useful; LoRA answers a different
parameter-efficiency question and should not replace the full baseline.

Keep evaluation protocol and seeds fixed when comparing B2 to another model.
Use a local immutable Hub snapshot if exact encoder-weight revision is required.

See the [built-in model component](../../components/builtin-models/README.md)
and [interpreting results](../../../tutorials/interpreting-results.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

These are validated prior results, reused without retraining. Values are
percentages; `±` is sample standard deviation when multiple seeds exist.
Cityscapes uses the standard 19-class taxonomy. RailSem19 protocols use
`rail_union`, where unsupported classes are `—` and excluded from the mean.

| protocol | seeds | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 1 | 80.51 | 87.48 | 90.11 | 88.70 | 99.78 | 96.45 | 93.38 | 86.69 |
| RailSem19 | 3 | 70.47 ± 0.17 | 81.51 ± 0.14 | 82.50 ± 0.16 | 81.94 ± 0.16 | 99.41 ± 0.00 | 89.89 ± 0.11 | 82.43 ± 0.08 | 78.62 ± 0.13 |
| Cityscapes → RailSem19 | 3 | 66.44 ± 0.03 | 79.17 ± 0.06 | 79.14 ± 0.05 | 78.98 ± 0.04 | 99.30 ± 0.00 | 88.17 ± 0.03 | 79.74 ± 0.05 | 74.31 ± 0.09 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.42 |
| sidewalk | 86.61 |
| building | 93.15 |
| wall | 61.31 |
| fence | 63.27 |
| pole | 65.70 |
| traffic-light | 73.70 |
| traffic-sign | 79.99 |
| vegetation | 92.86 |
| terrain | 64.75 |
| sky | 95.21 |
| person | 83.71 |
| rider | 65.45 |
| car | 95.53 |
| truck | 86.51 |
| bus | 89.84 |
| train | 82.48 |
| motorcycle | 71.67 |
| bicycle | 79.46 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 62.93 ± 0.14 | 56.76 ± 0.15 |
| sidewalk | 63.24 ± 0.08 | 58.88 ± 0.22 |
| construction | 79.59 ± 0.18 | 77.68 ± 0.06 |
| fence | 58.59 ± 0.09 | 54.31 ± 0.13 |
| pole | 63.76 ± 0.23 | 62.58 ± 0.06 |
| traffic-light | 56.91 ± 0.37 | 53.83 ± 0.28 |
| traffic-sign | 51.59 ± 0.52 | 51.05 ± 0.46 |
| vegetation | 87.04 ± 0.51 | 86.21 ± 0.01 |
| terrain | 69.98 ± 0.09 | 65.51 ± 0.23 |
| sky | 95.84 ± 0.08 | 95.33 ± 0.09 |
| human | 66.71 ± 0.24 | 66.60 ± 0.33 |
| car | 81.90 ± 0.08 | 81.12 ± 0.19 |
| truck | 45.23 ± 2.75 | 41.60 ± 1.41 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 83.82 ± 0.35 | 81.56 ± 0.27 |
| rail-track | 90.39 ± 0.04 | 84.06 ± 0.10 |
| rail-raised | 73.46 ± 0.05 | 65.49 ± 0.11 |
| rail-embedded | 57.12 ± 0.27 | 48.99 ± 0.41 |
| tram-track | 74.89 ± 0.11 | 60.26 ± 0.20 |
| trackbed | 76.01 ± 0.01 | 70.55 ± 0.13 |

### Evidence notes

- Cityscapes is the 500-image validation split in `cityscapes19`; RailSem19 is
  the fixed 850-image validation split in `rail_union`.
- Every row uses EMA weights, 1024×1024 sliding windows at stride 768, and no
  test-time augmentation.
- Mean precision, Dice, and specificity were deterministically reconstructed
  from the retained confusion matrices because these historical records
  predate those convenience fields.
- The three-seed Cityscapes stage from the rail-transfer case study used
  `rail_union` and is not substituted for the standard Cityscapes-19 result.
- The Cityscapes result has one seed and its exact 40,000-step checkpoint was
  not retained. The final in-memory EMA result is valid but not
  checkpoint-replayable.
- Full normalized metrics, class support, source revisions, and artifact
  checksums are in
  [`segformer_b2.json`](../../../results/model-comparison/records/segformer_b2.json).

<!-- segmentary:generated-city-rail-benchmark:end -->
