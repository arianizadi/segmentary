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
