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
| completed iterations | `40,000 / 40,000` |
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
mean percentages: each metric is one clean number even when multiple retained
seeds contribute to it. Cityscapes uses the standard 19-class taxonomy.
RailSem19 protocols use `rail_union`, where unsupported classes are `—` and
excluded from the mean. The machine record retains each individual seed.

| protocol | iterations | seeds | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 1 | 80.51 | 87.48 | 90.11 | 88.70 | 99.78 | 96.45 | 93.38 | 86.69 |
| RailSem19 | 40,000 / 40,000 | 3 | 70.47 | 81.51 | 82.50 | 81.94 | 99.41 | 89.89 | 82.43 | 78.62 |
| Cityscapes → RailSem19 | 60,000 / 60,000 | 3 | 66.44 | 79.17 | 79.14 | 78.98 | 99.30 | 88.17 | 79.74 | 74.31 |

The transfer total is 40,000 Cityscapes iterations plus 20,000 RailSem19
iterations. Its final RailSem19 checkpoint correctly has final-stage
`global_step=20,000`.

### Resource evidence

These are historical training measurements from the retained result records.
Multi-seed wall time and GPU-hours are means per run. They are separate from the
standardized inference benchmark, which is pending and therefore left blank.

| protocol | parameters | final checkpoint | train wall / run | GPU-hours / run | peak train VRAM / GPU | inference FPS | latency | inference VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 27,362,772 | — | 1h 37m 16s | 12.97 | 11.83 GiB | — | — | — |
| RailSem19 | 27,364,310 | 418.1 MiB | 3h 33m 10s | 14.21 | 21.95 GiB | — | — | — |
| Cityscapes → RailSem19 | 27,364,310 | 418.1 MiB | 5h 14m 02s | 20.94 | 21.95 GiB | — | — | — |

The Cityscapes row has no final checkpoint size because its exact
40,000-iteration checkpoint was not retained. Standardized inference FPS,
latency, and VRAM will be filled only after every model can be measured with the
same input, runtime, warmup, precision, and device protocol.

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
| road | 62.93 | 56.76 |
| sidewalk | 63.24 | 58.88 |
| construction | 79.59 | 77.68 |
| fence | 58.59 | 54.31 |
| pole | 63.76 | 62.58 |
| traffic-light | 56.91 | 53.83 |
| traffic-sign | 51.59 | 51.05 |
| vegetation | 87.04 | 86.21 |
| terrain | 69.98 | 65.51 |
| sky | 95.84 | 95.33 |
| human | 66.71 | 66.60 |
| car | 81.90 | 81.12 |
| truck | 45.23 | 41.60 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 83.82 | 81.56 |
| rail-track | 90.39 | 84.06 |
| rail-raised | 73.46 | 65.49 |
| rail-embedded | 57.12 | 48.99 |
| tram-track | 74.89 | 60.26 |
| trackbed | 76.01 | 70.55 |

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
